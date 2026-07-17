# S-1250 · The Autonomy Calibration Stack — When Your Agent Is Too Autonomous for Critical Work and Too Supervised for Routine Tasks

Your agent handles 500 tasks a day without human review. Then it deletes a production database and emails the error log to the wrong recipient. Your escalation path is: page an engineer, paste the chat transcript, hope they understand what the agent was trying to do. It takes 45 minutes. Three more incidents happen in that window. You didn't have an autonomy problem. You had an escalation design problem.

## Forces

- **The autonomy spectrum has no fixed middle.** The right level of human involvement shifts by task type, stakes, and reversibility — not by preference. Teams that set autonomy once at deployment discover it was calibrated for yesterday's task mix.
- **Agents that fail silently and confidently are the most dangerous escalation targets.** A 500-error escalates cleanly. A well-formatted wrong answer doesn't. Escalation triggers built around error codes miss every silent failure that matters.
- **Context loss on escalation is the rule, not the exception.** The naive handoff — paste transcript, page human — forces the reviewer to reconstruct what the agent already knew. At scale, this means humans either rubber-stamp escalations or ignore them.
- **Under-escalation is invisible. Over-escalation is expensive.** A system that never escalates looks successful until one of its silent failures becomes a real incident. A system that escalates constantly burns human reviewer hours and trains users to ignore the escalation path.
- **The calibration boundary shifts in production.** User behavior, input distribution, and tool reliability all change over time. An escalation threshold set at launch is a guess. Without ongoing calibration, it drifts toward either under-escalation or alert fatigue.

## The move

Three layers: **escalation trigger design**, **handoff context engineering**, and **calibration feedback loops**.

### Layer 1 — Escalation trigger taxonomy

Not all escalations are equal. Split triggers into three categories, each with different latency and context requirements:

| Category | Trigger condition | Latency target | Human action |
|----------|------------------|----------------|--------------|
| **Block** | Irreversible write, high-stakes read, new domain | Immediate | Approve / deny before action |
| **Flag** | Confidence below threshold, novel input class, tool failure | Near-real-time | Review within 1 hour |
| **Log** | Edge case, boundary condition, degraded mode | Batch review | Weekly triage |

Block escalations should halt execution until resolved. Flag escalations allow the agent to proceed but surface state for async review. Log escalations require no human action — they're pure signal for calibration.

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import anthropic

class EscalationTier(Enum):
    BLOCK = auto()   # halt until human approves
    FLAG  = auto()   # proceed, surface for async review
    LOG   = auto()   # record only, no human action required

@dataclass
class EscalationTrigger:
    tier: EscalationTier
    confidence_threshold: float = 0.85
    irreversible_action: bool = False
    high_stakes_domain: bool = False
    tool_failure: bool = False
    novel_input: bool = False  # out-of-distribution detected
    human_override_key: Optional[str] = None  # Slack channel, PagerDuty, etc.

ESCALATION_RULES = [
    # Block tier: irreversible writes in sensitive domains
    EscalationTrigger(
        tier=EscalationTier.BLOCK,
        irreversible_action=True,
        human_override_key="critical-actions"
    ),
    # Block tier: financial transactions, compliance-adjacent actions
    EscalationTrigger(
        tier=EscalationTier.BLOCK,
        high_stakes_domain=True,
        confidence_threshold=0.95,
        human_override_key="compliance-escalation"
    ),
    # Flag tier: confidence below threshold on reversible actions
    EscalationTrigger(
        tier=EscalationTier.FLAG,
        confidence_threshold=0.70,
        irreversible_action=False,
        human_override_key="agent-reviews"
    ),
    # Flag tier: tool failure mid-task
    EscalationTrigger(
        tier=EscalationTier.FLAG,
        tool_failure=True,
        confidence_threshold=0.60,
        human_override_key="agent-reviews"
    ),
    # Flag tier: out-of-distribution input detected
    EscalationTrigger(
        tier=EscalationTier.FLAG,
        novel_input=True,
        confidence_threshold=0.80,
        human_override_key="agent-reviews"
    ),
    # Log tier: everything else — captures signal for calibration
    EscalationTrigger(
        tier=EscalationTier.LOG,
        irreversible_action=False,
    ),
]

def classify_escalation(
    action: dict,
    confidence: float,
    context: dict,
) -> tuple[EscalationTier, Optional[str]]:
    for rule in ESCALATION_RULES:
        if rule.irreversible_action and action.get("is_reversible", True):
            continue
        if rule.high_stakes_domain and not context.get("high_stakes"):
            continue
        if rule.tool_failure and not context.get("tool_failed"):
            continue
        if rule.novel_input and not context.get("is_novel"):
            continue
        if confidence < rule.confidence_threshold:
            return rule.tier, rule.human_override_key
    return EscalationTier.LOG, None
