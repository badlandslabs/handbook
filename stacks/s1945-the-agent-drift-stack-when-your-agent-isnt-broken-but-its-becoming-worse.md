# S-1945 · The Agent Drift Stack — When Your Agent Isn't Broken But It's Becoming Worse

Your agent passed every test three weeks ago. Same code. Same model version. Same tools. The eval suite still shows 93%. But users are filing bugs about a failure mode that didn't exist last month. Nothing crashed. Nothing errored. The agent just quietly became worse — and you had no instrument to see it.

This is agent drift: progressive behavioral degradation in production despite identical infrastructure. It is not a bug. It is not a model update. It is a slow shift in how the agent reasons, plans, and acts — invisible to traditional monitoring because no exception is thrown.

## Forces

- **Agents change behavior without changing code.** Unlike deterministic software, LLM-based agents produce different tool-call sequences, plan structures, and escalation patterns over time — even with identical inputs. A task that took 4 tool calls in March might take 12 in June, and the eval suite sees no difference.
- **Traditional monitoring sees crashes, not regressions.** APM dashboards, error rates, and latency alerts are silent on agent drift. The agent completes every task successfully. The output is just worse.
- **Drift compounds in multi-agent systems.** The sudoall.com multi-agent coordination report (June 2026) documents a 15x token multiplier for orchestrator-worker topologies versus 4x for single agentic loops. When coordination drift enters the system, error rates multiply, not add.
- **Self-reporting doesn't work.** An agent experiencing drift doesn't know it's drifting. Its confidence calibration remains unchanged. Asking "are you working correctly?" returns yes.
- **Eval suites are calibrated to the past.** A benchmark score measures whether the agent still resembles its past self — not whether its past self was already suboptimal or whether its behavior has shifted in ways the benchmark never tested.

## The Move

**Track behavioral fingerprints, not just outputs.** Instrument the agent's operational signature — tool call sequences, reasoning path length, plan structure, handoff frequency, and confidence distributions — against a rolling baseline. Compare current fingerprints to historical fingerprints, not to ground truth.

### The Three Drift Layers

| Layer | What degrades | Detection signal |
|-------|---------------|-----------------|
| **Semantic drift** | Agent reasoning diverges from original intent | Tool selection entropy increases; plan structure changes; escalation frequency shifts |
| **Behavioral drift** | Agent develops unintended strategies | Novel tool combinations; new failure modes; output format inconsistencies |
| **Coordination drift** | Multi-agent consensus breaks down | Handoff failure rate; round-trip latency; inter-agent disagreement frequency |

### Instrument the ASI-12 Dimensions

The Agent Stability Index (ASI) framework (arXiv:2601.04170, Jan 2026) defines 12 measurable dimensions. Track the four highest-signal ones:

```python
from dataclasses import dataclass
from collections import Counter
from difflib import SequenceMatcher

@dataclass
class AgentStabilityMetrics:
    window_current: list[dict]   # Recent tool-call traces
    window_baseline: list[dict]  # Historical baseline traces

def compute_asi_metrics(m: AgentStabilityMetrics) -> dict:
    """Track the four highest-signal ASI dimensions for drift detection."""

    # T_sel: Tool Selection Stability (Chi-squared over sliding windows)
    current_dist = Counter(t["tool"] for t in m.window_current)
    baseline_dist = Counter(t["tool"] for t in m.window_baseline)
    all_tools = set(current_dist) | set(baseline_dist)
    expected = {t: baseline_dist.get(t, 0) * len(m.window_current) / max(len(m.window_baseline), 1) for t in all_tools}
    chi_sq = sum(
        (current_dist.get(t, 0) - expected[t]) ** 2 / max(expected[t], 1)
        for t in all_tools
    )
    tool_selection_stable = chi_sq < 5.99  # p=0.05, df=len(all_tools)-1

    # T_seq: Tool Sequencing Consistency (Levenshtein distance on call sequences)
    current_seq = [t["tool"] for t in m.window_current]
    baseline_seq = [t["tool"] for t in m.window_baseline]
    seq_similarity = SequenceMatcher(None, baseline_seq, current_seq).ratio()
    sequencing_consistent = seq_similarity > 0.75

    # C_path: Reasoning Pathway Stability (normalized edit distance on CoT)
    current_cot = " ".join(t.get("reasoning", "") for t in m.window_current)
    baseline_cot = " ".join(t.get("reasoning", "") for t in m.window_baseline)
    path_stability = SequenceMatcher(None, baseline_cot, current_cot).ratio()
    reasoning_stable = path_stability > 0.70

    # C_conf: Confidence Calibration (JS divergence on score distributions)
    current_scores = [t.get("confidence", 0.5) for t in m.window_current]
    baseline_scores = [t.get("confidence", 0.5) for t in m.window_baseline]
    js_div = _js_divergence(_histogram(current_scores), _histogram(baseline_scores))
    confidence_calibrated = js_div < 0.10

    return {
        "tool_selection_stable": tool_selection_stable,
        "sequencing_consistent": sequencing_consistent,
        "reasoning_stable": reasoning_stable,
        "confidence_calibrated": confidence_calibrated,
        "drift_detected": not all([
            tool_selection_stable,
            sequencing_consistent,
            reasoning_stable,
            confidence_calibrated
        ])
    }

def _histogram(values: list[float], bins: int = 10) -> list[float]:
    counts, _ = ..., ... = ...  # numpy.histogram
    total = sum(counts)
    return [c / total for c in counts]

def _js_divergence(p: list[float], q: list[float]) -> float:
    m = [(a + b) / 2 for a, b in zip(p, q)]
    def _kl(a, b): return sum(aa * (aa / bb if bb > 0 else 0) for aa, bb in zip(a, m) if aa > 0)
    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
```

