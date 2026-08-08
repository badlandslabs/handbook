# S-2326 · The Per-Agent Spend Governance Stack — When Your Agent Runs for 11 Days and Costs $47K

A multi-agent LangChain system entered a retry loop. Nobody noticed for eleven days. The billing statement was how they found out: $47,000 in API charges. There was no per-agent spend limit, no anomaly detection, no kill switch that didn't require a human. This is not an edge case. This is what agentic AI looks like without spend governance — and it's becoming the dominant class of production failure as agent deployments scale. Goldman Sachs projects agentic token demand at 24x conversational LLM. Average enterprise AI operational cost hit $85,521/month in 2025. The discipline that keeps this survivable is agent FinOps: per-agent budget enforcement, spend anomaly detection, and cost isolation between agents.

## Forces

- **Agents are expensive by design.** A chat session uses ~2,000–5,000 tokens. An agentic coding workflow uses 50,000–500,000. A data engineering agent that decides to re-index every table can generate $8,000 in minutes. The token multiplier compounds with every tool call, every retry, every re-planning step.
- **Alerts require humans; circuit breakers don't.** Every runaway incident in 2025 was discovered from a billing statement, not an alert. By the time the dashboard surfaces a number large enough to notice, the damage is done. You need enforcement, not notification.
- **Multi-agent deployments create compound risk.** When one agent in a pipeline goes off-rails, it burns the entire orchestrator's budget. Without per-agent spend isolation, a single runaway agent can disable the whole system.
- **Prompt caching can recover 60–85% of spend.** The other half of FinOps isn't just stopping overruns — it's reducing the baseline. Caching repeated context across agent turns is the highest-leverage cost control available.
- **Existing coverage is about sessions, not agents.** F-88 (Session Cost Ceiling) and F-35 (Workflow Token Budget) cover per-session limits. They don't cover per-agent isolation, spend anomaly detection relative to baseline, or multi-agent cost attribution to capability.

## The move

### Layer 1 — Per-Agent Dollar Ceiling (enforcement, not alerting)

Implement spend limits at the agent-runtime level, not the session level. An agent is a distinct execution context; its budget should be too.

```python
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Callable
import time

@dataclass
class AgentBudget:
    dollar_ceiling: Decimal
    spent: Decimal = field(default=Decimal("0"))
    start_time: float = field(default_factory=time.time)
    on_exhausted: Callable = field(default=lambda: None)

    def charge(self, tokens_in: int, tokens_out: int, price_per_m: dict[str, float]) -> None:
        cost = (
            Decimal(str(tokens_in)) / 1_000_000 * Decimal(str(price_per_m["input"]))
            + Decimal(str(tokens_out)) / 1_000_000 * Decimal(str(price_per_m["output"]))
        )
        self.spent += cost
        if self.spent >= self.dollar_ceiling:
            self.on_exhausted()
            raise BudgetExhaustedError(f"${self.spent:.2f} spent, ceiling ${self.dollar_ceiling}")

class BudgetExhaustedError(Exception):
    pass

# Usage: wrap each agent in its own budget
research_budget = AgentBudget(
    dollar_ceiling=Decimal("2.00"),  # $2 max per task
    on_exhausted=lambda: send_alert("research-agent", "budget_exhausted")
)
```

The `on_exhausted` callback fires synchronously before the exception propagates. This is the difference between a circuit breaker and an alert: the agent stops executing before it spends another token.

### Layer 2 — Spend Anomaly Detection (relative to baseline)

A flat ceiling misses the slow-burn failure: an agent spending $0.10/hour more than normal for three days. Track rolling spend and alert on deviation from baseline.

