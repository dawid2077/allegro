"""Natural-language → structured criteria parser.

Uses the LLM fallback chain by default and degrades to a regex-based
heuristic parser when the LLM is unavailable or returns invalid JSON.
"""

from __future__ import annotations

import re

import structlog

from allegro_evaluate.config import Settings
from allegro_evaluate.llm.client import LLMError, OpenRouterClient
from allegro_evaluate.llm.prompts import PARSER_SYSTEM_PROMPT, build_parser_user_prompt
from allegro_evaluate.models import ChatMessage, SearchCriteria
from allegro_evaluate.utils import extract_json, parse_price_from_text

# "under 3000 PLN" / "do 3000 zł" / "pod 3000" / "max 4000 zł" / "poniżej 2500"
_UPPER_PRICE_RE = re.compile(
    r"\b(?:under|below|less than|max(?:imum)?|up to|budget(?:\s+of)?|do|pod|poniżej|mniej niż|maks(?:ymalnie)?)\s*"
    r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:pln|zł|zl|zloty|złotych)?",
    re.IGNORECASE,
)
# "od 1000 zł" / "at least 1000" / "min 500"
_LOWER_PRICE_RE = re.compile(
    r"\b(?:from|above|over|at least|min(?:imum)?|od|powyżej|co najmniej)\s*"
    r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:pln|zł|zl|zloty|złotych)?",
    re.IGNORECASE,
)


class QueryParser:
    """Parse a user query into :class:`SearchCriteria`."""

    def __init__(
        self,
        client: OpenRouterClient,
        settings: Settings,
        logger: structlog.typing.FilteringBoundLogger | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.log = logger or structlog.get_logger("allegro_evaluate.llm.parser")
        self.last_model = ""

    def parse(self, raw_query: str) -> SearchCriteria:
        """Parse a raw query, falling back to heuristics on any failure."""
        raw_query = raw_query.strip()
        if not raw_query:
            raise ValueError("query must not be empty")

        try:
            criteria = self._parse_with_llm(raw_query)
            self.log.info("criteria_parsed", source="llm", criteria=criteria.model_dump())
            return criteria
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            self.log.warning("llm_parse_failed_using_heuristics", error=str(exc))
            criteria = self._parse_heuristic(raw_query)
            self.log.info("criteria_parsed", source="heuristic", criteria=criteria.model_dump())
            return criteria

    def _parse_with_llm(self, raw_query: str) -> SearchCriteria:
        messages = [
            ChatMessage(role="system", content=PARSER_SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_parser_user_prompt(raw_query)),
        ]
        response = self.client.chat_with_fallback(
            messages, temperature=0.1, max_tokens=512, json_mode=True
        )
        self.last_model = response.model
        data = extract_json(response.content)
        if not isinstance(data, dict):
            raise ValueError("parser returned non-object JSON")
        # Be lenient about key naming/casing from weaker models.
        normalized: dict[str, object] = {k.lower().strip(): v for k, v in data.items()}
        return SearchCriteria(
            query=str(normalized.get("query") or raw_query).strip(),
            must_have=_as_str_list(normalized.get("must_have")),
            nice_to_have=_as_str_list(normalized.get("nice_to_have")),
            excluded=_as_str_list(normalized.get("excluded")),
            min_price=_as_optional_float(normalized.get("min_price")),
            max_price=_as_optional_float(normalized.get("max_price")),
            summary=str(normalized.get("summary") or ""),
        )

    def _parse_heuristic(self, raw_query: str) -> SearchCriteria:
        """Deterministic fallback: extract prices and a few obvious specs."""
        max_price = _first_price(_UPPER_PRICE_RE.search(raw_query))
        min_price = _first_price(_LOWER_PRICE_RE.search(raw_query))

        # A bare "<number> <currency>" at the end is also an upper bound,
        # e.g. "laptop 3000 zł" or "iphone 15 3000".
        if max_price is None and min_price is None:
            fallback = parse_price_from_text(raw_query)
            if fallback is not None and fallback >= 100:
                max_price = fallback

        must_have = _extract_features(raw_query)

        # A cleaned query: drop price phrases and standalone currency tokens.
        cleaned = _UPPER_PRICE_RE.sub("", raw_query)
        cleaned = _LOWER_PRICE_RE.sub("", cleaned)
        cleaned = re.sub(r"\b(?:pln|zł|zl|zloty|złotych)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-–")

        if not cleaned:
            cleaned = raw_query

        return SearchCriteria(
            query=cleaned,
            must_have=must_have,
            nice_to_have=[],
            excluded=[],
            min_price=min_price,
            max_price=max_price,
            summary=f"Parsed heuristically from: {raw_query}",
        )


def _extract_features(raw_query: str) -> list[str]:
    """Greedy feature extraction: memory/storage specs, GPUs, CPU brands."""
    tokens: list[str] = []
    patterns = (
        r"\b\d+\s*(?:gb|tb)\s*ram\b",
        r"\b(?:ssd|hdd)\s*\d+\s*(?:gb|tb)\b",
        r"\b\d+\s*(?:gb|tb)\s*(?:ssd|hdd)\b",
        r"\b\d+\s*(?:gb|tb)\b",
        r"\b(?:intel|amd|nvidia|rtx|gtx|ryzen|core|apple)\s*[\w\s\-]{1,20}\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, raw_query, flags=re.IGNORECASE):
            token = match.group(0).strip()
            tokens.append(token)

    # Keep only tokens that are not substrings of another, longer token.
    unique: list[str] = []
    for token in tokens:
        lower = token.lower()
        if any(lower in other.lower() and lower != other.lower() for other in tokens):
            continue
        if lower not in [u.lower() for u in unique]:
            unique.append(token)
    return unique


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _as_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_price(match: re.Match[str] | None) -> float | None:
    if not match:
        return None
    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
