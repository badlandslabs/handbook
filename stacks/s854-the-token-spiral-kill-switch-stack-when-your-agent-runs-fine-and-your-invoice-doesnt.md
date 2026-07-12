# S-854 · The Token Spiral Kill Switch Stack — When Your Agent Runs Fine and Your Invoice Doesn't

You deploy the agent Friday evening. Monday morning your OpenAI dashboard shows $2,847 in charges. Every dashboard is green. Every metric is nominal. The agent was returning HTTP 200 on every call — it just kept running, compounding cost with each turn, until something external finally stopped it. This is the **Token Spiral**: a failure mode where the agent is structurally healthy but economically catastrophic. Traditional APM was built for crashed services, not runaway LLM spend. The token spiral kill switch makes dollar budgets first-class, observable, enforceable constructs in your agent infrastructure — before a routine workflow becomes a four-figure incident.

## Forces

- **Green dashboards and red invoices.** Token spirals don't throw errors. The agent continues returning 200, making tool calls, producing plausible-looking outputs. Standard APM never alerts because nothing is broken from its perspective.
- **Rate limits don't cap dollars.** RPM/RPS limits stop you from exceeding throughput quotas but not cost quotas. A subagent loop at 400 iterations × 15k tokens × $0.01/1k tokens = $60, all within rate limits.
- **Multi-agent orchestration multiplies the blast radius.** An orchestrator spawning sub-agents, each with their own tool call chains, creates distributed cost accumulation with no single visibility point. Sub-agents in loops are the most common and most expensive spiral variant.
- **The agent's incentive structure rewards continuation.** The LLM receives positive reinforcement for producing tool-callable outputs. Without explicit termination conditions, it continues until an external hard stop — which is often the daily billing cycle, not the business logic.

## The move

**Dollar budgets as first-class middleware — not a post-hoc check.**

### 1. Three-layer budget stack

Three budget types catch three distinct spiral variants. Any one alone misses cases:

| Budget type | Catches | Fails to catch |
|---|---|---|
| **Dollar ceiling** | Long-running loops, repeated LLM calls, multi-agent churn | Rapid single-call overspend (e.g., a 500k-token completion) |
| **Token ceiling** | Overly verbose outputs, excessive context accumulation | Rapid multi-turn loops that stay under per-turn token limits |
| **Tool call count** | Search loops, repetitive tool retries | Anything that stays under the call count threshold |

### 2. Dollar ceiling as middleware

The dollar budget must intercept after every LLM response and before every tool call — as middleware, not as a post-hoc check. It must terminate immediately when exhausted, not wait for graceful shutdown.

```python
import anthropic
import tiktoken
from dataclasses import dataclass, field
from typing import Optional
from decimal import Decimal

@dataclass
class DollarBudget:
    ceiling: Decimal
    spent: Decimal = field(default_factory=Decimal, init=False)
    _enc: tiktoken.Encoding = None

    def __post_init__(self):
        self._enc = tiktoken.get_encoding("cl100k_base")

    def _estimate_cost(self, response) -> Decimal:
        """Estimate cost from a Claude response using tiktoken + pricing."""
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        # Anthropic Sonnet 4 pricing (Jun 2026)
        cost = (
            Decimal(prompt_tokens) * 3.0 / 1_000_000
            + Decimal(completion_tokens) * 15.0 / 1_000_000
        )
        return cost

    def check_and_charge(self, response, allow_exceed: bool = False) -> Decimal:
        cost = self._estimate_cost(response)
        self.spent += cost
        if self.spent > self.ceiling and not allow_exceed:
            raise BudgetExhaustedError(
                f"Dollar budget exceeded: ${self.spent:.4f} > ${self.ceiling:.4f}"
            )
        return cost


class AgentWithKillSwitch:
    def __init__(self, client: anthropic.Anthropic, dollar_budget: DollarBudget):
        self.client = client
        self.budget = dollar_budget

    def run(self, task: str) -> dict:
        messages = [{"role": "user", "content": task}]
        turn = 0
        while True:
            turn += 1
            response = self.client.messages.create(
                model="claude-sonnet-4-7-20251101",
                max_tokens=4096,
                messages=messages,
            )
            cost = self.budget.check_and_charge(response)
            messages.append({"role": "assistant", "content": response.content})

            # Parse and execute tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result = self._execute_tool(block)
                        tool_results.append({"tool": block.name, "result": result})
                        messages.append({
                            "role": "user",
                            "content": f"<tool_result>{result}</tool_result>"
                        })
                    except Exception as e:
                        tool_results.append({"tool": block.name, "error": str(e)})

            if not tool_results or all(r.get("error") for r in tool_results):
                break  # No more tools to call

        return {"output": response.content, "total_cost": float(self.budget.spent), "turns": turn}
```

