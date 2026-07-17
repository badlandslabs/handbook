# S-1198 · The Thinking Token Blind Spot Stack — When Your Reasoning Model's Inner Monologue Costs More Than Your Entire App

Your Claude Opus invoice arrived 2.4× higher than last month. Every engineering dashboard is green. No incidents. No code changes. The culprit: reasoning tokens. The invisible half of the model's output — its internal chain-of-thought — is billed at the same rate as your visible response, but your observability stack never logged a single token of it. Finance found the problem before engineering did. This is the **Thinking Token Blind Spot**: the gap between what your logs measure and what your provider charges.

## Forces

- **The model's inner monologue is output.** Reasoning tokens from extended-thinking APIs (Claude extended thinking, OpenAI o3/o4) are billed as output tokens but don't appear in `choices[0].message.content`. Standard loggers miss them entirely.
- **The multiplier is 5–8×.** Thinking tokens cost 5–8× more per token than standard output on the same model. A single complex query can generate 20,000–40,000 invisible thinking tokens and 500 visible ones — the thinking is 98% of the bill.
- **Standard APM is blind.** OpenTelemetry instrumentation built for standard LLMs captures output token counts from the visible response field. It never reads `gen_ai.usage.reasoning.output_tokens` or `usage.output_tokens_details.reasoning_tokens`. Every dashboard stays green while the invoice grows.
- **A 2+2 query can cost $0.50.** Enabling extended thinking globally — even for trivial requests — is the most common production mistake. Factual lookups, simple retrievals, and short summaries don't need deep reasoning, but the thinking budget applies to every call.
- **The finance analyst finds it first.** Teams routinely discover a reasoning-model regression via invoice anomaly, not engineering alert. By then, the overage spans weeks of production traffic.

## The move

### 1. Extract thinking tokens from API metadata — every call

The thinking token count lives in the API response metadata. Log it on every request:

```python
import anthropic

client = anthropic.Anthropic()

def llm_call(model: str, messages: list, thinking_budget: int | None = None) -> dict:
    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    response = client.messages.create(model=model, messages=messages, **extra_kwargs)

    # Extract thinking tokens — the invisible half of the bill
    usage = response.usage
    thinking_tokens = getattr(usage.output_tokens_details, 'thinking_tokens', 0) if hasattr(usage, 'output_tokens_details') else 0
    visible_tokens = usage.output_tokens - thinking_tokens
    cost = _calc_cost(model, usage.input_tokens, usage.output_tokens)

    # Emit BOTH as OpenTelemetry spans
    span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
    span.set_attribute("gen_ai.usage.reasoning.output_tokens", thinking_tokens)  # ← the blind spot
    span.set_attribute("gen_ai.usage.visible_output_tokens", visible_tokens)
    span.set_attribute("gen_ai.cost.total", cost)

    return {
        "content": response.content[0].text,
        "thinking_tokens": thinking_tokens,
        "visible_tokens": visible_tokens,
        "total_output_tokens": usage.output_tokens,
        "cost_usd": cost,
    }
```

For OpenAI reasoning models, the equivalent is `usage.output_tokens_details.reasoning_tokens`.

### 2. Set per-request hard cost caps

Never let a reasoning model run unbounded. Set both `max_tokens` and a dollar ceiling:

```python
MAX_COST_PER_CALL = 0.10  # hard cap — trip before this, not after
MAX_OUTPUT_TOKENS = 4096  # caps visible + thinking combined

response = client.messages.create(
    model="claude-opus-4-5",
    messages=messages,
    thinking={"type": "enabled", "budget_tokens": 8000},
    max_tokens=MAX_OUTPUT_TOKENS,
)
```

If the thinking budget in tokens times the per-token rate exceeds your cost cap, reduce the budget or route to a non-reasoning model.

### 3. Route by task complexity — not globally

Thinking is not free, and it is not always needed. Gate reasoning model usage by task type:

```python
REASONING_MODELS = {"claude-opus-4-5", "o3", "gpt-o3"}
FAST_MODELS = {"claude-sonnet-4-5", "gpt-4o-mini", "gemini-2.5-flash"}

REQUIRES_DEEP_REASONING = {
    "architectural_design", "multi_step_code", "formal_proof",
    "cross_domain_analysis", "novel_algorithm", "policy_reasoning",
}
SKIP_REASONING = {
    "factual_lookup", "simple_retrieval", "format_transform",
    "single_hop_qa", "short_summary", "classification",
}

def route_model(task_type: str) -> str:
    if task_type in REQUIRES_DEEP_REASONING:
        return random.choice(REASONING_MODELS)
    if task_type in SKIP_REASONING:
        return random.choice(FAST_MODELS)
    # Default: classify dynamically
    return (
        random.choice(REASONING_MODELS)
        if _estimate_complexity(task_type) > 0.7
        else random.choice(FAST_MODELS)
    )
```

A 5-token factual lookup routed to a reasoning model burns $0.10–$0.50 in thinking tokens. A $0.001 fast-model call handles it identically.

### 4. Monitor the reasoning-to-visible ratio per request type

