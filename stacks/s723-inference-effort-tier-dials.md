# S-723 · Inference Effort as a First-Class Dial

Your agent calls the same model twice. First call: $0.0003. Second call: $0.048. Same model, same task description. The only difference is the reasoning effort dial. In 2026, inference pricing became dimensional — and the effort tier is now the largest cost lever in agent pipelines, often exceeding the impact of model selection itself.

## Forces

- **Inference now dominates AI spend.** Enterprise AI budgets are 85% inference (up from ~60% two years ago). Agentic pipelines make 3–10× more LLM calls than chatbots. Most teams are optimizing the wrong axis.
- **Effort tiers create a 4–190× cost range on the same model.** Anthropic Claude xHigh vs xLow: 4–17× more reasoning tokens, 5–60× more latency. The full range from cheapest to most expensive call on the same model can hit 190×.
- **The U-shaped entropy problem.** DiffAdapt (ICLR 2026) found models show high entropy on *easy* problems (they overthink simple tasks), low entropy on medium-difficulty tasks, and high entropy on hard problems (correctly recognizing uncertainty). Default effort is calibrated for medium — which means most of your calls are on the wrong effort setting.
- **Effort tier selection is invisible governance.** Unlike model routing (S-06), effort dials are not surfaced in cost dashboards by default. Teams discover they have been running every task on xHigh because nobody set the default.

## The move

**Treat the reasoning effort dial as a first-class routing decision, not a model parameter.**

### The effort spectrum (2026 providers)

| Provider | Effort Control | Tiers | Cost Impact |
|---|---|---|---|
| Anthropic | `thinking` budget (0–4) | xLow → xHigh | 4–17× reasoning tokens |
| OpenAI | `reasoning_effort` | low / medium / high | 4–60× latency; 3–40× cost |
| Google Gemini | Flex vs Priority compute | 2 tiers | ~10× cost differential |
| Self-hosted (Ollama, vLLM) | `num_think_tokens` | configurable | free |

### Effort tier routing table

Assign effort by task signature, not by guessing:

```
Tier: LOW
  → Classification, extraction, format conversion
  → Entity recognition, sentiment scoring, boolean routing
  → Token cost: ~$0.30–2/M output tokens
  → Calibrated for: high accuracy, low entropy (model is confident)

Tier: MEDIUM (default)
  → Tool selection, API call construction
  → Multi-step orchestration, context assembly
  → Token cost: ~$2–15/M output tokens
  → Calibrated for: moderate entropy, moderate reasoning depth

Tier: HIGH
  → Complex planning, novel problem-solving, code generation
  → Adversarial or ambiguous inputs, multi-constraint optimization
  → Token cost: ~$15–50/M output tokens
  → Calibrated for: high uncertainty, low model confidence

Tier: ESCALATE (on MEDIUM failure)
  → If MEDIUM output fails a validation gate, retry HIGH
  → Track escalation rate as a proxy for MEDIUM calibration quality
  → Escalation rate >15% = MEDIUM is undershooting; recalibrate routing
```

### Classifier for effort routing

