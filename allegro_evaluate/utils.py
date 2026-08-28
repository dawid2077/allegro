"""Small helpers shared across modules."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_NUMBER_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d{1,2})?)")
_PLN_RE = re.compile(r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:pln|zł|zl|zloty|złotych)", re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Extract a JSON value from LLM output.

    Model output is frequently wrapped in Markdown code fences or padded with
    prose. This tries a direct parse first, then scans for the outermost
    balanced ``{...}`` / ``[...]`` block.

    Raises:
        ValueError: if no valid JSON can be found.
    """
    text = text.strip()
    if not text:
        raise ValueError("empty model output")

    # Strip a wrapping ```json ... ``` code fence.
    fence = _JSON_FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            char = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == open_ch:
                depth += 1
            elif char == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError("no valid JSON found in model output")


def parse_price_from_text(text: str) -> float | None:
    """Best-effort price extraction from a Polish listing snippet.

    Looks for an explicit ``PLN``/``zł`` marker first, then falls back to the
    first numeric value that looks like a price (>= 2 digits).
    """
    if not text:
        return None
    normalized = text.replace(" ", " ").replace(" ", " ")

    explicit = _PLN_RE.search(normalized)
    target = explicit if explicit else _NUMBER_RE.search(normalized)
    if not target:
        return None
    raw = target.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace into a single space and trim."""
    return re.sub(r"\s+", " ", text).strip()
