# S-06 · Model Routing

Send each task to the model best suited for it — not the most powerful one you have.

## Forces
- Frontier models (Opus, GPT-5) cost 10–100× more per token than small models
- Most tasks don't need frontier capability; routing them there wastes money
- A single model serving all tasks creates a bottleneck and inflates cost
- Routing wrong (cheap model on a hard task) degrades quality silently

## The move

**Build a router:** a lightweight classifier (or rule set) that dispatches each request to the right tier.

**The tiers (as of mid-2026):**

| Tier | Models | Use for |
|---|---|---|
| Local | Llama 3.x, Qwen3 via Ollama | High-volume, private data, formatting, extraction |
| Small hosted | Haiku 4.5, GPT-4o-mini | Classification, simple Q&A, structured output |
| Mid hosted | Sonnet 4.6, GPT-4o | Summarization, code review, reasoning |
| Frontier | Opus 4.8, GPT-5 | Complex reasoning, planning, hard judgment calls |

**Routing signals:**
- Task type: extraction → small; multi-step reasoning → frontier
- Input length: long context → models with large windows (Claude 200K+, Gemini 1M+)
- Latency budget: streaming UI → fast small model; batch job → frontier is fine
- Data sensitivity: PII → local model only

**Minimal router (rule-based):**
```python
def route(task_type: str, token_count: int) -> str:
    if token_count > 100_000:
        return "claude-opus-4-8"          # large context
    if task_type in ("extract", "classify", "format"):
        return "claude-haiku-4-5-20251001"  # cheap and fast
    if task_type == "reason":
        return "claude-sonnet-4-6"          # balanced
    return "claude-opus-4-8"                # default to best
```

## Receipt
> Verified 2026-06-25 — used llama3.2 (via Ollama, localhost:11435) as the lightweight router to classify 10 requests (EASY/MEDIUM/HARD) against their intended tier. Tier prices below are **illustrative** ($0.30 / $3 / $15 per M tokens, small/mid/frontier) — verify current vendor pricing.

```
router agreed with intended tier: 4/10
  EASY tasks (4):   all 4 correct
  MEDIUM tasks (3): all downgraded to EASY
  HARD tasks (3):   downgraded to MEDIUM (2) or EASY (1)
distribution chosen: EASY 8, MEDIUM 2, HARD 0

cost (equal token volume per request):
  all-frontier: $150.00     routed: $8.40     "savings": 94%
```

Read this as a warning, not a win. The headline **94%** is partly *illusory*: the weak router systematically **under-rated** difficulty — it sent "prove √2 is irrational" and "design a distributed rate limiter" to the cheapest tier. That is the misrouting failure exactly: a hard task on a weak model yields *fluent, plausible, wrong* output that no downstream step catches. The cost lever is real (easy tasks genuinely cost ~50× less), but **the router is the hard part** — a cheap router "saves" by under-provisioning. Mitigations: use a stronger model as the router, bias toward routing *up* on uncertainty, and measure router accuracy against held-out human labels before trusting the savings number.

## See also
[S-01](s01-local-model-dispatch.md) · [S-05](s05-multi-agent-patterns.md) · [R-01](../frontier/r01-model-landscape.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper
Keywords: `model routing` · `LLM cascade` · `RouteLLM` · `FrugalGPT` · `cost optimization` · `model selection`
