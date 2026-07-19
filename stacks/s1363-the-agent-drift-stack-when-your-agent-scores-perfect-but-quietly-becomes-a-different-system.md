# S-1363 · The Agent Drift Stack — When Your Agent Scores Perfect but Quietly Becomes a Different System

Your agent passes every eval. Your monitoring shows green. But somewhere between week two and week six of production, the agent started making systematically different decisions — stricter on refunds, looser on credit approvals, routing tickets differently — without any code change, model swap, or configuration update. This is agent drift: the progressive, silent degradation of agent behavior that standard monitoring cannot see because it measures what the agent can do, not what the agent is doing.

## Forces

- **Eval coverage is retrospective.** Standard evals benchmark capability at a point in time. They tell you what the agent could do last month. They say nothing about what the agent is doing today after 3,000 interactions on live traffic.
- **Standard monitoring watches output quality, not behavioral direction.** Accuracy rates, latency, token counts — all green — while the agent's decision boundaries shift imperceptibly. The monitoring stack has no signal for "the agent now approves 40% fewer refunds by default."
- **Drift compounds before it exceeds thresholds.** A 2% shift in routing behavior per week is invisible to alert thresholds. After six weeks, 12% of customers receive systematically different treatment. No alert fires.
- **Context accumulation is a drift accelerator.** As conversation history grows, the model subtly anchors on recent interactions. A customer-support agent that handled three difficult refund requests in a row will later default toward denial — not because of a policy change, but because recent context has shifted its implicit reference point.
- **Long-running agents are the primary target.** Per arXiv:2601.04170 (Rath, Jan 2026): nearly half of long-running agents are measurably affected by 600 interactions. Median detectable drift onset: 73 interactions (IQR: 52–114). The longer an agent runs, the more it drifts.

## The Move

### 1. Instrument behavioral anchors, not just outputs

Define **behavioral anchors**: measurable boundaries that should not shift over time. For a refund agent: approval rate ±5%, average response length ±20%, escalation rate ±3%. Store these as a **behavioral baseline** captured at deployment time.

```python
import json
from datetime import datetime, timedelta

class BehavioralBaseline:
    def __init__(self, agent_id: str, window_hours: int = 168):
        self.agent_id = agent_id
        self.baseline = None
        self.window = timedelta(hours=window_hours)
        self.anchors = {}

    def capture(self, metrics: dict[str, float]) -> None:
        """Capture baseline from first `window` hours of production."""
        self.baseline = {
            "captured_at": datetime.utcnow().isoformat(),
            "metrics": metrics.copy(),
        }
        for key, val in metrics.items():
            self.anchors[key] = {
                "lower": val * 0.95,   # −5%
                "upper": val * 1.05,   # +5%
                "drift_score": 0.0,
            }

    def measure(self, current: dict[str, float]) -> dict:
        """Return drift report: anchor name → deviation from baseline."""
        if not self.baseline:
            return {"status": "no_baseline"}
        report = {"status": "ok", "alerts": []}
        for key, baseline_val in self.baseline["metrics"].items():
            if key not in current:
                continue
            curr = current[key]
            anchor = self.anchors.get(key, {})
            deviation_pct = (curr - baseline_val) / baseline_val * 100
            report[key] = {
                "baseline": baseline_val,
                "current": curr,
                "deviation_pct": round(deviation_pct, 2),
            }
            if anchor and not (anchor["lower"] <= curr <= anchor["upper"]):
                report["status"] = "drift"
                report["alerts"].append({
                    "anchor": key,
                    "severity": "warning" if abs(deviation_pct) < 20 else "critical",
                    "deviation_pct": round(deviation_pct, 2),
                    "baseline": baseline_val,
                    "current": curr,
                })
        return report
```

### 2. Run a behavioral eval loop, not just a capability eval

Separate **can-it** from **does-it**:

| Question | Captured By | Cadence |
|----------|-------------|---------|
| Can it approve refunds correctly? | Capability eval (static test suite) | On model/code change |
| Is it approving refunds at the same rate it started with? | Behavioral drift eval (anchor comparison) | Daily on live traffic |

Run a **regression replay**: take the last 50 production decisions, re-run them against the current agent state, and diff the outputs. If the diff rate exceeds 5%, investigate.

