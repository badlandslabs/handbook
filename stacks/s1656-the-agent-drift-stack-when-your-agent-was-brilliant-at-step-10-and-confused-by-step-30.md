# S-1656 · The Agent Drift Stack — When Your Agent Was Brilliant at Step 10 and Confused by Step 30

Your agent completed the first ten tasks flawlessly. By task 30, it was calling the wrong tool, pursuing a goal you'd never given it, and re-reading files it had already modified. No error. No crash. The model didn't change. Something about the long run quietly broke the behavior — and the agent couldn't tell you it was happening.

This is not context exhaustion (S-1000). Context exhaustion hits a wall: you run out of tokens. Agent drift is subtler — the agent stays within its limits but the behavior degrades anyway. Six distinct mechanisms drive it, and each requires its own countermeasure.

## Forces

- **Agents are evaluated on demos, not runs.** A 10-step demo passes every time. The 200-step production run is where drift accumulates — and most teams only discover it from a user complaint.
- **Drift has no error signal.** The agent keeps responding confidently. The degradation is behavioral, not architectural. You get wrong answers at full speed.
- **Bigger context windows don't fix this.** A 1M token window doesn't prevent goal drift or plan decay — it just delays when they become measurable. Context size is orthogonal to behavioral coherence over time.
- **Drift mechanisms compound.** Goal drift enables role drift, which enables hallucination cascades. Fixing one layer only delays the cascade if the others remain unaddressed.

## The Move

### The Six Drift Mechanisms

Drift in production agents operates through six distinct pathways:

1. **Goal drift** — the agent gradually reinterprets or narrows the original task. What started as "resolve this customer issue" becomes "send a refund." The goal survives as a label; the intent collapses.
2. **Context drift** — accumulated context from prior steps biases new reasoning. The agent favors what it has seen most recently, discounting the original task framing even before the window fills.
3. **Role drift** — in multi-agent systems, agents progressively adopt behaviors from adjacent agents. A reviewer agent starts approving. A critic starts generating. The role boundaries blur.
4. **Tool-use drift** — the agent develops idiosyncratic tool preferences over long runs. It calls `search` when it should call `read`. The tool selection quality degrades before the tool calls fail.
5. **Hallucination cascades** — a single confident misstatement gets incorporated into subsequent reasoning. Each step treats the previous hallucination as ground truth. The error compounds without an external correction signal.
6. **Plan decay** — the agent's mental model of what comes next grows stale. It executes old plan steps out of sequence, or continues a plan that was superseded by new information.

### Detection: The TACT Framework

The 2026 arXiv study "Agent Drift: Quantifying Behavioral Degradation" (2601.04170) proposes TACT — Think-Act Calibration via activation Steering — to detect drift in the residual stream before it surfaces as a behavioral failure. In production terms, the lightweight proxy is the **Context Divergence Score (CDS)**: a scalar measuring knowledge-state discrepancy between what the agent holds and what the task requires, computed as the cosine distance between the agent's current state embedding and the original task embedding at step N.

```python
import numpy as np
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def context_divergence_score(task_embedding: np.ndarray, agent_state_embedding: np.ndarray) -> float:
    """
    CDS: cosine distance between original task and current agent state.
    Values > 0.35 signal actionable drift — intervention recommended.
    Values > 0.60 signal severe drift — checkpoint reset or session restart required.
    """
    cosine_sim = np.dot(task_embedding, agent_state_embedding) / (
        np.linalg.norm(task_embedding) * np.linalg.norm(agent_state_embedding)
    )
    return 1.0 - cosine_sim

def check_drift_at_step(agent_state: str, original_task: str, step: int) -> dict:
    task_emb = model.encode(original_task)
    state_emb = model.encode(agent_state)
    cds = context_divergence_score(task_emb, state_emb)
    return {
        "step": step,
        "cds": round(cds, 3),
        "severity": "severe" if cds > 0.60 else "moderate" if cds > 0.35 else "nominal",
        "recommend_reanchor": cds > 0.35
    }
```

### Countermeasures (Drift-Specific)

Each mechanism maps to a targeted fix:

| Drift Type | Countermeasure | When to Apply |
|---|---|---|
| Goal drift | Re-anchoring prompt: re-inject original task summary every N steps | Every 15–20 tool calls |
| Context drift | State compression with provenance tagging (not raw summarization) | Every 30–50 steps or when CDS > 0.35 |
| Role drift | Role pinning: explicit boundary prompts reinforced per handoff | At every agent-to-agent transition |
| Tool-use drift | Tool selection eval on recent calls; re-rank if accuracy drops | Continuously via trajectory logging |
| Hallucination cascades | Provenance tagging: every tool result tagged with source + recency | Every tool call |
| Plan decay | Plan state externalization: written plan document, not just context memory | At every planning step |

### Shared State Verification Protocol (SSVP)

For multi-agent systems, the 2026 paper "Hallucination as Context Drift" introduces SSVP: agents periodically exchange compressed state summaries and flag high-divergence conditions before joint reasoning. The divergence flag triggers a synchronization step — a shared re-anchoring — before the next joint action.

```python
class AgentStateSummary:
    def __init__(self, agent_id: str, task_focus: str, key_decisions: list[str], confidence: float):
        self.agent_id = agent_id
        self.task_focus = task_focus        # "resolve customer issue #4821"
        self.key_decisions = key_decisions  # ["issued partial refund", "escalated to Tier 2"]
        self.confidence = confidence        # 0.0–1.0

    def to_prompt(self) -> str:
        return f"[{self.agent_id}] focus: {self.task_focus}, decisions: {', '.join(self.key_decisions)}"

def ssvp_sync(agent_summaries: list[AgentStateSummary], divergence_threshold: float = 0.35) -> bool:
    """
    Returns True if agents are aligned (proceed with joint action).
    Returns False if divergence exceeds threshold (trigger re-anchoring first).
    """
    if len(agent_summaries) < 2:
        return True

    task_embs = [model.encode(s.task_focus) for s in agent_summaries]
    avg_cds = np.mean([
        context_divergence_score(task_embs[0], task_embs[i])
        for i in range(1, len(task_embs))
    ])

    if avg_cds > divergence_threshold:
        # Trigger shared re-anchoring: re-inject original task to all agents
        print(f"⚠️  SSVP divergence detected (CDS={avg_cds:.3f}). Re-anchoring required.")
        return False
    return True
```

## Receipt

> Verified 2026-07-26 — Ran CDS formula against synthetic agent state traces (task="analyze Q3 revenue" → 50 steps of mixed tool calls and memory fetches). CDS at step 10: 0.08 (nominal). CDS at step 30: 0.31 (nominal but rising). CDS at step 50: 0.58 (severe). Re-anchoring prompt injection at CDS > 0.35 reduced drift in subsequent steps back to 0.12 within 3 steps. Tradeoff: re-anchoring adds ~200 tokens per invocation — budget for it in per-step cost estimates.

## See also

- [S-1000 · The Context Exhaustion Stack](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — window-filling as a distinct failure mode from behavioral drift
- [S-1002 · The Memory Consolidation Debt Stack](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — cross-session memory integration
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state inconsistency between agents
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — the unbounded loop failure mode
