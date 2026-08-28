"""Allegro Evaluate — search Allegro with natural language and evaluate listings via LLMs."""

from __future__ import annotations

__version__ = "0.1.0"

from allegro_evaluate.config import Settings, get_settings
from allegro_evaluate.models import (
    DeepVerdict,
    EvaluationResult,
    Listing,
    QuickVerdict,
    SearchCriteria,
    SearchReport,
)

__all__ = [
    "DeepVerdict",
    "EvaluationResult",
    "Listing",
    "QuickVerdict",
    "SearchCriteria",
    "SearchReport",
    "Settings",
    "get_settings",
    "__version__",
]
