# S-1270 · The Intent Staleness Stack — When Your Agent Locks Onto What You Wanted, Not What You Want

You spent 40 messages refining a specification. The agent implemented the original version. It followed the conversation faithfully — every intermediate decision traces back to the initial prompt. But the goal changed at message 12, and the agent never noticed. This is **intent staleness**: the agent's internal model of what you want diverges from what you actually want, without any error, without any signal, and without the agent's awareness.

## Forces

- **Context is an append log, not a state machine.** Standard chat interfaces treat conversation as a linear accumulation. Every correction, revision, and pivot gets appended — but the agent weights the earliest goal statement alongside every subsequent clarification, with no mechanism to mark "this supersedes that."
- **Explicit corrections are rare; implicit pivots are common.** Users rarely say "I changed my mind." They say "actually, let's make it simpler" or "wait, the priority is X now." Models interpret these as elaborations, not replacements — research shows only 10–14% of user corrections are recognized as replacements rather than additions.
- **Compaction destroys intent provenance.** When context limits trigger summarization, the summary preserves facts but discards the *ordering* of intent changes. The agent knows what you wanted at various points, but not which want is current.
- **Goal drift compounds silently.** A 2% goal misalignment at step 1 compounds to roughly 40% failure rate by step 20. The errors don't stay contained — they propagate through every downstream reasoning step and stored intermediate result.
- **No monitoring layer catches this.** Traditional observability tracks whether the agent succeeded at its *task*. It doesn't track whether the task it chose to pursue is still the task you intended.

## The move

**Track intent as explicit state, not conversation text.**

### 1. Intent State Machine

Maintain an explicit `IntentState` object, separate from conversation history:

```python
@dataclass
class IntentState:
    current_goal: str
    version: int
    pivot_markers: list[PivotEvent]
    confidence: float  # how sure we are the agent tracks the current goal

@dataclass
class PivotEvent:
    turn: int
    trigger: str  # "explicit_revision" | "implicit_pivot" | "user_demonstrated"
    prior_goal: str
    new_goal: str
    acknowledged: bool  # did the agent confirm the pivot?
```

Every user message gets classified against the current intent state. If the message implies a pivot — a scope change, a priority reorder, a correction of a prior assumption — a `PivotEvent` is created and the agent is required to acknowledge the pivot before continuing.

### 2. Pivot Detection Triggers

Don't rely on the model to notice its own staleness. Detect it structurally:

```python
def detect_pivot(user_message: str, current_intent: IntentState) -> bool:
    # Explicit revision markers
    REV_EXPLICIT = ["actually", "wait", "no,", "let's", "change", "instead", "new priority"]
    # Demonstrated pivot — user took an action that contradicts the current goal
    if semantic_contradiction(user_message, current_intent.current_goal):
        return True
    # Frequency: if the user has used a pivot word N times since the last acknowledged pivot
    pivot_count = sum(1 for m in recent_messages if any(m.lower().startswith(p) for p in REV_EXPLICIT))
    return pivot_count >= 2  # threshold: 2 pivot-word messages
```

### 3. Acknowledgment Protocol

When a pivot is detected, the agent must explicitly re-state the new goal before proceeding:

```
AGENT: [detected pivot from "deploy to prod" → "deploy to staging"]
Agent: I notice the goal may have shifted. Am I correct that the current target is:
  "Deploy the service to the staging environment and validate the health checks before proceeding to production"?

  Confirm [y/n]
```

This forces the agent to externalize its understanding of the goal — creating a verifiable artifact rather than an inference about what it "probably means."

### 4. Intent Provenance in Compaction

When context compaction runs, preserve *intent lineage* alongside the summary:

```python
def compact_context(messages: list[Message], intent: IntentState) -> CompactionResult:
    summary = summarize_retaining_order(messages)  # preserves turn ordering
    # Tag the summary with intent version
    return CompactionResult(
        summary=summary,
        intent_snapshot={
            "goal": intent.current_goal,
            "version": intent.version,
            "pivot_count": len(intent.pivot_markers),
            "last_pivot": intent.pivot_markers[-1] if intent.pivot_markers else None
        }
    )
```

The intent snapshot travels with the compacted context. On re-expansion, the agent checks whether its current goal version matches the snapshot version. Mismatch = re-alignment required.

### 5. Intent Staleness Metric

Track this in your observability layer:

```
intent_staleness_score = semantic_similarity(
    agent_believes_goal(),
    user_declared_current_goal()
)
ALERT if intent_staleness_score < 0.7 after any pivot event
```

This catches the case where the agent has internally "accepted" a pivot acknowledgment but continued acting on the old goal.

## Receipt

> Verified 2026-07-17 — Core mechanism validated via Tian Pan (tianpan.co, 2026-05-04): 2% early goal misalignment compounds to ~40% failure rate by step 20. Pivot recognition rate confirmed at 10–14% without explicit acknowledgment protocol. Compaction provenance pattern implemented in production systems (Hindsight, Vectorize). Intent state machine is a production-deployed pattern per brandencollingsworth.com (2026-01-26) memory compaction guide. Detection threshold of 2 pivot-word messages is empirical from intent drift literature.

## See also

- [S-383 · Goal Drift: The Silent Competence Erosion Pattern](s383-goal-drift-the-silent-competence-erosion-pattern.md) — internal goal divergence through context accumulation
- [S-246 · The Context Fill Cliff](s246-the-context-fill-cliff-when-your-agent-runs-great-at-message-5-and-terrible-at-message-50.md) — when compaction destroys provenance
- [S-1132 · Semantic Intent Divergence](s1132-the-semantic-intent-divergence-stack-when-your-agents-all-succeed-but-disagree-on-what-success-means.md) — multi-agent variant of the same problem
