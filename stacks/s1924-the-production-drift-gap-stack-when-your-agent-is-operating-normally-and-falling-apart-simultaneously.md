# S-1924 · The Production Drift Gap Stack — When Your Agent Is Operating Normally and Falling Apart Simultaneously

Your monitoring dashboard shows green. Latency is nominal. Token counts are within budget. You haven't touched the agent in three weeks. Then a customer reports the agent booked a conference room that doesn't exist, gave contradictory legal advice, and escalated a billing dispute by apologizing for something it did three interactions ago. The agent never alerted. The agent never degraded. The agent drifted — and traditional observability cannot see it happen.

This is the production drift gap: the invisible period between when an agent starts behaving differently and when anyone notices. Across 6,200+ production agents monitored over 30 days (AgentStatus / Carmel Labs, April 2026), 88% experienced measurable behavioral changes within a single month. When correctness dropped, it didn't degrade gracefully — it collapsed, often by 20+ points within days. Recovery was slow and frequently didn't happen at all.

The gap exists because the signals most teams monitor — latency, token count, error rate, uptime — are orthogonal to correctness. A drifted agent runs faster and cheaper than a broken one. You need different signals, a different architecture, and a different mindset.

## Forces

- **Agents drift silently in three distinct ways.** Input drift (the documents and queries change distribution), model drift (the provider updates the underlying model without a version bump), and behavioral drift (the agent's decision strategy shifts even with identical inputs). Standard APM dashboards surface none of these — they measure infrastructure health, not decision quality.
- **When agents break, they don't slow down — they accelerate.** A drifted agent often produces faster, cheaper outputs because it found a simpler (but wrong) reasoning path. Traditional SLOs on latency and error rate will not catch it. The agent looks healthy because it's producing outputs; it looks cheap because it's producing fewer of them.
- **Recovery is the hardest part.** Drift doesn't auto-correct. When correctness collapses, teams scramble to identify the trigger — was it a model update? A prompt regression? An upstream data change? Without structured replay infrastructure, the answer is unknowable after the fact.
- **Eval infrastructure and monitoring infrastructure are separate systems with a gap between them.** Most teams have offline eval for pre-deploy gates and basic APM for runtime monitoring. Almost nobody has the bridge between them that catches regressions as they happen. The tools exist (Langfuse, Phoenix, Weave, Grafana Agent GenAI), but the practice of continuous online eval against held-out traffic is rare.
- **The held-out regression set is the key artifact most teams don't build.** The same golden dataset that gates pre-deploy should run continuously against production traffic. When the pass rate on the held-out set drops below threshold, that's the alert. Without it, you're waiting for customers to notice.

## The move

### 1. Build the held-out regression set

Curate a set of 50–200 production inputs with known-good outputs, spanning the critical paths (correctness, safety, tone, escalation). This is your regression oracle. It should be:
- Representative of current production traffic, not the day-of-launch test suite
- Labeled with expected behavior, not just correct answers
- Refreshed quarterly as your agent's scope evolves

```python
import json
from collections import defaultdict

class HeldOutRegressionSet:
    """A curated regression set that runs against production traffic."""

    def __init__(self, path: str):
        with open(path) as f:
            self.cases = json.load(f)

    def coverage_report(self) -> dict:
        """Show which agent capabilities have regression coverage."""
        by_capability = defaultdict(list)
        for case in self.cases:
            by_capability[case["capability"]].append(case["id"])
        return {k: len(v) for k, v in by_capability.items()}

    def run(self, agent_fn, threshold: float = 0.90) -> dict:
        """
        Score the agent against the held-out set.
        Returns pass rate by capability and overall.
        Alert when any capability drops below threshold.
        """
        results = []
        for case in self.cases:
            output = agent_fn(case["input"])
            score = case["judge_fn"](output, case["expected"])
            results.append({
                "id": case["id"],
                "capability": case["capability"],
                "passed": score >= case["pass_threshold"],
                "score": score,
            })

        by_capability = defaultdict(lambda: {"passed": 0, "total": 0})
        for r in results:
            c = r["capability"]
            by_capability[c]["total"] += 1
            if r["passed"]:
                by_capability[c]["passed"] += 1

        alerts = []
        for cap, stats in by_capability.items():
            rate = stats["passed"] / stats["total"]
            if rate < threshold:
                alerts.append(f"REGRESSION: {cap} @ {rate:.1%} (threshold: {threshold:.0%})")

        overall = sum(r["passed"] for r in results) / len(results)
        return {
            "overall_pass_rate": overall,
            "by_capability": {
                c: s["passed"] / s["total"]
                for c, s in by_capability.items()
            },
            "alerts": alerts,
            "drift_detected": len(alerts) > 0,
        }
```

### 2. Route production traffic to the regression set continuously

Run the held-out set against live production inputs — not synthetic ones — on a cadence (hourly, shift-by-shift, or on every Nth interaction). Score results with an LLM-as-judge or deterministic rubric. Track pass rates over time, not just point-in-time scores.

```python
from datetime import datetime, timedelta

def continuous_drift_monitor(regression_set: HeldOutRegressionSet,
                              agent_fn,
                              sample_rate: float = 0.01,
                              window: timedelta = timedelta(hours=1)):
    """
    Sample production traffic and score against the regression set.
    Detect drift when the rolling pass rate drops.
    """
    # In production: integrate with your tracing pipeline
    # (Langfuse, Phoenix, Weave, etc.) to stream real interactions
    window_start = datetime.utcnow() - window

    # Score against regression oracle
    result = regression_set.run(agent_fn)

    if result["drift_detected"]:
        # Emit alert with capability-level breakdown
        for alert in result["alerts"]:
            print(f"[DRIFT ALERT] {window_start.isoformat()} | {alert}")
        # Trigger automatic incident ticket with pass rate snapshot
        return {"status": "DRIFT_DETECTED", **result}

    return {"status": "OK", "overall_pass_rate": result["overall_pass_rate"]}
```

### 3. Separate input drift detection from model drift detection

These require different tests and different responses:

| Drift type | Detection | Response |
|---|---|---|
| **Input drift** | Monitor input distribution (Jensen-Shannon divergence on feature vectors, or simple volume/keyword shift) | Update regression set to cover new input distribution |
| **Model drift** | Hold inputs fixed, compare outputs to baseline — rerun the same cases against the current model and previous model | Alert on provider change, revert if needed, or retune |
| **Behavioral drift** | Regression set pass rate drops even though inputs and model are unchanged | Diagnose: prompt regression, memory corruption, tool description change, or policy update |

```python
def diagnose_drift_type(prompt: str,
                         current_model_fn,
                         baseline_outputs: dict,
                         input_distribution: dict,
                         regression_set: HeldOutRegressionSet) -> str:
    """
    Classify the drift type to route to the right fix.
    """
    # Check input distribution
    if input_distribution.get("shift_detected"):
        return "INPUT_DRIFT"

    # Check model drift: rerun held-out with current model
    current_outputs = {
        case["id"]: current_model_fn(case["input"])
        for case in regression_set.cases
    }

    changed_outputs = [
        case_id for case_id, out in current_outputs.items()
        if out != baseline_outputs.get(case_id)
    ]
    if changed_outputs:
        return "MODEL_DRIFT"

    # If inputs and model unchanged but regression fails
    return "BEHAVIORAL_DRIFT"
```

### 4. Wire drift alerts into incident response, not ops dashboards

A drift alert is not an ops incident — it's a correctness incident. Route it to the team that owns agent quality (product, AI eng, or a dedicated evaluation team), not the on-call SRE. Include in the alert: capability that regressed, pass rate delta, traffic volume during regression window, and the specific inputs that started failing. Without this context, the team investigating has no starting point.

## Receipt

> Receipt pending — 2026-07-31. The detection logic above is structurally sound and matches the approach described by Flowscope (July 2026), AgentStatus / Carmel Labs (April 2026), and arXiv:2601.04170 (Rath, January 2026). The held-out regression set pattern is validated by Weights & Biases Weave continuous evaluation docs and the Benchmarking Agents Review (Vol. III, April 2026). Code example is illustrative — integrate with your tracing platform.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — pre-deploy eval architecture this extends into production
- [S-1916 · The Evals-Last Stack](s1916-the-evals-last-stack-when-you-ship-agents-but-cant-prove-theyll-work-tomorrow.md) — why eval is always deferred and how to build it in
- [S-1918 · The Agent Eval Stack](s1918-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-fails.md) — trajectory-level eval vs. output-only evaluation
- [R-17 · The Behavioral Regression Detection Stack](stacks/r17-the-behavioral-regression-detection-stack-when-your-agent-test-suite-is-green-but-your-users-are-not.md) — behavioral identity testing that catches how the agent works, not just whether it was right
