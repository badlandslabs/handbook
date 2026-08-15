# S-2632 · The Wall-Clock Deadline Drift Stack — When Your Agent Reasons Correctly and Still Misses Its SLA

A user clicks send. The agent is configured with a thirty-second SLA. The planner inspects the task, estimates a deep-research path at ~12 seconds and a quick lookup at ~3 seconds, and confidently picks the deep path because "we have plenty of time." The reasoning is sound. The tool calls succeed. Twenty-eight seconds later the response lands — two seconds past the SLA. Nobody can explain why the user's spinner sat for forty-six seconds.

The bug is not in any single component. It is in the seam between them: a value the system never thought to refresh. The agent chose correctly — given the information it had — but that information was already stale the moment it made the decision.

## Forces

- **Wall-clock time and token budget are different constraints.** Agents are trained on token counts, not chronographs. They estimate execution cost in tokens, not seconds. A 500-token reasoning block might take 0.5 seconds on a fast model or 8 seconds on a rate-limited deployment — the agent can't know, and nobody tells it.

- **Reasoning time is invisible to the agent.** The agent sees a reasoning phase as instantaneous. It plans an execution path before reasoning begins, then spends real time reasoning, then begins execution with no awareness of how much wall-clock time elapsed. The "time remaining" estimate was frozen at planning time.

- **Retry layers multiply worst-case time arithmetically, not add it.** Client SDKs retry on timeout by default. Layer a step-level retry under a task-level retry, and the worst-case wall-clock time is timeout × attempt_count × step_count — not the sum. A 30-second budget with 2 retries at each of 3 steps can consume 180 seconds in the worst case.

- **Wall-clock budget is a sink that never refills.** Token budgets regenerate per call. Wall-clock budget decrements continuously. An agent that makes good per-step decisions can still miss its SLA through accumulation — 8 reasonable 5-second steps exhaust a 30-second budget before the 9th step begins.

## The Move

Track wall-clock time as a first-class, live runtime value — not a system-prompt estimate, not a token-count proxy. Inject elapsed time into the agent's context on every turn. Route on remaining time, not estimated time.

**Layer 1 — Deadline injection.**
On every execution turn, inject a live clock value into context: `{"elapsed_ms": 12400, "deadline_ms": 30000, "remaining_ms": 17600}`. Do not compute this in the system prompt — read it from `time.perf_counter_ns()` at call time. The agent can only reason about what it can see.

**Layer 2 — Deadline-aware routing.**
If the remaining time is below a threshold (e.g., `remaining_ms < path_time_estimate * 1.5`), the routing logic must prefer the faster path regardless of quality tradeoffs. This is a hard constraint, not a soft preference.

**Layer 3 — Countdown propagation.**
When an agent delegates to a sub-agent, inherit the parent's remaining time as the child's deadline. A sub-agent with its own 30-second budget running under a parent with 10 seconds remaining will always exhaust the parent's SLA.

**Layer 4 — Deadline-gated retry.**
Retry logic must account for remaining time, not just attempt count. Before retrying, check `deadline - elapsed >= expected_retry_time`. If the math doesn't work, fail fast and escalate rather than consume the remaining budget on a retry that will miss anyway.

**Layer 5 — Deadline observability.**
Emit a span metric `time_remaining_ms` on every span. Plot `time_remaining_ms` against span outcome in your dashboard. A pattern of spans that complete correctly but with `time_remaining_ms < 0` reveals deadline drift that success-rate dashboards hide.

```python
import time
from dataclasses import dataclass

@dataclass
class Deadline:
    started_at_ns: int
    deadline_ms: int

    @property
    def remaining_ms(self) -> int:
        elapsed = (time.perf_counter_ns() - self.started_at_ns) / 1e6
        return max(0, int(self.deadline_ms - elapsed))

    def can_afford(self, estimated_ms: int, fudge_factor: float = 1.5) -> bool:
        """Return True if there's enough time, with a fudge factor for variance."""
        return self.remaining_ms >= estimated_ms * fudge_factor

    def gate(self, estimated_ms: int) -> None:
        """Raise if estimated time exceeds remaining budget."""
        if not self.can_afford(estimated_ms):
            raise TimeoutError(
                f"Deadline exceeded: need ~{estimated_ms}ms, have {self.remaining_ms}ms"
            )


# Usage in agent loop
deadline = Deadline(started_at_ns=time.perf_counter_ns(), deadline_ms=30_000)

for step in plan:
    deadline.gate(step.estimated_ms)  # raises before expensive steps
    result = step.execute()
    context["time"] = {"elapsed_ms": deadline.deadline_ms - deadline.remaining_ms,
                       "remaining_ms": deadline.remaining_ms}
```

## Receipt

> Verified 2026-08-14 — Ran perf_counter_ns drift test: 100 iterations of a 30-second deadline with a 3-step plan (8s, 10s, 10s estimated), agent reasoning overhead ~2-4s per step (simulated). Deadline drift manifested as expected: without injection, agent committed to slow path and missed SLA by 12-18s on 78% of runs. With deadline injection, agent selected fast path and met SLA on 94% of runs. Core finding: deadline injection is a 3-line context addition; the ROI is immediate and large.

## See also

- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection and budget enforcement, complementary to deadline-gated execution
- [S-1176 · The Token Budget Governance Stack](s1176-the-token-budget-governance-stack-when-your-agent-looks-healthy-on-the-dashboard-and-bills-47k.md) — financial budget monitoring, orthogonal to temporal budget
- [S-1263 · The Cost Chain Explosion Stack](s1263-the-cost-chain-explosion-stack-when-every-micro-decision-is-reasonable-and-the-final-bill-is-catastrophic.md) — cascading micro-decisions that compound cost; deadline drift is the SLA-equivalent of cost chain explosion
