# [S-2685] · The Inference Budget Enforcement Stack

When your billing dashboard lights up red, your Slack channel fills with cost alerts, and your CFO is asking questions — and none of it would have stopped the runaway inference call that caused it. Visibility is not enforcement.

## Situation

You built a multi-agent pipeline that routes customer inquiries through a classifier agent, then a research agent, then a synthesis agent. Each uses GPT-5 or Claude 3.7. You have Datadog dashboards, GCP billing exports, and a cost anomaly alert at 120% of baseline. Last month, a recursive tool-call loop ran for 47 minutes on a single ticket. Your alert fired at 2:31 AM. The invoice arrived at the end of the month. The alert didn't stop the loop. Nothing did.

This is the **visibility-without-enforcement gap**: the 2026 inference cost problem disguised as a FinOps problem.

## Forces

- **Agent loops run at machine speed.** A recursive tool call that generates 10,000 tokens per iteration hits your budget faster than any human can respond to a Slack alert. Alerts are postmortem in agentic systems.
- **Context compounding amplifies cost silently.** Each loop iteration adds tokens to context. A 10-iteration loop doesn't cost 10× the first call — it costs 10× the first call *plus* compounding context overhead. Microsoft Research (2026) found 30× cost variance on identical tasks across different agent loop configurations.
- **Token budget enforcement and dollar budget enforcement are different problems.** S-2595 covers token budget enforcement (hard caps on input/output tokens). This entry covers the harder problem: *dollar-denominated, time-bounded enforcement* — the thing that actually makes finance happy.
- **Per-agent budgets and per-request budgets aren't enough.** Your synthesis agent has a 50K-token cap. But the real cost driver is *orchestration-level* budget exhaustion across multiple agents sharing a request — the loop spans agents, so no single agent cap catches it.
- **The 2026 cost crisis is architectural, not operational.** Teams that "add a budget alert" are treating a structural problem with a monitoring solution. The fix requires enforcement points in the execution path, not observers watching the aftermath.

## The Move

Split enforcement into **three layers** with decreasing aggressiveness:

### Layer 1 — Hard Dollar Ceiling (execution-path enforcement)

Put a spending cap *in the request path*, not the billing path. This is a running counter incremented per token and compared against a configurable ceiling before each model invocation.

```python
import tiktoken
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
import time

class BudgetAction(Enum):
    RETRY_CHEAPER = "retry_cheaper"
    TRUNCATE = "truncate"
    ESCALATE = "escalate"
    ABORT = "abort"

@dataclass
class DollarBudgetEnforcer:
    """
    Runtime dollar-denominated budget enforcement for LLM pipelines.
    Unlike token budgets (S-2595), this tracks actual spend against
    a configurable dollar ceiling — the unit finance cares about.
    """
    dollar_ceiling: float          # e.g., 2.00 per request
    current_spend: float = 0.0
    token_price_per_1k: float = 0.0  # e.g., 0.003 for input, 0.015 for output
    enforcement_action: BudgetAction = BudgetAction.ABORT
    on_enforcement: Optional[Callable[["DollarBudgetEnforcer", float], None]] = None

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.token_price_per_1k
                + output_tokens * self.token_price_per_1k) / 1000

    def can_invoke(self, input_tokens: int, output_tokens: int) -> tuple[bool, float]:
        """Returns (allowed, projected_spend). Check BEFORE the API call."""
        projected = self.current_spend + self.estimate_cost(input_tokens, output_tokens)
        return projected <= self.dollar_ceiling, projected

    def record_invoke(self, input_tokens: int, output_tokens: int) -> None:
        """Call AFTER the API response arrives to update spend counter."""
        self.current_spend += self.estimate_cost(input_tokens, output_tokens)
        if self.current_spend >= self.dollar_ceiling:
            self._trigger_enforcement()

    def _trigger_enforcement(self):
        if self.on_enforcement:
            self.on_enforcement(self, self.current_spend)


# Example: per-request budget with automatic fallback to cheaper model
def with_fallback_enforcement(enforcer: DollarBudgetEnforcer, model_premium, model_cheap):
    """Wraps an LLM call: enforce budget, then fall back on breach."""
    def invoke(messages, model=model_premium):
        enc = tiktoken.encoding_for_model(model)
        input_text = str(messages)
        input_tokens = len(enc.encode(input_text))
        output_estimate = 2048  # conservative upper bound for planning

        allowed, projected = enforcer.can_invoke(input_tokens, output_estimate)
        if not allowed:
            # Try cheaper model before aborting
            if model == model_premium:
                return invoke(messages, model=model_cheap)
            raise BudgetExceededError(
                f"Request budget exceeded: ${enforcer.current_spend:.4f} "
                f"of ${enforcer.dollar_ceiling:.2f} ceiling"
            )
        return model(messages)
    return invoke
```