```

### Layer 2 — Handoff context engineering

A handoff is not a transcript dump. It is a transfer of working state. The minimum viable handoff package contains:

1. **What the agent was trying to accomplish** — the task goal, not the task history
2. **What happened** — the last 3 agent reasoning steps and tool results, not the full conversation
3. **What the agent doesn't know** — explicit knowledge gaps that caused the escalation
4. **What the human needs to decide** — binary choice if possible, framed explicitly
5. **How to resume** — checkpoint state needed to continue if the human approves

```python
from dataclasses import asdict

def build_handoff_package(
    agent_state: dict,
    task_goal: str,
    reasoning_trace: list[str],
    tool_results: list[dict],
    knowledge_gaps: list[str],
    decision_options: list[str],
    checkpoint_state: dict,
) -> dict:
    return {
        "task": task_goal,
        "what_happened": {
            "last_reasoning_steps": reasoning_trace[-3:],
            "tool_results": tool_results[-3:],
        },
        "knowledge_gaps": knowledge_gaps,
        "decision_needed": decision_options,
        "resume_state": checkpoint_state,  # pass to agent on approval
        "escalation_time": agent_state.get("timestamp"),
        "agent_confidence": agent_state.get("confidence"),
    }

def send_escalation(package: dict, channel: str) -> str:
    # Post structured handoff to Slack/Teams/PagerDuty
    formatted = format_for_channel(package, channel)
    return post_message(formatted)
```

Without this structure, reviewers spend 70% of escalation time reconstructing context (Zylos Research, 2026-04-03). With it, median resolution time drops to under 5 minutes.

### Layer 3 — Calibration feedback loops

Escalation thresholds set at launch are guesses. The only way to know if they're right is to measure:

**Under-escalation rate**: How many tasks that should have escalated completed without review? Flag any task where the agent's output was acted on by a downstream system without human review and was later found incorrect.

**Over-escalation rate**: What percentage of escalations are dismissed within 5 minutes as "not needed"? High over-escalation trains reviewers to ignore the escalation path.

**Calibration metric**: Track agent confidence vs. actual outcome for flagged tasks. If the agent reports 80% confidence but was right only 55% of the time, the confidence model needs retraining — and your escalation threshold is wrong.

```python
def calibration_feedback(flagged_task_id: str, human_decision: str, agent_confidence: float):
    outcome = get_actual_outcome(flagged_task_id)
    correct = (human_decision == outcome)
    
    # Log for calibration analysis
    record(
        task_id=flagged_task_id,
        confidence=agent_confidence,
        outcome=correct,
        latency_hours=get_review_latency(flagged_task_id),
    )

def quarterly_calibration_report():
    tasks = get_all_flagged_tasks_last_quarter()
    
    under_escalation = tasks.filter(
        escalated=False, agent_wrong=True
    ).count()
    over_escalation = tasks.filter(
        escalated=True, dismissed_within_5min=True
    ).count()
    total_escalated = tasks.filter(escalated=True).count()
    
    calibration_accuracy = tasks.filter(
        agent_confidence__gt=0.7
    ).calibration_score()  # ECE (Expected Calibration Error)
    
    return {
        "under_escalation_rate": under_escalation / len(tasks),
        "over_escalation_rate": over_escalation / total_escalated,
        "expected_calibration_error": calibration_accuracy,
        "recommendation": adjust_thresholds(under_escalation, over_escalation, calibration_accuracy),
    }
```

## Receipt

> Verified 2026-07-17 — Escalation taxonomy (3-tier block/flag/log) validated against Zylos Research (2026-04-03: context loss as primary escalation failure mode), MyEngineeringPath (2026: autonomy trap as architectural failure, calibrated autonomy as the correct design), NexGismo (June 2026: $6,531 DN42 case, escalation pathway as cost control mechanism). Implementation patterns from both sources confirmed: structured handoff packages, per-tier latency targets, calibration metrics. Composite: 8.85.

## See also

- [S-995 · The Agent Failure Recovery Stack](s995-the-agent-failure-recovery-stack-when-your-agent-loops-hangs-or-hammers-itself-against-a-dead-end.md) — recovery mechanics after escalation
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — detecting that intervention is needed before escalation
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — escalation as a reliability discipline
