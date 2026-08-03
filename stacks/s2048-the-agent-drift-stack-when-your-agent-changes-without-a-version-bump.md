# S-2048 · The Agent Drift Stack — When Your Agent Changes Without a Version Bump

Your evaluation suite passed with 94% accuracy on Monday. On Friday, the agent is at 81%. No code changed. No deployment happened. The model version string is identical. The task is the same. But the agent's behavior is measurably, materially different — and you cannot explain why.

This is agent drift: the progressive degradation of an LLM agent's decision quality, output consistency, and behavioral stability over extended interaction sequences, without any explicit parameter changes or infrastructure failures. Unlike classical software bugs (reproducible, attributable to code), agent drift is probabilistic, multi-causal, and invisible to traditional monitoring. Carmel Labs tracked 6,200+ production agents over 30 days using 18 million tests. 88% experienced at least one measurable drift event. Over 1.54 million drift events were recorded. When accuracy dropped, it dropped hard — not by percentage points, but in sudden quality cliff events.

## Forces

- **Production monitoring catches crashes, not behavioral change.** Standard agent observability alerts on error rates, latency, and cost. None of these spike during a drift event — the agent is still running, still producing outputs, still completing tasks. The outputs are just worse.

- **You cannot replay the past.** Unlike deterministic software where you can git checkout and reproduce the bug, each agent interaction is a unique LLM sample. When drift is detected at 3pm on Thursday, the 9am Tuesday session that started the degradation cannot be reconstructed.

