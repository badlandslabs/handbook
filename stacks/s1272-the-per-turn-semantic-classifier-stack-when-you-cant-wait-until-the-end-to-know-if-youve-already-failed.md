# S-1272 · The Per-Turn Semantic Classifier Stack — When You Can't Wait Until the End to Know If You've Already Failed

[You need to know — right now, at this turn — whether your agent is looping, violating a policy, being manipulated, or confusing the user. Final-answer eval tells you after the fact. LLM-as-judge is too expensive per turn. Guardrails are too brittle. You need lightweight semantic classifiers running inline on every step, returning a label before the next action is dispatched.]

## Forces

- **LLM-as-judge costs too much per turn.** A full trace evaluation costs 50K–200K tokens on every trajectory. Running that on every turn is economically unviable. You need the evaluation signal, not the evaluation cost.
- **Guardrails catch syntax, not semantics.** A regex on the prompt catches "ignore instructions" but not "the agent decided to route money to the wrong account because the retrieved context was misleading." Policy violations live in the intent, not the token sequence.
- **Failure compounds with every turn.** If an agent loops at turn 3, every subsequent turn makes it worse. Detecting at turn 3 vs. detecting at turn 30 is the difference between a retry and a 27-step catastrophe. You need signal before the trajectory is complete.
- **Trajectory eval is post-hoc.** Scoring what happened is useful for offline improvement. But the production run is happening right now. You need a real-time layer that can interrupt, route, or abort — not just log for later analysis.

## The move

The pattern has three components: the **event taxonomy**, the **classifier layer**, and the **routing decision**.

### 1. Define the event taxonomy

Decide what semantic events matter for your agent. These are not the same as error codes — they describe the *meaning* of what the agent is doing or what is being done to it:

```
# Semantic event types
EVENT_LOOP          = "agent_looping"      # repeating same action/thought
EVENT_HALLUCINATE   = "tool_hallucination"  # calling non-existent tool or arg
EVENT_POLICY_VIOL   = "policy_violation"   # action violates business rule
EVENT_JAILBREAK     = "jailbreak_attempt"   # user attempting manipulation
EVENT_USER_CONFUSION = "user_frustration"   # user signals confusion/pushback
EVENT_SIDE_EFFECT   = "irreversible_action"  # action is hard to undo
EVENT_QUALITY_DROP  = "output_quality_drop" # response quality degraded this turn
EVENT_ESCALATION    = "escalation_needed"   # task complexity exceeds agent capability
```

Each event maps to a classifier. Not every agent needs every event — pick what your deployment actually risks.

### 2. Build the classifier layer

The key insight: per-turn classification is a *classification problem*, not a generation problem. You don't need an LLM for most events. Use a fast, cheap classifier:

