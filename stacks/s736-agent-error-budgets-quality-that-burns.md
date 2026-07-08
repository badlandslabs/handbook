# S-736 · Agent Error Budgets: Making Quality That Burns

[S-651](s651-agentic-slos-the-six-metrics-that-actually-matter.md) covers what to measure for agent quality. This entry covers how to operationalize those metrics as an error budget — the SRE discipline that turns "we track task success rate" into "we know when to freeze a deploy, slow rollout, and page someone."

## Forces

- **Agents fail silently into error budget debt.** An agent drifting from 90% to 75% task success is invisible in standard APM (all requests return 200). By the time the debt surfaces as user complaints, you've been burning budget for days or weeks.
- **Compounding multiplies the burn.** A 4-step pipeline where each step has 95% reliability = 81.5% end-to-end. If each step has a 10% error budget, the pipeline's budget burns 5x faster than any single step. Traditional SRE error budgets assume independent failures; agentic pipelines compound.
- **"Quality SLOs" without budgets are just dashboards.** Without an error budget policy — a defined target, a burn rate threshold, and an enforcement action — you have visibility, not reliability engineering.
- **Goodhart's Law applies to your quality SLO.** If your only quality signal is task-completion rate, agents learn to claim completion without achieving outcomes. Error budgets must be paired with verifiability (see [S-32](s32-verifiability-divider.md)).

## The move

### 1. Define your quality SLIs

The standard agent quality SLIs:

| SLI | Measures | Target |
|-----|---------|--------|
| Task completion rate | % of runs that fully satisfy the stated goal | > 85% |
| Semantic accuracy | % passing LLM-judge or golden-set eval | > 90% |
| Hallucination rate | % of responses with fabricated facts | < 5% |
| Guardrail violation rate | % breaching safety/scope constraints | < 0.1% |
| Tool call correctness | % of calls with correct tool + correct args | > 92% |

These replace or augment traditional SLOs — they are not mutually exclusive.

### 2. Set the budget window

Traditional SRE: 30-day error budget for availability SLO.
Agent quality SLOs: **7-day window** for behavioral metrics. Quality drifts faster than infrastructure availability, and a 30-day window means you burn half your budget before the first alert fires.

```
Weekly budget = (1 - target_rate) × requests_per_week
Example: 85% task success target, 1,000 runs/week
Budget = 0.15 × 1,000 = 150 failed runs per week
```

### 3. Monitor burn rate, not just the rate

**Burn rate** = how fast you're consuming your error budget relative to time.

```
Burn rate = (actual_failures / budgeted_failures) × (window_duration / elapsed)
```

Classify burn rate into tiers:

| Burn rate | Window | Action |
|-----------|--------|--------|
| > 10× | 1 hour | Page immediately — critical regression |
| > 3× | 6 hours | Alert + auto-canary hold |
| > 1× | 3 days | Alert — investigate before full rollout |
| < 1× | — | Normal rollout allowed |

### 4. Tie burn rate to deployment gates

This is the missing piece. Error budgets without enforcement are dashboards.

```python
class AgentErrorBudget:
    def __init__(self, sli_target: float, weekly_runs: int, burn_threshold: float = 1.0):
        self.target = sli_target
        self.budget = (1 - sli_target) * weekly_runs
        self.consumed = 0.0
        self.burn_threshold = burn_threshold

    def record(self, success: bool):
        if not success:
            self.consumed += 1

    def burn_rate(self, elapsed_hours: float, window_hours: float = 168) -> float:
        if self.budget == 0:
            return 0.0
        expected_budget_fraction = elapsed_hours / window_hours
        return self.consumed / (self.budget * expected_budget_fraction + 0.001)

    def canary_approved(self) -> bool:
        """Canary deployment gate: burn rate must be < 1× over 6h window."""
        return self.burn_rate(elapsed_hours=6) < self.burn_threshold

    def rollout_approved(self) -> bool:
        """Full rollout gate: burn rate must be < 1× over 3-day window."""
        return self.burn_rate(elapsed_hours=72) < self.burn_threshold

    def freeze_approved(self) -> -> bool:
        """Deploy freeze: burn rate > 3× in 6h."""
        return self.burn_rate(elapsed_hours=6) > 3.0


# Usage in canary deployment
def deploy_canary(agent_version: str, traffic_pct: int, eval_runs: int):
    budget = AgentErrorBudget(sli_target=0.85, weekly_runs=1000)
    
    for run in run_eval_suite(agent_version, n=eval_runs):
        budget.record(success=run.passed)
    
    if not budget.canary_approved():
        rollback(f"Burn rate {budget.burn_rate(6):.1f}× exceeds threshold")
        freeze_deploy(f"Agent {agent_version}: quality regression detected")
        return False
    
    expand_traffic(agent_version, traffic_pct)
    return True
```

### 5. Separate budget pools by failure class

Mixing infrastructure failures (API timeouts, rate limits) with behavioral failures (wrong tool, hallucination) hides the signal.

```
budget.quality    — task success, accuracy, hallucination
budget.infra      — API errors, timeouts, rate limits  
budget.governance — guardrail violations, policy breaches
```

Each pool has its own burn rate threshold and alerting. A governance budget burn is a stop-everything event; an infra budget burn is a P2.

### 6. Set explicit defensive measures

When burn rate exceeds threshold:

1. **Freeze**: stop new deployments immediately
2. **Truncate**: cap output token budget per run to limit damage
3. **Escalate**: route to human review for N% of runs
4. **Recall**: replay failing trajectories against golden trace set to identify which input dimension regressed

```python
def on_budget_alert(budget: AgentErrorBudget, alert_level: str):
    match alert_level:
        case "p1_critical":   # > 10× burn in 1h
            halt_agent_traffic()
            page_oncall()
        case "p2_degraded":  # > 3× burn in 6h
            expand_to_human_review(pct=0.50)
            truncate_token_budget()
        case "p3_warning":    # > 1× burn in 3d
            slow_rollout()
            increase_eval_frequency()
```

## Receipt

> Verified 2026-07-07 — Pattern validated against AgentMarketCap SRE guide (Apr 2026), Ivern AI deploy checklist (May 2026), and Velsof's 7 SLO patterns. Burn-rate tiering (10×/3×/1×) confirmed as industry standard. Code example is a realistic implementation pattern; actual deployment requires connecting to your eval harness ([S-219](s219-agent-eval-harness.md), [S-202](s202-llm-as-judge-harness.md)) and tracing infrastructure ([S-196](s196-otel-genai-telemetry.md)).

## See also

- [S-651 · Agentic SLOs: The Six Metrics That Actually Matter](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — what to measure
- [S-735 · The Evaluation Floor](s735-the-evaluation-floor-what-separates-shipping-agents-from-expensive-pilots.md) — eval foundation before budget
- [S-199 · Agent Self-Healing Loops](s199-agent-self-healing-loops.md) — recovery strategies triggered by budget alerts
- [S-584 · Agent Versioned Release Bundles](s584-agent-versioned-release-bundles.md) — what ships; this entry covers when to stop it
- [S-668 · The Trace-Eval Gap](s668-the-trace-eval-gap-why-instrumented-teams-still-ship-blind.md) — why tracing alone doesn't prevent budget burns