- **The cause is almost never one thing.** Drift accumulates from multiple sources simultaneously: model training data shifts (the model was retrained on Tuesday), prompt effectiveness decay (the same system prompt scores lower as the model's training data evolves), context window pressure (as conversation history grows, the model attends less to early instructions), and feedback loop amplification (if the agent uses its own past outputs as context, small biases compound).

- **Benchmark obsolescence is silent.** Your eval suite measures the agent against a ground truth that itself shifts. A benchmark passing today can measure a behavior the model no longer exhibits tomorrow.

- **88% of agents drift within 30 days.** This is not a rare edge case. It is the default behavior of production LLM agents over time.

## The move

### The Agent Stability Index

The foundational metric: ASI = 1 - (deviation from baseline / baseline rate). Track it continuously against a 7-day rolling baseline, not a one-time pre-deployment benchmark.

```python
import numpy as np
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ASISnapshot:
    timestamp: datetime
    task_id: str
    outcome: float  # 0.0 = fail, 1.0 = pass
    latency_ms: float
    token_count: int

class AgentStabilityMonitor:
    """Tracks Agent Stability Index (ASI) with rolling baseline."""

    def __init__(self, window_days: int = 7, alert_threshold: float = 0.05):
        self.window = timedelta(days=window_days)
        self.alert_threshold = alert_threshold
        self.snapshots: deque[ASISnapshot] = deque()
        self.baseline_outcomes: list[float] = []
        self.baseline_rate: float | None = None

    def record(self, task_id: str, outcome: float, latency_ms: float, token_count: int):
        snapshot = ASISnapshot(datetime.utcnow(), task_id, outcome, latency_ms, token_count)
        self.snapshots.append(snapshot)
        self._prune_old()
        self._recompute_baseline()

    def _prune_old(self):
        cutoff = datetime.utcnow() - self.window
        while self.snapshots and self.snapshots[0].timestamp < cutoff:
            self.snapshots.popleft()

    def _recompute_baseline(self):
        """Rolling baseline: last 7 days of data."""
        if len(self.snapshots) < 20:
            return  # Not enough data
        self.baseline_outcomes = [s.outcome for s in self.snapshots]
        self.baseline_rate = np.mean(self.baseline_outcomes)

    @property
    def current_rate(self) -> float | None:
        if len(self.snapshots) < 5:
            return None
        recent = [s for s in self.snapshots 
                  if s.timestamp > datetime.utcnow() - timedelta(hours=24)]
        if not recent:
            return None
        return np.mean([s.outcome for s in recent])

    @property
    def ASI(self) -> float | None:
        if self.baseline_rate is None or self.baseline_rate == 0:
            return None
        current = self.current_rate
        if current is None:
            return None
        return 1.0 - abs(current - self.baseline_rate) / max(self.baseline_rate, 0.01)

    @property
    def drift_detected(self) -> bool:
        asi = self.ASI
        if asi is None:
            return False
        return asi < (1.0 - self.alert_threshold)

    def diagnose(self) -> dict:
        """Decompose drift into contributing factors."""
        if not self.snapshots or len(self.snapshots) < 20:
            return {"status": "insufficient_data"}

        recent = [s for s in self.snapshots 
                  if s.timestamp > datetime.utcnow() - timedelta(hours=24)]
        baseline = [s for s in self.snapshots 
                    if s.timestamp <= datetime.utcnow() - timedelta(hours=24)]

        if not recent or not baseline:
            return {"status": "insufficient_data"}

        return {
            "ASI": round(self.ASI, 4) if self.ASI else None,
            "drift_detected": self.drift_detected,
            "baseline_outcome_rate": round(np.mean([s.outcome for s in baseline]), 3),
            "current_outcome_rate": round(np.mean([s.outcome for s in recent]), 3),
            "baseline_avg_latency_ms": round(np.mean([s.latency_ms for s in baseline]), 1),
            "current_avg_latency_ms": round(np.mean([s.latency_ms for s in recent]), 1),
            "latency_shift_pct": round(
                (np.mean([s.latency_ms for s in recent]) - 
                 np.mean([s.latency_ms for s in baseline])) / 
                max(np.mean([s.latency_ms for s in baseline]), 0.001) * 100, 1
            ),
            "snapshot_count": len(self.snapshots),
            "drift_type": self._classify_drift(recent, baseline),
        }

    def _classify_drift(self, recent: list, baseline: list) -> str:
        recent_rate = np.mean([s.outcome for s in recent])
        baseline_rate = np.mean([s.outcome for s in baseline])
        recent_latency = np.mean([s.latency_ms for s in recent])
        baseline_latency = np.mean([s.latency_ms for s in baseline])

        rate_drop = baseline_rate - recent_rate
        latency_shift = (recent_latency - baseline_latency) / baseline_latency

        if rate_drop > 0.05 and latency_shift > 0.2:
            return "quality_and_latency_degradation"
        elif rate_drop > 0.05:
            return "quality_drift_only"
        elif latency_shift > 0.2:
            return "latency_drift_only"
        else:
            return "subtle_drift_below_threshold"
```

### The Drift Detection Protocol

Three signals to track continuously:

1. **Outcome rate**: rolling 24-hour success rate vs. 7-day baseline. Alert when ASI < 0.95.
2. **Latency distribution**: if median latency shifts > 20% without infrastructure change, flag it.
3. **Token velocity**: agents burning tokens faster than progress indicate loop or prompt-decay drift.

```python
def drift_protocol(monitor: AgentStabilityMonitor):
    """Alert-driven drift response protocol."""
    diag = monitor.diagnose()

    if diag.get("status") == "insufficient_data":
        return {"action": "collect", "reason": "need_more_samples"}

    if not monitor.drift_detected:
        return {"action": "monitor", "ASI": diag.get("ASI")}

    drift_type = diag.get("drift_type", "unknown")
    rate_drop = diag.get("baseline_outcome_rate", 1.0) - diag.get("current_outcome_rate", 0)

    # Severity tiers
    if rate_drop > 0.20:
        severity = "critical"
    elif rate_drop > 0.10:
        severity = "major"
    elif rate_drop > 0.05:
        severity = "minor"
    else:
        severity = "warning"

    return {
        "action": "investigate",
        "severity": severity,
        "ASI": diag.get("ASI"),
        "drift_type": drift_type,
        "rate_drop_pct": round(rate_drop * 100, 1),
        "next_steps": _drift_response(drift_type, severity),
    }

def _drift_response(drift_type: str, severity: str) -> list[str]:
    responses = {
        "quality_and_latency_degradation": [
            "Check model provider status for updates or deprecations",
            "Audit recent conversation history for context pressure buildup",
            "Compare token velocity before and after the drift window",
        ],
        "quality_drift_only": [
            "Re-run eval suite against golden dataset",
            "Compare prompt effectiveness scores (same prompt, different model version?)",
            "Check if the model's training data cutoff has changed",
        ],
        "latency_drift_only": [
            "Audit infrastructure (model API latency, tool call latencies)",
            "Check context size — longer contexts slow generation",
        ],
        "subtle_drift_below_threshold": [
            "Increase sampling and re-evaluate in 4 hours",
            "Log for trend analysis",
        ],
    }
    return responses.get(drift_type, ["manual_review_required"])
```

### The Drift-Freeze Archive

When a drift event is detected, the first action is to freeze the current state. Before making any changes, archive: recent production traces, the full conversation history window, eval results against the last 3 versions, and current system prompt + model version.

This freeze is what makes root cause analysis possible. Without it, you cannot know whether the drift came from the model, the prompt, the context, or the data.

> Receipt pending — 2026-08-02

## See also

- [S-1326 · The Library Drift Stack](s1326-the-library-drift-stack-when-your-agent-learns-new-skills-and-becomes-slowly-worse.md) — skill accumulation degrading retrieval quality over time
- [S-1928 · The Regression Budget Stack](s1928-the-regression-budget-stack-when-your-agent-worked-last-tuesday-and-you-dont-know-why-it-doesnt-today.md) — no pre-deployment contract for acceptable quality degradation
- [S-820 · The Memory Poisoning Defense Stack](s820-the-memory-poisoning-defense-stack-four-layers-against-asi06.md) — cross-session memory contamination as a drift vector
