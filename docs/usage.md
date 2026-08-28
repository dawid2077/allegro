# Usage Guide

## Commands

### `search` — Find and evaluate products

```bash
allegro-evaluate search "your query here" [OPTIONS]
```

**Required argument:**
- `query` — Natural language description (English or Polish)

**Options:**
| Flag | Short | Description | Default |
|------|-------|-------------|---------|
| `--max-results` | `-n` | Number of best matches to return | `TOP_K` (3) |
| `--min-score` | | Minimum match score (0–100) | none |
| `--output-format` | `-f` | `table`, `json`, or `markdown` | `table` |
| `--config` | | Path to TOML config file | none |
| `--verbose` | `-v` | Enable DEBUG logging | false |

---

## Examples

### Basic search (Polish query)
```bash
allegro-evaluate search "laptop 16GB RAM SSD 512GB do 3000 zł"
```

### English query with custom result count
```bash
allegro-evaluate search "iPhone 15 128GB under 4000 PLN" --max-results 5
```

### Filter by minimum score
```bash
allegro-evaluate search "gaming laptop RTX 4060" --min-score 70
```

### JSON output for scripting
```bash
allegro-evaluate search "monitor 27 inch 144Hz" --output-format json | jq '.evaluated[0].title'
```

### Markdown output for notes
```bash
allegro-evaluate search "mechanical keyboard brown switches" --output-format markdown > results.md
```

### Verbose logging (debugging)
```bash
allegro-evaluate search "test" --verbose
```

---

## Configuration Commands

### Show current settings
```bash
allegro-evaluate config show
```

Output:
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key                       ┃ Value                                       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ OpenRouter API key        │ sk-or-v1-abcd…wxyz                          │
│ Base URL                  │ https://openrouter.ai/api/v1                │
│ Primary model             │ nvidia/nemotron-3-ultra                     │
│ Fallback models           │ meta-llama/llama-3.1-70b-instruct:free, …   │
│ Stage-1 model             │ (default: meta-llama/llama-3.1-70b-instruct:free) │
│ Max listings              │ 50                                          │
│ Max pages                 │ 10                                          │
│ Top K                     │ 3                                           │
│ Stage-1 candidates        │ 15                                          │
│ Stage-1 batch size        │ 10                                          │
│ Scrape delay              │ 2.0–5.0 s                                   │
│ Headless                  │ True                                        │
│ Default output format     │ table                                       │
│ Log level                 │ INFO                                        │
└───────────────────────────┴─────────────────────────────────────────────┘
```

### Set up OpenRouter API key (interactive)
```bash
allegro-evaluate config setup
# Prompts for key (hidden input), asks for confirmation
```

### Change primary model
```bash
allegro-evaluate config set-model "openai/gpt-4o"
allegro-evaluate config set-model "anthropic/claude-3.5-sonnet"
```

---

## Output Formats

### Table (default) — Human-friendly
```
┏━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ #  ┃ Score ┃ Title                                        ┃ Price     ┃ Match ┃ Reasoning                             ┃
┡━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1  │  92   │ Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB │ 2 899 zł  │   ✓   │ Excellent match: 16GB RAM, 512GB SSD… │
│ 2  │  87   │ Dell XPS 13 16GB 512GB i7                   │ 3 199 zł  │   ✓   │ Good match: meets specs, slight price…│
│ 3  │  78   │ HP EliteBook 840 G10 16GB 512GB             │ 2 599 zł  │   ✓   │ Solid match: all must-haves present…  │
└────┴───────┴─────────────────────────────────────────────┴───────────┴───────┴───────────────────────────────────────┘
[dim]Listings scraped: 47 · Models: meta-llama/llama-3.1-70b-instruct:free, nvidia/nemotron-3-ultra[/dim]
```

### JSON — Machine-readable
```json
{
  "criteria": {
    "query": "laptop",
    "must_have": ["16GB RAM", "SSD 512GB"],
    "nice_to_have": [],
    "excluded": [],
    "min_price": null,
    "max_price": 3000,
    "summary": "Laptop with 16GB RAM and 512GB SSD under 3000 PLN"
  },
  "query": "laptop 16GB RAM SSD 512GB do 3000 zł",
  "total_listings": 47,
  "evaluated": [
    {
      "listing": {
        "id": "1234567890",
        "title": "Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB",
        "price": 2899.0,
        "currency": "PLN",
        "description": "Stan: nowy, gwarancja 24 mies.",
        "url": "https://allegro.pl/oferta/laptop-lenovo-thinkpad-x1-carbon-16gb-512gb-1234567890",
        "image_url": "https://img.allegro.example/p.jpg"
      },
      "score": 92.0,
      "match": true,
      "reasoning": "Excellent match: 16GB RAM, 512GB SSD, price under 3000 PLN. ThinkPad X1 Carbon is a premium ultrabook with great build quality.",
      "pros": ["16GB RAM", "512GB SSD", "Under budget", "Premium build"],
      "cons": ["Integrated graphics only"],
      "stage": "deep",
      "model_used": "nvidia/nemotron-3-ultra"
    }
  ],
  "models_used": ["meta-llama/llama-3.1-70b-instruct:free", "nvidia/nemotron-3-ultra"]
}
```

### Markdown — For Obsidian/notes
```markdown
# Best matches for: laptop 16GB RAM SSD 512GB do 3000 zł

