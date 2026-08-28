"""Pydantic data models shared across the whole tool.

Keep this module free of I/O dependencies so it can be imported by every
layer (scraper, LLM, CLI) without side effects.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat-completion message."""

    role: Literal["system", "user", "assistant"]
    content: str


class Listing(BaseModel):
    """A single Allegro listing (as scraped from the search results page)."""

    id: str = Field(description="Stable identifier for the listing")
    title: str = Field(description="Listing title (in Polish)")
    price: float | None = Field(default=None, description="Price in PLN")
    currency: str = Field(default="PLN", description="ISO-ish currency code")
    description: str = Field(default="", description="Short description snippet")
    url: str = Field(default="", description="Absolute URL of the listing")
    image_url: str | None = Field(default=None, description="URL of the main listing image")


class SearchCriteria(BaseModel):
    """Structured search criteria parsed from a natural-language query."""

    query: str = Field(description="Core search string sent to the Allegro search box")
    must_have: list[str] = Field(
        default_factory=list,
        description="Required features/specs, e.g. ['16GB RAM', 'SSD 512GB']",
    )
    nice_to_have: list[str] = Field(
        default_factory=list,
        description="Preferred but optional features",
    )
    excluded: list[str] = Field(
        default_factory=list,
        description="Terms/conditions to exclude, e.g. ['uszkodzony', 'regenerowany']",
    )
    min_price: float | None = Field(default=None, ge=0, description="Lower price bound in PLN")
    max_price: float | None = Field(default=None, ge=0, description="Upper price bound in PLN")
    summary: str = Field(default="", description="Human-readable one-line summary of the criteria")


class QuickVerdict(BaseModel):
    """Result of stage-1 (cheap, permissive) evaluation for one listing."""

    index: int = Field(description="Index of the listing within the current batch")
    match: bool = Field(description="Whether the listing plausibly matches")
    score: float = Field(ge=0, le=100, description="Quick confidence score 0-100")
    reason: str = Field(default="", description="One-sentence justification")


class DeepVerdict(BaseModel):
    """Result of stage-2 (deep, strict) evaluation for a single listing."""

    score: float = Field(ge=0, le=100, description="Match score 0-100")
    match: bool = Field(description="Whether the listing is a good match")
    reasoning: str = Field(default="", description="Detailed reasoning")
    pros: list[str] = Field(default_factory=list, description="Positive aspects")
    cons: list[str] = Field(default_factory=list, description="Negative aspects")


class EvaluationResult(BaseModel):
    """Evaluation of a single listing (either quick or deep)."""

    listing: Listing
    score: float = Field(ge=0, le=100, description="Match score 0-100")
    match: bool = Field(default=False, description="Whether the listing matches the criteria")
    reasoning: str = Field(default="", description="Why the model scored it this way")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    stage: Literal["quick", "deep"] = Field(default="deep", description="Which stage produced this result")
    model_used: str = Field(default="", description="Model that produced this evaluation")


class SearchReport(BaseModel):
    """Full output of a search-and-evaluate run."""

    criteria: SearchCriteria = Field(description="Parsed criteria that were applied")
    query: str = Field(default="", description="Original user query")
    total_listings: int = Field(default=0, description="Number of listings scraped")
    evaluated: list[EvaluationResult] = Field(
        default_factory=list,
        description="Best matches, sorted by score descending",
    )
    models_used: list[str] = Field(default_factory=list, description="Models that produced results")
