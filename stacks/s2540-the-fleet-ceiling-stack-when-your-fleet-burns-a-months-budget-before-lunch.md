# S-2540 · The Fleet Ceiling Stack — When Your Agent Fleet Burns a Month's Budget Before Lunch

[Every agent has a session budget. None of them have a fleet budget. At 2 PM, the research agent, the coding agent, the QA agent, and the review agent are each at 60% of their session limits — all green. At 2:01 PM, all four hit their limits simultaneously and spawn escalation paths. At 2:15 PM, someone notices the invoice. The fleet has consumed a month's budget in 15 minutes. Nobody owns the total.]

## Forces

- **Individual budgets don't sum to fleet budgets.** Each agent has a per-session ceiling. Nobody has a fleet ceiling. When 50 concurrent sessions each consume 80% of their budget at the same time, the total fleet spend spikes 40× above baseline — silently, because every individual dashboard shows green.
- **Agents optimize locally, not globally.** An agent at 90% of its budget doesn't know the fleet is at 95% of the total ceiling. It makes a locally rational decision to do one more expensive tool call. The fleet doesn't have a signal for "collectively, we've hit the wall."
- **Cost attribution is retroactive until it isn't.** Most teams discover fleet overruns through invoices, not alerts. By the time the finance team flags the anomaly, the damage is done and the budget is gone.
- **Kill switches exist but aren't wired.** Per-agent termination exists in every framework. Fleet-level kill switches — that stop all agents of a type simultaneously — are not default and rarely wired to the billing API.

## The move

### 1. Fleet Budget Hierarchy

Structure budgets as a three-level pool:

```
Fleet Ceiling (org-level) → Agent-Type Pool → Per-Session Budget
```

The **fleet ceiling** is the hard stop for all agents of a given type. It is the level that actually prevents the $500K bill, not the per-session cap. Each **agent-type pool** (research, coding, review) gets a share of the fleet ceiling. Each **per-session** budget draws from the pool. Pool exhaustion triggers a fleet-wide pause for that agent type, not a per-session stop.

The pool model also enables **priority spill**: critical-path agents can borrow from idle pools, with automatic payback when the idle agent's session ends.

### 2. Hard Ceiling vs. Soft Alert as a Product Decision

Soft alerts (Slack notification at 80%) are theater. A hard ceiling terminates the session before the next API call — no message to the agent, no continuation. The choice between hard and soft must be explicit per agent type:

| Agent Type | Policy | Rationale |
|---|---|---|
| Research / exploration | Soft alert → hard stop at 100% | High variance, recoverable |
| Transactional / user-facing | Hard ceiling from call 1 | Billing risk unacceptable |
| Internal automation | Soft alert → hard stop at 110% | Some overage acceptable, not runaway |

Wiring the hard ceiling: intercept at the LLM API call boundary. Every call passes through a budget gate that checks `current_fleet_spend + estimated_call_cost <= fleet_ceiling`. If not, return a structured error to the orchestration layer — not to the model — and route to a degraded mode or queue.

### 3. Cross-Session Spend Tracking

The tracking schema must be per-span, not per-request. One agent task fans out into dozens of priced events: LLM tokens, retrieval calls, tool executions, durable-state operations. Attribution requires:

```python
class SpendEvent:
    trace_id: str          # OTel trace ID for causal chain
    agent_id: str          # which agent instance
    agent_type: str        # research | coding | review
    session_id: str
    priced_span: str       # which operation
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime
    metadata: dict         # task_id, user_id, org_id for chargeback
```

Every priced event flows to a fleet budget coordinator. The coordinator maintains the running aggregate per pool and per fleet ceiling. It is the single writer to the budget state — every agent reads from it but none write to it.

### 4. Fleet Ceiling Kill Switch

A fleet ceiling kill switch stops all agents of a given type simultaneously when the ceiling is hit, regardless of individual session state. This is distinct from per-session termination:

- **Per-session kill**: stops one agent instance. Others continue.
- **Fleet kill switch**: stops all instances of that agent type. Requires explicit re-enablement from an authorized owner.

Implement as a flag in the fleet coordinator: `fleet_pools[agent_type].frozen = True`. All agents poll this flag before every LLM call. When frozen, the orchestration layer returns a `FleetBudgetExceeded` error to the workflow — which can then trigger a human approval flow or queue the task for later.

The kill switch must be in the infrastructure layer (API gateway, orchestration proxy), not in the agent prompt. Prompt-based budget signals fail when the model is reasoning hard and ignores meta-instructions.

### 5. Chargeback Attribution

To make budget ownership real, every priced span must roll up to a cost center:

```python
def rollup_spend(events: list[SpendEvent]) -> dict[str, float]:
    return {
        f"team:{t}": sum(e.cost_usd for e in events if e.metadata.get("team") == t)
        for t in set(e.metadata.get("team") for e in events)
    }
```

Tag every task launch with `team`, `project`, and `cost_center` metadata. Without this, fleet budget data exists but nobody acts on it — it looks like an infrastructure problem, not a team problem. With it, team leads get their own dashboards and the budget conversation shifts from "we have a fleet problem" to "the research team needs to optimize their retrieval strategy."

### 6. Anomaly Detection: The 15-Minute Spike Pattern

The fleet ceiling failure mode is distinctive: a sharp, uniform spike across all agent pools at the same time, driven by simultaneous session budget exhaustion triggering escalation paths. Detect it with:

- **Spike ratio**: `current_15m_spend / rolling_15m_average`. Alert at 3×. Hard stop at 10×.
- **Cross-pool correlation**: if 3+ pools spike within the same 5-minute window, freeze the fleet ceiling and alert.
- **Cost-per-task trend**: if the average cost-per-successful-task rises 2× week-over-week, flag before it hits the ceiling.

```python
# Fleet budget coordinator pseudocode
def check_ceiling(agent_type: str, estimated_cost: float) -> None:
    pool = fleet_pools[agent_type]
    fleet_total = sum(p.current_spend for p in fleet_pools.values())
    
    if fleet_total + estimated_cost >= fleet_ceiling:
        freeze_fleet(agent_type)
        alert(budget_team, f"Fleet ceiling hit: {agent_type}")
        emit_incident(trace_id=current_trace(), reason="fleet_ceiling")
    elif pool.current_spend + estimated_cost >= pool.capacity:
        pool.frozen = True
        reroute_to_queue(agent_type)
```

## Receipt

> Verified 2026-08-12 — Research sources: (1) Waxell.ai token budget enforcement article (Jun 2026) — $47K analyzer-verifier loop incident, per-session vs fleet ceilings; (2) TokenFence cost management article (Mar 2026) — autonomous agents making 12 reasoning steps, spawning 4 sub-agents, 8 tools = unpredictable cost explosion; (3) Finout agentic AI cost governance (Jun 2026) — Gartner 40% cancellation rate from cost overruns, per-request/session/day limits; (4) NextPage IT FinOps guide (Jun 2026) — seven budget lines model (LLM tokens, retrieval, tool calls, infra, observability, retries, human review); (5) Circuit Breaker Python library (MonetiseBG, Jun 2026) — budget-guard and loop-killer modes, post-hoc enforcement default; (6) Waxell before/after enforcement article (Jun 2026) — Uber burned annual budget by April 2026, $500M reported Claude bill. Actual production patterns confirm fleet ceiling as the gap: individual budgets exist, fleet budgets do not.

## See also

- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-as-a-first-class-behavioral-dimension.md) — agent-level cost self-regulation (complementary: this entry is fleet/infra level, that entry is agent/behavior level)
- [S-1176 · Token Budget Governance](s1176-the-token-budget-governance-stack-when-your-agent-looks-healthy-on-the-dashboard-and-bills-47k.md) — the $47K dashboard-blind loop (this entry adds fleet-ceiling, pool hierarchy, and chargeback to token-level enforcement)
- [S-1243 · Token Budget](s1243-the-token-budget-stack-when-your-agent-spends-more-than-your-engineer.md) — per-session token budget mechanics (this entry is the organizational ceiling above per-session budgets)
