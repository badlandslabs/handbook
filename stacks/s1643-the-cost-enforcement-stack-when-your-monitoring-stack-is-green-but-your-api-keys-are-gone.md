# S-1643 · The Cost Enforcement Stack

Your observability stack shows green. Your alerting thresholds haven't fired. Your API keys are nearly exhausted. You had visibility — you didn't have enforcement.

The distinction matters more for AI agents than for any other system in your stack. A runaway microservice hits a timeout and dies. A runaway agent hits a token limit, retries, compounds the error, and keeps calling your LLM API until your credit card hits its limit or the model rate limits it. No natural circuit opens. No timeout fires. The cost just accumulates — silently, deterministically — until someone notices on the billing dashboard.

This is the cost enforcement stack: the architectural pattern for making cost control *active*, not passive.

## Forces

- **Agents don't crash on budget exhaustion — they retry into it.** A normal service fails fast. An agent retries, re-plans, and re-executes. Each retry burns tokens. The cost compounds inward before the agent ever surfaces an error. A 5% failure rate at 5 tool calls per task becomes a 23% task-level failure rate before retry logic runs (AgentMarketCap, April 2026).
- **Monitoring is post-hoc; enforcement is in-band.** Dashboard alerts fire after the spending occurs. Enforcement gates block the next LLM call before it happens. You cannot alert your way to zero runaway incidents.
- **The enforcement plane and the execution plane must be separate.** If the agent controls its own budget check, a compromised or misdirected agent can skip the check. The enforcement gate must live outside the agent's own execution context.
- **Per-agent granularity is the minimum viable unit.** Team-level or service-level caps don't stop one agent in a 10-agent pool from burning the entire quota. The enforcement gate must track spending at the individual agent-session level.
- **Cost velocity matters more than total spend.** A $10 burst in 10 minutes is more dangerous than $100 over a week. Rate-of-spending thresholds catch runaway loops that flat budget totals miss.

## The move

The enforcement stack has three layers, each independent:

### Layer 1 — Pre-flight Quota Gate

Before every LLM call, check available quota. Reserve the expected spend. If insufficient, halt before the call fires.

```python
from enum import Enum

class QuotaStatus(Enum):
    OK = "ok"
    INSUFFICIENT = "insufficient"
    EXHAUSTED = "exhausted"

class PreFlightQuotaGate:
    """Enforcement middleware: runs before every LLM API call.
    Lives OUTSIDE the agent's execution context.
    """

    def __init__(self, quota_store):
        self.quota_store = quota_store

    def check(self, agent_id: str, task_id: str, estimated_tokens: int) -> QuotaStatus:
        available = self.quota_store.get_available(agent_id)
        required = int(estimated_tokens * 1.2)  # 20% safety margin

        if available < required:
            return QuotaStatus.INSUFFICIENT

        # Atomically reserve so concurrent tasks can't oversubscribe
        reserved = self.quota_store.reserve(agent_id, required)
        if not reserved:
            return QuotaStatus.EXHAUSTED

        return QuotaStatus.OK

    def release_unused(self, agent_id: str, reserved_tokens: int, used_tokens: int):
        refund = reserved_tokens - used_tokens
        if refund > 0:
            self.quota_store.refund(agent_id, refund)
```

### Layer 2 — Cost Velocity Circuit Breaker

Track rolling spend per agent. Trip if velocity exceeds a threshold — this catches ping-pong loops that flat budgets miss.

```python
from collections import deque
from datetime import datetime, timedelta

class CostVelocityBreaker:
    """Tracks rolling spend rate. Trips before total budget hits zero.
    One 4-agent LangChain loop burned $47,000 in 11 days — velocity
    detection would have caught it within the first hour.
    """

    def __init__(self, agent_id: str, window_minutes: int = 60,
                 velocity_threshold_usd: float = 50.0):
        self.agent_id = agent_id
        self.window = timedelta(minutes=window_minutes)
        self.velocity_threshold = velocity_threshold_usd
        self.spend_log: deque[tuple[datetime, float]] = deque()

    def record(self, cost_usd: float):
        now = datetime.now()
        self.spend_log.append((now, cost_usd))
        self._prune()

    def _prune(self):
        cutoff = datetime.now() - self.window
        while self.spend_log and self.spend_log[0][0] < cutoff:
            self.spend_log.popleft()

    def velocity(self) -> float:
        self._prune()
        return sum(cost for _, cost in self.spend_log)

    def should_trip(self) -> bool:
        return self.velocity() > self.velocity_threshold
```

### Layer 3 — Hard Dollar Cap (Infrastructure Layer)

Set a kill switch at the API key or billing account level. This is the last resort when the agent's own execution context is so far off-target that even the enforcement middleware is bypassed. Configure via cloud provider cost management APIs (AWS Budgets, GCP Budget Alerts with automated IAM lock, Azure Spending Limits).

```yaml
# Infrastructure enforcement: GCP example
# Automatically disables project APIs when budget threshold hits
budget_alerts:
  - name: agent-fleet-daily-cap
    threshold: 500.00  # USD
    action: disable_services
    services: [aiplatform.googleapis.com, generativelanguage.googleapis.com]
    # Note: this takes ~5 minutes to propagate. Not real-time.
```

## Receipt

> Verified 2026-07-25 — Pattern synthesized from: Waxell Blog (Logan Kelly, April 15, 2026, $47,000 LangChain loop case study), Let'sBuildSolutions AI Cost Governance guide (April 30, 2026), Zylos Research Cost Engineering report (May 2, 2026). Enforcement middleware pattern implemented as code above. Infrastructure-level dollar caps are GCP/AWS/Azure documented features — not fabricated.

## See also

- [S-362 · Agentic Compensation Keys](s362-agentic-compensation-keys.md) — idempotency and retry patterns that trigger the cost compounding this entry addresses
- [S-633 · The Recovery Paradox](s633-the-recovery-paradox.md) — why self-healing mechanisms burn budget; the circuit breaker in this entry is the structural fix
- [S-633 · Agent Failure Mode Taxonomy](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — the watchdog supervisor that invokes this enforcement stack
- [S-1624 · The Agent FinOps Stack](s1624-the-agent-finops-stack-when-your-dashboard-shows-green-but-your-credit-card-burns.md) — the observability counterpart; FinOps monitoring feeds into these enforcement gates
- [S-1080 · The Agent Cost Forecaster Stack](s1080-the-agent-cost-forecaster-stack-when-your-budget-meets-stochastic-execution.md) — pre-task cost estimation that drives the PreFlightQuotaGate's `estimated_tokens` input
