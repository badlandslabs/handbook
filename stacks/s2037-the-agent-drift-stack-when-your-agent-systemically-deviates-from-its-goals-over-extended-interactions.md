# S-2037 · The Agent Drift Stack — When Your Agent Systemically Deviates From Its Goals Over Extended Interactions

An agent that works correctly in a 10-step demo fails in a 1,000-step production run. Not because the model degraded — the same weights, the same API call — but because the agent's behavior progressively diverged from its original intent over extended interactions. This is **agent drift**: the progressive, measurable degradation of goal adherence, decision quality, and inter-agent coherence that emerges only in long-horizon deployments. The fix is not a better model. It's a drift-resistant architecture with built-in anchoring mechanisms.

## Forces

- Context accumulation is not neutral — as conversation history grows, earlier goals lose salience in favor of locally coherent but globally divergent behavior
- Multi-agent systems compound single-agent drift: coordination mechanisms amplify rather than correct individual drift trajectories
- Standard evaluation catches capability deficits, not behavioral degradation over time — a system can score identically at step 10 and step 1,000 while behaving differently
- Agents trained on their own interaction histories can reinforce drifted patterns through implicit in-context learning
- No production alerting framework currently tracks drift as a first-class signal — teams discover drift only when outputs are visibly wrong or costs spike

## The move

**Three drift types** (arXiv:2601.04170, Rath, Jan 2026):

1. **Semantic drift** — Progressive deviation from original intent. The agent's evolving context causes it to reframe or abandon the original goal in favor of locally coherent but globally divergent sub-goals.
2. **Coordination drift** — Breakdown in multi-agent consensus. Peer agents accumulate different semantic drifts, causing their shared state to diverge and handoff contracts to become inconsistent.
3. **Behavioral drift** — Emergence of unintended behavioral patterns. The agent develops habits (repeated tool patterns, preferred failure modes, implicit policies) that were never explicitly programmed and may violate original constraints.

**The drift detection layer**:

```python
import numpy as np
from collections import deque

class BehavioralAnchor:
    """
    Maintains a rolling behavioral fingerprint and alerts on drift.
    Anchored against the initial session goal state, not just prior steps.
    """
    def __init__(self, goal_embedding: np.ndarray, threshold: float = 0.15, window: int = 50):
        self.anchor = goal_embedding          # vector of original intent/constraints
        self.window = deque(maxlen=window)     # recent N decision embeddings
        self.drift_score = 0.0
        self.threshold = threshold

    def step(self, decision_embedding: np.ndarray, step_num: int):
        """Record a decision and compute drift from anchor."""
        self.window.append(decision_embedding)
        if len(self.window) < 10:
            return 0.0  # insufficient history

        # Cosine similarity to anchor — low = high drift
        anchor_sim = float(np.dot(self.anchor, decision_embedding) /
                          (np.linalg.norm(self.anchor) * np.linalg.norm(decision_embedding) + 1e-8))

        # Weighted drift: recent decisions weighted more heavily
        recency_weight = np.linspace(0.5, 1.0, len(self.window))
        recency_weight /= recency_weight.sum()
        window_matrix = np.array(list(self.window))
        anchor_sims = np.dot(window_matrix, self.anchor) / (
            np.linalg.norm(window_matrix, axis=1) * np.linalg.norm(self.anchor) + 1e-8)
        weighted_sim = float(np.dot(anchor_sims, recency_weight))

        self.drift_score = 1.0 - weighted_sim

        if self.drift_score > self.threshold:
            # Trigger anchoring intervention
            self._reanchor(step_num)

        return self.drift_score

    def _reanchor(self, step_num: int):
        """Hard re-anchor: inject original goal into context."""
        # Don't reset — surface the drift and force explicit re-confirmation
        return {
            "event": "DRIFT_DETECTED",
            "step": step_num,
            "score": self.drift_score,
            "action": "GOAL_RECONFIRM",
            "prompt_addition": (
                "Reminder: the original objective was [GOAL]. "
                "Current context has drifted from this goal. "
                "Confirm whether to continue, adjust, or abort."
            )
        }


class DriftAwareRouter:
    """
    Routes tasks through agents based on drift state.
    High-drift agents get escalated or handed off, not continued.
    """
    def __init__(self, agents: dict, drift_monitor: BehavioralAnchor):
        self.agents = agents
        self.monitor = drift_monitor

    def route(self, task: dict, decision_emb: np.ndarray, step: int) -> str:
        drift = self.monitor.step(decision_emb, step)
        if drift > 0.30:
            return self.agents["fresh"]     # hand off to low-drift agent
        elif drift > 0.15:
            return self.agents["supervisor"]  # escalate to human review
        else:
            return self.agents["current"]  # continue normally
```

**Three mitigation strategies** (from arXiv:2601.04170):

1. **Episodic memory consolidation** — Periodically compress the agent's accumulated context into a goal-faithful summary that is checked against the original intent. Discard locally coherent but globally divergent content.
2. **Drift-aware routing** — Route tasks through agents with low current drift scores. Track drift per-agent and exclude high-drift agents from critical decision paths.
3. **Adaptive behavioral anchoring** — Inject periodic "anchor checks" that re-expose the agent to its original goal state. Use the anchor's goal embedding to score all recent decisions.

**Drift monitoring in practice**:

```python
# Production monitoring: emit drift score as an observability metric
def emit_drift_metric(agent_id: str, session_id: str, score: float, step: int):
    """Send to your OTel pipeline as a gauge metric."""
    print(json.dumps({
        "metric": "agent.drift_score",
        "agent_id": agent_id,
        "session_id": session_id,
        "step": step,
        "value": score,       # 0.0 = perfect alignment, 1.0 = full drift
        "severity": "warning" if score > 0.15 else "ok",
    }))
```

- Alert threshold: drift_score > 0.15 → warning; > 0.30 → escalate
- Evaluate drift_score weekly against a held-out "intent consistency" test set
- Do not conflate drift with capability regression — a drifting agent may score the same on benchmarks while behaving differently on your specific workflows

## Receipt

> Verified 2026-08-02 — arXiv:2601.04170 (Rath, Jan 2026) establishes the theoretical framework with three drift types and three mitigation strategies. BehavioralAnchor and DriftAwareRouter patterns synthesized from the mitigation taxonomy. Concrete thresholds (0.15/0.30) drawn from enterprise production alerting conventions in agentic monitoring literature (Collibra, Syrin AI, 2026). No benchmark for the code — test against your own production traces.

## See also

- [S-1896 · The Agentic Deadlock Stack](stacks/s1896-the-agentic-deadlock-stack-when-your-multi-agent-pipeline-freezes-and-every-agent-blames-someone-else.md) — coordination failure under load; drift compounds this by causing agents to disagree on what "done" means
- [S-1773 · The Context Hygiene Stack](stacks/s1773-the-context-hygiene-stack-when-your-agents-remember-things-that-never-happened.md) — memory contamination as a driver of semantic drift
- [S-1943 · The Agentic Observability Gap Stack](stacks/s1943-the-agentic-observability-gap-stack-when-your-dashboard-is-green-and-your-agent-isnt.md) — monitoring gap: drift has no first-class metric in most APM stacks today
- [S-1882 · The Overthinking Spiral Stack](stacks/s1882-the-overthinking-spiral-stack-when-your-agent-reasons-itself-into-higher-costs-and-lower-accuracy.md) — a specific behavioral drift pattern: reasoning paths that amplify cost without improving accuracy
