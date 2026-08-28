"""Tests for the natural-language -> SearchCriteria parser."""

from __future__ import annotations

import json

import pytest

from allegro_evaluate.llm.client import LLMResponse, ModelUnavailable
from allegro_evaluate.llm.parser import QueryParser, _extract_features


class StubClient:
    """Minimal OpenRouterClient stand-in for parser tests."""

    def __init__(self, response: LLMResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple] = []

    def chat_with_fallback(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


# ------------------------------------------------------------------- heuristics


def test_heuristic_max_price(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    criteria = parser._parse_heuristic("laptop do 3000 zł")
    assert criteria.max_price == 3000
    assert criteria.query == "laptop"


def test_heuristic_min_price(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    criteria = parser._parse_heuristic("iphone od 2000 zł")
    assert criteria.min_price == 2000
    assert criteria.query == "iphone"


def test_heuristic_both_bounds(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    criteria = parser._parse_heuristic("od 1000 do 3000 zł")
    assert criteria.min_price == 1000
    assert criteria.max_price == 3000


def test_heuristic_bare_price_becomes_max(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    criteria = parser._parse_heuristic("laptop 2500 zł")
    assert criteria.max_price == 2500


def test_heuristic_extracts_features(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    criteria = parser._parse_heuristic("laptop 16GB RAM SSD 512GB")
    assert "16GB RAM" in criteria.must_have
    assert "SSD 512GB" in criteria.must_have


def test_extract_features_dedupes_substrings():
    features = _extract_features("laptop 16GB RAM SSD 512GB")
    assert features == ["16GB RAM", "SSD 512GB"]


# --------------------------------------------------------------------- llm path


def test_llm_parse_success(settings):
    content = json.dumps(
        {
            "query": "laptop",
            "must_have": ["16GB RAM", "SSD 512GB"],
            "nice_to_have": ["podświetlana klawiatura"],
            "excluded": ["uszkodzony"],
            "min_price": None,
            "max_price": 3000,
            "summary": "Laptop with 16GB RAM and 512GB SSD under 3000 PLN",
        }
    )
    client = StubClient(response=LLMResponse(content=content, model="test-model"))
    parser = QueryParser(client=client, settings=settings)

    criteria = parser.parse("szukam laptopa 16GB RAM SSD 512GB do 3000 zł")

    assert criteria.query == "laptop"
    assert criteria.must_have == ["16GB RAM", "SSD 512GB"]
    assert criteria.excluded == ["uszkodzony"]
    assert criteria.max_price == 3000
    assert parser.last_model == "test-model"


def test_llm_failure_falls_back_to_heuristics(settings):
    client = StubClient(error=ModelUnavailable("no api key"))
    parser = QueryParser(client=client, settings=settings)

    criteria = parser.parse("laptop do 3000 zł")

    assert criteria.max_price == 3000
    assert criteria.summary.startswith("Parsed heuristically")


def test_invalid_llm_json_falls_back_to_heuristics(settings):
    client = StubClient(response=LLMResponse(content="definitely not json", model="test-model"))
    parser = QueryParser(client=client, settings=settings)

    criteria = parser.parse("laptop do 3000 zł")

    assert criteria.summary.startswith("Parsed heuristically")


def test_empty_query_raises(settings):
    parser = QueryParser(client=StubClient(), settings=settings)
    with pytest.raises(ValueError):
        parser.parse("   ")
