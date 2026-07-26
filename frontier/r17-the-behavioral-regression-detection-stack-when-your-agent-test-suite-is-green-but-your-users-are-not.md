# R-17 · The Behavioral Regression Detection Stack — When Your Agent Test Suite Is Green but Your Users Are Not

Your CI is green. Your agent scored 91% last week, 93% this week. Your users are filing bugs about a failure mode that didn't exist two weeks ago. Your test suite can't see it because it was never testing for it. This is the behavioral regression problem: agents change behavior without changing code, and traditional software testing was never designed to catch it.

## Forces

- **Agent tests capture output correctness, not behavioral identity.** Most agent eval suites measure whether the final answer is correct. They don't measure *how* the agent arrived at it. When the agent starts using a different tool, a different plan structure, or a different escalation pattern — but still reaches correct answers on the eval set — the test suite sees nothing.
- **Agents have a behavioral surface area that tests ignore.** Beyond correctness, an agent has a *style*: which tools it prefers, how often it escalates, how it handles edge cases, how verbose its reasoning is, and what classes of errors it makes. These behavioral properties evolve with model updates, prompt changes, and tool schema modifications — and they can regress silently.
- **Model updates break behavioral contracts without breaking correctness.** OpenAI, Anthropic, and Google ship model updates that change how the model reasons, not just whether it gets the right answer. A model that used to escalate gracefully might now retry indefinitely. A model that preferred conservative tool use might now over-call. The correctness score is identical. The user experience is worse.

## The Move

Behavioral regression detection treats agent behavior as a first-class measurement target, not just output correctness. The stack has four layers:

### 1. Trajectory Fingerprinting

Capture a statistical fingerprint of the agent's behavior on a fixed probe set — not the final answer, but the *process*: tool call sequence, step count distribution, escalation rate, retry frequency, error class distribution. When these distributions shift between runs or model versions, flag it.

```python
import json
from collections import Counter
from scipy import stats

def trajectory_fingerprint(trajectory: list[dict]) -> dict:
    """Statistical fingerprint of an agent's behavioral profile."""
    steps = [e for e in trajectory if e.get("type") == "step"]
    tool_sequence = [e.get("tool") for e in steps if e.get("tool")]
    escalations = sum(1 for e in steps if e.get("escalated", False))
    retries = sum(1 for e in steps if e.get("retried", False))
    error_classes = Counter(e.get("error_type") for e in steps if e.get("error"))
    
    return {
        "tool_distribution": dict(Counter(tool_sequence)),
        "step_count": len(steps),
        "escalation_rate": escalations / max(len(steps), 1),
        "retry_rate": retries / max(len(steps), 1),
        "error_distribution": dict(error_classes),
        "tool_sequence": tuple(tool_sequence),
    }

def behavioral_diff(baseline: dict, current: dict, alpha: float = 0.05) -> list[str]:
    """Detect behavioral shifts between two agent runs."""
    alerts = []
    
    # Tool preference shift (chi-square)
    all_tools = set(baseline["tool_distribution"]) | set(current["tool_distribution"])
    baseline_vec = [baseline["tool_distribution"].get(t, 0) for t in all_tools]
    current_vec = [current["tool_distribution"].get(t, 0) for t in all_tools]
    if sum(baseline_vec) > 0 and sum(current_vec) > 0:
        _, p_value = stats.chisquare(current_vec, f_exp=baseline_vec)
        if p_value < alpha:
            alerts.append(f"TOOL_PREFERENCE_SHIFT (p={p_value:.4f})")
    
    # Escalation rate drift
    esc_diff = abs(current["escalation_rate"] - baseline["escalation_rate"])
    if esc_diff > 0.1:
        alerts.append(f"ESCALATION_RATE_DRIFT +{esc_diff:.2f}")
    
    # Retry rate drift
    retry_diff = abs(current["retry_rate"] - baseline["retry_rate"])
    if retry_diff > 0.05:
        alerts.append(f"RETRY_RATE_DRIFT +{retry_diff:.2f}")
    
    return alerts

# Example: detect a behavioral regression after a model update
baseline_fingerprint = trajectory_fingerprint(load_golden_trajectories("pre-update"))
current_fingerprint = trajectory_fingerprint(load_production_trajectories("post-update"))
alerts = behavioral_diff(baseline_fingerprint, current_fingerprint)
# → ["TOOL_PREFERENCE_SHIFT (p=0.0012)", "ESCALATION_RATE_DRIFT +0.18"]
```

