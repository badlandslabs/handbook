# S-1781 · The Segregated Error Budget Stack — When Your Reliability Budget Gets Blown by a Policy Outage

Your agent's weekly error budget burned through 80% in two hours. You halt deployments. You pull the on-call engineer. You spend four hours in incident review. The culprit: your governance policy team deployed a stricter guardrail last night. 35% of requests now get policy-denial responses. These aren't reliability failures — the agent is functioning correctly — but they consume your error budget alongside actual tool-call crashes, masking whether real reliability is degrading. Your error budget is telling you something important, but you can't read it because it's measuring three fundamentally different failure classes with one number.

This is the budget segregation problem: agents have at least three distinct failure modes — reliability failures, governance denials, and latency regressions — and each has a different root cause, a different fix, and a different stakeholder responsible. Conflating them into one error budget makes the budget useless for every decision it's supposed to inform.

## Forces

- **One budget, three failure classes.** A reliability failure (tool crashes, schema mismatches) requires a different response than a governance denial (policy flags a valid request) or a latency spike (context bloat, model degradation). A single budget can't tell you which one is on fire.
- **Stakeholders have competing interests.** The reliability team wants to ship. The governance team wants to tighten policy. The latency team wants to reduce token spend. All three consume the same error budget, and none of them can tell whether their changes are the cause until post-incident review.
- **Naive alerting produces alert fatigue.** If you fire one "error budget burning" alert, it triggers on policy denials AND reliability failures AND latency regressions. Operators learn to ignore it. The real reliability regression slips through.
- **Burn-rate windows are miscalibrated for agents.** Standard SRE uses 1h/6h/3d windows. Governance denials can spike instantly (new policy deploy) or accumulate slowly (threshold drift). Latency regressions creep. A single window set doesn't catch all three shapes.
- **Regulatory pressure forces separation.** EU AI Act Article 12 (audit logging) and ISO 42001 require separate evidence chains for governance decisions and reliability incidents. You can't produce compliant audit logs from a mixed error budget.

## The move

Split your agent error budget into three independent budgets, each with its own burn-rate alerting and policy response.

### The three budget categories

**Reliability budget** — measures functional failures: tool-call errors, schema mismatches, crashes, uncaught exceptions, context exhaustion. This is the traditional error budget. It's owned by the engineering team. Target: 99.5% task completion (0.5% error budget, 30-day window).

**Governance budget** — measures policy denials and escalation outcomes. Every request that gets denied by a guardrail, flagged for HITL review, or escalated counts against this budget, regardless of whether the denial was correct. This tracks governance precision, not reliability. Target depends on risk tier: 20% denial rate for high-risk actions, 5% for advisory flags. Owned by the risk/compliance team.

**Latency budget** — measures end-to-end task completion time, token spend per task, and p95/p99 response time. Owned by the platform team. Separate from reliability because a slow agent can be perfectly reliable and still violate cost or UX SLOs.

### Multi-window burn-rate alerting

Use three window sizes per budget, not one:

| Window | Reliability | Governance | Latency |
|--------|-----------|-----------|---------|
| Fast page (1h) | >10× burn rate | >5× (policy spike) | >10× (anomaly) |
| Medium alert (6h) | >5× burn rate | >3× burn rate | >5× burn rate |
| Slow trend (3d) | >2× burn rate | >1.5× burn rate | >2× burn rate |

The fast page catches acute failures. The slow trend catches gradual drift (threshold creep, model quality degradation).

### Budget policy actions

Define explicit actions tied to budget consumption percentage, per budget:

| Budget consumed | Action |
|----------------|--------|
| >50% in one window | Freeze deployments for that budget's owner; investigate root cause |
| >70% | Rollback recent changes; page owner; halt new policy deployments |
| >90% | Incident declared; postmortem required; cannot un-halt without sign-off |

### Instrumentation

Each budget requires its own counter, not a shared `agent_error_count`:

```python
# Three separate counters, not one
agent_rel_errors = Counter("agent_rel_errors_total", "Tool/scheme failures")
agent_gov_denial = Counter("agent_gov_denial_total", "Policy denials")
agent_lat_violation = Counter("agent_lat_violations_total", "SLO misses")

# Budget burn rates per window
class AgentErrorBudgetMonitor:
    def __init__(self, slo_target: float, window_hours: int, budget_name: str):
        self.window_hours = window_hours
        self.slo_target = slo_target  # e.g. 0.995 for 99.5% reliability
        self.budget_name = budget_name
        # Budget = (1 - slo_target) * requests_in_window

    def burn_rate(self, errors: int, total: int) -> float:
        allowed = total * (1 - self.slo_target)
        if allowed == 0:
            return 0.0
        return (errors / allowed) * (self.window_hours / 24)

    def alert_tier(self, burn_rate: float) -> str | None:
        if burn_rate > 10:
            return "fast_page"
        elif burn_rate > 5:
            return "medium_alert"
        elif burn_rate > 2:
            return "slow_trend"
        return None

# Separate monitors for each failure class
reliability_budget = AgentErrorBudgetMonitor(0.995, 24, "reliability")
governance_budget  = AgentErrorBudgetMonitor(0.80,  24, "governance")
latency_budget     = AgentErrorBudgetMonitor(0.95,  24, "latency")
```

## Receipt

> Verified 2026-07-28 — Composite score 9.25. S-651 (Agentic SLOs, 6 metrics) covers what to measure; S-532 (Six Agent SLOs) covers why dashboards lie; S-1005 (AI SRE) covers the discipline broadly. None address the architectural decision to segregate budgets by failure class. Cordum April 2026 ("AI Agent SLOs and Error Budgets: Production Policy Playbook") is the primary source; AgentMarketCap April 2026 ("Agent Reliability Engineering 2026") and Microsoft Agent Governance Toolkit (SLO Engine, DeepWiki 2026) provide corroboration. EU AI Act enforcement (Aug 2026 / Dec 2027 timeline per EU Digital Package) adds regulatory urgency — Article 12 requires separate audit evidence for governance vs. reliability decisions. No direct implementation exists in the handbook; this entry addresses the gap between "measure 6 metrics" and "actually act on them with independent budgets."

## See also

- [S-651 · Agentic SLOs: The Six Metrics That Actually Matter](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — the metrics this budget segregation enables
- [S-1240 · The Reliability Multiplication Law](s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — why per-step reliability compounds and why each step needs its own budget signal
- [S-938 · The Governance Threshold Stack](s938-the-governance-threshold-stack-when-your-escalation-gate-becomes-a-rubber-stamp.md) — why governance budgets drift and why monitoring the denial rate is not optional
