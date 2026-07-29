# S-1837 · The Agentic FinOps Stack: When Your Agent Spends $400 to Find a Nickel

You get the invoice: $412 for a single agent run that was supposed to cost $0.05. The agent spent $400 in reasoning tokens looking for a $0.05 discrepancy it already found. The CFO wants to know why. Your monitoring dashboard shows 100% uptime. Your agent logs show no errors. The cost is simply the result of giving an autonomous agent a blank check — and no policy to stop it.

Agentic FinOps is the discipline of governing agent spend by making token, tool, and downstream infrastructure costs budgeted, attributed, capped, and proactively optimized — before the invoice arrives.

## Forces

- **Agents make cost-behavior-driven decisions that humans never preview.** A single task can trigger 3–10x more LLM calls than a simple chatbot — planning, tool selection, execution, verification, response generation all bill separately. A software-engineering agent running on an o1-class model can cost $5–8 per task before you add retrieval, sandbox spin-up, or retry logic.
- **Token cost compounds through multiplicative structure.** Three agents × five sub-calls = 15 LLM calls per round. At 50K tokens × $0.015/1K = $11.25 per round. Twenty rounds per batch, ten batches per day = $2,250/day. The individual call is cheap; the orchestration multiplier is not.
- **Tokens are the visible line item; everything else is hidden.** Cache storage, sandbox VMs, embedding generation, guardrail calls, retrieval pipelines, and egress often represent 40–60% of actual spend — none of it visible in the token count.
- **Traditional FinOps alerts after the fact; agents need pre-execution enforcement.** By the time a dashboard fires an alert, the $400 decision has already been made and the tokens have already been spent.

## The move

Split cost governance into three enforcement layers, applied before the agent decides, not after it bills.

### Layer 1 — Per-Action Token Caps

Cap tokens per individual LLM call and per tool invocation. This is the smallest unit of enforcement.

```python
import anthropic
from dataclasses import dataclass

@dataclass
class TokenBudget:
    max_tokens_per_call: int   # e.g., 4096 for a quick routing call
    max_thinking_tokens: int   # separate cap for reasoning model thinking
    max_tool_calls: int        # hard cap per task
    max_total_tokens: int      # all calls combined

class BudgetedClient:
    def __init__(self, budget: TokenBudget):
        self.budget = budget
        self.total_spent = 0
        self.tool_call_count = 0

    def chat(self, messages: list, thinking: bool = False) -> str:
        budget = self.budget.max_thinking_tokens if thinking else self.budget.max_tokens_per_call

        if self.total_spent >= self.budget.max_total_tokens:
            raise BudgetExceededError(
                f"Task exceeded total budget {self.budget.max_total_tokens} tokens "
                f"(spent: {self.total_spent}). Stopping."
            )
        if self.tool_call_count >= self.budget.max_tool_calls:
            raise ToolCallLimitError(
                f"Task hit tool-call cap {self.budget.max_tool_calls}. "
                f"Tool calls so far: {self.tool_call_count}."
            )

        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=budget,
            messages=messages
        )
        self.total_spent += response.usage.input_tokens + response.usage.output_tokens
        return response.content
```

### Layer 2 — Per-Task Cost Budget with Graceful Degradation

The task-level budget gates the entire agent run. When exceeded, the agent degrades to a cheaper fallback — it doesn't abort; it simplifies.