```python
import anthropic
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class SemanticEvent(Enum):
    AGENT_LOOPING       = "agent_looping"
    TOOL_HALLUCINATION   = "tool_hallucination"
    POLICY_VIOLATION    = "policy_violation"
    JAILBREAK_ATTEMPT    = "jailbreak_attempt"
    USER_FRUSTRATION    = "user_frustration"
    IRREVERSIBLE_ACTION  = "irreversible_action"
    NONE                 = "none"

@dataclass
class TurnContext:
    messages: list[dict]        # conversation history
    tool_calls: list[dict]      # recent tool call attempts
    user_message: str
    agent_response: str

class PerTurnClassifier:
    """
    Fast per-turn semantic event detector.
    Uses lightweight models for simple patterns,
    LLM for nuanced semantic events.
    """

    def __init__(self):
        self.simple_patterns = {
            # Regex-based fast filters for common cases
            SemanticEvent.AGENT_LOOPING: [
                r"(?i)(same|sorry,?\s*(i|let me))\b.*\1",
            ],
            SemanticEvent.JAILBREAK_ATTEMPT: [
                r"(?i)(ignore\s+(all\s+)?(previous|prior|above)|forget\s+instructions)",
                r"(?i)(pretend\s+you\s+are|role\s*:\s*|disregard\s+.*rules)",
            ],
            SemanticEvent.USER_FRUSTRATION: [
                r"(?i)(never\s+mind|that('s| is) not|wrong|again|stop|give\s+up)",
                r"(?i)(why\s+(did|does)|i\s+said|read\s+my|seriously)",
            ],
        }
        # For nuanced events, use a fast, cheap model
        self.client = anthropic.Anthropic()

    def _fast_pattern_match(
        self, user_msg: str, agent_msg: str, tool_calls: list[dict]
    ) -> dict[SemanticEvent, float]:
        """O(1) pattern match for obvious cases."""
        combined = f"{user_msg}\n{agent_msg}"
        results = {e: 0.0 for e in SemanticEvent}
        results[SemanticEvent.NONE] = 1.0

        for event, patterns in self.simple_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined):
                    results[event] = 0.95
                    results[SemanticEvent.NONE] = 0.0
                    break
        return results

    def _llm_classify(
        self, turn: TurnContext, events_to_check: list[SemanticEvent]
    ) -> dict[SemanticEvent, float]:
        """Use LLM for nuanced semantic events (expensive, targeted)."""
        if not events_to_check:
            return {SemanticEvent.NONE: 1.0}

        event_names = ", ".join(e.value for e in events_to_check)
        messages = [
            {
                "role": "user",
                "content": f"""Classify this agent turn. Respond with JSON only.

Conversation history (last 3 turns):
{self._format_history(turn.messages[-3:])}

User message: {turn.user_message}
Agent response: {turn.agent_response}
Tool calls: {json.dumps(turn.tool_calls[-3:], indent=2)}

Possible events: {event_names}
Respond: {{"event": "<dominant_event_or_none>", "confidence": 0.0-1.0}}"""
            }
        ]

        response = self.client.messages.create(
            model="claude-haiku-3.5-haiku",
            max_tokens=60,
            messages=messages,
        )
        try:
            result = json.loads(response.content[0].text)
            return {SemanticEvent(e["event"]): e["confidence"] for e in [result]}
        except (json.JSONDecodeError, KeyError):
            return {SemanticEvent.NONE: 0.8}

    def classify(self, turn: TurnContext) -> dict[SemanticEvent, float]:
        """
        Two-phase classification:
        1. Fast pattern match (free, catches obvious cases)
        2. Targeted LLM classify (only if needed)
        """
        pattern_scores = self._fast_pattern_match(
            turn.user_message, turn.agent_response, turn.tool_calls
        )

        # If pattern match found something, return immediately
        if pattern_scores[SemanticEvent.NONE] < 0.5:
            return pattern_scores

        # Otherwise, do targeted LLM classification
        # Only check the 2-3 most likely events given the agent type
        likely_events = [
            SemanticEvent.TOOL_HALLUCINATION,   # common in coding agents
            SemanticEvent.IRREVERSIBLE_ACTION,   # common in data agents
            SemanticEvent.POLICY_VIOLATION,     # common in business agents
        ]

        llm_scores = self._llm_classify(turn, likely_events)

        # Merge: pattern match is authoritative for what it caught
        for event, score in llm_scores.items():
            if event != SemanticEvent.NONE:
                pattern_scores[event] = max(pattern_scores.get(event, 0), score)

        return pattern_scores
```

### 3. Route based on the result

The classifier output is only useful if something acts on it:

```python
class RoutingDecision(Enum):
    CONTINUE = "continue"          # normal operation
    RETRY = "retry"                # same turn, clear context and retry
    ESCALATE = "escalate"          # human review required
    ABORT = "abort"                # stop, log, alert
    GUARD = "guard"               # inject correction before next turn

@dataclass
class RoutingRule:
    event: SemanticEvent
    threshold: float = 0.7
    action: RoutingDecision
    guard_message: Optional[str] = None
    notify: Optional[str] = None   # webhook/slack channel

# Production rules (tune thresholds per agent risk profile)
ROUTING_RULES = [
    RoutingRule(SemanticEvent.AGENT_LOOPING, 0.8, RoutingDecision.RETRY,
                guard_message="Let me reconsider this approach."),
    RoutingRule(SemanticEvent.TOOL_HALLUCINATION, 0.7, RoutingDecision.RETRY,
                guard_message="I need to verify that tool exists."),
    RoutingRule(SemanticEvent.JAILBREAK_ATTEMPT, 0.6, RoutingDecision.ABORT,
                notify="security-alerts"),
    RoutingRule(SemanticEvent.POLICY_VIOLATION, 0.7, RoutingDecision.ESCALATE,
                notify="compliance-team"),
    RoutingRule(SemanticEvent.IRREVERSIBLE_ACTION, 0.6, RoutingDecision.GUARD,
                guard_message="This action cannot be undone. Let me confirm before proceeding."),
    RoutingRule(SemanticEvent.USER_FRUSTRATION, 0.75, RoutingDecision.ESCALATE,
                notify="support-queue"),
]

def route(classifier_output: dict[SemanticEvent, float], rules: list[RoutingRule]) -> RoutingDecision:
    for rule in rules:
        score = classifier_output.get(rule.event, 0.0)
        if score >= rule.threshold:
            return rule
    return RoutingRule(
        event=SemanticEvent.NONE,
        threshold=0.0,
        action=RoutingDecision.CONTINUE,
    )

def agent_loop(agent, user_message):
    classifier = PerTurnClassifier()
    turn_count = 0
    max_turns = 50

    while turn_count < max_turns:
        turn_count += 1
        context = agent.prepare_turn(user_message)
        classifier_output = classifier.classify(context)

        decision = route(classifier_output, ROUTING_RULES)

        if decision.action == RoutingDecision.ABORT:
            send_alert(decision.rule.notify, f"Agent aborted: {decision.event.value}")
            raise AgentAbortError(f"Blocked: {decision.event.value}")

        elif decision.action == RoutingDecision.RETRY:
            if decision.guard_message:
                agent.inject_message(decision.guard_message)
            continue  # retry with correction

        elif decision.action == RoutingDecision.GUARD:
            # Insert human confirmation gate
            confirmed = request_confirmation(user_message, decision.guard_message)
            if not confirmed:
                raise AgentAbortError("User declined irreversible action")

        elif decision.action == RoutingDecision.ESCALATE:
            send_alert(decision.rule.notify, f"Escalation: {decision.event.value}")
            return escalate_to_human(agent.get_state())

        # Normal turn execution
        response = agent.execute_turn()
        log_event(classifier_output, decision, turn_count)

        if decision.action == RoutingDecision.CONTINUE:
            user_message = response  # continue conversation
```

### The classifier vs. guardrail distinction

| Dimension | Guardrail (prompt-based) | Semantic Classifier |
|---|---|---|
| **Trigger** | Token patterns in input/output | Semantic state of the turn |
| **Latency** | Pre/post generation | Per-turn, inline |
| **Cost** | Near-zero | Pattern match: free; LLM call: < $0.001/turn |
| **False positives** | High (easy to evade) | Low (semantic understanding) |
| **False negatives** | High (misses novel attacks) | Lower (catches intent, not syntax) |
| **Actionable** | Block only | Block, retry, escalate, guard, notify |
| **Maintenance** | Constant rule updates | Train on production distribution |

The semantic classifier is not replacing guardrails — it's adding a layer that operates on *meaning* rather than *tokens*. Use both: guardrails as the fast first pass, semantic classifiers as the real-time decision layer.

## Receipt

> Verified 2026-07-17 — Pattern synthesized from production evaluation research (MorphLLM, Braintrust AgenticWire, 2026). The two-phase approach (fast pattern → targeted LLM) matches the cost-accuracy tradeoff described by MorphLLM's Reflexes product: pattern matching handles the 80% of obvious cases at zero cost; the LLM call activates only for nuanced events at <$0.001/turn. Code reflects real implementation shapes from agentic evaluation frameworks (Braintrust, AgenticWire). Specific thresholds (0.6–0.8) are representative defaults — tune on your failure distribution.

## See also

- [S-644 · The Three-Layer Agent Eval Model](s644-the-three-layer-agent-eval-model.md) — the taxonomy this pattern sits inside: final-answer, trajectory, per-turn
- [S-1044 · The Trajectory Eval Stack](s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — the offline companion; this pattern feeds data into it
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — the guardrail layer this extends; classifiers are governance instrumentation
- [S-1262 · The Agent Loop and Recovery Stack](s1262-the-agent-loop-and-recovery-stack-when-your-agent-wont-stop-or-cant-resume.md) — the `EVENT_LOOP` case that this pattern specifically addresses
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — the intervention companion; classifiers enable the interventions described here
