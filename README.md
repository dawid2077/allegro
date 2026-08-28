# Allegro Evaluate 🔍

Search [Allegro](https://allegro.pl) with a natural-language query and let LLMs
tell you which listings are the best match.

```
allegro-evaluate search "laptop 16GB RAM SSD 512GB under 3000 PLN"
```

The tool scrapes 25–100 Allegro search results (headless Chromium via
Playwright), then runs a **two-stage LLM evaluation**:

1. **Stage 1 — quick filter**: a cheap free model scores every listing against
   the parsed criteria and drops clear non-matches.
2. **Stage 2 — deep evaluation**: the primary model (**Nemotron 3 Ultra** via
   OpenRouter) reasons about each candidate in detail.

The top 3 best matches are returned with match scores and reasoning.

## Highlights

- 🌐 **Web scraping only** — no official Allegro API.
- 🇵🇱 Polish listings, English code.
- 🧠 **LLM fallbacks** — if Nemotron is unavailable/rate-limited, the chain
  falls back to free models (Llama 3.1 70B, Qwen 2.5 72B, Mixtral 8x7B,
  Gemma 2 27B).
- 🕊️ **Respectful scraping** — random delays, user-agent rotation, pagination
  limits.
- 🧪 Fully unit-tested with mocked HTTP and browser layers.

## Quick start

```bash
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env   # then add OPENROUTER_API_KEY
allegro-evaluate search "laptop 16GB RAM SSD 512GB pod 3000 zł"
```

See [docs/Installation](docs/Installation.md) and
[docs/Usage](docs/Usage.md) for details.

## Documentation

The `docs/` folder is an Obsidian vault — open it as a vault in Obsidian for
wikilinks, Mermaid diagrams and tags.

| Document | Contents |
| --- | --- |
| [docs/Overview](docs/Overview.md) | Project overview + architecture (Mermaid) |
| [docs/Installation](docs/Installation.md) | Install, configure, first run |
| [docs/Usage](docs/Usage.md) | CLI commands and examples |
| [docs/Modules](docs/Modules.md) | Module breakdown and data flow |
| [docs/Evaluation](docs/Evaluation.md) | Evaluation internals and prompts |

## License

MIT
