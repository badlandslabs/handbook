# S-2033 · The Agent Trust Calibration Stack — When Your Team Trusts the Wrong Agent and Overrides the Right One

Your agent has a 91% task completion rate. Your team overrides it on 60% of outputs anyway. Meanwhile, the agent that actually breaks things — the one with the 74% rate — gets approved on sight because it "looks confident." You don't have a model problem. You have a **trust calibration problem**: the human side of the human-agent loop has no instrumentation.

GJETA 2026 analyzed 34 verified sources on trust in agentic AI systems and confirmed: *"Trust miscalibration, encompassing both over-reliance and under-reliance, constitutes the most prevalent failure mode in deployed agentic systems, and current transparency tools remain inadequate for supporting informed human oversight at operational scale."* The Anthropic Research team (Feb 2026), analyzing millions of Claude Code and API interactions, found the same pattern across domains. Today, the EU AI Act's enforcement of human oversight obligations makes this an actual compliance surface, not just a soft UX concern.

## Forces

- **Trust is a dynamic accumulation, not a static property.** Human trust in an agent changes with every interaction — correctly. But without instrumentation, that change happens invisibly, in the wrong direction, and without a record.
- **Over-trust and under-trust are both learnable and both costly.** Over-trust produces approved wrong outputs. Under-trust produces unnecessary interruptions that eliminate the agent's value proposition. Teams migrate to one failure mode or the other and never notice.
- **Token probability correlates poorly with accuracy post-RLHF.** The standard uncertainty signal — logprob, entropy — degrades after fine-tuning. Teams that build escalation on token confidence are building on sand.
- **Trust drifts faster than capability.** An agent that performs at 90% in week 1 may perform at 78% in week 8 (behavioral drift, data staleness, upstream API changes). Human trust, once earned, decays slowly. The gap compounds silently.
- **Static autonomy levels are insufficient.** S-355 maps L0–L5; S-1261 maps model confidence. Neither maps the human's calibrated trust level — the thing that actually determines whether a human approves or overrides.

## The Move

The fix is a three-layer instrumentation stack that makes human trust legible, tunable, and self-correcting.

### 1. Instrument the trust signal explicitly

Track three signals per session, per agent, per task type:

```python
class TrustSignal:
    approval_rate: float        # outputs approved / outputs presented
    override_rate: float        # human changed output / outputs presented
    override_direction: dict   # {"weaken": N, "strengthen": N, "reject": N}

    # The trust ratio: above this → agent operates autonomously
    # below this → escalate before output
    trust_ratio: float = approval_rate / (override_rate + 0.01)

    # Overtime drift: does trust_ratio decay session-over-session?
    trust_trajectory: list[float]

class TrustInstrument:
    def record(self, task_type: str, agent_output: Any,
               human_action: str, session_id: str):
        # human_action: "approve" | "weaken" | "strengthen" | "reject"
        # Persist to per-task-type trust log
        self.log.append({
            "ts": now(),
            "session": session_id,
            "task_type": task_type,
            "action": human_action,
        })

    def trust_ratio(self, task_type: str, lookback: str = "7d") -> float:
        window = self.filter(lookback=lookback, task_type=task_type)
        approved = sum(1 for e in window if e["action"] == "approve")
        overridden = sum(1 for e in window if e["action"] != "approve")
        return approved / (overridden + 0.01)
```

### 2. Dynamic breakpoints: trust-ratio-driven escalation

Replace static autonomy levels with trust-ratio gates that auto-escalate when the human's calibrated trust drops:

