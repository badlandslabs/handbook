# S-1022 · The Agent Drift Stack — When Your Multi-Agent System Changes Without Changing

Your multi-agent system worked flawlessly in the pilot. Three months and 50,000 tasks later, task success has dropped from 91% to 58%. No model updates. No code changes. No configuration diffs. The system is running the same architecture it launched with — but it is no longer the same system. This is not a memory leak. It is **agent drift**.

## Situation

You run a customer-service multi-agent pipeline: a triage agent routes tickets, a resolution agent drafts responses, a quality agent reviews before sending. For the first two weeks, the system sustained 88% first-contact resolution. By week twelve, it is at 61%. Individual agents test fine in isolation. The pipeline degrades silently, in production, without any changes to the underlying code.

## Forces

- **Agents are not static — they are dynamic systems.** Unlike traditional software where behavior is fixed until code changes, LLM-based agents can shift their behavioral patterns over time through accumulated interaction context, without any explicit parameter updates.
- **Multi-agent drift is multiplicative, not additive.** Single-agent drift compounds within one pipeline. Multi-agent drift compounds *between* agents — the triage agent drifts, which changes what the resolution agent receives, which accelerates the resolution agent's drift. Three agents with mild drift create a system that fails in ways none of them individually exhibit.
- **Standard monitoring misses drift entirely.** You are watching for crashes, errors, and latency spikes. Agent drift produces plausible, coherent, *wrong* outputs. The system looks healthy by every conventional metric while silently degrading. Classic evaluation suites (pass/fail, final-answer scoring) cannot detect drift — they measure outcomes, not behavioral trajectories.
- **The drift surface is invisible by default.** LLMs do not expose their internal state between calls. You cannot observe that the triage agent has quietly shifted from "route to specialist" to "route to self-serve" until the specialist queue empties and customers complain.
- **Reset is not a solution — it erases institutional knowledge.** Blowing away context and starting fresh gets you back to week-one performance, but also back to week-one ignorance. You lose learned workflows, customer context, and accumulated judgment.

## The move

Measure drift with the **Agent Stability Index (ASI)**, a composite covering twelve behavioral dimensions across three drift types:

| Drift Type | What Degrades | ASI Signal |
|---|---|---|
| **Semantic drift** | Agent's interpretation of task intent progressively warps | Reasoning pathway similarity drops across equivalent inputs |
| **Coordination drift** | Multi-agent consensus breaks down; agents disagree on shared state | Inter-agent agreement rate on shared facts declines |
| **Behavioral drift** | Unintended strategies emerge; agent invents novel (and wrong) approaches | Tool-call sequence entropy increases; novel tool combos appear |

**Detection: Shadow-mode ASI scoring.** Run every N tasks (e.g., every 100) through a golden eval set of known inputs with expected trajectories. Score the actual trajectory against the golden using ASI. Track the ASI score over time. A declining ASI is the first signal of drift — before any production failures appear.

**Prevention: Episodic memory consolidation with behavioral anchoring.** The mitigation strategy from the January 2026 arXiv paper on Agent Drift (Rath, 2026). At configurable episode boundaries, consolidate recent agent trajectories into a compressed behavioral summary. Use this summary as an explicit anchoring prompt — "your established workflow for routing is: [anchor]" — on each new session. This does not prevent all drift but slows it by giving agents a stable behavioral reference.

**Containment: Drift-aware routing.** Route tasks to agents with lower measured drift when high-drift agents are detected. Flag high-drift agents for human review rather than letting them propagate degraded behavior downstream.

