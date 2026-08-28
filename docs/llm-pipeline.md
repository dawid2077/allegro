# LLM Pipeline — Stage 1 & Stage 2 Deep Dive

## Overview

The evaluation pipeline uses **two LLM passes** to balance cost/quality:

```
Stage 1 (Quick Filter)          Stage 2 (Deep Evaluation)
┌─────────────────────┐         ┌─────────────────────┐
│ Model: cheap/free   │         │ Model: Nemotron 3   │
│ Batch: 10 listings  │  ──→    │ One-by-one          │
│ Output: match bool  │         │ Output: score 0-100 │
│ + score + reason    │         │ + reasoning + pros/cons│
└─────────────────────┘         └─────────────────────┘
       ↓                               ↓
   Top 15 candidates              Top 3 final results
```

---

## Stage 1 — Quick Filter

### Purpose
Rapidly discard obviously irrelevant listings so the expensive model only evaluates promising candidates.

### Model
- Default: first fallback model (`meta-llama/llama-3.1-70b-instruct:free`)
- Configurable via `STAGE1_MODEL` or `settings.stage1_model`
- Temperature: `0.0` (deterministic)
- Max tokens: `1024`
- JSON mode: enforced

### Prompt

**System:**
```
You are a strict-but-permissive pre-filter for Allegro product listings.

Given the search criteria and a numbered list of listings, decide for EACH listing whether it
plausibly matches the requirements. This is a cheap first pass: a listing should be marked as a
match whenever there is a reasonable chance it satisfies the must-have specs and the price bounds.
Do not over-filter; the deep evaluation stage will make the final call.

Return a JSON object with a single key "results" holding an array of verdicts, one per listing:
{"results": [{"index": <int>, "match": <bool>, "score": <float 0-100>, "reason": "<short sentence>"}]}

The "index" must be the position of the listing in the input list (starting at 0). Respond with
ONLY the JSON object.
```

**User (built dynamically):**
```
SEARCH CRITERIA:
Query: laptop
Must have: 16GB RAM, SSD 512GB
Max price: 3000 PLN
Summary: Laptop with 16GB RAM and 512GB SSD under 3000 PLN

LISTINGS:
[0] Title: Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB | Price: 2899 zł | Snippet: Stan: nowy, gwarancja 24 mies.
[1] Title: Laptop HP 15s 8GB RAM 256GB SSD | Price: 1999 zł | Snippet: Stan: nowy
[2] Title: Dell XPS 13 16GB 512GB i7 | Price: 3199 zł | Snippet: Stan: nowy, gwarancja 24 mies.

Return the JSON object with a verdict for every index 0..2.
```

### Output Schema
```json
{
  "results": [
    {"index": 0, "match": true, "score": 85, "reason": "Meets RAM, SSD, and price criteria"},
    {"index": 1, "match": false, "score": 20, "reason": "Only 8GB RAM and 256GB SSD"},
    {"index": 2, "match": true, "score": 70, "reason": "Meets specs but slightly over budget"}
  ]
}
```

