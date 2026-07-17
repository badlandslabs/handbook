# S-1231 · The Staged Rollout Quality Oracle

[Your support agent's new prompt passes CI. Your eval suite passes. You route 5% of traffic to it — and two weeks later discover it has been routing complex tickets to the wrong department at twice the rate of the old version. Error rates were unchanged. Latency was fine. The agent "worked." But it worked worse, invisibly, at scale.]

## Forces

- **Traditional canary metrics are blind to agent quality regression.** Error rate, HTTP status codes, and latency all look normal when an agent produces a plausible but contextually wrong answer. The agent completed the task — it just completed it incorrectly.
- **Eval suites are snapshots, not surveillance.** A CI gate tests against a fixed golden dataset before deploy. It cannot detect regressions on the real traffic distribution, edge cases that never made it into the eval set, or behavioral drift over time.
- **Rollback decisions require evidence you don't have mid-rollout.** When should you promote from 5% to 20%? When do you kill the rollout? Traditional canary answers these with numeric thresholds on numeric metrics. Agent quality is a judgment call — and you don't have a judge watching.
- **The compounding cost of delay.** Every hour at a degraded quality level means more wrong outcomes, more user frustration, and more support tickets. But rolling forward without evidence is also dangerous. You need a system that generates evidence fast enough to matter.

## The Move

The Staged Rollout Quality Oracle is a three-layer system: **behavioral signals → quality gate → promotion policy**.

### Layer 1 — Emit Behavioral Signals (Not Just Metrics)

Instrument the agent to emit structured quality signals alongside every response. These are not logs — they are the inputs to your quality gate:

```python
@dataclass
class QualitySignal:
    task_type: str           # "classification", "retrieval", "reasoning", etc.
    tool_call_count: int
    tool_call_errors: int
    context_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    task_completed: bool     # did the agent report task done?
    confidence: float        # model-reported confidence (calibrated separately)
    downstream_outcome: Optional[str]  # e.g., "user_accepted", "escalated", "no_response"

    # LLM-judged quality (sampled, not every call)
    judge_score: Optional[float]  # 0-1, scored by stronger model
    judge_reasons: Optional[str]
```

Emit these on every turn. Store in a time-series DB (InfluxDB, ClickHouse, or even just a structured log table). The downstream outcome field is the most valuable — it is the only ground-truth quality signal that doesn't require a second model call.

### Layer 2 — The Quality Gate

The gate evaluates at each stage boundary (5% → 20% → 100%). It requires:

1. **Minimum traffic exposure**: At least N requests per stage before evaluation (e.g., 1,000 or 24h of traffic at that percentage, whichever is first). Prevents premature promotion on a lucky sample.
2. **Downstream outcome comparison**: Side-by-side comparison of `downstream_outcome` distribution between old and new versions. Require: `new.no_escape_rate >= old.no_escape_rate - epsilon`.
3. **LLM judge spot-check**: Sample 5% of responses from both versions, score with a stronger model (e.g., GPT-4.5 scoring Claude 3.5 outputs). Require: new mean judge score >= old mean - delta.
4. **Task completion rate**: `task_completed` must not drop by more than 2%.
5. **Cost-per-task sanity**: If cost-per-successful-outcome increases by >20%, flag for review even if quality metrics pass.

```python
def quality_gate(candidate: str, baseline: str, stage: int) -> GateResult:
    """Returns (pass, details) for stage promotion."""
    traffic_min = STAGE_TRAFFIC_MINIMUM[stage]  # e.g., 1000, 5000, 20000
    if exposed_count(candidate) < traffic_min:
        return GateResult.HOLD  # not enough traffic yet

    # Downstream outcome comparison (primary signal)
    outcomes_new = downstream_outcomes(candidate, window="24h")
    outcomes_old = downstream_outcomes(baseline, window="24h")
    escape_rate_delta = outcomes_new["escalated"] / len(outcomes_new) \
                      - outcomes_old["escalated"] / len(outcomes_old)
    if escape_rate_delta > ESCALATION_TOLERANCE[stage]:
        return GateResult.REJECT  # more escalations → rollback

    # Judge spot-check (secondary signal)
    sample_size = min(100, int(exposed_count(candidate) * 0.05))
    if exposed_count(candidate) > 500:
        judge_comparison = llm_judge_compare(
            sample(candidate, sample_size),
            sample(baseline, sample_size)
        )
        if judge_comparison.new_mean < judge_comparison.old_mean - JUDGE_DELTA[stage]:
            return GateResult.REJECT

    return GateResult.PASS

STAGE_TRAFFIC_MINIMUM = {1: 1000, 2: 5000, 3: 20000}
ESCALATION_TOLERANCE = {1: 0.02, 2: 0.01, 3: 0.005}
JUDGE_DELTA = {1: 0.05, 2: 0.03, 3: 0.02}
```

### Layer 3 — Promotion Policy with Hard Stops

Define the stage percentages and the policy that governs them:

```python
ROLLBACK_TRIGGERS = {
    "escalation_rate_delta": 0.03,   # hard stop: rollback immediately
    "judge_score_delta": 0.10,       # hard stop: rollback immediately
    "cost_per_outcome_delta": 0.50,  # hard stop: rollback + alert
    "tool_error_rate": 0.15,         # hard stop: system instability
}
```

The key insight: **the gate must be deterministic enough to block promotion but sensitive enough to catch regressions before they compound**. At 5% traffic, a 2% degradation in escalation rate means ~200 wrong outcomes per 10,000 requests. At 100%, that is 2,000. The gate catches it at 5%.

### The Shadow Mode Option

For high-stakes rollouts, run shadow mode before staged rollout: both versions process every request, but only the baseline's response is returned to users. Compare quality signals from both in parallel. Shadow mode is expensive (2x inference cost) but eliminates user exposure during the evaluation window.

## Receipt

> Verified 2026-07-17 — Synthesized from: Agentbrisk (2026) on canary deployment quality signals for AI agents, AltairaLabs (Apr 2026) on progressive rollout patterns with behavioral gates, Zylos Research (2026) on agent evaluation frameworks, and empirical patterns from production canary incidents reported in HN/LangChain community. Core structure: behavioral signal emission → downstream outcome tracking → tiered quality gate → staged promotion with hard rollback triggers. The staged approach (5% → 20% → 100%) reduces wrong-outcome exposure by ~95% vs. direct-to-100% rollout. Shadow mode trades 2x cost for zero user exposure during evaluation.

## See also

- [S-787 · Invisible Model Drift: The Silent Provider Update Pattern](s787-invisible-model-drift-the-silent-provider-update-pattern.md) — why behavioral monitoring matters even for unchanged deployments
- [F-41 · Feature Flags for AI Rollout](forward-deployed/f41-feature-flags-for-ai.md) — the traffic-splitting infrastructure this quality gate runs on
- [S-914 · The Observability Trap](s914-the-observability-trap-stack-when-your-dashboard-watches-your-agent-burn-47k.md) — why observability without interception is just expensive logging
- [S-655 · Silent Failure Detection for Production Agents](s655-silent-failure-detection-for-production-agents.md) — downstream outcome tracking patterns
