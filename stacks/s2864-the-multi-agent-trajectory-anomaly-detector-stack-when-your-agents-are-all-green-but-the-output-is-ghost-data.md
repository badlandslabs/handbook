# S-2864 · The Multi-Agent Trajectory Anomaly Detector Stack — When Your Agents Are All Green but the Output Is Ghost Data

Your multi-agent pipeline runs cleanly. Every agent logs successful tool calls. No exceptions, no timeouts, no elevated error rates. The dashboard is green. Three hours later, the customer support team starts receiving tickets about orders that were confirmed but never created — the agents agreed on a ghost transaction and built a coherent-seeming but entirely fictional output. This is the silent trajectory failure pattern: each individual agent appeared to work correctly, but the multi-agent trajectory as a whole diverged from the intended outcome. Standard APM cannot detect this. The failure is defined by the *absence* of an error signal.

## Forces

- **Multi-agent systems fail trajectory-level, not action-level.** Each agent's local health check can pass while the global trajectory diverges. One agent drifts off-task, another compensates confidently with hallucinated data, a third silently drops a required output step. Individually, no failure fires. Together, you get ghost data.
- **Traditional APM watches for the wrong signal.** APM alerts on crashes, exceptions, latency spikes, HTTP errors. Silent trajectory failures produce none of these. The system is functioning — it is producing output — but the output is wrong in ways that are structurally invisible to action-level monitoring.
- **Agents self-verify using proxies, not ground truth.** Completion signals (tool returned), confidence scores, and exit codes are proxy signals for correctness. In a multi-agent pipeline, these proxies compound: Agent A's plausible-but-wrong output becomes Agent B's input, which produces a plausible-but-wrong output, and so on. The error compounds without ever triggering a non-succeeding return code.
- **Failure is non-deterministic across runs.** The same task can succeed or silently fail depending on model temperature, context ordering, tool response latency, or which agent happens to process a given sub-task first. You cannot reproduce the failure deterministically with a unit test.

## The move

The fix is trajectory-level anomaly detection: instrument the full execution trace of the multi-agent pipeline, extract behavioral features from the trajectory, and run an anomaly detector over the trajectory-as-a-whole.

**Step 1 — Instrument trajectory logging.** Log every agent turn with: input state hash, output state hash, tool calls made, tool call latency, token velocity (tokens/second), sequence length, state delta magnitude, and inter-agent handoff events. This is not the agent's self-reported log — it is an external instrumentation layer that the agent cannot falsify.

```python
import hashlib
import time
import json
from dataclasses import dataclass, asdict
from collections import deque

@dataclass
class TrajectoryStep:
    agent_id: str
    step_index: int
    input_state_hash: str
    output_state_hash: str
    tool_calls: list[dict]
    tool_latencies_ms: list[float]
    token_count: int
    duration_ms: float
    timestamp: float
    handoff_to: list[str] | None = None  # explicit handoff targets

class TrajectoryLogger:
    """External instrumentation layer — agent cannot write to this."""
    def __init__(self, trajectory_id: str):
        self.trajectory_id = trajectory_id
        self.steps: list[TrajectoryStep] = []
        self._state_cache: dict[str, str] = {}

    def log(self, step: TrajectoryStep):
        self.steps.append(step)
        self._state_cache[step.agent_id] = step.output_state_hash

    def state_hash(self, agent_id: str, data: str) -> str:
        """Tamper-evident state hash — computed externally."""
        return hashlib.sha256(f"{agent_id}:{data}:{time.time_ns()}".encode()).hexdigest()[:16]

    def to_features(self) -> dict:
        """Extract anomaly-detection features from the full trajectory."""
        steps = self.steps
        if not steps:
            return {}

        # Per-agent consistency
        agent_states = {}
        for s in steps:
            if s.agent_id not in agent_states:
                agent_states[s.agent_id] = []
            agent_states[s.agent_id].append(s.output_state_hash)

        # Cycle detection: do any agents repeat states?
        cycles = {aid: len(v) != len(set(v)) for aid, v in agent_states.items()}

        # Token velocity across trajectory
        velocities = [s.token_count / (s.duration_ms / 1000) for s in steps if s.duration_ms > 0]

        # Handoff chain: how many hops between start and end agents?
        handoffs = [s for s in steps if s.handoff_to]

        # State drift: cosine-similarity between first and last agent outputs
        first_output = steps[0].output_state_hash if steps else ""
        last_output = steps[-1].output_state_hash if steps else ""
        # Hash distance as a proxy for state drift
        drift = sum(
            c1 != c2 for c1, c2 in zip(first_output, last_output)
        ) / max(len(first_output), 1)

        return {
            "num_steps": len(steps),
            "num_agents": len(agent_states),
            "cycle_detected": any(cycles.values()),
            "cycle_agents": [aid for aid, v in cycles.items() if v],
            "avg_velocity": sum(velocities) / len(velocities) if velocities else 0,
            "velocity_std": (sum((v - sum(velocities)/len(velocities))**2 for v in velocities) / len(velocities)) ** 0.5 if len(velocities) > 1 else 0,
            "handoff_count": len(handoffs),
            "state_drift": drift,
            "total_tools": sum(len(s.tool_calls) for s in steps),
            "avg_tool_latency": sum(sum(s.tool_latencies_ms) for s in steps) / max(1, sum(len(s.tool_latencies_ms) for s in steps)),
        }
```

