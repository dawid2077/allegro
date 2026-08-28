"""Tests for the OpenRouter client: retries and the fallback model chain."""

from __future__ import annotations

import json

import httpx
import pytest

from allegro_evaluate.llm.client import ModelUnavailable, OpenRouterClient
from tests.fakes import make_messages


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _err(status: int, message: str = "boom") -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message}})


def test_returns_content_and_model(settings, llm_client):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok("hello from primary")

    client = llm_client(handler)
    response = client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])

    assert response.content == "hello from primary"
    assert response.model == settings.primary_model
    assert captured["body"]["model"] == settings.primary_model
    assert captured["body"]["messages"][0]["role"] == "user"


def test_falls_back_when_primary_fails(settings, llm_client):
    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        if model == settings.primary_model:
            return _err(429, "rate limited")
        return _ok("fallback answer")

    client = llm_client(handler)
    response = client.chat_with_fallback(
        make_messages("hi"),
        models=[settings.primary_model, settings.fallback_models[0]],
    )

    assert response.content == "fallback answer"
    assert response.model == settings.fallback_models[0]


def test_uses_default_model_chain(settings, llm_client):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        requested.append(model)
        if model == settings.primary_model:
            return _err(429)
        return _ok("ok")

    client = llm_client(handler)
    response = client.chat_with_fallback(make_messages("hi"))

    assert requested[0] == settings.primary_model
    assert requested.count(settings.primary_model) == settings.max_retries
    assert requested[-1] == settings.fallback_models[0]
    assert response.model == settings.fallback_models[0]


def test_all_models_fail_raises(settings, llm_client):
    client = llm_client(lambda request: _err(500))

    with pytest.raises(ModelUnavailable) as excinfo:
        client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])

    assert "all models failed" in str(excinfo.value)


def test_missing_api_key_raises_before_http(settings):
    settings.openrouter_api_key = ""
    client = OpenRouterClient(settings)

    with pytest.raises(ModelUnavailable):
        client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])


def test_retries_transient_error_then_succeeds(settings, llm_client):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return _err(503, "unavailable")
        return _ok("after retries")

    client = llm_client(handler)
    response = client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])

    assert response.content == "after retries"
    assert calls["n"] == 3


def test_non_retryable_status_is_not_retried(settings, llm_client):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _err(400, "bad request")

    client = llm_client(handler)

    with pytest.raises(ModelUnavailable):
        client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])
    assert calls["n"] == 1


def test_json_mode_adds_response_format(settings, llm_client):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok('{"ok": true}')

    client = llm_client(handler)
    client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model], json_mode=True)

    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_empty_content_is_treated_as_failure(settings, llm_client):
    client = llm_client(lambda request: httpx.Response(200, json={"choices": [{"message": {}}]}))

    with pytest.raises(ModelUnavailable):
        client.chat_with_fallback(make_messages("hi"), models=[settings.primary_model])