### Processing
- Batches of `stage1_batch_size` (default 10)
- Failed batches are logged and skipped (don't kill the run)
- All `match=true` results collected, sorted by score descending
- Top `stage1_candidates` (default 15) indices passed to Stage 2

### Design Decisions
| Decision | Rationale |
|----------|-----------|
| Permissive (`match=true` on reasonable chance) | Avoid false negatives; Stage 2 catches false positives |
| Batch size 10 | Fits in context window of cheap models; single call per batch |
| Score 0-100 | Allows ranking within matches |
| Index-based | Stable reference to original listing array |

---

## Stage 2 — Deep Evaluation

### Purpose
Produce detailed, trustworthy evaluations of the top candidates with reasoning, pros/cons, and a calibrated score.

### Model
- Primary: `nvidia/nemotron-3-ultra` (via OpenRouter)
- Falls back through chain on failure
- Temperature: `0.1` (slight variation for reasoning)
- Max tokens: `1024`
- JSON mode: enforced

### Prompt

**System:**
```
You are a meticulous product-matching expert for Allegro.

You are given ONE listing and the user's search criteria. Evaluate whether the listing is a
genuinely good match.

Consider every "must_have" feature explicitly — a listing missing any must-have is NOT a match,
even if it is otherwise excellent. Check price bounds. Weigh "nice_to_have" items to break ties
and improve the score.

Return a JSON object with EXACTLY these keys:
- "score": float 0-100 overall match score
- "match": boolean, true only if ALL must-have requirements are met and the price fits
- "reasoning": a detailed explanation (2-4 sentences) covering each requirement
- "pros": array of short positive points
- "cons": array of short negative points / missing features

Respond with ONLY the JSON object.
```

**User (built dynamically per listing):**
```
LISTING TO EVALUATE:
Title: Laptop Lenovo ThinkPad X1 Carbon 16GB 512GB
Price: 2899 zł
Snippet: Stan: nowy, gwarancja 24 mies.
URL: https://allegro.pl/oferta/laptop-lenovo-thinkpad-x1-carbon-16gb-512gb-1234567890

SEARCH CRITERIA:
Query: laptop
Must have: 16GB RAM, SSD 512GB
Max price: 3000 PLN
Summary: Laptop with 16GB RAM and 512GB SSD under 3000 PLN

Return the JSON object now.
```

### Output Schema
```json
{
  "score": 92.0,
  "match": true,
  "reasoning": "Excellent match: the listing explicitly states 16GB RAM and 512GB SSD in the title, and the price of 2899 PLN is under the 3000 PLN budget. The ThinkPad X1 Carbon is a premium ultrabook known for build quality and keyboard. The snippet confirms 'nowy' (new) condition with 24-month warranty.",
  "pros": ["16GB RAM", "512GB SSD", "Under budget", "Premium build quality", "24-month warranty"],
  "cons": ["Integrated graphics only", "Older CPU generation"]
}
```

### Processing
- Runs in parallel via `ThreadPoolExecutor` (`stage2_concurrency`, default 4)
- Each listing evaluated independently
- Failed evaluations (model error, invalid JSON, validation error) are logged and skipped
- Results sorted by score descending
- Top `top_k` (default 3) returned

### Scoring Guidelines (Model-Enforced)

| Score Range | Meaning |
|-------------|---------|
| 90–100 | Perfect match: all must-haves, price well within budget, strong nice-to-haves |
| 80–89 | Strong match: all must-haves, price within budget, minor tradeoffs |
| 70–79 | Good match: all must-haves, price at/near limit, some compromises |
| 60–69 | Borderline: meets must-haves but price slightly over or missing nice-to-haves |
| 50–59 | Partial: missing one nice-to-have, price OK |
| < 50 | Poor match: missing must-haves or significantly over budget |

**Critical rule:** `match=true` **only if ALL must_have criteria met AND price within bounds.**

---

## Fallback Chain Behavior

### Stage 1
- Uses `stage1_model` if set, otherwise `fallback_models[0]`
- If that model fails → tries next fallback → etc.
- If all fail → Stage 1 returns empty candidates → Stage 2 skipped → empty results

### Stage 2
- Starts with `primary_model` (Nemotron 3 Ultra)
- On failure → tries each fallback in order
- First successful model produces the verdict
- `model_used` recorded in each `EvaluationResult`

### Retry Logic (per model)
```
Attempt 1 → fail (retryable) → wait 1.5s
Attempt 2 → fail (retryable) → wait 2.25s
Attempt 3 → fail (retryable) → wait 3.375s
Attempt 4 → raise ModelUnavailable for this model
```

Retryable statuses: 408, 429, 500, 502, 503, 504 + network errors
Non-retryable: 400, 401, 403, 404, etc. → immediate fallback

---

## Prompt Engineering Notes

### JSON-Only Output
All prompts end with:
> `Respond with ONLY the JSON object.`

Models (especially free ones) often add prose. The `extract_json()` utility handles:
- Markdown code fences: ````json ... ````
- Leading/trailing text
- Finds outermost balanced `{...}` or `[...]`

### Polish Language Support
- System prompts in English (models understand English better)
- User queries can be Polish or English
- Parser system prompt explicitly: "The request may be written in English or Polish. Produce Polish strings for the search query and features."
- Listings come from Allegro in Polish; prompts feed them as-is
- Stage 2 reasoning in English (for user readability)

### Temperature Settings
| Stage | Temperature | Why |
|-------|-------------|-----|
| Parser | 0.1 | Near-deterministic parsing |
| Stage 1 | 0.0 | Consistent filtering |
| Stage 2 | 0.1 | Slight variation for nuanced reasoning |

### Token Budgets
| Call | Max Tokens | Typical Use |
|------|------------|-------------|
| Parser | 512 | Short JSON output |
| Stage 1 | 1024 | ~10 verdicts × ~50 tokens |
| Stage 2 | 1024 | Detailed reasoning + pros/cons |

---

## Model Comparison for This Task

| Model | Cost | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| Nemotron 3 Ultra | Paid | Medium | ★★★★★ | Stage 2 (primary) |
| Llama 3.1 70B | Free | Fast | ★★★★☆ | Stage 1, Stage 2 fallback |
| Qwen 2.5 72B | Free | Fast | ★★★★☆ | Stage 2 fallback |
| Mixtral 8x7B | Free | Fast | ★★★☆☆ | Stage 2 fallback |
| Gemma 2 27B | Free | Very Fast | ★★★☆☆ | Stage 2 fallback |

**Recommendation:** Use Nemotron 3 Ultra for Stage 2; free models for Stage 1 and fallback.

---

## Extending the Pipeline

### Add a Stage 3 (Verification)
```python
# In evaluator.py
def _stage3(self, results, criteria):
    # Re-evaluate top 1 with a different model/prompt for verification
    pass
```

### Change Scoring to Weighted
Modify `DeepVerdict` and prompts:
```python
# New fields
must_have_score: float
nice_to_have_score: float
price_score: float
```

### Add Structured Feature Extraction
Before Stage 2, extract structured specs from listing HTML:
```python
# In scraper.py
def _extract_structured_specs(self, element) -> dict:
    # Parse "Intel i7-1360P / 16GB / 512GB SSD / 14\" / Win 11"
    return {"cpu": "...", "ram_gb": 16, "storage_gb": 512, ...}
```

---

## Debugging the Pipeline

### Enable DEBUG logging
```bash
allegro-evaluate search "query" --verbose
```

### Inspect Stage 1 Output
```python
# In code
evaluator = ListingEvaluator(client, settings)
indices = evaluator._stage1(listings, criteria)
print(indices)  # [0, 2, 5, ...]
```

### Inspect Stage 2 Calls
```python
# Patch build_stage2_user_prompt to print
from allegro_evaluate.llm import prompts
original = prompts.build_stage2_user_prompt
def debug_build(listing, criteria):
    prompt = original(listing, criteria)
    print("=== STAGE 2 PROMPT ===")
    print(prompt)
    return prompt
prompts.build_stage2_user_prompt = debug_build
```

### Test with Mock Client
```python
from tests.fakes import llm_handler_from_resolver
# Use resolver to return canned stage1/stage2 responses
```

---

## Cost Estimation

### Per Search (50 listings, 15 candidates, top 3)

| Stage | Calls | Model | Est. Tokens | Cost (OpenRouter) |
|-------|-------|-------|-------------|-------------------|
| Parse | 1 | Primary/fallback | ~300 in, ~200 out | ~$0.001 |
| Stage 1 | 5 (batches of 10) | Free fallback | ~2000 in, ~500 out | $0 (free) |
| Stage 2 | 3 (parallel) | Nemotron 3 Ultra | ~1500 in, ~800 out | ~$0.01–0.03 |

**Total: ~$0.01–0.04 per search** (mostly Stage 2)

### With Free Models Only
If primary fails and all fallbacks are free: **$0** (rate limits apply)

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Stage 1 returns 0 candidates | Cheap model too strict | Lower threshold, check prompt |
| Stage 2 all `match=false` | Must-haves too strict / not in title | Relax must_have, check parser |
| JSON parse errors | Free model adds prose | Improve `extract_json()`, add `json_mode=True` |
| `ModelUnavailable` | All models failed / no credits | Check OpenRouter credits, add more fallbacks |
| Slow Stage 2 | Low concurrency | Increase `stage2_concurrency` |

---

## Prompt Versioning

Prompts are in `prompts.py` as module-level constants. To version:

1. Copy prompt to `prompts_v2.py`
2. Update `evaluator.py` imports
3. Test with `pytest tests/test_evaluator.py -v`
4. Compare results on same queries

**Tip:** Keep prompts in code (not external files) for git history and reproducibility.