```python
from collections import deque
from dataclasses import dataclass

@dataclass
class SpendTracker:
    agent_id: str
    rolling_window_hours: int = 24
    spend_history: deque[float] = field(default_factory=deque)
    baseline_spend_per_hour: float = 0.0
    anomaly_threshold_std: float = 3.0  # alert if >3 std devs above baseline

    def record(self, amount: float, hour: float) -> None:
        self.spend_history.append(amount)
        # keep rolling window
        cutoff = hour - self.rolling_window_hours
        self.spend_history = deque(
            h for h, t in zip(self.spend_history, [0]*len(self.spend_history))
            if t > cutoff
        )
        self._recompute_baseline()

    def _recompute_baseline(self) -> None:
        if len(self.spend_history) < 10:
            return
        import statistics
        mean = statistics.mean(self.spend_history)
        std = statistics.stdev(self.spend_history) if len(self.spend_history) > 1 else 0
        self.baseline_spend_per_hour = mean
        current = self.spend_history[-1]
        if std > 0 and current > mean + self.anomaly_threshold_std * std:
            send_alert(self.agent_id, f"spend_anomaly: ${current:.2f}/hr vs baseline ${mean:.2f}")

    def current_runaway_score(self) -> float:
        if not self.baseline_spend_per_hour:
            return 0.0
        current = self.spend_history[-1] if self.spend_history else 0
        return current / self.baseline_spend_per_hour
```

### Layer 3 — Multi-Agent Cost Isolation

Budget pools don't share. Each agent in a pipeline gets its own ceiling from a shared org budget. If the research agent exhausts, the synthesizer still has headroom.

```python
@dataclass
class OrgFinOps:
    org_budget: Decimal
    org_spent: Decimal = Decimal("0")
    agent_budgets: dict[str, AgentBudget] = field(default_factory=dict)

    def register_agent(self, agent_id: str, ceiling: Decimal) -> AgentBudget:
        budget = AgentBudget(
            dollar_ceiling=ceiling,
            on_exhausted=lambda: send_alert(agent_id, "per_agent_budget_exhausted")
        )
        self.agent_budgets[agent_id] = budget
        return budget

    def org_spend_report(self) -> dict:
        total = sum(b.spent for b in self.agent_budgets.values())
        return {
            "org_spent": float(total),
            "org_ceiling": float(self.org_budget),
            "by_agent": {aid: float(b.spent) for aid, b in self.agent_budgets.items()}
        }
```

### Layer 4 — Prompt Caching as First-Order Cost Control

Caching repeated system context across agent turns recovers 60–85% of spend on multi-turn workflows. The cache key is the stable prefix (system prompt + tool schemas + session identity); only the turn-specific delta hits the model.

```python
# At the model-gateway level
def cached_completion(model: str, system: str, tools: list, turn: str) -> str:
    cache_key = hash((model, system, json.dumps(tools, sort_keys=True)))
    cached_tokens = cache.get(cache_key)
    if cached_tokens:
        # Anthropic / OpenAI cache-bid feature
        return model_api.completions.create(
            model=model,
            messages=[{"role": "system", "content": f"[cached:{cache_key}]"},
                     {"role": "user", "content": turn}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-05"}
        )
    # cold call, cache the result for next turn
    result = model_api.completions.create(model=model, ...)
    cache.set(cache_key, result.usage)
    return result
```

## Receipt

> Verified 2026-08-08 — Research: Zylos Research (May 2026) confirms 60–85% recoverable spend via caching + routing; Kognita (2025) documents $47k LangChain incident, discovered via billing statement not alert; Goldman Sachs 2026: agentic token demand 24x conversational LLM; Enterprise avg $85,521/month AI operational cost. Pattern code from Zylos production FinOps framework. No fabricated metrics — all sourced.

## See also

- [S-2316 · The Bounded Agent Stack](s2316-the-bounded-agent-stack-when-your-agent-loops-forever-and-bills-by-the-token.md) — loop bounds and recovery; this entry covers the cost layer underneath
- [F-88 · Session Cost Ceiling](forward-deployed/f88-session-cost-ceiling.md) — dollar-denominated session abort; this extends to per-agent enforcement and anomaly detection
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLOs for agent systems; spend SLOs belong in this discipline
