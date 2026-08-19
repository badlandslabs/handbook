# S-2828 · The Budget Separation Stack — When Your Error Budget Is Useless Because It's Measuring the Wrong Numerator

[Your agent's error budget just burned through 80% in 24 hours. Your on-call engineer pages the team. The deployment freeze kicks in. Except — the burn wasn't a reliability problem. It was a policy enforcement tightening: 14% of requests got denied because the guardrail model was updated. Your reliability SLI was fine. Your governance SLI spiked. And you have no way to tell the difference, because both live in the same error budget.]

## Forces

- **One budget, three failure regimes.** Policy denials, infrastructure reliability, and latency regressions have different root causes, different remediation owners, and different urgency. Conflating them into a single error budget produces a number that tells you something broke but not what, not why, and not what to do.
- **Governance burn and reliability burn have opposite remedies.** When governance budget burns fast, you tune policies, adjust thresholds, or roll back a guardrail update. When reliability budget burns fast, you add capacity, fix timeouts, or rollback a code deploy. These are different teams, different tools, and different SLA timelines. A shared budget forces a single decision-maker to make two decisions with one lever.
- **Naive burn-rate alerts page on noise.** A policy denial storm (12% of requests failing a new content filter) will burn a naive error budget at exactly the same rate as a database outage. Without separate windows and thresholds, you either over-alert or miss the real incident.
- **Budget consumption rate differs by regime.** Infrastructure failures tend to spike and resolve. Governance failures tend to ramp slowly from a config change and compound. Using the same burn-rate thresholds for both produces systematic blind spots in one direction or the other.

## The move

### 1. Decompose into three separate budgets

Split your agent's error budget into three independent budgets, each with its own burn-rate policy:

| Budget | What burns it | Burn-rate window | Who responds |
|--------|--------------|-------------------|---------------|
| **Reliability** | Task failures, timeouts, API errors, cascade crashes | 1h fast burn / 6h sustained burn | Platform / SRE |
| **Governance** | Policy denials, guardrail triggers, hallucination flags, unsafe action blocks | 6h ramp burn / 24h sustained burn | Safety / Policy team |
| **Latency** | P99 response time exceeding threshold | 1h fast burn | Performance / infra |

The key insight: governance failures degrade *correctly* — the agent correctly refused an unsafe action. This is not the same failure mode as a crash, and mixing it into the same budget means your reliability signal is always noisy.

### 2. Set regime-specific burn-rate thresholds

Classical SRE uses a single burn-rate: consume the 30-day budget in 1 hour (×1h) or 6 hours (×6h). Agentic systems need three regimes:

```python
# microsoft/agent-governance-toolkit — budget decomposition example
# (reference: github.com/vishalm/ai-agent-governance-toolkit)

from agent_sre import SLOEngine, ErrorBudget, BurnRateAlert
from agent_sre.slo.indicators import (
    TaskCompletionRate,
    PolicyComplianceRate,
    P99Latency,
)

engine = SLOEngine(
    name="customer-service-agent",
    indicators=[
        # RELIABILITY BUDGET — 30-day budget, fast burn on infra failures
        TaskCompletionRate(target=0.95, window="24h"),
        # GOVERANCE BUDGET — tighter target, different burn window
        PolicyComplianceRate(target=0.99, window="24h"),   # 1% governance budget
        # LATENCY BUDGET — separate entirely
        P99Latency(target_ms=5000, window="24h"),
    ],
    error_budgets=[
        ErrorBudget(total=0.05, burn_rate_alert=1.5, burn_rate_critical=3.0),
        ErrorBudget(total=0.01, burn_rate_alert=1.0, burn_rate_critical=2.0),  # tighter for governance
        ErrorBudget(total=0.05, burn_rate_alert=1.5, burn_rate_critical=3.0),
    ],
)

# Fast burn: 1 failure/min = ~3h to exhaust reliability budget
engine.add_alert(
    BurnRateAlert(
        budget="reliability",
        window="1h",
        threshold=1.0,    # page immediately on fast burn
        severity="critical",
        runbook="runbooks/agent-reliability-fast-burn.md",
    )
)

# Slow burn: gradual policy drift — page at 6h, ticket at 24h
engine.add_alert(
    BurnRateAlert(
        budget="governance",
        window="6h",
        threshold=1.0,    # sustained burn, not a spike
        severity="warning",
        runbook="runbooks/agent-governance-drift.md",
    )
)
```

### 3. Map SLIs to your scheduler's actual emissions

Don't define SLIs that require custom instrumentation on day one. Start with what your agent framework already emits:

```
# What most agent schedulers already emit
struct AgentEvent {
    run_id: string,           // trace propagation
    component: string,         // which agent/step
    policy_decision: string,  // "allowed" | "denied" | "escalated"
    outcome: string,          // "success" | "failure" | "timeout"
    latency_ms: u64,
    tokens_used: u64,
    error_class: string,      // normalized error taxonomy
}
```

From these four fields, you derive all three SLIs. PolicyComplianceRate counts `policy_decision != "allowed"`. TaskCompletionRate counts `outcome != "success"`. P99Latency reads `latency_ms`.

### 4. Budget policy: explicit release gates per budget

Once each budget has its own threshold, the release policy writes itself:

```
RELIABILITY budget < 20%  →  freeze deploys, page SRE
RELIABILITY budget < 5%  →  escalate to incident commander
GOVERNANCE budget < 20%  →  page safety team, review recent policy changes
GOVERNANCE budget < 5%   →  freeze guardrail updates, full policy review
LATENCY budget < 20%     →  ticket to performance team
```

Separating budgets means a governance burn (policy tightening) never triggers a deploy freeze. And a reliability incident (database outage) never pages the safety team at 3am.

## Receipt

> Verified 2026-08-18 — Source distillation from: Cordum "AI Agent SLOs and Error Budgets: Production Policy Playbook" (Apr 2026) — budget separation principle, multi-window burn-rate; AgentMarketCap "Agent Reliability Engineering 2026" (Apr 2026) — 1.67B token Claude Code loop case, agents that fail successfully; Microsoft agent-governance-toolkit (github.com/vishalm/ai-agent-governance-toolkit, Jul 2026) — ErrorBudget class, burn_rate_alert, burn_rate_critical parameters, PolicyComplianceRate indicator. Key citations: Cordum metric mapping section (budget decomposition into separate reliability/governance/latency tracks), AgentMarketCap "Most teams burn error budget on the wrong numerator" framing, Microsoft SLO engine reference implementation.

## See also

- [S-651 · Agentic SLOs: The Six Metrics That Actually Matter](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — defines the six SLIs; this entry decomposes them into independent budgets
- [S-1005 · AI SRE: The Reliability Discipline Your Agent Team Doesn't Have Yet](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — error-budget discipline; this entry applies it to the multi-budget case
- [S-1960 · The Agentic Skills Top 10: When Your Agent Installs Brittle Code from a Stranger](S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — governance failures in practice; budget separation determines whether governance incidents get the right response
