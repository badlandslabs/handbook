# S-1682 · The Escalation Architecture Stack — When Your Agent Hits the Wall and Nobody Is There

Your agent encounters a task that exceeds its capability ceiling — a domain it's unfamiliar with, a decision with irreversible consequences, or a confidence threshold it can't clear. In a fully autonomous system, it either acts without sufficient certainty or stalls. In a production system, it should escalate — but "escalation" is not a boolean flag. It's an architecture. Most teams that add human-in-the-loop do it as an afterthought, wiring a blocking dialog into a single point in the workflow. The result is a system that either over-escalates (every task waits for a human) or under-escalates (high-stakes actions bypass the gate). The pattern that works: risk-stratified, context-preserving, audit-logged escalation as a first-class architectural primitive.

## Forces

- **Full autonomy is only safe below the capability ceiling.** An agent that can handle 80% of tasks independently will confidently mishandle the other 20%. That 20% contains your highest-stakes, most expensive, most legally sensitive decisions. Treating it the same as the 80% is a liability.
- **Blocking escalation kills throughput.** Pausing a production workflow for human approval introduces latency, creates queue backlog, and trains operators to approve reflexively — defeating the purpose. Escalation must be fast, informative, and surgical, not a full workflow freeze.
- **Context does not survive naive handoffs.** A human asked to approve an agent's action without the full reasoning trace cannot make an informed decision. You must preserve not just what the agent decided, but why — the tool outputs, the intermediate conclusions, the confidence signals, and the alternatives considered.
- **Escalation is a first-class action, not an exception handler.** Tacking it onto the error path means it only triggers on obvious failures. Real escalation needs to trigger on uncertainty, risk classification, and capability boundary detection — not just on raised exceptions.
- **Operators need to act, not investigate.** If approving an escalation requires the human to re-run the agent's research to understand what they're approving, they won't do it. The escalation payload must be a self-contained briefing, not a link to a trace.

## The Move

### 1. Classify Risk Before You Escalate

Every agent action carries a risk profile along two axes: **impact severity** (what happens if this goes wrong) and **reversibility** (can we undo it). Map these to a 2×2:

| | **Reversible** | **Irreversible** |
|---|---|---|
| **Low impact** | Proceed autonomously | Warn + proceed |
| **Medium impact** | Warn + proceed | Escalate |
| **High impact** | Escalate | Hard stop + escalate |

This isn't a hard-coded lookup table — it's a risk classification function that runs before every action. For a coding agent: file writes are medium impact; `git push --force` or `DROP TABLE` are high impact. For a research agent: web search is low impact; sending an email is high impact. The function can reference a policy registry, a tool-risk manifest, or a model-based risk estimator. The key is that it fires at decision time, not at exception time.

```python
from enum import Enum, auto
from dataclasses import dataclass

class Impact(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()

class Reversibility(Enum):
    REVERSIBLE = auto()
    IRREVERSIBLE = auto()

@dataclass
class RiskProfile:
    impact: Impact
    reversibility: Reversibility

def classify_action(action: dict) -> RiskProfile:
    tool = action.get("tool")
    args = action.get("args", {})

    # Tool-risk manifest
    HIGH_IMPACT_TOOLS = {"send_email", "delete_records", "git_push_force",
                         "drop_table", "execute_sql_write", "transfer_funds"}
    IRREVERSIBLE_MODIFIERS = {"--force", "DANGEROUS", " destructive": True}

    if tool in HIGH_IMPACT_TOOLS:
        impact = Impact.HIGH
    elif tool in {"write_file", "update_record", "api_post"}:
        impact = Impact.MEDIUM
    else:
        impact = Impact.LOW

    reversibility = Reversibility.REVERSIBLE
    for modifier in IRREVERSIBLE_MODIFIERS:
        if modifier in str(args):
            reversibility = Reversibility.IRREVERSIBLE
            break

    return RiskProfile(impact, reversibility)

def should_escalate(profile: RiskProfile) -> bool:
    return (profile.impact == Impact.HIGH or
            (profile.impact == Impact.MEDIUM and
             profile.reversibility == Reversibility.IRREVERSIBLE))
```

### 2. Preserve Full Reasoning Context in the Escalation Payload

When escalation triggers, the human needs a self-contained briefing — not a link to follow or a trace to reconstruct. Structure the payload around the `5W`:

```python
@dataclass
class EscalationPayload:
    action: str              # What the agent wants to do
    reasoning: str           # Why it chose this action
    alternatives: list[str] # What else it considered and rejected
    confidence: float        # 0.0–1.0, model-reported
    tool_outputs: list[str]  # Raw outputs that informed the decision
    risk_profile: RiskProfile
    session_id: str
    undo_plan: str          # How to reverse this if it goes wrong
    human_can_veto: bool    # Is this a hard stop or advisory?

def build_escalation_payload(agent_state: AgentState,
                               proposed_action: dict,
                               confidence: float) -> EscalationPayload:
    return EscalationPayload(
        action=f"{proposed_action['tool']}({proposed_action['args']})",
        reasoning=agent_state.last_reasoning_trace[-3:],  # last 3 steps
        alternatives=agent_state.rejected_alternatives[-3:],
        confidence=confidence,
        tool_outputs=[t["output"] for t in agent_state.tool_history[-5:]],
        risk_profile=classify_action(proposed_action),
        session_id=agent_state.session_id,
        undo_plan=generate_undo_plan(proposed_action),
        human_can_veto=agent_state.policy.allows_veto(proposed_action["tool"]),
    )
```

### 3. Route to the Right Operator with Timeout Handling

Not every escalation needs the same human. A financial transaction approval goes to a finance manager; a data deletion goes to a data steward; a code deployment goes to a senior engineer. Implement a routing function with an escalating chain of custody:

```python
from enum import Enum, auto
from typing import Callable
import asyncio

class EscalationTier(Enum):
    L1_ADVISORY = auto()   # Human notified, agent proceeds if no response in 5 min
    L2_APPROVAL = auto()   # Agent pauses, human must approve within 30 min
    L3_HARD_STOP = auto()  # Agent stops, human must explicitly approve to proceed

ESCALATION_ROUTING = {
    Impact.HIGH: {
        Reversibility.IRREVERSIBLE: EscalationTier.L3_HARD_STOP,
        Reversibility.REVERSIBLE: EscalationTier.L2_APPROVAL,
    },
    Impact.MEDIUM: {
        Reversibility.IRREVERSIBLE: EscalationTier.L2_APPROVAL,
        Reversibility.REVERSIBLE: EscalationTier.L1_ADVISORY,
    },
}

async def escalate(payload: EscalationPayload,
                   notify_channels: list[Callable]) -> bool:
    tier = ESCALATION_ROUTING[payload.risk_profile.impact][
        payload.risk_profile.reversibility
    ]

    routing = {
        "financial": ["#finance-approvals"],
        "destructive": ["#data-stewards"],
        "code": ["#engineering-oncall"],
        "default": ["#agent-oversight"],
    }
    channel_key = routing.get(payload.risk_profile.impact.name.lower(), "default")
    channels = [c for key, ch in zip(channel_key, notify_channels)
                for c in ch if key in routing]

    for channel in channels:
        await channel.send(payload)  # Slack, PagerDuty, email, etc.

    timeout = {"L1_ADVISORY": 300, "L2_APPROVAL": 1800, "L3_HARD_STOP": 3600}[
        tier.name
    ]

    if tier == EscalationTier.L1_ADVISORY:
        # Proceed after timeout if no veto received
        return await wait_with_default(payload.session_id, timeout, default=True)
    elif tier == EscalationTier.L2_APPROVAL:
        return await wait_for_decision(payload.session_id, timeout)
    else:  # L3_HARD_STOP
        decision = await wait_for_decision(payload.session_id, timeout)
        if decision is None:
            raise EscalationTimeout(f"No decision on {payload.action} in {timeout}s")
        return decision
```

### 4. Audit the Decision and Its Context

Every escalation creates a permanent record: what was escalated, what context was provided, who decided, what they decided, and how long it took. This audit log serves three purposes: regulatory compliance, operator performance review, and pattern analysis to improve the risk classifier over time.

```python
@dataclass
class EscalationRecord:
    payload: EscalationPayload
    decision: str           # "approved", "rejected", "vetoed", "timeout"
    decided_by: str         # operator identity
    latency_seconds: float  # time-to-decision
    model_version: str      # for classifier drift analysis
    timestamp: str
```

## Contrarian Angle

Most teams add escalation because they don't trust the agent. They treat it as a safety net. The right frame is different: escalation is a **capability router**. The goal is not to prevent the agent from acting — it's to route each action to the right decision-maker (agent or human) based on who is actually better equipped to evaluate it. An agent that escalates correctly is not failing; it's exhibiting good judgment. Over-escalation is a failure of the risk classifier, not a sign of insufficient agent capability.

## See also

- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — the risk classification function in this entry extends the capability ceiling threshold model from a binary hard/soft ceiling to a continuous risk surface
- [S-996 · The Harness Matters More Stack](s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — escalation is part of the production harness; the 92.5% human-delivery statistic motivates the pattern
- [S-1286 · The Handoff Contract](s1286-the-handoff-contract-when-your-agent-hands-off-work-and-the-context-goes-missing.md) — escalation is a specialized handoff between agent and human, with the same context-preservation requirements
