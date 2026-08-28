"""Tests for the two-stage evaluation pipeline."""

from __future__ import annotations

import httpx

from allegro_evaluate.llm.evaluator import ListingEvaluator
from allegro_evaluate.models import Listing, SearchCriteria
from tests.fakes import llm_handler_from_resolver


def make_criteria() -> SearchCriteria:
    return SearchCriteria(query="laptop", must_have=["16GB RAM"], max_price=3000)


def make_listing(index: int, title: str, price: float = 2000.0) -> Listing:
    return Listing(
        id=str(index),
        title=title,
        price=price,
        description="snippet",
        url=f"https://allegro.pl/oferta/{index}",
    )


def _stage1_all_match(n: int) -> dict:
    return {"results": [{"index": i, "match": True, "score": 70, "reason": "ok"} for i in range(n)]}


# --------------------------------------------------------------------- stage 1


def test_stage1_keeps_only_matches(settings, llm_client):
    listings = [make_listing(i, f"Item {i}") for i in range(3)]
    stage1 = {
        "results": [
            {"index": 0, "match": True, "score": 80, "reason": "ok"},
            {"index": 1, "match": False, "score": 20, "reason": "missing must-have"},
            {"index": 2, "match": True, "score": 60, "reason": "ok"},
        ]
    }
    client = llm_client(llm_handler_from_resolver(lambda msg: stage1 if "LISTINGS:" in msg else None))
    evaluator = ListingEvaluator(client=client, settings=settings)

    indices = evaluator._stage1(listings, make_criteria())

    assert indices == [0, 2]


def test_stage1_sorts_matches_by_score(settings, llm_client):
    listings = [make_listing(i, f"Item {i}") for i in range(3)]
    stage1 = {
        "results": [
            {"index": 0, "match": True, "score": 40, "reason": "ok"},
            {"index": 1, "match": True, "score": 90, "reason": "ok"},
            {"index": 2, "match": True, "score": 70, "reason": "ok"},
        ]
    }
    client = llm_client(llm_handler_from_resolver(lambda msg: stage1 if "LISTINGS:" in msg else None))
    evaluator = ListingEvaluator(client=client, settings=settings)

    assert evaluator._stage1(listings, make_criteria()) == [1, 2, 0]


def test_stage1_handles_batch_failure(settings, llm_client):
    client = llm_client(lambda request: httpx.Response(500, json={"error": {"message": "boom"}}))
    evaluator = ListingEvaluator(client=client, settings=settings)
    listings = [make_listing(i, f"Item {i}") for i in range(3)]

    assert evaluator._stage1(listings, make_criteria()) == []


def test_stage1_respects_candidate_cap(settings, llm_client):
    settings.stage1_candidates = 2
    listings = [make_listing(i, f"Item {i}") for i in range(5)]
    stage1 = {
        "results": [{"index": i, "match": True, "score": 50 + i, "reason": "ok"} for i in range(5)]
    }
    client = llm_client(llm_handler_from_resolver(lambda msg: stage1 if "LISTINGS:" in msg else None))
    evaluator = ListingEvaluator(client=client, settings=settings)

    assert len(evaluator._stage1(listings, make_criteria())) == 2


# --------------------------------------------------------------------- stage 2


def test_evaluate_returns_top_k_sorted(settings, llm_client):
    settings.top_k = 2
    listings = [make_listing(i, f"Item {i}") for i in range(3)]
    stage2_by_title = {
        "Item 0": {"score": 50, "match": False, "reasoning": "meh", "pros": [], "cons": ["weak"]},
        "Item 1": {"score": 90, "match": True, "reasoning": "great", "pros": ["fast"], "cons": []},
        "Item 2": {"score": 80, "match": True, "reasoning": "good", "pros": [], "cons": []},
    }

    def resolver(msg: str) -> dict | None:
        if "LISTING TO EVALUATE:" in msg:
            title = next(
                line for line in msg.splitlines() if line.startswith("Title: ")
            ).split("Title: ", 1)[1]
            return stage2_by_title[title]
        if "LISTINGS:" in msg:
            return _stage1_all_match(3)
        return None

    client = llm_client(llm_handler_from_resolver(resolver))
    evaluator = ListingEvaluator(client=client, settings=settings)

    results = evaluator.evaluate(listings, make_criteria())

    assert [r.listing.title for r in results] == ["Item 1", "Item 2"]
    assert results[0].score == 90
    assert results[0].match is True
    assert results[0].stage == "deep"
    assert results[0].model_used == settings.primary_model
    assert results[0].pros == ["fast"]
    assert evaluator.models_used == [settings.primary_model]


def test_evaluate_empty_listings(settings, llm_client):
    evaluator = ListingEvaluator(client=llm_client(lambda msg: None), settings=settings)
    assert evaluator.evaluate([], make_criteria()) == []


def test_evaluate_returns_nothing_when_no_candidates(settings, llm_client):
    listings = [make_listing(0, "Item 0")]
    stage1 = {"results": [{"index": 0, "match": False, "score": 10, "reason": "no"}]}
    client = llm_client(llm_handler_from_resolver(lambda msg: stage1 if "LISTINGS:" in msg else None))
    evaluator = ListingEvaluator(client=client, settings=settings)

    assert evaluator.evaluate(listings, make_criteria()) == []


def test_stage2_skips_malformed_verdict(settings, llm_client):
    listings = [make_listing(0, "Item 0")]
    stage1 = _stage1_all_match(1)

    def resolver(msg: str) -> dict | None:
        if "LISTING TO EVALUATE:" in msg:
            return {"score": "not-a-number", "match": True}  # fails DeepVerdict validation
        if "LISTINGS:" in msg:
            return stage1
        return None

    client = llm_client(llm_handler_from_resolver(resolver))
    evaluator = ListingEvaluator(client=client, settings=settings)

    assert evaluator.evaluate(listings, make_criteria()) == []
