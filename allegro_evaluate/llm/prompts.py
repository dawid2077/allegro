"""Prompt templates for the parser and both evaluation stages.

All prompts are written to be robust across the fallback models (including
free variants that are less instruction-following than Nemotron 3 Ultra):
they demand JSON-only output and repeat the required schema.
"""

from __future__ import annotations

from allegro_evaluate.models import Listing, SearchCriteria

PARSER_SYSTEM_PROMPT = """You are a shopping query parser for Allegro, the Polish online marketplace.

Convert a natural-language product request into structured JSON. The request may be
written in English or Polish. Produce Polish strings for the search query and features.

Return a JSON object with EXACTLY these keys:
- "query": a short core search string suitable for the Allegro search box (in Polish)
- "must_have": array of required features/specs as short Polish phrases (e.g. ["16GB RAM", "SSD 512GB"])
- "nice_to_have": array of preferred but optional features (short Polish phrases)
- "excluded": array of terms/conditions the user does not want (e.g. ["uszkodzony", "regenerowany"])
- "min_price": number or null (PLN)
- "max_price": number or null (PLN)
- "summary": a one-line English summary of the requirements

Rules:
- Only put features in must_have when they are clearly required.
- Extract price constraints ("under 3000 PLN", "do 3000 zł", "max 4000") into max_price;
  "od X zł" / "at least X" into min_price.
- "used"/"używany" is a condition, not a search keyword: add it to excluded only if the
  user does NOT want used items; otherwise keep the search query neutral.
- The "query" must be short (1-4 words).

Respond with ONLY the JSON object and nothing else."""


def build_parser_user_prompt(raw_query: str) -> str:
    return f"Product request: {raw_query}\n\nReturn the JSON object now."


STAGE1_SYSTEM_PROMPT = """You are a strict-but-permissive pre-filter for Allegro product listings.

Given the search criteria and a numbered list of listings, decide for EACH listing whether it
plausibly matches the requirements. This is a cheap first pass: a listing should be marked as a
match whenever there is a reasonable chance it satisfies the must-have specs and the price bounds.
Do not over-filter; the deep evaluation stage will make the final call.

Return a JSON object with a single key "results" holding an array of verdicts, one per listing:
{"results": [{"index": <int>, "match": <bool>, "score": <float 0-100>, "reason": "<short sentence>"}]}

The "index" must be the position of the listing in the input list (starting at 0). Respond with
ONLY the JSON object."""


def build_stage1_user_prompt(criteria: SearchCriteria, listings: list[Listing]) -> str:
    rows = []
    for idx, listing in enumerate(listings):
        price = f"{listing.price:g} zł" if listing.price is not None else "price unknown"
        rows.append(
            f"[{idx}] Title: {listing.title} | Price: {price} | Snippet: {listing.description or 'n/a'}"
        )
    criteria_block = _format_criteria(criteria)
    return (
        "SEARCH CRITERIA:\n"
        f"{criteria_block}\n\n"
        "LISTINGS:\n"
        + "\n".join(rows)
        + "\n\nReturn the JSON object with a verdict for every index 0.."
        f"{len(listings) - 1}."
    )


STAGE2_SYSTEM_PROMPT = """You are a meticulous product-matching expert for Allegro.

You are given ONE listing and the user's search criteria. Evaluate whether the listing is a
genuinely good match.

Consider every "must_have" feature explicitly — a listing missing any must-have is NOT a match,
even if it is otherwise excellent. Check price bounds. Weigh "nice_to_have" items to break ties
and improve the score.

Return a JSON object with EXACTLY these keys:
- "score": float 0-100 overall match score
- "match": boolean, true only if ALL must-have requirements are met and the price fits
- "reasoning": a detailed explanation (2-4 sentences) covering each requirement
- "pros": array of short positive points
- "cons": array of short negative points / missing features

Respond with ONLY the JSON object."""


def build_stage2_user_prompt(listing: Listing, criteria: SearchCriteria) -> str:
    price = f"{listing.price:g} zł" if listing.price is not None else "price unknown"
    listing_block = (
        "LISTING TO EVALUATE:\n"
        f"Title: {listing.title}\n"
        f"Price: {price}\n"
        f"Snippet: {listing.description or 'n/a'}\n"
        f"URL: {listing.url}"
    )
    return (
        listing_block
        + "\n\nSEARCH CRITERIA:\n"
        + _format_criteria(criteria)
        + "\n\nReturn the JSON object now."
    )


def _format_criteria(criteria: SearchCriteria) -> str:
    lines = [f"Query: {criteria.query}"]
    if criteria.must_have:
        lines.append("Must have: " + ", ".join(criteria.must_have))
    if criteria.nice_to_have:
        lines.append("Nice to have: " + ", ".join(criteria.nice_to_have))
    if criteria.excluded:
        lines.append("Exclude: " + ", ".join(criteria.excluded))
    if criteria.min_price is not None:
        lines.append(f"Min price: {criteria.min_price:g} PLN")
    if criteria.max_price is not None:
        lines.append(f"Max price: {criteria.max_price:g} PLN")
    if criteria.summary:
        lines.append(f"Summary: {criteria.summary}")
    return "\n".join(lines)