```python
class AgenticFinOps:
    def __init__(self, task_budget_usd: float):
        self.task_budget_usd = task_budget_usd
        self.spent_usd = 0.0
        # Prices per 1M tokens (approximate, Q3 2026)
        self.prices = {
            "claude-opus-4-6":  {"input": 15.0,  "output": 75.0},
            "claude-sonnet-4":  {"input": 3.0,   "output": 15.0},
            "claude-haiku-3":   {"input": 0.8,   "output": 4.0},
        }

    def _tokens_to_usd(self, model: str, input_toks: int, output_toks: int) -> float:
        p = self.prices[model]
        return (input_toks * p["input"] + output_toks * p["output"]) / 1_000_000

    def run(self, task: str, mode: str = "full") -> dict:
        """
        mode: 'full' (opus for reasoning), 'standard' (sonnet), 'fast' (haiku)
        """
        # Downgrade if we're at risk of overspend
        if mode == "full" and self.spent_usd > self.task_budget_usd * 0.7:
            mode = "standard"
        if mode == "standard" and self.spent_usd > self.task_budget_usd * 0.9:
            mode = "fast"

        result = self._execute(task, model=self._mode_to_model(mode))
        cost = self._tokens_to_usd(result["model"], result["input_toks"], result["output_toks"])
        self.spent_usd += cost

        return {
            **result,
            "mode_used": mode,
            "cost_usd": cost,
            "total_spent_usd": self.spent_usd,
            "budget_remaining_usd": max(0, self.task_budget_usd - self.spent_usd),
        }

    def _execute(self, task: str, model: str) -> dict:
        # ... actual execution
        pass
```

### Layer 3 — Fleet-Level Spend Governance with Autonomous Throttling

At the fleet level, track spend against a running budget window and throttle or queue new runs when approaching the limit.

```python
from datetime import datetime, timedelta
from collections import deque

class FleetBudgetController:
    def __init__(self, daily_budget_usd: float, window_hours: int = 24):
        self.daily_budget_usd = daily_budget_usd
        self.window_hours = window_hours
        self.spend_log: deque[tuple[datetime, float]] = deque()  # (timestamp, cost)

    def can_run(self, estimated_cost_usd: float) -> bool:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=self.window_hours)

        # Prune old entries
        while self.spend_log and self.spend_log[0][0] < cutoff:
            self.spend_log.popleft()

        total = sum(cost for _, cost in self.spend_log)
        return (total + estimated_cost_usd) <= self.daily_budget_usd

    def record(self, cost_usd: float):
        self.spend_log.append((datetime.utcnow(), cost_usd))

    def get_fleet_status(self) -> dict:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=self.window_hours)
        while self.spend_log and self.spend_log[0][0] < cutoff:
            self.spend_log.popleft()
        total = sum(cost for _, cost in self.spend_log)
        return {
            "window_hours": self.window_hours,
            "spent_usd": round(total, 4),
            "budget_usd": self.daily_budget_usd,
            "utilization_pct": round(100 * total / self.daily_budget_usd, 1),
            "remaining_usd": round(max(0, self.daily_budget_usd - total), 4),
        }
```

### The Cost Attribution Problem

You cannot govern what you cannot decompose. Tag every agent run with: product line, feature, customer tier, deployment environment, and agent version. Without attribution, a $50K spike tells you nothing — with it, you know exactly which team, which product, and which task type drove the overrun.

```python
# Tag every call with structured metadata for post-hoc analysis
run_tags = {
    "product": "code-review",
    "team": "platform-eng",
    "customer_tier": "enterprise",
    "env": "production",
    "agent_version": "v2.4.1",
    "autonomy_mode": "plan",    # plan mode uses ~7x tokens vs. standard
}
# Log to your observability platform (Portkey, Langfuse, Datadog)
```

## Receipt

> Receipt pending — 2026-07-29

Verified on: real production run showing task-mode Claude Code averaging $6/developer/day, with 90% of users below $12/day, and plan-mode runs using ~7x more tokens than standard sessions (Cordum, April 2026). Budget enforcement layers tested conceptually against the agentic-finops GitHub framework (sandyshd/agentic-atqbfinops). Full end-to-end receipt pending run against live fleet with the three-layer enforcement stack.

## See also

- [S-1032 · The Dead Letter Stack](stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — failure-driven cost burns
- [S-1011 · The Rate-Limited Multi-Agent Pattern](stacks/s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — coordination failure amplifies spend
- [S-1802 · The Reasoning Budget Control Stack](stacks/s1802-the-reasoning-budget-control-stack-when-your-thinking-tokens-cost-more-than-your-compute.md) — test-time compute cost governance
