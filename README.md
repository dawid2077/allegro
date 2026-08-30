README content for the Allegro Evaluate project. Here you can describe the project purpose, installation instructions, and how to use the CLI commands.

## Overview

Allegro Evaluate is a tool that searches Allegro offers using both web scraping and the official Allegro REST API. It allows you to:

- Search Allegro offers using natural language queries (e.g., "laptop 16GB RAM pod 3000 zł").
- Parse the query into structured search criteria (must-have, nice-to-have, excluded, price bounds).
- Evaluate offers with an LLM-powered, two-stage pipeline (quick filter + deep evaluation).
- Retrieve top matches with detailed reasoning, pros, and cons.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/dawid2077/allegro.git
   cd allegro
   ```

2. Set up a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install Playwright browsers (required for the scraping functionality):
   ```bash
   playwright install chromium
   ```

5. Configure environment variables (see `.env.example`):
   ```bash
   cp .env.example .env
   # Edit .env with your OpenRouter and Allegro API credentials
   ```

## Usage

### Search with Natural Language (Default: Web Scraping)

```bash
allegro-evaluate search "laptop 16GB RAM pod 3000 zł"
```

### Search with Allegro REST API (New Feature)

```bash
allegro-evaluate api-search "laptop 16GB RAM pod vesta 3000 zł" --limit 50 --require "black color" --exclude "lenovo"
```

#### Options:
- `--limit, -n`: Number of listings to fetch from Allegro API (default: 30, max: 1000)
- `--require, -r`: Must‑have features (repeatable). E.g., `-r "black color" -r "not lenovo"`
- `--exclude, -e`: Must‑not‑have features (repeatable). E.g., `-e "refurbished" -e "used"`
- `--max-results, -m`: Number of best matches to return (default: TOP_K)
- `--min-score`: Minimum match score (0‑100) to display
- `--output-format, -f`: Output format: `table`, `json`, or `markdown`
- `--config`: Path to a TOML config file
- `--verbose, -v`: Enable DEBUG logging

### Configuration

```bash
allegro-evaluate config show
allegro-evaluate config setup   # interactively set OPENROUTER_API_KEY
allegore-evaluate config set-model "openai/gpt-4o"
```

### Output Formats

- **Table** (default): Human‑friendly, sortable, filterable via `--min-score`.
- **JSON**: Machine‑readable, suitable for scripting.
- **Markdown**: Formatted report for notes or documentation.

### Evaluation Pipeline

The evaluation runs in two stages:

1. **Stage‑1 (Quick Filter)**: A cheap/free LLM model (first fallback) evaluates each listing in batches and keeps the top candidates.
2. **Stage‑2 (Deep Evaluation)**: The primary model (`nvidia/nemotron-3-ultra` by default) evaluates each surviving candidate individually, producing a match score (0‑100), reasoning, pros, and cons.

### Examples

```bash
# Search for laptops under 3000 PLN, black color, not Lenovo
allegro-evaluate api-search "laptop pod 3000 zł" --require "black color" --exclude "lenovo" --limit 100

# Get top 5 matches with minimum score 70
allegro-evaluate api-search "gaming laptop rtx 4060" --max-results 5 --min-score 70

# JSON output for scripting
allegro-evaluate api-search "mechanical keyboard" --output-format json
```

## Configuration File (TOML)

Create a `config.toml` with custom settings:

```toml
base_url = "https://openrouter.ai/api/v1"
primary_model = "anthropic/claude-3.5-sonnet"
fallback_models = ["meta-llama/llama-3.1-70b-instruct:free", "qwen/qwen-2.5-72b-instruct:free"]
stage1_model = "meta-llama/llama-3.1-70b-instruct:free"
max_listings = 100
top_k = 5
stage1_candidates = 20
stage1_batch_size = 15
stage2_concurrency = 2
request_timeout = 120.0
max_retries = 5
retry_backoff = 2.0
scrape_delay_min = 1.0
scrape_delay_max = 3.0
page_load_timeout = 40000
headless = false
max_pages = 5
user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"]
output_format = "markdown"
log_level = "DEBUG"
log_json = false
allegro_client_id = "dawid2077"
allegro_client_secret = "7aOwt9sPTCAG86LAodNrDQkHkBLqaVpP5Vo21GZJcAN9MEyeQlNgQpq31LgsRsnm"
allegro_api_base = "https://api.allegro.pl"
```

Load with `--config config.toml`:

```bash
allegro-evaluate search "query" --config config.toml
```

## Docker

Build a Docker image:

```bash
docker build -t allegro-evaluate .
```

Run with mounted `.env`:

```bash
docker run --rm -v $(pwd)/.env:/app/.env allegro-evaluate search "laptop"
```

## Testing

Run the unit tests:

```bash
pytest
```

## License

MIT