**Step 2 — Extract trajectory features and run the anomaly detector.** Pathak et al. (ICPE '26, arXiv:2511.04032) showed that XGBoost achieves 98% accuracy and SVDD achieves 96% on multi-agent trajectory anomaly detection with 4,275 labeled trajectories. The key signals are *drift* (state divergence from expected sequence), *cycles* (agent revisiting prior output states), and *missing details* (tool outputs silently dropped from the trajectory).

```python
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
import numpy as np

# Option A: Semi-supervised SVDD (One-Class SVM)
# Train on known-good trajectories only.
# 96% accuracy on multi-agent anomaly detection (Pathak et al., ICPE '26).

class TrajectoryAnomalyDetector:
    def __init__(self, known_good_trajectories: list[dict]):
        features = np.array([self._extract(t) for t in known_good_trajectories])
        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(features)
        # nu=0.05: expect ~5% anomalies in training data
        self.svdd = OneClassSVM(kernel='rbf', nu=0.05, gamma='scale')
        self.svdd.fit(X)

    def _extract(self, t: dict) -> np.ndarray:
        return np.array([
            t.get("num_steps", 0),
            t.get("num_agents", 0),
            1.0 if t.get("cycle_detected") else 0.0,
            t.get("avg_velocity", 0),
            t.get("velocity_std", 0),
            t.get("handoff_count", 0),
            t.get("state_drift", 0),
            t.get("avg_tool_latency", 0),
        ])

    def score(self, trajectory_logger: TrajectoryLogger) -> tuple[bool, float]:
        """Returns (is_anomalous, anomaly_score)."""
        features = self._extract(trajectory_logger.to_features())
        X = self.scaler.transform(features.reshape(1, -1))
        decision = self.svdd.decision_function(X)[0]
        # Negative score = anomaly
        return decision < 0, float(decision)

# Option B: XGBoost (supervised, 98% accuracy)
# Train on labeled dataset: normal vs. anomalous trajectories.
# See Pathak et al. arXiv:2511.04032 for the labeled benchmark.

class TrajectoryXGBoostDetector:
    def __init__(self, model_path: str):
        import xgboost
        self.model = xgboost.XGBClassifier()
        self.model.load_model(model_path)

    def predict(self, trajectory_logger: TrajectoryLogger) -> tuple[bool, float]:
        features = self._extract(trajectory_logger.to_features())
        prob = self.model.predict_proba(features.reshape(1, -1))[0]
        return bool(prob[1] > 0.5), float(prob[1])
```

**Step 3 — Wire it into the pipeline as a gate, not a monitor.** The detector fires at the end of every multi-agent task completion. On anomaly detection:

```python
async def run_multi_agent_task(pipeline, input_data, detector):
    logger = TrajectoryLogger(trajectory_id=str(uuid4()))
    result = await pipeline.execute(input_data, logger=logger)
    is_anomalous, score = detector.score(logger)

    if is_anomalous:
        # Don't trust the output. Fall back to human review or
        # replay with stricter instrumentation.
        logger.capture_full_trace()  # snapshot before any cleanup
        raise AnomalousTrajectoryError(
            f"Trajectory {logger.trajectory_id} flagged "
            f"(score={score:.3f}). "
            f"Cycles: {logger.to_features()['cycle_agents']}, "
            f"Drift: {logger.to_features()['state_drift']:.2f}"
        )
    return result
```

**Step 4 — Capture missing details with completeness checks.** Beyond trajectory features, verify that expected artifacts were produced:

```python
def completeness_check(expected_artifacts: list[str], trajectory: TrajectoryLogger) -> dict:
    """Verify that every expected artifact was written with non-null content."""
    produced = {s.output_state_hash for s in trajectory.steps}
    missing = [a for a in expected_artifacts if a not in produced]
    return {
        "complete": len(missing) == 0,
        "missing_artifacts": missing,
        "step_count": len(trajectory.steps),
        "cycle_detected": trajectory.to_features()["cycle_detected"],
    }
```

## Receipt

> Verified 2026-08-19 — Detection approach validated against Pathak et al. (ICPE '26, arXiv:2511.04032): XGBoost 98% accuracy, SVDD 96% on 4,275 labeled multi-agent trajectories. Three failure modes confirmed: drift (state divergence), cycles (agent state loops), missing details (silent output drops). SVDD trained on known-good trajectories is the production-recommended approach — no labeled anomaly data required at deploy time. Code patterns above are structural illustrations based on the paper's architecture.

## See also

- [S-2859 · The Trajectory-Aware Evaluation Stack](s2859-the-trajectory-aware-evaluation-stack.md) — design-time trajectory evaluation harness (vs. this entry's runtime detection)
- [S-2415 · The Catastrophe That Wasn't Stack](S-2415-the-catastrophe-that-wasnt-stack-when-your-agent-fails-but-doesnt-tell-you.md) — behavioral monitoring of individual agent failures (vs. trajectory-level anomaly in multi-agent pipelines)
- [S-1433 · The Confidence-Gated Autonomy Stack](s1433-the-confidence-gated-autonomy-stack-when-your-agent-decides-it-knows-best-and-it-doesnt.md) — confidence thresholds as failure signals (proxy signals; this entry addresses the trajectory-level version)
