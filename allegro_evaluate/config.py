"""Configuration management.

Settings are resolved in this order (lowest to highest precedence):

1. Hard-coded defaults
2. Environment variables / ``.env`` file (uppercase names, e.g. ``OPENROUTER_API_KEY``)
3. Values passed explicitly (e.g. from a TOML config file or CLI)
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

OutputFormat = Literal["table", "json", "markdown"]


class Settings(BaseSettings):
    """Runtime configuration for allegro-evaluate."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- OpenRouter -------------------------------------------------------
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter API base URL")
    primary_model: str = Field(
        default="nvidia/nemotron-3-ultra",
        description="Primary model for deep (stage-2) evaluation",
    )
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "meta-llama/llama-3.1-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "mistralai/mixtral-8x7b-instruct:free",
            "google/gemma-2-27b-it:free",
        ],
        description="Free fallback models, tried in order",
    )
    stage1_model: str | None = Field(
        default=None,
        description="Cheap model for stage-1 filtering; defaults to fallback_models[0]",
    )

    # --- Allegro API ------------------------------------------------------
    allegro_client_id: str = Field(default="", description="Allegro API client ID")
    allegro_client_secret: str = Field(default="", description="Allegro API client secret")
    allegro_api_base: str = Field(default="https://api.allegro.pl", description="Allegro API base URL")

    # --- Pipeline ---------------------------------------------------------
    max_listings: int = Field(default=50, ge=1, description="Maximum listings to scrape")
    top_k: int = Field(default=3, ge=1, description="How many best matches to return")
    stage1_candidates: int = Field(default=15, ge=1, description="Candidates kept after stage-1 filter")
    stage1_batch_size: int = Field(default=10, ge=1, description="Listings per stage-1 LLM call")
    stage2_concurrency: int = Field(default=4, ge=1, description="Parallel deep evaluations")

    # --- HTTP / retries ---------------------------------------------------
    request_timeout: float = Field(default=60.0, description="HTTP timeout for OpenRouter calls (s)")
    max_retries: int = Field(default=3, ge=1, description="Retries per model on transient errors")
    retry_backoff: float = Field(default=1.5, ge=1.0, description="Exponential backoff base")

    # --- Scraping ----------------------------------------------------------
    scrape_delay_min: float = Field(default=2.0, ge=0, description="Min delay between page requests (s)")
    scrape_delay_max: float = Field(default=5.0, ge=0, description="Max delay between page requests (s)")
    page_load_timeout: int = Field(default=30_000, ge=1_000, description="Navigation timeout (ms)")
    headless: bool = Field(default=True, description="Run Chromium headless")
    max_pages: int = Field(default=10, ge=1, description="Max search-result pages to fetch")
    user_agents: list[str] = Field(default_factory=lambda: DEFAULT_USER_AGENTS[:])

    # --- Output / logging -------------------------------------------------
    output_format: OutputFormat = Field(default="table", description="Default CLI output format")
    log_level: str = Field(default="INFO", description="Logging level")
    log_json: bool = Field(default=False, description="Emit structured JSON logs")

    @field_validator("fallback_models")
    @classmethod
    def _fallback_models_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("fallback_models must contain at least one model")
        return value

    def all_models(self) -> list[str]:
        """Full model chain: primary first, then fallbacks."""
        chain = [self.primary_model, *self.fallback_models]
        seen: list[str] = []
        for model in chain:
            if model not in seen:
                seen.append(model)
        return seen


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def load_settings_from_file(path: str | Path) -> Settings:
    """Load settings, layering a TOML file on top of defaults/env.

    Env vars still take precedence over the TOML file's own defaults is NOT
    possible in one call, so we let pydantic-settings resolve env first and
    then merge explicit TOML values as init kwargs (init kwargs win over env).
    """
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as fh:
        data = tomllib.load(fh)
    data = cast(dict, data)  # TOML table -> mapping
    return Settings(**data)
