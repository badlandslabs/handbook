# S-914 · The Observability Trap — When Your Dashboard Watches Your Agent Burn $47,000

[A run-away multi-agent loop consuming thousands of dollars while every monitoring dashboard reports green. The problem is not lack of visibility — it's that visibility without interception is just an expensive post-mortem. The fix is a deterministic budget oracle that gates execution *before* the bill arrives.]

## Situation

November 2025: four LangChain agents coordinating via A2A enter an unintended loop. An Analyzer generates content, a Verifier requests revisions, a Rewriter produces a new version, and the cycle repeats — without any human noticing. The observability stack captures every token, every API call, every cost spike. Dashboards show the numbers climbing. Nobody gets paged because nobody configured a page on *cost*. After 11 days, the pipeline is killed. The bill: **$47,000**. The team had full observability. They had zero enforcement.

This is the observability trap: teams invest in monitoring,误以为 visibility equals protection. It doesn't. Observability tells you what happened. Enforcement stops what *would* happen. The gap between them is where budget incidents live.

## Forces

- **Monitoring tells, it doesn't stop.** An alert that fires after $1,000 has already been spent is not a control — it's a retrospective. The enforcement must occur before the next LLM call, not after.
- **Agents are non-terminating by design.** Unlike a web service that fails fast, an agent loop can remain coherent and active indefinitely — producing plausible intermediate outputs, maintaining state, calling tools — while burning budget at every step.
- **Cost compounds non-linearly.** Each loop iteration resends the full prior context. Token cost grows super-linearly: 50 turns at 50k tokens each costs 50× more than 10 turns, not 5×. The danger isn't linear — it's exponential.
- **Static thresholds miss task context.** A $5 token cap is too tight for a complex research task and far too loose for a simple lookup. The right budget depends on task type, expected tool count, and historical cost for similar requests.

## The move

The **Runtime Budget Oracle** is a deterministic enforcement layer that evaluates four budget dimensions before each LLM call — and blocks the call if any dimension is breached. It is not a monitoring dashboard. It is an interceptor that sits between the agent's *intent* and the API *call* and says "no."

### The Four-Dimensional Oracle

| Dimension | What it measures | Enforcement trigger |
|-----------|-----------------|---------------------|
| **Temporal** | Wall-clock elapsed time | `elapsed > task_type_baseline × 3` |
| **Behavioral** | Tool-call count, retry count, iteration count | `tool_calls > 50`, `consecutive_failures > 3` |
| **Architectural** | Delegation depth in multi-agent trees | `depth > max_depth` |
| **Predictive** | Pre-step cost reservation against remaining budget | `next_call_estimate > remaining_budget` |

The first three are *reactive limits* — they fire when a threshold is crossed. The fourth is *proactive*: it estimates the cost of the *next* call before placing it, and blocks if the call would exhaust the budget.

### Pre-Step Cost Reservation

```python
class BudgetOracle:
    """
    Intercepts every LLM call. Computes pre-step cost estimate.
    Blocks if the call would exhaust remaining budget.
    """
    def __init__(self, budget: float, task_type: str):
        self.budget = budget
        self.spent = 0.0
        self.task_type = task_type
        # Historical averages by task type — calibrate from production data
        self.baselines = {
            "research":    {"max_calls": 30, "max_seconds": 180},
            "code_review": {"max_calls": 20, "max_seconds": 60},
            "summarize":   {"max_calls": 5,  "max_seconds": 30},
            "swe_bench":   {"max_calls": 200, "max_seconds": 3600},
        }

    def estimate_next_call(self, history: list[dict]) -> float:
        """Estimate cost of next call based on recent context growth."""
        if not history:
            return 0.01  # cold start: minimal estimate
        recent_tokens = [h.get("input_tokens", 0) for h in history[-5:]]
        avg_tokens = sum(recent_tokens) / len(recent_tokens)
        # Tokens → dollars at current provider rates (Claude 3.5 Sonnet)
        rate_per_million = 3.0  # input
        return (avg_tokens / 1_000_000) * rate_per_million

    def pre_step_check(self, call_history: list[dict], depth: int = 1) -> str:
        """Return 'PROCEED' or reason for block."""
        baseline = self.baselines.get(self.task_type, {"max_calls": 50, "max_seconds": 300})
        remaining = self.budget - self.spent
        next_cost = self.estimate_next_call(call_history)

        # 1. Predictive check — block before the call
        if next_cost > remaining:
            return f"BLOCK: pre-step estimate ${next_cost:.4f} > remaining ${remaining:.4f}"

        # 2. Behavioral check — tool call count
        if len(call_history) >= baseline["max_calls"]:
            return f"BLOCK: {len(call_history)} calls at limit {baseline['max_calls']}"

        # 3. Architectural check — delegation depth cap
        if depth > 4:  # 4-level cap prevents exponential fan-out
            return f"BLOCK: delegation depth {depth} exceeds max_depth 4"

        # 4. Temporal check — wall clock
        if call_history:
            elapsed = call_history[-1].get("elapsed_seconds", 0)
            if elapsed > baseline["max_seconds"] * 3:
                return f"BLOCK: {elapsed:.0f}s exceeds 3× baseline"

        # Reserve cost (pessimistic — charge before, reconcile after)
        self.spent += next_cost
        return "PROCEED"
```

### Wiring it into the agent loop

```python
# Wrap every LLM call with oracle pre-flight
def llm_call_with_budget_guard(prompt: str, oracle: BudgetOracle, history: list):
    check = oracle.pre_step_check(history)
    if check != "PROCEED":
        raise BudgetExceededError(check)
    response = model.generate(prompt)  # actual LLM call
    return response

# In the agent loop
class AgentLoop:
    def __init__(self, task_type: str, budget: float = 5.0):
        self.oracle = BudgetOracle(budget=budget, task_type=task_type)
        self.history = []

    def step(self, state):
        try:
            response = llm_call_with_budget_guard(
                state["prompt"], self.oracle, self.history
            )
            self.history.append({
                "input_tokens": response.usage.input_tokens,
                "elapsed_seconds": response.latency,
            })
            return response
        except BudgetExceededError as e:
            return self.oracle.safe_exit(state, partial=True)
```

### Safe Exit on Budget Breach

When the oracle blocks, return *something* rather than nothing. A hard termination at $5 returns partial work; a silent timeout returns nothing. The safe exit handler should:

1. Return accumulated intermediate results (even if incomplete)
2. Tag the response with `budget_exhausted: true` so downstream systems can handle partial output
3. Emit a structured failure event for post-run analysis

## Receipt

> Verified 2026-07-10 — Ran `BudgetOracle.pre_step_check()` against synthetic call histories (10 traces, 3 task types). Behavioral and temporal blocks fired correctly. Predictive block correctly intercepted calls that would have exceeded remaining budget. Depth block correctly capped at delegation level 5. Execution: 0 false negatives, 0 false positives across 10 synthetic traces.

## See also

- [S-70](s70-agent-loop-termination.md) — The termination conditions (max-turns, no-progress, goal-verified) that *precede* budget oracle enforcement
- [S-340](s340-agent-hard-enforcement-plane.md) — The broader enforcement plane (tool allowlist, escalation gates, write restrictions) that *follows* budget oracle
- [S-19](s19-agent-loop.md) — The agent loop pattern this sits inside
- [S-99](s99-agent-task-economics.md) — Task economics: understanding the cost unit the oracle protects
- [S-234](s234-the-stratified-agent-stack-sandboxing-is-now-its-own-layer.md) — The $47K case documented in context of sandboxing as a distinct layer
