# S-2443 · The Triple-Axis SLO Stack — When Correctness, Cost, and Latency Fail Separately but Together

[Your agent's correctness SLO is healthy. Your cost SLO is healthy. Your latency SLO is healthy. But your customer just complained that a batch of invoices was processed incorrectly at 3x normal cost while completing in half the expected time. Three separate SLOs drifted simultaneously, each within budget, and no single alert fired. This is the triple-axis failure: the most dangerous production mode because it passes every individual check.]

## Forces

- **Agents fail along independent axes.** Correctness, cost, and latency are orthogonal failure modes. An agent can get faster while getting wrong. It can get cheaper while getting slower. Each axis follows its own degradation curve, and standard SLO monitoring checks them in isolation — missing the compound state where all three are drifting but none is alarming.
- **SLOs measure what you track, not what matters.** Availability at 99.9% means nothing if 8% of available requests return wrong answers. Latency at P99 < 2s means nothing if cost per request tripled because the agent started calling tools redundantly. Each SLO dashboard is a floor, not a signal about the intersection.
- **Traditional SLO burn rates don't model agent pipelines.** SRE burn rate alerting (Google SRE Workbook) assumes a single SLI per SLO, consumed at a roughly constant rate. Agent pipelines compound: each step has its own correctness/cost/latency axis, and a 4-step pipeline with 95% correctness at each step gives you 81.4% end-to-end — a burn rate no single-step SLO captures.
- **"All-green" dashboards hide the real failure mode.** The defining 2025–2026 production failure is agents that return HTTP 200, finish in normal time, and produce wrong output at elevated cost. No alert. No page. A budget burn that only surfaces when Finance runs the monthly report.

## The move

### Define Three Independent SLIs

Track each axis as its own SLI with its own error budget:

```
Outcome SLO:  "Did the agent produce a correct, complete result?"
  SLI: % of runs where output passes automated outcome verification
  Target: 94% (30-day error budget: 540 min bad/month)
  Burn rate alert: >50% of budget consumed in 1 hour

Cost SLO:  "Did the agent stay within token and tool-call budget?"
  SLI: % of runs where cost < defined threshold (e.g., $0.50/run)
  Target: 96% (30-day error budget: 288 min over-budget/month)
  Burn rate alert: >50% of budget consumed in 4 hours

Latency SLO:  "Did the agent complete within the time SLA?"
  SLI: % of runs completing within time threshold (e.g., 30s)
  Target: 95% (30-day error budget: 360 min slow/month)
  Burn rate alert: >50% of budget consumed in 1 hour
```

### Track the Compound State

Add a fourth, composite view:

```python
# Composite health state — the intersection that individual SLOs miss
def composite_state(outcome_ok: bool, cost_ok: bool, latency_ok: bool) -> str:
    axes = [("outcome", outcome_ok), ("cost", cost_ok), ("latency", latency_ok)]
    good = sum(1 for _, ok in axes if ok)
    bad  = [name for name, ok in axes if not ok]

    if good == 3:
        return "NOMINAL"         # all three healthy
    elif good == 2:
        return f"SINGLE_AXIS_DEGRADED: {bad}"  # one axis bad
    elif good == 1:
        return f"DUAL_DEGRADED: {bad}"          # two axes bad — page
    else:
        return "TRIPLE_FAIL"                     # all three bad — severity: critical

# Composite burn rate: max(burn_rates), not sum
# Because the most constrained axis is the real bottleneck
composite_burn_rate = max(outcome_burn, cost_burn, latency_burn)

# Alert on composite, not individual
if composite_burn_rate > 0.5:  # >50% of any axis budget in short window
    page_oncall(f"Composite burn rate alert: {composite_burn_rate:.1%}")
```

### The Interaction Matrix

Map the six possible dual-axis failures — each has a distinct operational response:

| Axes failing | Root cause pattern | Typical trigger |
|---|---|---|
| Outcome + Cost | Agent making redundant tool calls or retrying | Tool output drift, context confusion |
| Outcome + Latency | Agent in long reflection loop with degraded reasoning | Context pollution, model degradation |
| Cost + Latency | Agent over-simplifying or looping | Task too complex, budget pressure causing shortcuts |
| Outcome only | Core task failure, agent gave up or hallucinated | Prompt drift, tool schema change |
| Cost only | Token inefficiency, verbose reasoning | Prompt bloat, redundant context |
| Latency only | Tool latency, rate limits | Infrastructure bottleneck |

This matrix turns a passive dashboard into an incident triage guide — the axis combination tells you where to look first.

### Pinpoint Budget Consumption

Use long-window and short-window burn rate alerts (Google SRE Workbook) on each axis independently:

```python
# Long window: 30-day error budget consumption
# Short window: 1-hour burst consumption
# Alert if: short_window_burn > 14.4x long_window_budget
# (This means 1 hour consuming at a rate that would exhaust the 30-day budget in 1 hour)

SHORT_WINDOW_HOURS = 1
LONG_WINDOW_DAYS = 30

for axis in ["outcome", "cost", "latency"]:
    short_burn = budget_consumed(axis, hours=SHORT_WINDOW_HOURS)
    long_budget = total_budget(axis, days=LONG_WINDOW_DAYS)
    long_burn_rate = long_budget / (LONG_WINDOW_DAYS * 24)

    if short_burn > 14.4 * long_burn_rate:
        page_oncall(f"Burst burn on {axis}: exhausting 30-day budget")
```

## Receipt

> Verified 2026-08-10 — Source: agentmarketcap.ai (Agent Reliability Engineering 2026), alexcloudstar.com (AI SLOs 2026), genta.dev (AI Agent Reliability Engineering 2026), Velsof (AI Agent SLO Patterns 2026). Composite multi-axis SLO tracking is an emerging pattern; no production implementation reference was found to run. Pattern validated against existing entries S-651 (six agentic metrics), S-736 (agent error budgets), S-1151 (behavioral telemetry), S-1781 (segregated error budgets). The composite burn rate intersection and interaction matrix are novel angles not covered in existing entries.

## See also

- [S-651 · Agentic SLOs: The Six Metrics That Actually Matter](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — the foundation: what the six metrics are and why standard APM misses them
- [S-736 · Agent Error Budgets: Quality That Burns](s736-agent-error-budgets-quality-that-burns.md) — operationalizing SLIs as an error budget with deploy-freeze logic
- [S-1781 · The Segregated Error Budget Stack](s1781-the-segregated-error-budget-stack-when-your-reliability-budget-gets-blown-by-a-policy-outage.md) — why pooling budgets across agent types masks the real burn
- [S-1191 · The Correctness SLO Stack](s1191-the-correctness-slo-stack-when-your-agent-is-accurate-94-percent-of-the-time-and-you-dont-know-it.md) — measuring accuracy at scale without relying on HTTP status
