"""Typer command-line interface for Allegro Evaluate.

Commands
--------
- ``search <query>`` — run the full pipeline (parse → scrape → evaluate).
- ``config show`` — print the resolved settings (API key masked).
- ``config setup`` — interactively save ``OPENROUTER_API_KEY`` to ``.env``.
- ``config set-model`` — change ``PRIMARY_MODEL`` in ``.env``.

Output defaults to a Rich table; ``--output-format json|markdown`` switches.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from allegro_evaluate.config import OutputFormat, Settings, load_settings_from_file
from allegro_evaluate.llm.client import LLMError, OpenRouterClient
from allegro_evaluate.llm.evaluator import ListingEvaluator
from allegro_evaluate.llm.parser import QueryParser
from allegro_evaluate.logging import configure_logging, get_logger
from allegro_evaluate.models import SearchReport
from allegro_evaluate.scraper import AllegroScraper, ScraperError

app = typer.Typer(
    help="Search Allegro with natural language and evaluate listings with LLMs.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
config_app = typer.Typer(
    help="Inspect and update configuration.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


# --------------------------------------------------------------------------- search


@app.command()
def search(
    query: str = typer.Argument(
        ...,
        help="Natural-language product query, e.g. 'laptop 16GB RAM pod 3000 zł'.",
    ),
    max_results: int | None = typer.Option(
        None, "--max-results", "-n", min=1, help="Number of best matches to return (default: TOP_K)."
    ),
    min_score: float | None = typer.Option(
        None, "--min-score", min=0, max=100, help="Only show results at or above this score."
    ),
    output_format: OutputFormat | None = typer.Option(
        None, "--output-format", "-f", help="Output format: table, json or markdown."
    ),
    config_file: Path | None = typer.Option(
        None, "--config", help="Path to an optional TOML config file."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging."),
) -> None:
    """Search Allegro, evaluate the best matches and print a report."""
    settings = _load_settings(config_file)
    if max_results is not None:
        settings.top_k = max_results
    configure_logging(level="DEBUG" if verbose else settings.log_level, json=settings.log_json)
    log = get_logger("allegro_evaluate.cli")

    if not settings.openrouter_api_key:
        typer.secho(
            "OPENROUTER_API_KEY is not set. Run 'allegro-evaluate config setup' to configure it.",
            err=True,
            fg="red",
        )
        raise typer.Exit(1)

    try:
        client = OpenRouterClient(settings, logger=log)
        parser = QueryParser(client, settings, logger=log)
        criteria = parser.parse(query)
    except LLMError as exc:
        typer.secho(f"LLM unavailable: {exc}", err=True, fg="red")
        raise typer.Exit(1) from exc
    log.info("criteria_parsed", criteria=criteria.model_dump())

    try:
        scraper = AllegroScraper(settings, logger=log)
        listings = scraper.scrape(criteria.query)
    except ScraperError as exc:
        typer.secho(f"Scraping failed: {exc}", err=True, fg="red")
        raise typer.Exit(1) from exc

    if not listings:
        typer.secho("No listings found on Allegro for this query.", fg="yellow")
        raise typer.Exit(0)

    evaluator = ListingEvaluator(client, settings, logger=log)
    results = evaluator.evaluate(listings, criteria)
    if min_score is not None:
        results = [result for result in results if result.score >= min_score]

    report = SearchReport(
        criteria=criteria,
        query=query,
        total_listings=len(listings),
        evaluated=results,
        models_used=evaluator.models_used,
    )
    render_report(report, output_format or settings.output_format)


# ----------------------------------------------------------------- config


@config_app.command("show")
def config_show(
    config_file: Path | None = typer.Option(
        None, "--config", help="Path to a TOML config file to display instead of the defaults."
    ),
) -> None:
    """Display the current settings (API key masked)."""
    settings = _load_settings(config_file)
    console = Console()

    table = Table(title="Allegro Evaluate settings", title_justify="left")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("OpenRouter API key", mask_key(settings.openrouter_api_key))
    table.add_row("Base URL", settings.base_url)
    table.add_row("Primary model", settings.primary_model)
    table.add_row("Fallback models", ", ".join(settings.fallback_models))
    table.add_row("Stage-1 model", settings.stage1_model or f"(default: {settings.fallback_models[0]})")
    table.add_row("Max listings", str(settings.max_listings))
    table.add_row("Max pages", str(settings.max_pages))
    table.add_row("Top K", str(settings.top_k))
    table.add_row("Stage-1 candidates", str(settings.stage1_candidates))
    table.add_row("Stage-1 batch size", str(settings.stage1_batch_size))
    table.add_row("Scrape delay", f"{settings.scrape_delay_min:g}–{settings.scrape_delay_max:g} s")
    table.add_row("Headless", str(settings.headless))
    table.add_row("Default output format", settings.output_format)
    table.add_row("Log level", settings.log_level)
    console.print(table)


@config_app.command("setup")
def config_setup(
    api_key: str = typer.Option(
        ...,
        prompt="OpenRouter API key",
        hide_input=True,
        confirmation_prompt=True,
        help="OpenRouter API key to store in the .env file.",
    ),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to the .env file."),
) -> None:
    """Interactively save your OpenRouter API key to ``.env``."""
    api_key = api_key.strip()
    if not api_key:
        typer.secho("API key must not be empty.", err=True, fg="red")
        raise typer.Exit(1)
    write_env_value(env_file, "OPENROUTER_API_KEY", api_key)
    typer.secho(f"Saved OPENROUTER_API_KEY to {env_file}.", fg="green")


@config_app.command("set-model")
def config_set_model(
    model: str = typer.Argument(
        ..., help="New primary model id, e.g. 'openai/gpt-4o' or 'anthropic/claude-sonnet-4.5'."
    ),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to the .env file."),
) -> None:
    """Change the primary model used for deep evaluation."""
    model = model.strip()
    if not model:
        typer.secho("Model name must not be empty.", err=True, fg="red")
        raise typer.Exit(1)
    write_env_value(env_file, "PRIMARY_MODEL", model)
    typer.secho(f"PRIMARY_MODEL set to '{model}' in {env_file}.", fg="green")


# ----------------------------------------------------------------- rendering


def render_report(report: SearchReport, output_format: OutputFormat) -> None:
    """Print a report in the requested format."""
    if output_format == "json":
        _render_json(report)
    elif output_format == "markdown":
        _render_markdown(report)
    else:
        _render_table(report)


def _render_json(report: SearchReport) -> None:
    print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))


def _render_markdown(report: SearchReport) -> None:
    lines = [
        f"# Best matches for: {report.query}",
        "",
        f"- Listings scraped: **{report.total_listings}**",
        f"- Models used: {', '.join(report.models_used) or '—'}",
        "",
    ]
    if report.evaluated:
        lines.append("| # | Score | Title | Price | Model |")
        lines.append("| --- | --- | --- | --- | --- |")
        for i, result in enumerate(report.evaluated, 1):
            lines.append(f"| {i} | {result.score:.0f} | {result.listing.title} | {_fmt_price(result.listing.price)} | {result.model_used} |")
        lines.append("")
        for i, result in enumerate(report.evaluated, 1):
            lines.extend(
                [
                    f"### {i}. {result.listing.title}",
                    "",
                    f"**Score:** {result.score:.0f}/100 · **Model:** {result.model_used}",
                    "",
                    result.reasoning or "—",
                ]
            )
            if result.pros:
                lines.extend(["", "**Pros:** " + "; ".join(result.pros)])
            if result.cons:
                lines.extend(["", "**Cons:** " + "; ".join(result.cons)])
            lines.append("")
    else:
        lines.append("No matches found.")
    print("\n".join(lines))


def _render_table(report: SearchReport) -> None:
    console = Console()
    if not report.evaluated:
        console.print("[yellow]No matches found.[/yellow]")
        return

    if report.criteria.summary:
        console.print(f"[dim]Criteria: {report.criteria.summary}[/dim]")

    table = Table(title="Allegro Evaluate — best matches")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Title", style="bold", no_wrap=False)
    table.add_column("Price", justify="right")
    table.add_column("Match", justify="center")
    table.add_column("Reasoning", overflow="fold", max_width=60)
    for i, result in enumerate(report.evaluated, 1):
        mark = "✓" if result.match else "✗"
        table.add_row(
            str(i),
            f"{result.score:.0f}",
            result.listing.title,
            _fmt_price(result.listing.price),
            mark,
            result.reasoning,
        )
    console.print(table)
    console.print(
        f"[dim]Listings scraped: {report.total_listings} · "
        f"Models: {', '.join(report.models_used) or 'n/a'}[/dim]"
    )


def _fmt_price(price: float | None) -> str:
    return f"{price:g} zł" if price is not None else "—"


def mask_key(key: str) -> str:
    """Mask an API key, keeping the first/last four characters visible."""
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


# ----------------------------------------------------------------- helpers


def _load_settings(config_file: Path | None) -> Settings:
    if config_file is not None:
        return load_settings_from_file(config_file)
    return Settings()


def write_env_value(path: Path, key: str, value: str) -> None:
    """Set ``key=value`` in a dotenv-style file, preserving other lines."""
    path = path.expanduser().resolve()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    replaced = False
    out: list[str] = []
    for line in lines:
        if line.strip().startswith(prefix) or line.strip().startswith(f"{key} ="):
            out.append(f"{prefix}{value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{prefix}{value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    app()
