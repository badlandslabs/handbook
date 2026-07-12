# S-940 · The Agent Drift Recovery Stack — When Your Agent Breaks But Doesn't Know It

Your eval dashboard shows green. Your production quality is falling. AgentStatus tracked 6,200+ production agents over 30 days — 88% experienced measurable behavioral drift. When agents break, they don't degrade gracefully. They collapse. The eval caught the pre-drift state. The recovery system doesn't exist.

Detection without recovery is monitoring theater. S-932 covers the eval loop that catches drift. S-934 covers rubric coupling. This entry covers what comes after detection: the architectural stack that moves a drifting agent from collapse to recovery — without human intervention for known failure modes, with a human-in-the-loop gate for novel ones.

## Forces

- **Agents collapse, they don't degrade.** A traditional service degrades: latency increases, error rates rise, you see signals before failure. An agent drifts silently: it answers confidently, returns valid JSON, gets 200s — and is increasingly wrong. There is no gradual failure signal, only a cliff.
- **Recovery is harder than detection.** You can run eval on a schedule. Rolling back an agent that has written bad data, sent incorrect emails, or merged bad code is not a technical problem — it is a state-reconstruction problem. Most teams don't have a recovery architecture, only a detection dashboard.
- **Manual recovery is too slow for production.** The average time-to-detect for agent behavioral drift is 10–14 days (AgentStatus, 2026). Manual incident response adds another 2–5 days. In that window, a drifting agent compounds damage: bad outputs become training data for downstream agents, corrupted records pile up, user trust erodes.
- **Auto-recovery risks over-correction.** An agent that rolls back every time quality dips 2% is unusable. The recovery trigger must distinguish noise from signal, and known failure modes from novel ones that need human review.
- **Recovery state is stateful.** You need to know not just *that* the agent drifted, but *when* the drift started, *what* it affected, and *how far back* to roll. This requires trajectory snapshots, not just outcome logs.

## The Move

The drift recovery stack operates in four layers, each with a distinct trigger and action:

### Layer 1 — Drift Detection Gate (automated, runs continuously)
- Roll a pinned eval set against the current agent state on a schedule (hourly or per-N-turns).
- Compare trajectory-level metrics (not just outcome scores) against the golden baseline: tool selection rate, reasoning depth, refusal rate, output shape variance.
- Trigger: any single metric deviates >2σ from baseline, *or* any two metrics deviate >1.5σ simultaneously.
- Output: a drift event with `drift_type` (semantic / behavioral / coordination — see S-932), `confidence` score, and `affected_trajectory_window`.

```python
# Drift detection: trajectory-level comparison
def detect_drift(agent_state: Trajectory, baseline: EvalSet) -> DriftEvent | None:
    metrics = {
        "tool_selection_rate": compute_tool_selection(agent_state),
        "avg_reasoning_depth": compute_reasoning_depth(agent_state),
        "refusal_rate": compute_refusal_rate(agent_state),
        "output_shape_variance": compute_output_variance(agent_state),
    }
    deviations = {
        k: abs(v - baseline.means[k]) / baseline.stds[k]
        for k in metrics
    }
    # Trigger: single >2σ or two >1.5σ
    if any(d > 2.0 for d in deviations.values()):
        worst = max(deviations, key=deviations.get)
        return DriftEvent(type="behavioral", confidence=deviations[worst], metrics=deviations)
    if sum(1 for d in deviations.values() if d > 1.5) >= 2:
        return DriftEvent(type="semantic", confidence=0.7, metrics=deviations)
    return None
```

### Layer 2 — Recovery Mode Classification (automated)
Classify the drift event into a recovery strategy. Not all drift requires the same response.

| Drift Type | Likely Cause | Recovery Strategy |
|---|---|---|
| **Behavioral** (tool selection shift) | Model update, prompt drift | Prompt rollback to last known-good snapshot |
| **Semantic** (output intent shift) | Eval rubric obsolescence, data distribution shift | Rebuild eval rubric + re-score |
| **Coordination** (multi-agent desync) | Shared-state corruption, protocol version mismatch | Inter-agent state reconciliation |
| **Unknown** (no matching pattern) | Novel failure mode | Human review gate |

```python
def classify_recovery(event: DriftEvent, known_patterns: list[DriftPattern]) -> RecoveryStrategy:
    for pattern in known_patterns:
        if pattern.matches(event):
            return RecoveryStrategy(
                type=pattern.strategy,
                confidence=pattern.confidence,
                auto_approve=pattern.confidence > 0.85
            )
    # Novel — requires human
    return RecoveryStrategy(type="human_review", confidence=0.0, auto_approve=False)
```

### Layer 3 — Recovery Execution (automated for known patterns, gated for novel)
For auto-approved recoveries (confidence > 0.85, known drift type):

1. **Snapshot the current state** — save the drifting trajectory window before any changes.
2. **Apply the recovery action** — rollback prompt, reload tool schemas, reset shared state.
3. **Re-run the failing eval** — confirm the recovery resolved the specific metric that triggered the drift.
4. **Confirm with a canary** — run a single production request through the recovered agent before resuming full traffic.

```python
async def execute_recovery(strategy: RecoveryStrategy, event: DriftEvent) -> RecoveryResult:
    snapshot = await snapshot_trajectory(event.affected_window)
    if not strategy.auto_approve:
        return RecoveryResult(status="pending_human_review", snapshot=snapshot, event=event)
    
    # Rollback
    await apply_rollback(strategy)
    
    # Verify
    eval_pass = await run_targeted_eval(event)
    if eval_pass:
        canary = await run_canary_request()
        if canary.success:
            return RecoveryResult(status="recovered", snapshot=snapshot)
    
    # Recovery didn't take — escalate
    return RecoveryResult(status="escalated", snapshot=snapshot, event=event)
```

### Layer 4 — Post-Recovery Audit (automated, always)
Log the full recovery sequence: drift event → classification → action → verification → canary result. This creates the feedback loop that improves future classification confidence. Without this, the system repeats the same recovery sequence without learning.

## Receipt
> Verified 2026-07-11 — Architecture pattern synthesized from: AgentStatus Drift Report (April 2026, 6,200+ agents, 88% drifted in 30 days); S-932 continuous eval loop; S-934 eval rubric coupling; S-220 behavioral regression suite. The 4-layer recovery taxonomy (detect → classify → execute → audit) is the missing architectural complement to the detection and measurement entries. Empirical 88% drift rate validates urgency. The collapse-vs-degrade distinction is confirmed by AgentStatus: "when agents break, they do not degrade gracefully — they collapse."

## See also
- [S-932 · The Continuous Eval Loop Stack](../stacks/s932-the-continuous-eval-loop-stack-when-your-agent-changes-but-your-tests-dont.md) — detection layer; this entry is the recovery complement
- [S-934 · The Eval Rubric Coupling Problem](../stacks/s934-the-eval-rubric-coupling-problem-when-your-grading-rubric-ages-faster-than-your-agent.md) — why measurement itself drifts and compounds the recovery problem
- [S-220 · Agentic Behavioral Regression Suite](../stacks/s220-agentic-behavioral-regression-suite.md) — the CI-equivalent layer that triggers the detection gate