```python
import numpy as np
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta

@dataclass
class TrajectorySnapshot:
    task_id: str
    agent_id: str
    input_hash: str          # hash of the input task
    tool_sequence: list[str]
    reasoning_steps: int
    outcome: str            # "success", "partial", "failure"
    timestamp: datetime

@dataclass
class AgentStabilityIndex:
    agent_id: str
    trajectory_history: deque = field(default_factory=lambda: deque(maxlen=200))
    golden_set: list[dict] = field(default_factory=list)

    def compute_asi(self) -> float:
        """
        Agent Stability Index: composite of behavioral consistency metrics.
        Higher = more stable. Drops below threshold = drift detected.
        """
        if len(self.trajectory_history) < 10:
            return 1.0  # insufficient data

        # 1. Tool-sequence consistency: compare against golden trajectories
        recent_seqs = [s.tool_sequence for s in list(self.trajectory_history)[-20:]]
        seq_consistency = self._sequence_similarity(recent_seqs)

        # 2. Reasoning pathway stability: number of reasoning steps on equivalent inputs
        reasoning_variance = np.std([s.reasoning_steps for s in self.trajectory_history])

        # 3. Outcome rate: ratio of successful tasks in recent window
        recent = list(self.trajectory_history)[-50:]
        success_rate = sum(1 for s in recent if s.outcome == "success") / len(recent)

        # 4. Tool-call entropy: unexpected tool combinations signal behavioral drift
        seq_entropy = self._compute_entropy([tuple(s.tool_sequence) for s in recent])

        # Composite ASI (all normalized to 0-1)
        asi = (
            seq_consistency * 0.30 +
            max(0, 1 - reasoning_variance / 20) * 0.20 +
            success_rate * 0.35 +
            max(0, 1 - seq_entropy / 5.0) * 0.15
        )
        return round(asi, 3)

    def _sequence_similarity(self, seqs: list[list[str]]) -> float:
        """Fraction of recent trajectories matching the most common tool sequence."""
        if not seqs:
            return 1.0
        from collections import Counter
        counter = Counter(tuple(s) for s in seqs)
        most_common_count = counter.most_common(1)[0][1]
        return most_common_count / len(seqs)

    def _compute_entropy(self, seqs: list[tuple]) -> float:
        """Shannon entropy of tool sequence distribution. High entropy = behavioral drift."""
        if not seqs:
            return 0.0
        from collections import Counter
        counts = Counter(seqs)
        total = len(seqs)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * np.log2(p)
        return entropy

    def record(self, snapshot: TrajectorySnapshot):
        self.trajectory_history.append(snapshot)

    def is_drifted(self, threshold: float = 0.65) -> bool:
        """Drift is detected when ASI drops below threshold."""
        return self.compute_asi() < threshold

    def time_since_stable(self, threshold: float = 0.80) -> timedelta:
        """Return how long since ASI was above stability threshold."""
        history = list(self.trajectory_history)
        for i, snap in enumerate(reversed(history)):
            # Approximate ASI at each snapshot point
            window = history[max(0, len(history)-i-1):]
            if len(window) >= 10:
                recent_seqs = [s.tool_sequence for s in window[-20:]]
                seq_consistency = self._sequence_similarity(recent_seqs)
                reasoning_variance = np.std([s.reasoning_steps for s in window[-50:]]) if len(window) >= 50 else 0
                recent = window[-50:]
                success_rate = sum(1 for s in recent if s.outcome == "success") / len(recent)
                seq_entropy = self._compute_entropy([tuple(s.tool_sequence) for s in recent[-20:]])
                asi = (seq_consistency * 0.30 + max(0, 1 - reasoning_variance/20) * 0.20 +
                       success_rate * 0.35 + max(0, 1 - seq_entropy/5.0) * 0.15)
                if asi >= threshold:
                    return datetime.now() - snap.timestamp
        return timedelta(days=999)


# --- Drift-Aware Multi-Agent Router ---

class DriftAwareRouter:
    def __init__(self, agents: dict[str, AgentStabilityIndex], drift_threshold: float = 0.65):
        self.agents = agents
        self.threshold = drift_threshold

    def route(self, task: dict) -> str:
        """
        Choose agent with highest ASI (most stable).
        If all are drifted, flag for human review.
        """
        candidates = {
            agent_id: asi.compute_asi()
            for agent_id, asi in self.agents.items()
        }

        best_agent = max(candidates, key=candidates.get)
        best_asi = candidates[best_agent]

        if best_asi < self.threshold:
            return "HUMAN_REVIEW"  # All agents drifted; escalate

        return best_agent

    def report(self) -> dict:
        return {
            agent_id: {"asi": round(asi.compute_asi(), 3), "drifted": asi.is_drifted()}
            for agent_id, asi in self.agents.items()
        }


# --- Example usage ---
if __name__ == "__main__":
    triage_asi = AgentStabilityIndex(agent_id="triage-agent")
    resolver_asi = AgentStabilityIndex(agent_id="resolver-agent")
    router = DriftAwareRouter(
        agents={"triage-agent": triage_asi, "resolver-agent": resolver_asi},
        drift_threshold=0.65
    )

    # Simulate healthy traffic
    for i in range(100):
        triage_asi.record(TrajectorySnapshot(
            task_id=f"task_{i}", agent_id="triage-agent",
            input_hash="abc123", tool_sequence=["classify", "route"],
            reasoning_steps=3, outcome="success", timestamp=datetime.now()
        ))

    # Simulate degraded traffic (drift: more reasoning steps, varied tool sequences)
    for i in range(100, 150):
        triage_asi.record(TrajectorySnapshot(
            task_id=f"task_{i}", agent_id="triage-agent",
            input_hash="abc123", tool_sequence=["classify", "classify", "route", "escalate"],
            reasoning_steps=7, outcome="partial", timestamp=datetime.now()
        ))

    print(f"Triage ASI: {triage_asi.compute_asi()}")       # Should be lower after drift phase
    print(f"Drifted? {triage_asi.is_drifted()}")           # True once ASI drops below threshold
    print(f"Time drifted: {triage_asi.time_since_stable()}")  # How long since stable
    print(f"Routed to: {router.route({'task': 'urgent'})}")  # HUMAN_REVIEW if all drifted
    print(f"ASI report: {router.report()}")
```

> Receipt pending — 2026-07-12. Code demonstrates ASI computation and drift-aware routing architecture. In production, connect to your tracing/observability pipeline (e.g., Arize Phoenix, LangSmith) to auto-populate TrajectorySnapshots from real agent spans.

## When to reach for this

- You have a multi-agent system running continuously (>2 weeks) with declining success rates you cannot explain
- Your evaluation suite is green but production metrics are yellow
- You notice agents "inventing" new tool sequences or workflows that were never designed
- You are approaching or past the 11-week mark where Rath (2026) found drift becomes pronounced

## See also

- [S-1015 · The Stability Gradient](stacks/s1015-the-stability-gradient-when-your-agent-works-once-and-fails-twice.md) — stochastic single-trial variance within a session
- [S-1002 · The Memory Consolidation Debt Stack](stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — episodic memory failure as a contributing factor to drift
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — coordination failure modes that predate and accelerate coordination drift
- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — foundational patterns for multi-agent architecture
- [S-09 · Memory Systems](stacks/s09-memory-systems.md) — tiered memory architectures; episodic and semantic memory are inputs to ASI scoring