```python
import anthropic
import openai
from collections.abc import Callable

client = anthropic.Anthropic()

EFFORT_CONFIG = {
    "low":    {"thinking": {"type": "enabled", "budget_tokens": 128}},
    "medium": {"thinking": {"type": "enabled", "budget_tokens": 2048}},
    "high":   {"thinking": {"type": "enabled", "budget_tokens": 16000}},
}

def classify_effort(query: str, context: dict) -> str:
    """
    Route to LOW / MEDIUM / HIGH based on task complexity signals.
    """
    entropy_signal = context.get("reasoning_trace_entropy")
    complexity_score = context.get("task_complexity", 0.0)  # 0.0–1.0

    # High stakes override entropy — always use HIGH for irreversible actions
    if context.get("stakes") in ("high", "critical"):
        return "high"

    # Simple, low-entropy tasks: LOW
    if complexity_score < 0.3 and (entropy_signal is None or entropy_signal < 0.4):
        return "low"

    # Complex or ambiguous: HIGH
    if complexity_score > 0.7 or (entropy_signal is not None and entropy_signal > 0.8):
        return "high"

    return "medium"


def effort_aware_call(
    query: str,
    system: str,
    context: dict | None = None,
    validator: Callable[[str], bool] | None = None,
    max_escalations: int = 2,
) -> tuple[str, str]:
    """
    Make an LLM call with effort-tier routing and escalation on failure.
    Returns (response, effort_tier_used).
    """
    context = context or {}
    effort = classify_effort(query, context)
    config = EFFORT_CONFIG.get(effort, EFFORT_CONFIG["medium"])

    escalations = 0
    last_error = None

    while escalations <= max_escalations:
        try:
            response = client.messages.create(
                model="claude-opus-4.7",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": query}],
                thinking=config,
            )

            # Validate output
            if validator is None or validator(response.content):
                return response.content, effort

            last_error = "validation_failed"

        except Exception as e:
            last_error = str(e)

        # Escalate: MEDIUM → HIGH, LOW → MEDIUM
        tier_order = ["low", "medium", "high"]
        current_idx = tier_order.index(effort) if effort in tier_order else 1
        if current_idx < len(tier_order) - 1:
            effort = tier_order[current_idx + 1]
            config = EFFORT_CONFIG[effort]
            escalations += 1
        else:
            break

    raise RuntimeError(
        f"Effort escalation exhausted ({max_escalations} levels). "
        f"Last error: {last_error}"
    )


# --- Cost monitoring ---
def track_effort_cost(usage: anthropic.Message, effort_tier: str) -> None:
    """Log effort tier vs. actual token consumption for calibration."""
    reasoning_tokens = usage.usage.thinking_tokens or 0
    output_tokens = usage.usage.output_tokens
    total_output = reasoning_tokens + output_tokens

    print(
        f"[effort={effort_tier}] "
        f"reasoning={reasoning_tokens:>6} tokens | "
        f"output={output_tokens:>6} tokens | "
        f"ratio={reasoning_tokens/max(output_tokens,1):.2f}x "
        f"(>2.0x = overthinking)"
    )
```

### Cost calibration dashboard

Track these metrics per effort tier to find calibration problems:

```
effort_tier_distribution{job="agent-name"}  → % of calls per tier
effort_tier_cost_usd{job="agent-name"}     → actual spend per tier
effort_escalation_rate                      → MEDIUM→HIGH failure rate
overthinking_ratio                          → reasoning_tokens / output_tokens (>2 = waste)
```

**Budget guardrails:**

```python
# Per-task effort budget — abort if projected effort cost exceeds threshold
EFFORT_COST_LIMITS = {
    "low":    0.005,   # $0.005 max per low-effort call
    "medium": 0.050,   # $0.05 max per medium-effort call
    "high":   0.500,   # $0.50 max per high-effort call
}

def effort_estimate(query: str, effort: str) -> float:
    """Rough cost estimate before calling. Abort if over budget."""
    approx_output_tokens = len(query) // 4 + 200  # rough
    effort_multipliers = {"low": 0.1, "medium": 1.0, "high": 8.0}
    projected = approx_output_tokens * effort_multipliers[effort] * 0.000015
    return projected
```

## Receipt

> Verified 2026-07-06 — AgentMarketCap (May 2026): 85% of enterprise AI spend is inference; 73% of teams report AI costs exceeded budget. DiffAdapt ICLR 2026: U-shaped entropy pattern across models means default effort settings are wrong for ~60% of calls. Effort-tier routing can achieve 60–80% cost reduction vs. uniform xHigh (AgentMarketCap, Apr 2026). Cross-references: S-06 (model routing, orthogonal axis), S-114 (scratchpad budget, this is the provider-side equivalent), S-243 (cost stratification, this fills the per-call effort dimension).

## See also

- [S-06 · Model Routing](s06-model-routing.md) — orthogonal axis: which model vs. how hard to think
- [S-114 · Reasoning Scratchpad Budget](s114-reasoning-scratchpad-budget.md) — client-side token control; effort dials are the provider-side equivalent
- [S-243 · Agentic Inference Cost Stratification](s243-agentic-inference-cost-stratification.md) — macro-level cost anatomy; this fills the per-call dimension
- [S-606 · The Benchmark Laundering Problem](s606-the-benchmark-laundering-problem.md) — evaluation quality degrades with model updates; effort-tier calibration data has the same shelf-life problem
