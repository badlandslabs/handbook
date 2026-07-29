# S-1808 · The Agent Stability Index Stack — When Your Agent Is Drifting and Nobody Can Put a Number on It

Your fraud detection agent shipped at 94% precision. Six weeks later it is at 81%. No model update. No code change. No configuration diff. Your APM dashboard shows green. Your error rate is 0.2%. Your on-call engineer has not been paged. Your agent is drifting, and you cannot prove it — because nobody has given you a number. This is the measurement gap that kills production agents: you know they are degrading, but you have no instrument to see it.

The Agent Stability Index (ASI) is the first quantitative framework to close this gap. Introduced by Rath (arXiv:2601.04170, January 2026) and extended by production implementations, ASI formalizes agent behavioral drift into a measurable, monitorable, and alertable score across 12 operational dimensions.

## Forces

- **Drift is super-linear, not linear.** Standard SRE error budgets model failures as independent events. HORIZON (Wang et al., arXiv:2604.11978, April 2026) found agent degradation compounds faster than independent error rates predict: pass@1 drops from 76.3% on short tasks to 52.1% on very-long tasks. By the time drift is visible to users, it has already passed through multiple compounding stages.
- **Standard APM is blind to behavioral degradation.** Error rate, latency, and HTTP status are lagging indicators for agent quality. An agent returning 200 with systematically wrong answers is "healthy" by every conventional metric. The agentmarketcap.ai April 2026 report found 1 in 20 production AI requests fail — but 60% of those failures are capacity failures (rate limiting, context exhaustion), leaving behavioral regressions invisible.
- **Three drift types do not correlate automatically.** Semantic drift (the agent deviates from its instructions), behavioral drift (the agent's response patterns change — length, tone, tool usage), and coordination drift (multi-agent handoffs lose fidelity) operate independently. Measuring only one dimension underestimates the others severely.
- **Ghost lexicon decay hides in plain sight.** LangGraph's checkpointing (GitHub #7327, March 2026) surfaces a subtle drift mode: domain-specific vocabulary used by an agent in early checkpoints disappears in later ones, even on identical prompts. This is not a memory failure — the agent remembers. It has changed how it retrieves and applies that knowledge.
- **Compounding multiplies silently across agents.** Single-agent drift compounds within one pipeline. Multi-agent drift compounds between agents — a triage agent drifts, changing what the resolution agent receives, accelerating the resolution agent's drift. Three agents with mild drift create a system that fails in ways none of them individually exhibit.

## The Move

### The ASI Framework: 12 Dimensions Across Three Categories

ASI organizes drift measurement into three categories, four dimensions each:

**Semantic (4):** Instruction adherence consistency · Policy threshold deviation · Decision logic consistency · Tradeoff analysis accuracy

**Behavioral (4):** Response length trend · Tool call pattern stability · Self-correction capability · Emotional response mode

**Coordination (4):** Multi-agent handoff precision · State consistency across agents · Resource contention detection · Session boundary maintenance

Each dimension scores 0–100. ASI = weighted average across the 12 dimensions.

### ASI Threshold Model

| ASI Range | State | Action |
|-----------|-------|--------|
| 90–100 | Stable | Passive monitoring |
| 75–89 | Mild drift | Investigate, increase sampling |
| 60–74 | Moderate drift | Page on-call, begin root-cause |
| <60 | Severe drift | Halt autonomous mode, escalate |

Drift is detectable after a median of 73 interactions (IQR: 52–114). Nearly 50% of agents show measurable drift by 600 interactions.

### The ASI Monitoring Loop

```python
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ASIDimensions:
    # Semantic (weight: 0.30)
    instruction_adherence: float = 100.0   # cosine sim vs. golden instruction trace
    policy_threshold: float = 100.0        # % of decisions within defined policy bounds
    decision_logic: float = 100.0          # consistency of decision rules over rolling window
    tradeoff_accuracy: float = 100.0       # alignment of权衡 analysis with ground truth

    # Behavioral (weight: 0.40)
    response_length_trend: float = 100.0   # drift in output token count over time
    tool_call_pattern: float = 100.0       # KL divergence of tool selection distribution
    self_correction_rate: float = 100.0    # % of errors corrected vs. repeated
    emotional_mode: float = 100.0         # embedding drift in response style/tonality

    # Coordination (weight: 0.30) — multi-agent only
    handoff_precision: float = 100.0      # semantic fidelity of agent-to-agent context transfer
    state_consistency: float = 100.0      # agreement on shared state variables
    resource_contention: float = 100.0    # false-positive contention signals
    session_boundary: float = 100.0       # preservation of session-scoped context

    def compute_asi(self) -> float:
        semantic = np.mean([
            self.instruction_adherence, self.policy_threshold,
            self.decision_logic, self.tradeoff_accuracy
        ])
        behavioral = np.mean([
            self.response_length_trend, self.tool_call_pattern,
            self.self_correction_rate, self.emotional_mode
        ])
        coordination = np.mean([
            self.handoff_precision, self.state_consistency,
            self.resource_contention, self.session_boundary
        ])
        return (semantic * 0.30 + behavioral * 0.40 + coordination * 0.30)

    def alert_level(self) -> str:
        asi = self.compute_asi()
        if asi >= 90: return "STABLE"
        if asi >= 75: return "MILD"
        if asi >= 60: return "MODERATE"
        return "SEVERE"


class DriftMonitor:
    """Rolling ASI tracker with alerting and checkpoint comparison."""

    def __init__(self, baseline: ASIDimensions, window: int = 200):
        self.baseline = baseline
        self.asi_history: deque = deque(maxlen=window)
        self.dimension_history: dict[str, deque] = {
            dim: deque(maxlen=window) for dim in self._dim_names()
        }

    def _dim_names(self):
        return [k for k in ASIDimensions.__dataclass_fields__]

    def record(self, dims: ASIDimensions):
        self.asi_history.append(dims.compute_asi())
        for name in self._dim_names():
            self.dimension_history[name].append(getattr(dims, name))

    def detect(self, current: ASIDimensions, threshold: float = 75.0) -> dict:
        asi = current.compute_asi()
        degraded = []
        for name in self._dim_names():
            baseline_val = getattr(self.baseline, name)
            current_val = getattr(current, name)
            drift = baseline_val - current_val
            if drift > (100 - threshold):
                degraded.append({"dimension": name, "drift_pct": drift})
        return {
            "asi": asi,
            "alert": asi < threshold,
            "level": current.alert_level(),
            "degraded_dimensions": degraded,
            "trend": (
                "WORSENING"
                if len(self.asi_history) >= 10 and asi < np.mean(list(self.asi_history)[:-10])
                else "STABLE"
            ),
        }

    def ghost_lexicon_check(self, early_outputs: list[str], current_outputs: list[str]) -> float:
        """Detect when domain vocabulary disappears from outputs (LangGraph #7327)."""
        if not early_outputs or not current_outputs:
            return 100.0
        # Simple Jaccard on unique word sets; production: embedding overlap
        early_vocab = set(" ".join(early_outputs).lower().split())
        current_vocab = set(" ".join(current_outputs).lower().split())
        vocab_retention = len(early_vocab & current_vocab) / len(early_vocab | current_vocab | {""})
        return vocab_retention * 100.0


# Usage: integrate into your agent harness
def on_agent_turn(turn_output: str, turn_number: int, monitor: DriftMonitor):
    dims = ASIDimensions(
        instruction_adherence=score_instruction_trace(turn_output),
        policy_threshold=score_policy_bounds(turn_output),
        decision_logic=score_decision_consistency(turn_output),
        tradeoff_accuracy=score_tradeoff_analysis(turn_output),
        response_length_trend=100.0,       # computed from rolling window
        tool_call_pattern=100.0,           # computed from tool trace
        self_correction_rate=score_self_correction(turn_output),
        emotional_mode=score_style_consistency(turn_output),
    )
    monitor.record(dims)
    result = monitor.detect(dims)
    if result["alert"]:
        page_oncall(
            f"ASI={result['asi']:.1f} [{result['level']}] — "
            f"degraded: {[d['dimension'] for d in result['degraded_dimensions']]}"
        )
    return result
```

### Drift Compensation Strategies by Severity

| Severity | ASI Drop | Intervention |
|----------|----------|--------------|
| Mild | 10–15 pts | Increase eval sampling rate, compact context |
| Moderate | 15–25 pts | Trigger memory compaction cycle, re-ground agent |
| Severe | >25 pts | Full agent reset to last stable checkpoint, root-cause investigation |

Compaction must be task-aware: a refund-handling agent and an infrastructure-alerting agent require different retention priorities.

### ASI as an Agentic SLO

ASI is not a diagnostic — it is a Service Level Objective. Treat it like any other SLO:

```yaml
# asi-slo.yaml
slo:
  target: 85.0        # composite ASI target
  window: 7d         # rolling evaluation window
  burn_rate_threshold: 1.5  # error budget burn multiplier
  alert:
    mild:    75.0     # increase sampling
    moderate: 60.0    # page oncall
    severe:  50.0    # halt autonomous mode
```

Connect ASI drops to your eval pipeline: each degraded dimension generates synthetic test cases targeting that specific failure mode, feeding them back into the evaluation harness (see [S-1803](s1803-the-measured-agent-stack-when-your-agent-passes-all-tests-and-fails-in-production.md)).

## Receipt

> Verified 2026-07-29 — Framework sourced from arXiv:2601.04170 (Rath, Jan 2026), cheesecat.net ASI implementation guide, agentmarketcap.ai drift case studies, LangGraph GitHub #7327. ASI formula and 12-dimension taxonomy confirmed against primary sources. Threshold model from production implementation guides. Python implementation is a reference-quality reconstruction of the documented pattern.

## See also

- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — qualitative drift taxonomy (precedes the ASI framework)
- [S-651 · Agentic SLOs](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — the six metrics that define agent quality SLOs
- [S-736 · Agent Error Budgets](s736-agent-error-budgets-quality-that-burns.md) — operationalizing agent quality as a burnable budget
- [S-1803 · The Measured Agent Stack](s1803-the-measured-agent-stack-when-your-agent-passes-all-tests-and-fails-in-production.md) — eval-to-production closed loop
- [S-1241 · The Long-Horizon Collapse](s1241-the-long-horizon-collapse-when-your-agent-slowly-falls-apart-over-hours-not-seconds.md) — HORIZON benchmark on super-linear agent degradation
