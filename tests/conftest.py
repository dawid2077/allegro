"""Shared pytest fixtures for the test suite."""

from __future__ import annotations

import httpx
import pytest

from allegro_evaluate.config import Settings
from allegro_evaluate.llm.client import OpenRouterClient


@pytest.fixture
def settings() -> Settings:
    """A Settings instance with deterministic, network-free values."""
    return Settings(
        openrouter_api_key="sk-test-1234567890",
        base_url="https://openrouter.ai/api/v1",
        primary_model="primary/test-model",
        fallback_models=["fallback/test-model-1", "fallback/test-model-2"],
        stage1_model="stage1/test-model",
        max_listings=10,
        top_k=3,
        stage1_candidates=5,
        stage1_batch_size=10,
        stage2_concurrency=2,
        scrape_delay_min=0.0,
        scrape_delay_max=0.0,
        max_pages=1,
    )


@pytest.fixture
def llm_client(settings: Settings, monkeypatch: pytest.MonkeyPatch):
    """Factory building an :class:`OpenRouterClient` around a mocked httpx handler.

    The ``time.sleep`` used by the retry loop is patched out so backoff never
    actually blocks the test.
    """
    monkeypatch.setattr("allegro_evaluate.llm.client.time.sleep", lambda _: None)

    def _make(handler):
        transport = httpx.MockTransport(handler)
        http = httpx.Client(base_url=settings.base_url, transport=transport)
        return OpenRouterClient(settings, http_client=http)

    return _make
