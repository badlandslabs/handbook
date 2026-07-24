# S-1571 · The Economic Firewall Stack — When Your Agent Runs for 11 Days and Burns $47,000

A 4-agent LangChain pipeline ran for 11 days, burning $47,000 in API costs via an Analyzer-Verifier infinite loop over the A2A protocol. Nobody noticed until the bill arrived. This is not an outlier — it is the predictable consequence of deploying autonomous agents without economic enforcement. The solution is an **economic firewall**: a runtime control layer that evaluates and enforces spending limits *before* each LLM call executes, not after.

## Situation

Your agent works in development. In production, it handles edge cases, loops, retries, and delegates in ways you didn't anticipate. Each iteration costs money. Without a spending ceiling, a single misbehaving agent can exceed your monthly cloud bill. Alerts don't help — they fire after the spend, not before. Rate limits don't help — they count requests, not dollars. You need enforcement that sits between the agent's intent and the API call.

## Forces

- **Agents are built for iteration.** Unlike traditional software that returns a result and stops, agents plan, retry, delegate, and loop. A single task can fan out into hundreds of billable API calls. The autonomy that makes them useful is the same property that makes them dangerous.
- **Alerts fire after the damage.** A $2,000 alert that arrives 3 hours into an infinite loop doesn't stop the loop. By the time a human reads it, the damage is done. Enforcement — not monitoring — is the only mechanism that actually prevents overspend.
- **Rate limits are the wrong primitive.** Per-minute or per-day request caps answer "how many calls?" not "how much money?" A task with 50 small calls and a task with 2 expensive ones can both respect request limits while having wildly different costs.
- **Cost is multi-dimensional.** A ceiling matters at the per-task level, per-session level, per-agent level, per-day level, and per-team level simultaneously. A single flat cap misses cases where a legitimate task legitimately costs more than a flat limit allows.
- **Partial results have value.** Hitting a spend ceiling should return the work done so far, not a crash with nothing. Unlike a failed payment, an interrupted agent task may have produced useful intermediate outputs worth surfacing.

## The move

Design the economic firewall as a policy-enforcement gateway that every LLM call passes through. The gateway has three layers:

**Layer 1 — Cost estimation before the call**

Before every LLM API call, estimate its cost based on the pending input token count and the configured model. This is not a hard cap yet — it's a projection. Compare it against remaining budget for the current task/session/agent. If the projected cost would exhaust the remaining budget, block the call before it starts.

```python
class EconomicFirewall:
    def __init__(self, per_session_cap: float, per_task_cap: float):
        self.session_budget = per_session_cap
        self.task_budget = per_task_cap
        self.session_spent = 0.0
        self.task_spent = 0.0

    def estimate(self, model: str, input_tokens: int, output_tokens: int = 0) -> float:
        price = PRICING[model]  # {model: (input_per_1M, output_per_1M)}
        return (input_tokens / 1_000_000 * price[0] +
                output_tokens / 1_000_000 * price[1])

    def preflight(self, call: LLMCall) -> EnforceResult:
        projected = self.estimate(call.model, call.input_tokens)
        if self.task_spent + projected > self.task_budget:
            return EnforceResult.BLOCK   # hard stop before call
        if self.session_spent + projected > self.session_budget:
            return EnforceResult.BLOCK
        # Soft warning: allow but log
        if self.task_spent + projected > self.task_budget * 0.8:
            return EnforceResult.WARN
        return EnforceResult.ALLOW

    def record(self, call: LLMCall, actual_cost: float):
        self.task_spent += actual_cost
        self.session_spent += actual_cost
```

**Layer 2 — Hard ceiling with partial result rollback**

When the firewall blocks a call, it does not crash the agent — it raises a structured `BudgetExceeded` exception that carries the work done so far. Downstream handlers can surface partial results, save checkpoints, or escalate to a human. The agent doesn't silently loop or return nothing; it returns something with a clear termination reason.

```python
def run_with_firewall(agent, task, firewall: EconomicFirewall):
    try:
        while not agent.is_done():
            call = agent.prepare_next_call()
            result = firewall.preflight(call)
            if result == EnforceResult.BLOCK:
                return agent.get_partial_result(
                    status="budget_exceeded",
                    spent=firewall.task_spent,
                    budget=firewall.task_budget,
                    reason="per_task_cap"
                )
            elif result == EnforceResult.WARN:
                agent.attach_warning(f"80% of task budget consumed")
            agent.execute(call)
            firewall.record(call, call.actual_cost)
    except BudgetExceeded as e:
        return e.partial_result
```

**Layer 3 — Hierarchical budget decomposition**

Distribute caps down a hierarchy so no single agent or task can monopolize the budget. A production deployment typically needs: team-level monthly cap → service-level daily cap → agent-level session cap → task-level per-run cap. The hierarchy means that even if one task exhausts its own cap, the session and agent caps still protect the broader system.

```
Team cap ($10K/month)
  └── Service A cap ($3K/day)
        └── Agent A1 cap ($50/session)
              └── Task T1 cap ($2/run)
```

## Receipt

> Verified 2026-07-24 — Research validated against three documented incidents: the $47,000 LangChain 11-day loop (Waxell, Apr 2026), the DN42 network scanning agent (Hacker News, Jun 2026), and the AgentBudget open-source project (github.com/AgentBudget/agentbudget). Key distinction confirmed: alerts fire post-spend; enforcement blocks pre-spend. Multi-dimensional budget hierarchy matches patterns in F-88 (session ceiling) and F-199 (per-task attribution) — this entry fills the gap of enforcement-as-architecture, not just measurement.

## See also

- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection and recovery (enforcement happens at the scaffold level; this entry handles cost enforcement as a separate, composable layer)
- [F-88 · Session Cost Ceiling](f88-session-cost-ceiling.md) — dollar-denominated session caps (this entry extends F-88 with pre-call estimation, hierarchical decomposition, and partial result semantics)
- [F-199 · Per-Task Cost Attribution](f199-per-task-cost-attribution.md) — attributing cost at the unit-of-work level (economic firewall makes attribution actionable by stopping overspending before it occurs)
- [S-1054 · The Agent Interrupt Stack](s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — clean agent termination (economic firewall provides a trigger mechanism for safe interruption)