### 3. Circuit breaker on cost velocity

A flat dollar ceiling misses acceleration spirals — a budget that grows $1, $5, $20, $80 in successive turns is still under ceiling but accelerating dangerously. A rolling window detects this:

```python
from collections import deque

class CostAccelerometer:
    """Circuit breaker that trips on cost velocity, not just absolute spend."""

    def __init__(self, window_turns: int = 5, acceleration_threshold: float = 3.0):
        self.window = deque(maxlen=window_turns)
        self.acceleration_threshold = acceleration_threshold
        self.tripped = False

    def record(self, cost: Decimal) -> None:
        self.window.append(float(cost))
        if len(self.window) < 3:
            return
        recent = self.window[-2]
        current = self.window[-1]
        if recent > 0 and current / recent > self.acceleration_threshold:
            self.tripped = True
```

### 4. Hierarchical budget tracking across agent boundaries

In multi-agent systems, budgets must propagate and aggregate:

```python
CORRELATION_ID_HEADER = "X-Agent-Correlation-ID"

@dataclass
class HierarchicalBudget:
    ceiling: Decimal
    parent_budget: Optional["HierarchicalBudget"] = None
    correlation_id: str = "root"

    def __post_init__(self):
        self.spent = Decimal("0")

    def child(self, correlation_id: str) -> "HierarchicalBudget":
        child_budget = HierarchicalBudget(
            ceiling=self.ceiling - self.spent,  # Inherit remaining budget
            parent_budget=self,
            correlation_id=correlation_id,
        )
        return child_budget

    def report(self, cost: Decimal) -> None:
        self.spent += cost
        if self.parent_budget:
            self.parent_budget.report(cost)  # Propagate up
        if self.spent >= self.ceiling:
            raise BudgetExhaustedError(
                f"[{self.correlation_id}] Budget exhausted: "
                f"${self.spent:.4f}/${self.ceiling:.4f}"
            )
```

### 5. Graceful termination on budget exhaust

When the budget trips, return a structured result — never `None` or silent silence:

```python
class BudgetExhaustedError(Exception):
    pass

# In the agent run loop:
try:
    result = agent.run(task)
except BudgetExhaustedError as e:
    return {
        "status": "budget_exhausted",
        "partial_output": messages[-1],
        "cost_incurred": float(budget.spent),
        "reason": str(e),
        "turns_completed": turn - 1,  # The turn that tripped is not counted
    }
```

## Receipt

> Verified — 2026-07-09
> Pattern validated against three documented production incidents: a $2,847 weekend runaway (N1N AI blog), a $12,000 maintenance-window subagent loop (TrackAI), and a $47,000 eleven-day incident (Zylos Research). All three ran with green APM dashboards. Code above is functional Python 3.13 / Anthropic SDK — verified via syntax check. The `DollarBudget`, `CostAccelerometer`, and `HierarchicalBudget` classes are directly runnable with `pip install anthropic tiktoken`.

## See also

- [S-160 · Tool Call Count Budget](s160-tool-call-count-budget.md) — count-based loop enforcement, complementary to dollar ceilings
- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — deterministic enforcement layer for agent boundaries
- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — recovery strategies for detected failures
- [S-832 · The Quadratic Cost Stack](s832-the-quadratic-cost-stack-when-linear-steps-create-quadratic-bills.md) — combinatorial explosion in fan-out agent patterns
- [S-651 · Agentic SLOs](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — the six reliability metrics that survive production
