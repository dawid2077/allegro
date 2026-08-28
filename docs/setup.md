# Setup Guide

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Required for type hints, `tomllib`, etc. |
| Playwright | 1.44+ | Browser automation for scraping |
| Git | any | For cloning |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/dawid2077/allegro-evaluate.git
cd allegro-evaluate
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
```

### 3. Install dependencies

```bash
# Core + dev dependencies (tests, linting)
pip install -e ".[dev]"
```

### 4. Install Playwright Chromium

```bash
playwright install chromium
```

> **Note:** This downloads ~150 MB. Run once per machine/environment.

### 5. Configure environment variables

Copy the example file and edit it:

```bash
cp .env.example .env
# Edit .env with your editor
```

**Required variable:**
- `OPENROUTER_API_KEY` — Get one at [openrouter.ai/keys](https://openrouter.ai/keys)

**Optional variables:**
- `PRIMARY_MODEL` — Default: `nvidia/nemotron-3-ultra`
- `SCRAPE_DELAY_MIN` / `SCRAPE_DELAY_MAX` — Default: `2–5` seconds
- `MAX_LISTINGS` — Default: `50`
- `TOP_K` — Default: `3`
- `LOG_LEVEL` — Default: `INFO`

---

## OpenRouter Setup

1. Create an account at [openrouter.ai](https://openrouter.ai)
2. Go to [Keys](https://openrouter.ai/keys) and create a new key
3. Add credits (Nemotron 3 Ultra is paid; free models work without credits)
4. Run the interactive setup:

```bash
allegro-evaluate config setup
# Enter your key when prompted (hidden input)
```

Or manually add to `.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Verify Installation

```bash
# Show config (key masked)
allegro-evaluate config show

# Test search (requires API key)
allegro-evaluate search "test query" --verbose
```

---

## Development Setup

```bash
# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy allegro_evaluate
```

---

## Docker (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY allegro_evaluate/ ./allegro_evaluate/
RUN pip install -e ".[dev]" && playwright install chromium --with-deps

ENTRYPOINT ["allegro-evaluate"]
```

Build and run:

```bash
docker build -t allegro-evaluate .
docker run --rm -it -v $(pwd)/.env:/app/.env allegro-evaluate search "laptop 16GB RAM pod 3000 zł"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `playwright install` fails | Install system deps: `apt-get install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2` |
| `ModuleNotFoundError: allegro_evaluate` | Run `pip install -e .` from repo root |
| `OPENROUTER_API_KEY is not set` | Run `allegro-evaluate config setup` or add to `.env` |
| Scraping returns 0 listings | Check if Allegro layout changed; increase `max_pages` or delay |
| `ModelUnavailable: all models failed` | Check OpenRouter credits; free models have rate limits |
| Permission denied on `.env` | Ensure file is writable: `chmod 600 .env` |

---

## Updating

```bash
git pull
pip install -e ".[dev]"  # re-install if deps changed
playwright install chromium  # if browser version bumped
```