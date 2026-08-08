# S-2321 · The Agent Drift Stack — When Your Agentic System Silently Becomes a Different System

Your multi-agent pipeline was 94% accurate in week one. By week eight it is 71%. The agents still start each task fresh. The model hasn't changed. The prompts are identical. Nobody changed the tooling. But something changed — not a crash, not a bad deploy, just slow, invisible mutation. This is agent drift, and it has no error log.

## Forces

- **LLMs are not deterministic observers.** Each turn the agent sees a slightly different context window, a different tool result, a slightly different token distribution. These micro-variations accumulate into macro-behavioral shifts that are invisible at the individual turn level.
- **Multi-agent systems compound drift.** When agents hand off tasks across 4–6 turns, each agent's drift feeds into the next agent's input. Semantic drift (the meaning shifting) and coordination drift (the handoff agreements breaking down) amplify each other.
- **Agents lack self-reference for drift.** An agent cannot observe that it has drifted — it only sees its current context. Drift is observable only from the outside, over time, against a stable baseline.
- **Standard monitoring tracks outputs, not behavior.** APM dashboards log latency, error rates, and cost. They don't log whether the agent's tool-selection strategy, response verbosity, or escalation threshold has shifted.
- **The literature gap is real.** As of mid-2026, only one paper (Rath, arXiv:2601.04170) formally quantifies agent drift. Most teams discover it when a customer reports the agent is "acting weird" — weeks after the degradation began.

## The move

Define drift formally, then instrument against it.

**Three drift axes (Rath, 2026):**

1. **Semantic drift** — progressive deviation from original task intent. The agent's understanding of what it is supposed to do shifts subtly over extended interactions. Early sessions apply a strict interpretation; later sessions take shortcuts or reframe the goal.
2. **Coordination drift** — breakdown in multi-agent consensus mechanisms. Handoff protocols between agents become loosely adhered to. Agents start skipping agreed checkpoints, making unilateral decisions, or disagreeing on shared state.
3. **Behavioral drift** — emergence of unintended strategies. The agent discovers a locally optimal path that violates a global constraint. It works within the agent's context window but produces artifacts that contradict the original design intent.

**Quantify with the Agent Stability Index (ASI).**

ASI is a composite metric across 12 behavioral dimensions:
- Response consistency (does the same input produce the same class of output?)
- Tool usage pattern stability (is the agent still selecting the same tools for the same task types?)
- Reasoning pathway stability (do multi-step traces follow comparable chains?)
- Inter-agent agreement rate (do agents in a pipeline agree on shared state?)
- Escalation rate (has the threshold for human escalation shifted?)
- Output format consistency (does structured output schema compliance hold?)

Track ASI on a rolling 7-day window. Alert when any single dimension drops more than 15% from the 30-day baseline.

**Three mitigation strategies (Rath, 2026):**

1. **Episodic Memory Consolidation** — periodically review and re-anchor agent memory against the original design intent. Treat memory hygiene as drift prevention, not just storage management. See S-1002 (Memory Consolidation Debt).
2. **Drift-Aware Routing** — detect drift early at the routing layer and reroute tasks to a fresh agent instance or restart the agent session before drift compounds. Track drift indicators per-agent, not just per-pipeline.
3. **Adaptive Behavioral Anchoring** — define a minimal behavioral contract (a harness of golden traces) that every agent instance must pass before processing production traffic. Re-run anchor traces weekly. If pass rate drops, quarantine and re-anchor.

```python
# Minimal ASI tracker skeleton
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class DriftSnapshot:
    timestamp: datetime
    tool_selection_entropy: float      # higher = more variation
    output_format_compliance: float   # 0.0–1.0
    escalation_rate: float             # escalations / total tasks
    inter_agent_agreement: float      # handoff state match rate

class AgentStabilityMonitor:
    def __init__(self, baseline_window_days=30, alert_threshold=0.15):
        self.baseline_window = baseline_window_days
        self.alert_threshold = alert_threshold
        self.history: deque[DriftSnapshot] = deque()

    def record(self, snapshot: DriftSnapshot):
        self.history.append(snapshot)
        cutoff = datetime.utcnow() - timedelta(days=self.baseline_window)
        self.history = deque(s for s in self.history if s.timestamp > cutoff)

    def compute_asi(self, window_days=7) -> dict[str, float]:
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        window = [s for s in self.history if s.timestamp > cutoff]
        if not window:
            return {}
        return {
            "tool_entropy": sum(s.tool_selection_entropy for s in window) / len(window),
            "format_compliance": sum(s.output_format_compliance for s in window) / len(window),
            "escalation_rate": sum(s.escalation_rate for s in window) / len(window),
            "agreement_rate": sum(s.inter_agent_agreement for s in window) / len(window),
        }

    def detect_drift(self) -> list[str]:
        current = self.compute_asi(window_days=7)
        baseline = self.compute_asi(window_days=30)
        alerts = []
        for dim, val in current.items():
            base = baseline.get(dim, val)
            if base == 0:
                continue
            pct_change = (base - val) / base
            if pct_change > self.alert_threshold:
                alerts.append(f"{dim}: {pct_change:.1%} degradation vs. baseline")
        return alerts
```

**Detection pattern — drift runs before it flies.**

The critical insight: drift is detectable weeks before it becomes catastrophic. A 5% ASI degradation in week 4 predicts a 23% degradation by week 8 in Rath's simulation (3 enterprise domain simulations, 1000+ interaction sequences). Instrument ASI from day one. Don't wait for the customer report.

## Receipt

> Verified 2026-08-08 — arXiv:2601.04170 (Rath, Jan 2026): Agent Drift framework with ASI across 12 dimensions, 3 drift types (semantic, coordination, behavioral), 3 mitigation strategies showing up to 81.5% drift reduction. Linux Foundation / BabyBots confirmed A2A v1.0 production deployments (June 2026) across supply chain, financial services, IT ops — multi-agent drift risk is increasing with adoption velocity. `drift-monitor` (elementalcollision, MIT, 18 commits, Apr 2026) provides an open-source implementation skeleton.

## See also

- [S-1002 · The Memory Consolidation Debt Stack](stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — episodic memory consolidation is drift mitigation strategy #1
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — coordination drift surfaces at agent boundaries
- [S-2320 · The Agent Evaluation Stack](stacks/s2320-the-agent-evaluation-stack-making-your-measurement-loop-tell-the-truth.md) — ASI tracking belongs in the measurement loop alongside pass@k and harness metrics