### Layer 2 — Orchestration-Level Token Velocity Watchdog

Track token accumulation *across* agents within a single user request. This catches cross-agent loops that no per-agent budget would catch.

```python
@dataclass
class VelocityWatchdog:
    """
    Detects runaway token accumulation across multi-agent pipelines.
    Triggers when token accumulation rate exceeds the threshold —
    catching loops faster than any dollar ceiling could.
    """
    tokens_per_minute_ceiling: float = 100_000  # ~5K-token/minute for fast loops
    window_seconds: int = 60
    token_history: list[tuple[float, int]] = field(default_factory=list)  # (timestamp, tokens)

    def record(self, token_count: int) -> bool:
        """Returns True if within budget, False if velocity exceeded."""
        now = time.time()
        self.token_history.append((now, token_count))

        # Prune history outside the window
        cutoff = now - self.window_seconds
        self.token_history = [(t, c) for t, c in self.token_history if t >= cutoff]

        total = sum(c for _, c in self.token_history)
        return total <= self.tokens_per_minute_ceiling
```

### Layer 3 — Cost-Aware Model Routing

Route to cheaper models when a request's accumulated cost profile predicts ceiling breach before it happens. This is the proactive version of the fallback pattern.

```python
def cost_aware_route(request_context: dict, agents: list[Agent]) -> Agent:
    """
    Routes to the cheapest capable agent given accumulated request cost.
    Uses running cost estimate + remaining budget to pick the next agent.
    """
    remaining = request_context.get("remaining_dollar_budget", 10.0)
    task_complexity = request_context.get("task_complexity", "medium")

    if remaining < 0.50:
        return agents.by_capability("simple-extraction")
    elif remaining < 2.00:
        return agents.by_capability("moderate-reasoning", prefer_cheap=True)
    else:
        return agents.by_capability(task_complexity)
```

## When to Reach for This

Use this when:
- You have billing dashboards but still get cost surprises
- Multi-agent pipelines share a budget across agents (no per-agent ceiling catches this)
- Recursive tool calls or loops are possible in your use case
- Finance is asking for per-request cost accountability
- You have an observability stack but no enforcement points in your execution path

The tell: when you can describe exactly *how* you overspent but had no architectural mechanism to prevent it.

## See also

- [S-2595 · The Token Budget Enforcement Stack](s2595-the-token-budget-enforcement-stack-when-your-alert-arrives-after-the-invoice.md) — token-level enforcement (Layer 1 complement); this entry covers dollar-denominated, cross-agent enforcement
- [S-2681 · The Agent Orchestration Stack](s2681-the-agent-orchestration-stack-when-one-agent-is-not-enough-and-ten-are-too-many.md) — orchestration patterns where Layer 2 velocity detection applies
- [S-2682 · The LLM Gateway Failure Atlas](s2682-the-llm-gateway-failure-atlas-when-your-proxy-looks-healthy-but-everything-is-broken.md) — gateway-layer enforcement points that complement this entry's execution-path controls