- Listings scraped: **47**
- Models used: meta-llama/llama-3.1-70b-instruct:free, nvidia/nemotron-3-ultra

| # | Score | Title | Price | Model |
| --- | --- | --- | --- | --- |
| 1 | 92 | Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB | 2 899 zł | nvidia/nemotron-3-ultra |
| 2 | 87 | Dell XPS 13 16GB 512GB i7 | 3 199 zł | nvidia/nemotron-3-ultra |
| 3 | 78 | HP EliteBook 840 G10 16GB 512GB | 2 599 zł | nvidia/nemotron-3-ultra |

### 1. Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB

**Score:** 92/100 · **Model:** nvidia/nemotron-3-ultra

Excellent match: 16GB RAM, 512GB SSD, price under 3000 PLN. ThinkPad X1 Carbon is a premium ultrabook with great build quality.

**Pros:** 16GB RAM; 512GB SSD; Under budget; Premium build

**Cons:** Integrated graphics only
```

---

## Query Tips

| Pattern | Example | Effect |
|---------|---------|--------|
| Price ceiling | `pod 3000 zł`, `under 3000 PLN`, `max 4000` | Sets `max_price` |
| Price floor | `od 1000 zł`, `above 1000`, `min 500` | Sets `min_price` |
| Must-have specs | `16GB RAM`, `SSD 512GB`, `RTX 4060` | Goes to `must_have` |
| Exclusions | `nie uszkodzony`, `not refurbished` | Goes to `excluded` |
| Polish/English mix | `laptop 16GB RAM do 3000 zł` | Works in both languages |

---

## Environment Variables

All settings can be overridden via `.env` or shell:

```bash
export OPENROUTER_API_KEY=sk-or-...
export PRIMARY_MODEL=openai/gpt-4o
export MAX_LISTINGS=100
export TOP_K=5
export SCRAPE_DELAY_MIN=3
export SCRAPE_DELAY_MAX=8
export LOG_LEVEL=DEBUG
export OUTPUT_FORMAT=json
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (even if 0 matches) |
| 1 | Configuration error, API failure, scraping error |
| 2 | Invalid arguments |

---

## Scripting Example

```bash
#!/bin/bash
# Find best laptop under 3000 PLN, output JSON, extract top title

result=$(allegro-evaluate search "laptop 16GB RAM SSD 512GB pod 3000 zł" --output-format json)
title=$(echo "$result" | jq -r '.evaluated[0].listing.title // "none"')
score=$(echo "$result" | jq -r '.evaluated[0].score // 0')

echo "Best match: $title (score: $score)"
```