```python
def regression_replay(agent, recent_decisions: list[dict], threshold: float = 0.05) -> dict:
    """
    Re-run recent decisions against current agent state.
    Returns diff rate and flagged cases.
    """
    diffs = 0
    flagged = []
    for decision in recent_decisions:
        current_output = agent.run(decision["input"])
        if current_output != decision["original_output"]:
            diffs += 1
            flagged.append({
                "input": decision["input"],
                "expected": decision["original_output"],
                "actual": current_output,
            })
    diff_rate = diffs / len(recent_decisions)
    return {
        "diff_rate": diff_rate,
        "threshold": threshold,
        "status": "DRIFT_DETECTED" if diff_rate > threshold else "stable",
        "flagged_count": len(flagged),
        "flagged": flagged[:5],  # first 5 for review
    }
```

### 3. Implement drift-aware routing for multi-agent systems

Per the Agent Drift arXiv paper, **drift-aware routing** routes requests away from agents that have exceeded behavioral drift thresholds, distributing load to agents within their stable operating window.

```python
def drift_aware_route(agents: list[Agent], request: str) -> Agent:
    """
    Route to agent with lowest drift score within its stable window.
    """
    candidates = [
        a for a in agents
        if a.drift_score < DRIFT_THRESHOLD and a.interaction_count < a.stable_window
    ]
    if not candidates:
        # Fallback: pick least-drifted, log escalation
        candidates = sorted(agents, key=lambda a: a.drift_score)
        log_escalation(f"All agents exceeding drift threshold. Lowest: {candidates[0].agent_id}")
    return min(candidates, key=lambda a: a.drift_score)
```

### 4. Anchor to episodic memory consolidation

The arXiv paper's most effective mitigation: **periodic episodic consolidation**. Every N interactions, compress the agent's recent behavioral patterns into a stable reference summary and inject it as a grounding anchor on the next session. This counteracts the recency bias that drives drift.

```python
def consolidate_episode(agent: Agent, window: int = 200) -> str:
    """
    Compress behavioral patterns from last `window` interactions into
    a grounding anchor that resets the agent's implicit reference point.
    """
    recent = agent.interaction_log[-window:]
    summary = summarize_behavioral_patterns(recent)
    anchor = (
        f"[BEHAVIORAL ANCHOR] This agent's core operational parameters: "
        f"{summary['approval_rate']} approval rate, "
        f"{summary['avg_response_time']}s response time, "
        f"{summary['escalation_rate']} escalation rate. "
        f"Maintain these parameters across all decisions."
    )
    agent.inject_anchor(anchor)
    agent.reset_interaction_log()  # start fresh window
    return anchor
```

## Detection Checklist

Run this weekly on every long-running production agent:

- [ ] Capture behavioral baseline in the first 168 hours of deployment
- [ ] Compare anchor metrics (approval rate, routing distribution, escalation rate) against baseline weekly
- [ ] Run regression replay on last 50 live decisions monthly
- [ ] Log drift score on every interaction; alert at >0.3 (normalized scale)
- [ ] Consolidate episodic memory every 200 interactions or weekly (whichever comes first)
- [ ] Freeze and redeploy if drift score exceeds 0.7 on any anchor

## Receipt

> Verified 2026-07-19 — arXiv:2601.04170 (Rath, Jan 2026) formally defines agent drift: 42% task success reduction, 3.2x human intervention increase, median drift onset at 73 interactions. Tenet AI blog (Apr 2026) documents semantic drift as a fourth monitoring category invisible to standard observability. Maxim's analysis (2026) confirms recency bias as drift accelerator. GitHub.com/alvabillwu/agent-drift (Jul 2026) provides open-source drift detection tooling. All three mitigation strategies (behavioral anchors, regression replay, episodic consolidation) drawn from published research and production practices.

## See also

[S-41 · Agent Handoff Patterns](s41-agent-handoff-patterns.md) · [S-100 · Agentic RAG](s100-agentic-rag.md) · [S-1360 · The Trace Reconstruction Stack](s1360-the-trace-reconstruction-stack-when-your-agent-fails-but-everything-looks-200-ok.md) · [S-1362 · The Regression Pipeline Stack](s1362-the-regression-pipeline-stack-when-your-agent-scores-well-but-silently-broke-in-production.md) · [F-191 · AI Agent Evaluation Harness](forward-deployed/f191-ai-agent-evaluation-harness.md)
