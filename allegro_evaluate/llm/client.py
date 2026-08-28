"""OpenRouter chat-completions client with retries and a fallback model chain.

The client tries the configured primary model first. When it fails
(rate limit, 5xx, bad response, missing credits), the fallback models are
tried in order. This keeps the tool working even when the strong paid model
is unavailable — at the cost of lower evaluation quality.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import httpx
import structlog

from allegro_evaluate.config import Settings
from allegro_evaluate.models import ChatMessage

RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class LLMError(RuntimeError):
    """Base class for LLM interaction failures."""


class ModelUnavailable(LLMError):
    """A single model (or the whole chain) failed."""


class LLMStatusError(LLMError):
    """The API responded with an HTTP error status."""

    def __init__(self, status_code: int, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class LLMResponse:
    """Successful completion returned by the fallback chain."""

    __slots__ = ("content", "model")

    def __init__(self, content: str, model: str) -> None:
        self.content = content
        self.model = model


class OpenRouterClient:
    """Thin, resilient wrapper around the OpenRouter ``/chat/completions`` endpoint."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.Client | None = None,
        logger: structlog.typing.FilteringBoundLogger | None = None,
    ) -> None:
        self.settings = settings
        self.log = logger or structlog.get_logger("allegro_evaluate.llm.client")
        self._http = http_client or httpx.Client(
            base_url=settings.base_url,
            timeout=settings.request_timeout,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
        )

    # -- public API ---------------------------------------------------------

    def chat_with_fallback(
        self,
        messages: Sequence[ChatMessage],
        *,
        models: Sequence[str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Run a completion, trying each model in the chain until one works.

        Returns:
            An :class:`LLMResponse` with the generated text and the model that
            produced it.

        Raises:
            ModelUnavailable: when every model in the chain failed.
        """
        if not self.settings.openrouter_api_key:
            raise ModelUnavailable(
                "OPENROUTER_API_KEY is not configured. Add it to your environment or .env file."
            )

        chain = list(models) if models else self.settings.all_models()
        errors: list[str] = []
        for model in chain:
            try:
                content = self._chat(model, messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
                self.log.info("llm_completion", model=model, status="ok")
                return LLMResponse(content=content, model=model)
            except LLMError as exc:  # noqa: PERF203 - per-model handling is the point
                self.log.warning("llm_model_failed", model=model, error=str(exc), exc_info=False)
                errors.append(f"{model}: {exc}")

        raise ModelUnavailable(
            "all models failed: " + "; ".join(errors)
        )

    # -- internals ----------------------------------------------------------

    def _chat(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [msg.model_dump() for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error: LLMError | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                return self._request_once(payload, model)
            except LLMStatusError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
            except httpx.TransportError as exc:  # network blips are retryable
                last_error = LLMError(f"transport error: {exc}")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUSES:
                    raise LLMStatusError(
                        exc.response.status_code, str(exc), retryable=False
                    ) from exc
                last_error = LLMStatusError(exc.response.status_code, str(exc), retryable=True)

            backoff = self.settings.retry_backoff ** attempt
            self.log.debug("llm_retry", model=model, attempt=attempt, backoff=round(backoff, 2))
            time.sleep(backoff)

        raise ModelUnavailable(f"model {model} failed after {self.settings.max_retries} attempts: {last_error}")

    def _request_once(self, payload: dict[str, Any], model: str) -> str:
        response = self._http.post("/chat/completions", json=payload)
        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            data = {}

        if response.status_code != 200:
            message = _error_message(data) or response.reason_phrase or "unknown error"
            raise LLMStatusError(
                response.status_code,
                f"{model}: HTTP {response.status_code}: {message}",
                retryable=response.status_code in RETRYABLE_STATUSES,
            )

        return _extract_content(data, model)


def _extract_content(data: dict[str, Any], model: str) -> str:
    """Pull the assistant text out of an OpenRouter response body."""
    try:
        message = data["choices"][0]["message"]
        content = message.get("content")
        if not content:
            # Some reasoning models return the visible answer under `reasoning`
            # and leave `content` empty.
            content = message.get("reasoning") or ""
        if content:
            return content
    except (KeyError, IndexError, TypeError):
        pass
    raise LLMStatusError(200, f"{model}: empty or unexpected response body: {data!r:.200}", retryable=False)


def _error_message(data: dict[str, Any]) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message", error))
    if isinstance(error, str):
        return error
    return ""