Track this as a first-class metric:

```python
# Per-request-type reasoning ratio baseline
reasoning_ratio_baseline = {
    "factual_lookup": 0.1,      # thinking should be minimal
    "code_generation": 2.5,      # thinking > visible is expected
    "architectural_design": 6.0, # thinking dominates
    "simple_classification": 0.3,
}

def alert_on_anomaly(task_type: str, thinking_tokens: int, visible_tokens: int):
    ratio = thinking_tokens / max(visible_tokens, 1)
    baseline = reasoning_ratio_baseline.get(task_type, 2.0)
    if ratio > baseline * 3:
        # Something is wrong — either the model is over-reasoning
        # or the task type classification is wrong
        send_alert(f"reasoning_ratio_anomaly", {
            "task_type": task_type,
            "ratio": ratio,
            "threshold": baseline,
            "thinking_tokens": thinking_tokens,
        })
```

A factual lookup that suddenly generates a 20:1 reasoning ratio is a routing error or a model behavioral change. Catch it before it compounds.

### 5. Alert on cost velocity in thinking tokens specifically

A flat dollar ceiling (S-854) catches token spiral from volume. But a thinking-token velocity alert catches a different failure: a reasoning-model behavioral drift where the same tasks generate 2× more thinking:

```python
class ThinkingTokenDriftDetector:
    """Detects when reasoning model starts thinking harder on the same tasks."""

    def __init__(self, window_size: int = 100, drift_threshold: float = 1.5):
        self.window: deque[int] = deque(maxlen=window_size)
        self.drift_threshold = drift_threshold
        self.baseline = None

    def record(self, thinking_tokens: int) -> None:
        self.window.append(thinking_tokens)
        if len(self.window) == self.window_size and self.baseline is None:
            self.baseline = sum(self.window) / len(self.window)

        if self.baseline and len(self.window) > 10:
            current_avg = sum(self.window) / len(self.window)
            if current_avg > self.baseline * self.drift_threshold:
                send_alert("thinking_token_drift", {
                    "current_avg": current_avg,
                    "baseline": self.baseline,
                    "ratio": current_avg / self.baseline,
                    "window": list(self.window),
                })
```

### 6. Surface thinking token cost in every trace

The final step: make thinking tokens visible where engineers actually look — the trace:

```python
# In your OpenTelemetry exporter
span.add_event("billing_analysis", {
    "visible_token_cost": visible_tokens * PRICE_PER_OUTPUT_TOKEN,
    "thinking_token_cost": thinking_tokens * PRICE_PER_OUTPUT_TOKEN,
    "total_call_cost": (visible_tokens + thinking_tokens) * PRICE_PER_OUTPUT_TOKEN,
    "thinking_share_of_bill_pct": round(thinking_tokens / max(output_tokens, 1) * 100, 1),
})
```

Engineers who see "$0.023 — 87% thinking tokens" on a simple lookup immediately understand the routing problem. Engineers who only see "$0.023 — OK" never fix it.

## Verifying

1. **Query your observability tool** for `gen_ai.usage.reasoning.output_tokens` across all LLM spans. If zero results: your instrumentation has the blind spot.
2. **Cross-reference** thinking token totals from your LLM provider's billing export against the sum of your logged `reasoning.output_tokens`. Gap > 5% means you're not logging all calls.
3. **Run a task-type audit**: aggregate thinking token spend per `task_type` label. Any non-reasoning task type with median ratio > 2:1 is a routing misclassification.

## References

- [Tian Pan — Thinking Tokens Are Invisible in Logs, Loud on Your Bill](https://tianpan.co/blog/2026-05-14-thinking-tokens-observability-billing-gap) (2026-05-14)
- [TokenFence — Extended Thinking Cost Control: Claude & OpenAI o3](https://tokenfence.dev/blog/extended-thinking-cost-explosion-claude-o3-budget-controls-2026) (2026-03-30)
- [AI Cost Check — Reasoning Model Pricing: What Thinking Tokens Cost (2026)](https://aicostcheck.com/blog/ai-reasoning-model-pricing-thinking-tokens)
- [Iris Eval — The Cost of Invisible Agents: What $0.47 Per Query Looks Like at Scale](https://iris-eval.com/blog/the-cost-of-invisible-agents) (2026-03-15)
- [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions/tree/v1.37.0/docs/gen-ai) (`gen_ai.usage.reasoning.output_tokens`)
- [S-854 Token Spiral Kill Switch](/stacks/s854-the-token-spiral-kill-switch-stack-when-your-agent-runs-fine-and-your-invoice-doesnt.md) — token spiral from volume; this entry covers token opacity from thinking
- [S-114 Reasoning Scratchpad Budget](/stacks/s114-reasoning-scratchpad-budget.md) — scratchpad budget sizing; this entry covers observability of thinking costs
- [S-857 Test-Time Compute Budget](/stacks/s857-the-test-time-compute-budget-stack-when-your-agent-thinks-too-much-and-costs-too-much.md) — compute budget allocation; this entry covers the observability gap