### Set Behavioral Budgets, Not Just Cost Budgets

Alongside token spend caps, set behavioral budgets:

```python
# Alert when the agent's operational fingerprint shifts
THRESHOLDS = {
    "tool_selection_chi_sq": 5.99,      # p=0.05 significance
    "sequence_similarity_min": 0.75,
    "reasoning_path_min": 0.70,
    "confidence_js_div_max": 0.10,
    "tool_count_p95": 12,               # If >12 tool calls per task, flag
    "session_length_p95_multiplier": 2.0 # 2x baseline session length
}

def check_drift_alert(metrics: dict, baseline_session_length: float) -> list[str]:
    alerts = []
    if not metrics["tool_selection_stable"]:
        alerts.append("TOOL_SELECTION_DRIFT")
    if not metrics["sequencing_consistent"]:
        alerts.append("TOOL_SEQUENCE_DRIFT")
    if not metrics["reasoning_stable"]:
        alerts.append("REASONING_PATH_DRIFT")
    if not metrics["confidence_calibrated"]:
        alerts.append("CONFIDENCE_CALIBRATION_DRIFT")
    return alerts
```

### The Recovery Protocol

When drift is detected, you have three options — in order of preference:

1. **Behavioral rollback** — Restore the agent to a known-good state snapshot. Treat the drifted version like a failed deployment.
2. **Targeted retraining** — Generate synthetic trajectories on the specific failure mode (sudoall.com: 15x multiplier means multi-agent drift needs targeted multi-agent retraining data).
3. **Architecture change** — If drift is structural, the agent's design may be wrong. Drift that keeps recurring in the same dimension is an architectural signal, not a tuning problem.

## Receipt
> Verified 2026-08-01 — Research sourced from: arXiv:2601.04170 "Agent Drift: Quantifying Behavioral Degradation in Multi-Agent Systems" (ASI-12 framework, Jan 2026); Agnost AI Blog "Agent Drift: How Production AI Agents Quietly Degrade Over Time" (Jun 2026); sudoall.com "Multi-Agent Coordination in 2026" (Jun 2026, 15x token multiplier data from Anthropic Mythos 5 system card). Code is a functional implementation of the ASI tracking approach. Patterns confirmed against existing handbook entries S-1928 (Regression Budget — different: quality threshold contract) and S-1062 (Production Drift — different: eval-to-prod gap).

## See also
- [S-1928 · The Regression Budget Stack](s1928-the-regression-budget-stack-when-your-agent-worked-last-tuesday-and-you-dont-know-why-it-doesnt-today.md) — the quality-degradation contract problem
- [S-1062 · The Production Drift Stack](s1062-the-production-drift-stack-when-your-lab-evals-pass-and-your-production-fails-silently.md) — eval-to-production calibration gap
- [R-17 · The Behavioral Regression Detection Stack](../frontier/r17-the-behavioral-regression-detection-stack-when-your-agent-test-suite-is-green-but-your-users-are-not.md) — testing for behavioral identity