```python
class TrustBreakpoint:
    """
    Breakpoints are not static gates — they are trust-ratio thresholds
    that adjust based on recent human behavior.
    """
    def __init__(self, task_type: str, baseline_trust: float = 0.9):
        self.task_type = task_type
        self.baseline = baseline_trust
        # Adaptive threshold: starts at baseline, tightens as agent earns trust
        self.threshold = baseline_trust

    def should_escalate(self, agent_output, task_type: str) -> bool:
        ratio = trust_instrument.trust_ratio(task_type)

        # Tighten threshold if trust is high and stable
        if ratio > 0.95:
            self.threshold = max(0.7, self.threshold - 0.02)
        # Widen threshold if trust is eroding
        elif ratio < 0.75:
            self.threshold = min(0.99, self.threshold + 0.05)

        # Escalate if stakes exceed current trust
        return agent_output.stakes > self.threshold

    def log_decision(self, agent_output, escalated: bool):
        # Future trust_ratio will reflect this decision
        trust_instrument.record(
            task_type=agent_output.task_type,
            agent_output=agent_output,
            human_action="escalated" if escalated else "auto-approved",
            session_id=agent_output.session_id,
        )
```

### 3. Detect over-trust and under-trust regimes

```python
class TrustRegimeDetector:
    """
    Trust miscalibration has two failure modes with opposite causes.
    Detecting which regime you're in is step one.
    """
    def classify_regime(self, task_type: str) -> str:
        ratio = trust_instrument.trust_ratio(task_type)
        agent_reliability = self.get_agent_reliability(task_type)

        if ratio > 0.95 and agent_reliability < 0.85:
            return "OVER_TRUST"   # agent is breaking things; human keeps approving
        elif ratio < 0.6 and agent_reliability > 0.9:
            return "UNDER_TRUST"  # agent is fine; human keeps overriding
        elif ratio < 0.75 and agent_reliability < 0.75:
            return "CALIBRATED"   # human is correctly skeptical
        else:
            return "CALIBRATED"

    def remediate(self, regime: str, task_type: str):
        if regime == "OVER_TRUST":
            # Force mandatory review for high-stakes outputs
            # Show failure rate in the approval UI
            send_alert(f"{task_type}: OVER_TRUST detected — override rate {self.override_rate:.0%}")
        elif regime == "UNDER_TRUST":
            # Show human the agent's longitudinal track record
            # Reduce friction: one-click approve instead of manual edit
            send_report(f"{task_type}: UNDER_TRUST — agent reliability {self.agent_reliability:.0%}, human approval rate {self.approval_rate:.0%}")
```

### 4. The trust budget

Treat trust like a currency with a burn rate. Every high-stakes output spends trust; every successful unassisted completion earns it back:

```python
class TrustBudget:
    def __init__(self, session_id: str, budget: float = 1.0):
        self.balance = budget

    def spend(self, stakes: float) -> bool:
        if self.balance >= stakes:
            self.balance -= stakes
            return True  # agent may proceed
        return False    # force escalation

    def earn(self, task_completed: bool):
        if task_completed:
            self.balance = min(1.0, self.balance + 0.05)

    def state(self) -> dict:
        return {"balance": self.balance, "status": "nominal" if self.balance > 0.3 else "depleted"}
```

## Receipt

> Verified 2026-08-02 — Research synthesis: GJETA 2026 (doi:10.30574/gjeta.2026.27.3.0137, Chidiebere Ugo-Enyinnah), Zylos Research (2026-05-27), Anthropic Research Measuring Agent Autonomy (Feb 2026), Nylas Agentic AI Report 2026 (1,000+ respondents), CloudZero Agentic AI Cost analysis (July 2026). Core finding confirmed across all: trust miscalibration is the dominant operational failure mode, and it is addressable with instrumentation that most teams lack.

## See also

- [S-355 · Agent Autonomy Levels: Bounded Autonomy](s355-agent-autonomy-levels-bounded-autonomy.md) — static L0–L5 classification; this entry adds the dynamic human-trust layer
- [S-1261 · The Confidence Calibration Stack](s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — model-side calibration (the agent's certainty); this entry covers the human-side (the operator's trust)
- [S-938 · Governance Threshold Stack](s938-the-governance-threshold-stack-when-your-escalation-gate-is-a-rubber-stamp.md) — escalation gates as rubber stamps; the trust calibration stack makes those gates legible and adaptive