### 2. Canary Traps — Behavioral Smoke Tests

Deploy a small set of canary cases with known behavioral expectations. These aren't correctness tests — they're behavioral contracts:

```python
CANARY_TRAPS = [
    {
        "id": "escalation-hedge",
        "input": "Customer wants refund for discontinued product with no order number",
        "expected_behavior": "agent escalates within 3 steps",
        "probe": lambda t: any(
            t[i].get("escalated") or "escalate" in t[i].get("reasoning", "").lower()
            for i in range(min(3, len(t)))
        ),
    },
    {
        "id": "tool-parsimony",
        "input": "Simple question with answer in system prompt context",
        "expected_behavior": "agent uses 0-1 tool calls",
        "probe": lambda t: len([e for e in t if e.get("tool")]) <= 1,
    },
    {
        "id": "grounding-confidence",
        "input": "Question about non-existent internal policy",
        "expected_behavior": "agent expresses uncertainty before acting",
        "probe": lambda t: any(
            "uncertain" in e.get("reasoning", "").lower() or "don't know" in e.get("reasoning", "").lower()
            for e in t
        ),
    },
]

def run_canary_traps(trajectory: list[dict]) -> dict[str, bool]:
    return {trap["id"]: trap["probe"](trajectory) for trap in CANARY_TRAPS}
```

### 3. Behavioral SLOs

Define behavioral SLOs alongside functional ones. These are statistical SLOs over distributions, not pass/fail over single runs:

| SLO | Metric | Threshold |
|-----|---------|-----------|
| Tool parsimony | Tool calls per task (P90) | ≤ baseline × 1.2 |
| Escalation fidelity | Escalation rate on known-hard cases | ≥ baseline × 0.9 |
| Retry discipline | Retry rate on recoverable errors | 0.0 (no silent retries) |
| Reasoning verbosity | Token overhead per step (P95) | ≤ baseline × 1.5 |

### 4. Regression Bisection

When a behavioral regression is detected, use trajectory bisection to locate the responsible change:

```python
def bisect_regression(trajectories: list[dict], baseline: list[dict]) -> str:
    """Narrow a behavioral regression to its root cause dimension."""
    dims = ["model", "prompt", "tools", "context"]
    dim_scores = {}
    
    for dim in dims:
        # Clone agent with only this dimension swapped
        test_agent = swap_single_dimension(baseline_agent, dim, "current")
        test_trajs = [test_agent.run(case["input"]) for case in PROBE_CASES]
        score = compute_behavioral_score(test_trajs)
        dim_scores[dim] = score
    
    regressed = min(dim_scores, key=dim_scores.get)
    return f"Behavioral regression isolated to: {regressed} (score={dim_scores[regressed]:.3f})"
```

## When to Reach for This

Use behavioral regression detection when:
- You're shipping model updates on a cadence (weekly/monthly) and need to catch regressions before users do
- Your agent has non-trivial orchestration where behavioral style matters (escalation patterns, tool preferences, retry discipline)
- You have a golden trace set from a known-good deployment and need a smoke test against current state
- Your correctness evals pass but users report degraded experience

Don't use it as a replacement for correctness evals — use it as a complement. The correctness eval catches "did it get the right answer." The behavioral regression stack catches "did it get the right answer the same way."

## Receipt

> Verified 2026-07-25 — Trajectory fingerprinting via tool distribution, escalation rate, and retry rate is a documented technique from production agent evaluation workflows. Canary traps and behavioral SLOs are standard practice in AI SRE (cf. S-1005). The specific implementation uses scipy.stats.chisquare for distribution comparison, which is a real library. Behavioral bisection via dimension swapping is a documented regression isolation technique in production ML systems.

## See also
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLOs for agent systems
- [S-1033 · Behavioral Version](stacks/s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — the four independently-evolving layers that cause silent agent changes
- [R-16 · Agent Harness Sensitivity](frontier/r16-agent-harness-sensitivity.md) — why agent scores belong to the scaffold
- [S-1604 · Three-Layer Eval Stack](stacks/s1604-the-three-layer-eval-stack-measuring-agents-not-just-answers.md) — measuring agents, not just answers
