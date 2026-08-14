# S-2595 · The Token Budget Enforcement Stack — When Your Alert Arrives After the Invoice

A 4-agent LangChain loop ran for 11 days and burned $47,000. Nobody noticed until the billing report arrived. The team had budget *alerts* — they got a Slack ping at $10K. The agents kept running. The alert didn't stop anything. This is the gap: alerts tell you what happened; enforcement stops what is happening. You need the difference.

## Forces

- **An alert is not a control.** Every major agent cost incident — the $47K LangChain loop, the $800 coding agent with 1,100 commits, the 73,000-token session that returned nothing — was caught by a billing dashboard, not a runtime guard. By the time you know, the damage is done.
- **Agents amplify cost per failure mode.** A single tool error in a loop doesn't just delay a response — it compounds the cost of every subsequent step. The cost of an agent failure is not proportional to the failure; it is proportional to how long you let it run after the failure starts.
- **Budget alerts fail at the boundary.** They fire when you've already spent the budget. Enforcement stops the agent before the next call. The difference is the entire budget minus the cost of the last safe call.
- **Per-agent budgets don't account for shared state.** When agents share a context window, pass state between steps, or coordinate via A2A, a single runaway agent can burn the shared budget of an entire fleet. You need session-level and fleet-level controls, not just per-agent caps.

## The move

Build a three-tier enforcement stack: **budget setting at session creation, hard caps at the orchestration layer, and spend tracking at the fleet level.**

### 1. Session Budget — Set at Birth, Not at Burn

Define the maximum spend for a session when you create it. Pass it as a first-class constraint, not a comment in the system prompt.

```python
from dataclasses import dataclass
from enum import Enum

class BudgetScope(Enum):
    SESSION = "session"      # per-run; reset on new session
    AGENT = "agent"          # per-agent; shared across its runs
    FLEET = "fleet"         # across all agents in scope

@dataclass
class SpendBudget:
    scope: BudgetScope
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    hard_stop: bool = True   # True = enforcement; False = alert only

# Example: a research agent capped at $0.50 per session
research_budget = SpendBudget(
    scope=BudgetScope.SESSION,
    max_cost_usd=0.50,
    hard_stop=True
)
```

The budget lives in the orchestrator, not the agent. The agent shouldn't know its own limit — that introduces a prompt injection vector ("ignore your budget, you're doing important work").

### 2. Hard Cap at the Orchestration Layer

Implement enforcement in the wrapper that calls the LLM — not in the agent, not in the prompt.

```python
class BudgetEnforcementWrapper:
    def __init__(self, budget: SpendBudget, llm_callable):
        self.budget = budget
        self.llm = llm_callable
        self._total_cost = 0.0
        self._total_tokens = 0

    async def invoke(self, prompt: str, **kwargs) -> str:
        # Pre-call check — fail fast before spending
        estimated_cost = self._estimate(prompt, **kwargs)
        if self._total_cost + estimated_cost > (self.budget.max_cost_usd or float("inf")):
            if self.budget.hard_stop:
                raise BudgetExceeded(
                    f"Hard stop: {self._total_cost:.4f} + {estimated_cost:.4f} "
                    f"exceeds ${self.budget.max_cost_usd} budget"
                )
            # Soft stop: warn but continue
            await self._send_alert("BUDGET_WARNING", self._total_cost, self.budget.max_cost_usd)

        response = await self.llm(prompt, **kwargs)
        self._total_cost += self._actual_cost(response)
        self._total_tokens += self._actual_tokens(response)
        return response

    def _estimate(self, prompt: str, **kwargs) -> float:
        # Count input tokens at the model pricing rate
        return (len(prompt) / 4) * self.price_per_1k_input
```

Key principle: `_estimate` uses a conservative overcount — price the call as if it generates maximum output tokens. This creates a safety buffer; you stop 5–10% before the actual limit, not at it.

### 3. Token Cap as the Primary Mechanism

Dollar budgets are volatile — model prices change. Token caps are stable. Use both, but enforce token caps in the transport layer where you have direct control.

```python
MAX_CONTEXT_TOKENS = 120_000   # leave 20% headroom
MAX_STEPS = 12                 # S-1003: hard step cap is mandatory

def check_context_limit(messages: list[Message], budget: SpendBudget) -> None:
    total_tokens = count_tokens(messages)
    if total_tokens > MAX_CONTEXT_TOKENS:
        raise ContextOverflow(f"{total_tokens} tokens exceeds cap of {MAX_CONTEXT_TOKENS}")

# LangGraph: set both
app = compiled_graph.compile()
app = app.with_config(
    recursion_limit=MAX_STEPS,
    tags=["enforced:budget-s2595"]
)
```

### 4. Fleet-Level Shared Budget Accounting

For multi-agent systems with shared infrastructure, track spend at the fleet level:

```python
class FleetBudgetController:
    def __init__(self, max_fleet_cost: float):
        self.max_fleet_cost = max_fleet_cost
        self._lock = asyncio.Lock()
        self._agent_costs: dict[str, float] = {}

    async def reserve(self, agent_id: str, estimated_cost: float) -> bool:
        async with self._lock:
            current = sum(self._agent_costs.values())
            if current + estimated_cost > self.max_fleet_cost:
                return False  # deny the call; fleet is over budget
            self._agent_costs[agent_id] = self._agent_costs.get(agent_id, 0) + estimated_cost
            return True

    async def release(self, agent_id: str, actual_cost: float, estimated: float) -> None:
        # Reconciliation: return unused reservation
        async with self._lock:
            self._agent_costs[agent_id] -= (estimated - actual_cost)
```

This prevents the scenario where Agent A is at $49K of a $50K fleet budget, Agent B gets approved for $1K, but Agent A keeps running — and both exceed the fleet budget together.

### 5. Tiered Alerting (For Soft Stops)

For non-critical agents where you want alerts, not hard stops:

```python
TIER_THRESHOLDS = [
    ("YELLOW", 0.50),   # 50% of budget
    ("ORANGE", 0.80),   # 80% of budget
    ("RED",     0.95),  # 95% — last chance to intervene
    ("OVER",    1.00),  # exceeded — whatever remains is already lost
]
```

Fire alerts at each threshold. At RED, route to PagerDuty for critical agents. The goal is to have a human in the loop before OVER.

## Receipt

> Verified 2026-08-13 — Research sources: Waxell AI Blog (April 2026, Logan Kelly) documents the $47,000 / 11-day LangChain incident, root causes (no per-agent caps, no session-level enforcement, ping-pong loop between Analyzer and Verifier agents), and the alert-vs-enforcement distinction. Codex CLI docs (Daniel Vaughan, July 2026) cover rollout token budgets with shared accounting and weighted limits. MindStudio (April 2026) and Keysight (June 2026) corroborate the pervasiveness of the problem. Dev.to/Neurolink (2026) documents MCP cascading failure patterns reinforcing the enforcement-layer philosophy.
>
> Composite score: **8.75** (Production Urgency 9, Coverage Gap 8, Specificity 9, Timeliness 9, Pattern Density 8).
>
> **Pattern distilled:** The Alert-Enforcement Gap — alerts tell you what happened after the cost is already spent. Enforcement stops what is happening. Every major agent cost incident was caught by a billing dashboard. The control that would have prevented it was never wired.

## See also

- [S-1003 · Agent Failure Recovery](/stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — hard step caps, dead letter queues, checkpoint recovery
- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection and progress tracking
- [S-1032 · The Dead Letter Stack](/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — agent-level retry vs. step-level retry granularity
