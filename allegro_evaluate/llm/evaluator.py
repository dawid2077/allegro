"""Two-stage listing evaluation.

Stage 1 (quick): a cheap/free model scores every listing in small batches and
drops obvious non-matches. Stage 2 (deep): the primary model evaluates each
surviving candidate individually, producing detailed reasoning.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

import structlog

from allegro_evaluate.config import Settings
from allegro_evaluate.llm.client import LLMError, OpenRouterClient
from allegro_evaluate.llm.prompts import (
    STAGE1_SYSTEM_PROMPT,
    STAGE2_SYSTEM_PROMPT,
    build_stage1_user_prompt,
    build_stage2_user_prompt,
)
from allegro_evaluate.models import (
    ChatMessage,
    DeepVerdict,
    EvaluationResult,
    Listing,
    QuickVerdict,
    SearchCriteria,
)
from allegro_evaluate.utils import extract_json


class ListingEvaluator:
    """Runs the quick→deep evaluation pipeline over scraped listings."""

    def __init__(
        self,
        client: OpenRouterClient,
        settings: Settings,
        logger: structlog.typing.FilteringBoundLogger | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.log = logger or structlog.get_logger("allegro_evaluate.llm.evaluator")
        self.models_used: list[str] = []

    @property
    def cheap_model(self) -> str:
        """Model used for stage-1 filtering (defaults to the first fallback)."""
        return self.settings.stage1_model or self.settings.fallback_models[0]

    def evaluate(self, listings: list[Listing], criteria: SearchCriteria) -> list[EvaluationResult]:
        """Run both stages and return the top-k deep evaluations (score desc)."""
        if not listings:
            return []

        candidates = self._stage1(listings, criteria)
        self.log.info("stage1_complete", candidates=len(candidates), total=len(listings))
        if not candidates:
            return []

        results = self._stage2(listings, candidates, criteria)
        results.sort(key=lambda r: r.score, reverse=True)
        top = results[: self.settings.top_k]
        self.log.info("stage2_complete", top=len(top), models_used=self.models_used)
        return top

    # -- stage 1 -----------------------------------------------------------

    def _stage1(self, listings: list[Listing], criteria: SearchCriteria) -> list[int]:
        """Return global listing indices that plausibly match, best first."""
        batch_size = self.settings.stage1_batch_size
        verdicts: dict[int, QuickVerdict] = {}

        for start in range(0, len(listings), batch_size):
            batch = listings[start : start + batch_size]
            try:
                batch_verdicts = self._stage1_batch(batch, criteria)
            except (LLMError, ValueError, TypeError, KeyError) as exc:
                self.log.warning("stage1_batch_failed", offset=start, error=str(exc))
                continue
            for local_index, verdict in batch_verdicts.items():
                if 0 <= local_index < len(batch):
                    verdicts[start + local_index] = verdict

        matched = [(idx, v.score) for idx, v in verdicts.items() if v.match]
        matched.sort(key=lambda item: item[1], reverse=True)
        return [idx for idx, _ in matched[: self.settings.stage1_candidates]]

    def _stage1_batch(self, batch: list[Listing], criteria: SearchCriteria) -> dict[int, QuickVerdict]:
        messages = [
            ChatMessage(role="system", content=STAGE1_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_stage1_user_prompt(criteria, batch)),
        ]
        response = self.client.chat_with_fallback(
            messages, temperature=0.0, max_tokens=1024, json_mode=True
        )
        if response.model not in self.models_used:
            self.models_used.append(response.model)
        data = extract_json(response.content)
        results = _get_results_list(data)

        verdicts: dict[int, QuickVerdict] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                verdict = QuickVerdict.model_validate(item)
            except Exception:  # noqa: BLE001 - skip malformed entries
                continue
            verdicts[verdict.index] = verdict
        return verdicts

    # -- stage 2 -----------------------------------------------------------

    def _stage2(
        self,
        listings: list[Listing],
        indices: list[int],
        criteria: SearchCriteria,
    ) -> list[EvaluationResult]:
        max_workers = min(self.settings.stage2_concurrency, len(indices))
        results: list[EvaluationResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_index = {
                pool.submit(self._evaluate_one, listings[idx], criteria): idx for idx in indices
            }
            for future in concurrent.futures.as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception:  # noqa: BLE001 - one bad listing must not kill the run
                    self.log.exception("stage2_listing_failed", listing_index=idx)

        return results

    def _evaluate_one(self, listing: Listing, criteria: SearchCriteria) -> EvaluationResult | None:
        messages = [
            ChatMessage(role="system", content=STAGE2_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_stage2_user_prompt(listing, criteria)),
        ]
        try:
            response = self.client.chat_with_fallback(
                messages, temperature=0.1, max_tokens=1024, json_mode=True
            )
        except LLMError as exc:
            self.log.warning("stage2_model_unavailable", title=listing.title, error=str(exc))
            return None

        if response.model not in self.models_used:
            self.models_used.append(response.model)
        try:
            data = extract_json(response.content)
            verdict = DeepVerdict.model_validate(data)
        except (ValueError, TypeError, KeyError) as exc:
            self.log.warning("stage2_invalid_verdict", title=listing.title, error=str(exc))
            return None

        return EvaluationResult(
            listing=listing,
            score=verdict.score,
            match=verdict.match,
            reasoning=verdict.reasoning,
            pros=verdict.pros,
            cons=verdict.cons,
            stage="deep",
            model_used=response.model,
        )


def _get_results_list(data: Any) -> list[Any]:
    """Normalise stage-1 output which may be ``{"results": [...]}`` or ``[...]``."""
    if isinstance(data, dict):
        results = data.get("results", [])
    elif isinstance(data, list):
        results = data
    else:
        results = []
    return results if isinstance(results, list) else []
