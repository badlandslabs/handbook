# S-2756 · The Silent Trajectory Failure Stack — When Your Agent Completes but the Answer Is Wrong

Your agent ran for 47 steps, made 12 tool calls, returned a confident answer in 3.2 seconds — and produced a result that was subtly, dangerously wrong. No exception. No alert. No error code. The trace shows every step succeeded individually. The final output failed silently.

This is the silent trajectory failure problem: agents that complete without signaling failure but produce wrong, incomplete, or looping results. It's the dominant failure mode in production agentic systems, and it's nearly invisible under standard observability.

## Forces

- **Success signal ≠ correctness signal.** Agents return HTTP 200 and "here's your answer." Traditional APM tools see a healthy completion. The trajectory that produced the answer is what actually needs auditing.
- **Failures are trajectory-level, not step-level.** Drift, cycles, and missing details don't surface as exceptions at any individual step. The failure is an emergent property of the entire execution path — no single tool call or LLM call fails, yet the output is wrong.
- **The correction-attribution gap.** Even when a retry or self-reflection loop recovers the correct answer, the system cannot identify which original step was decisive. Recovery masks the cause. Teams mark the incident "resolved" with no actionable fix.
- **Non-determinism hides regressions.** The same input can produce different trajectories across runs. A regression that causes silent failure on 8% of queries is invisible unless you're sampling trajectories, not just final outputs.
- **Scale amplifies silently.** At 1,000 daily runs, an 8% silent failure rate means 80 wrong answers per day with no automated detection. At 100,000 runs, it's 8,000.

## The Move

**Instrument trajectories, not just completions.** Capture the full execution trace — every tool call, every LLM reasoning step, every intermediate output — as a first-class artifact. Evaluate trajectories for failure patterns, not just final outputs for correctness.

### The Five Silent Failure Regimes

1. **Drift** — Agent diverges from the intended path, selecting tools or sub-agents irrelevant to the query. The output is on-topic but contextually misaligned.
2. **Cycles** — Agent re-plans repeatedly, re-invoking the same tools or agents. No error thrown; the agent appears to be working. Tokens are consumed with no progress.
3. **Missing details** — Agent returns a well-formed answer that omits critical requested information. The schema is correct, the content is incomplete.
4. **Tool silent failures** — External tools return unexpected results, hit rate limits, or produce schema drift. The agent propagates garbage without detecting it.
5. **Context propagation failures** — Dependent sub-agents or tools receive stale, truncated, or wrong context. Downstream steps build on broken assumptions.

### Detection Patterns

**Metamorphic relations** — Define correctness via end-state equivalence rather than text similarity. "If I ask the same question with different phrasings, do I get equivalent answers?" is more robust than string matching.

**Trajectory invariants** — Encode structural properties that must hold across all successful runs:
- Every tool call in the trajectory must have been reachable from the root intent
- Context propagation must satisfy a call-graph ordering constraint
- No agent may appear in a wait cycle without a timeout escalation

**Anomaly scoring** — Score trajectories against a behavioral baseline:
- Step count deviation from historical mean
- Tool call frequency distribution vs. expected pattern
- Retrieval result freshness relative to task type

**Chaos injection** — Test fault tolerance deliberately:
- Inject timeouts, rate limits, and partial responses (the `lambda` dimension of ReliabilityBench)
- Verify the agent detects and handles failures, not just recovers

### The Attribution Fix

When a trajectory fails, the answer isn't "retry until it works." The fix is step-level failure attribution:

```python
# Trajectory failure detection with step-level attribution
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TrajectoryStep:
    step_id: int
    agent_id: str
    tool: str
    input_: dict
    output: dict
    duration_ms: float
    error: Optional[str] = None

@dataclass
class DriftEvent:
    step_id: int
    drift_type: str          # 'intent', 'tool', 'context'
    confidence: float        # 0.0–1.0
    deviation_description: str

def detect_drift(trajectory: list[TrajectoryStep], intent: str) -> list[DriftEvent]:
    """
    Metamorphic-style drift detection:
    Compare each step against the declared intent graph.
    """
    events = []
    for step in trajectory:
        # Step is "drifting" if its tool is not reachable from the intent plan
        reachable_tools = intent_graph_reachable_tools(intent, max_depth=3)
        if step.tool not in reachable_tools:
            events.append(DriftEvent(
                step_id=step.step_id,
                drift_type='intent',
                confidence=0.87,  # calibrated against labeled drift dataset
                deviation_description=f"Tool '{step.tool}' not in reachable set for '{intent}'"
            ))
    return events

def detect_cycles(trajectory: list[TrajectoryStep]) -> list[dict]:
    """
    Cycle detection via agent-step fingerprinting.
    """
    seen: dict[tuple, int] = {}
    cycles = []
    for step in trajectory:
        fingerprint = (step.agent_id, step.tool, _hash(step.input_))
        if fingerprint in seen:
            cycles.append({
                "cycle_start": seen[fingerprint],
                "cycle_end": step.step_id,
                "length": step.step_id - seen[fingerprint],
                "fingerprint": fingerprint
            })
        seen[fingerprint] = step.step_id
    return cycles

def attribution_report(
    trajectory: list[TrajectoryStep],
    intent: str,
    expected_output_schema: dict
) -> dict:
    """
    Full silent-failure attribution across drift, cycles, missing details, tool failures.
    """
    drift_events = detect_drift(trajectory, intent)
    cycle_events = detect_cycles(trajectory)

    # Check each tool call for silent failures
    tool_failures = []
    for step in trajectory:
        if step.error or _is_silent_tool_failure(step):
            tool_failures.append({"step_id": step.step_id, "tool": step.tool})

    # Check final output against schema completeness
    output = trajectory[-1].output if trajectory else {}
    missing_fields = [
        k for k in expected_output_schema.keys()
        if k not in output or output[k] is None
    ]

    # Find root-cause: the earliest anomalous step
    all_anomalies = (
        [(e.step_id, f"drift: {e.drift_type}") for e in drift_events] +
        [(c["cycle_start"], "cycle") for c in cycle_events] +
        [(f["step_id"], f"tool_failure") for f in tool_failures] +
        [(len(trajectory) - 1, f"missing_fields: {missing_fields}")]
    )
    root_cause_step = min(all_anomalies, key=lambda x: x[0]) if all_anomalies else None

    return {
        "trajectory_length": len(trajectory),
        "drift_events": drift_events,
        "cycles": cycle_events,
        "tool_silent_failures": tool_failures,
        "missing_output_fields": missing_fields,
        "root_cause_step": root_cause_step,
        "failing_step": root_cause_step[0] if root_cause_step else None,
        "recommendation": _fix_recommendation(root_cause_step, drift_events, cycle_events)
    }

def _is_silent_tool_failure(step: TrajectoryStep) -> bool:
    """Detect tool failures that returned 200 OK but produced garbage."""
    if step.error:
        return False  # explicit error — not silent
    # Heuristic: empty output on a non-trivial tool call is suspicious
    if not step.output or (isinstance(step.output, dict) and not step.output.get("_data")):
        return True
    # Rate limit or partial response patterns
    if step.output.get("_truncated") or step.output.get("_rate_limited"):
        return True
    return False
```

### Monitoring Layout

| Signal | What it detects | How to capture |
|--------|-----------------|----------------|
| Drift rate | % of trajectories with intent deviation | Intent-graph comparison per step |
| Cycle frequency | % of trajectories with re-planning loops | Step fingerprinting |
| Tool silent failure rate | % of tool calls returning garbage | Output schema validation per tool |
| Missing detail rate | % of outputs missing required fields | Final output schema check |
| Step-level latency | Which step in the trajectory is slow | Per-step duration tracking |

## Receipt

> Verified 2026-08-16 — arXiv 2511.04032 (ACM ICPE 2026): "Detecting Silent Failures in Multi-Agentic AI Trajectories" defines the five-regime taxonomy (drift, cycles, missing details, tool failures, context propagation failures) validated against a curated multi-agent trajectory dataset. ICML 2026 FAGEN Workshop (ICLR virtual): "Tiny Silent Hallucinations in Agentic AI" quantifies the hidden failure mode problem. ReliabilityBench (arXiv 2601.06112): introduces the reliability surface R(k, ε, λ) for consistency, robustness, and fault tolerance across agent trajectories.

## See also

- [S-2747 · The Agent Trajectory Eval Stack](stacks/s2747-the-agent-trajectory-eval-stack-when-your-agent-succeeds-but-you-cant-prove-it.md) — trajectory-level evaluation as a proof of correctness
- [S-2748 · The Agent Failure Taxonomy Stack](stacks/s2748-the-agent-failure-taxonomy-stack-when-your-agent-errors-but-nobody-planned-the-recovery.md) — recoverable vs. unrecoverable failure classification
- [S-2753 · The Eval-or-Bust Stack](stacks/s2753-the-eval-or-bust-stack-when-you-cant-tell-if-your-agent-is-actually-working.md) — evaluation approaches for production agents
