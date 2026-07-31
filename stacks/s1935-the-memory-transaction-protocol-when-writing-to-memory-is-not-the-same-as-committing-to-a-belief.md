# S-1935 · The Memory Transaction Protocol — When Writing to Memory Is Not the Same as Committing to a Belief

Your agent calls a weather API. The API returns a garbled response. The agent summarizes it as "rain expected all day" and writes it to its memory profile. Tomorrow, every task uses that summary as a ground-truth premise for routing and decisions. The API was wrong for 20 minutes. Your agent will be wrong until something overwrites that profile entry — or until someone notices.

The core mistake: **every agent memory system conflates recording an observation with committing a belief.** In database systems, these are separate operations. In agent memory, they are the same write. That equivalence is the source of the most insidious class of silent failures in production agents.

## Forces

- **A memory write is not a belief commit.** When a tool returns a result, the agent summarizes it and stores the summary. That summary is immediately retrievable, immediately quotable, and immediately acted on — even if the tool was wrong, the summary was wrong, or the summary is now stale.
- **Compounding errors have no circuit breaker.** A wrong fact in memory becomes the premise for the next retrieval, which generates the next write, which overwrites the previous entry. The error compounds silently. There is no "this was a draft" concept in most agent memory systems.
- **Validation is retrospective, not prospective.** Most memory systems validate after the fact — if an error is noticed, someone corrects it. But agents make autonomous decisions between the write and the correction. The damage is already done.
- **Polluted beliefs survive context resets.** An agent that has internalized a wrong belief as a memory entry will re-express it even after the tool that caused the error is fixed, even after the context window is cleared, even after the session ends. The belief is persistent. The source is gone.
- **No provenance, no quarantine.** Most systems store what was written and when — but not whether it was validated, who validated it, or what the validation result was. A write that failed validation looks identical to one that passed.

## The move

Treat every memory write as a **tentative transaction**, not an immediate belief. Implement an 8-state belief lifecycle:

```
raw → tentative → validated → committed → action-safe
                ↘ quarantined (validation failed)
                ↘ superseded (adjudicated out)
                ↘ revoked (terminated)
                ↘ staged (awaiting manual review for high-stakes writes)
```

**The rule:** Only entries in `action-safe` state can drive tool calls with real side effects. Entries in `tentative` or `staged` can be retrieved for context but trigger a validation pass before use in write operations.

### State transitions

| Transition | Trigger | Who |
|---|---|---|
| raw → tentative | Memory write | Agent |
| tentative → validated | Automated check (source health, freshness, cross-reference) | System |
| tentative → quarantined | Automated check fails (contradiction detected, source timeout, malformed) | System |
| validated → committed | Threshold confidence reached | System |
| committed → action-safe | Entry used in successful side-effect-free task | System |
| committed → revoked | Downstream contradiction detected | System |
| staged → superseded | Manual review rejects | Human |

### Minimal working example

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

class BeliefState(Enum):
    RAW = "raw"
    TENTATIVE = "tentative"
    VALIDATED = "validated"
    COMMITTED = "committed"
    ACTION_SAFE = "action_safe"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    STAGED = "staged"

@dataclass
class BeliefRecord:
    id: str
    content: str
    source: str  # tool_name, user_input, agent_reflection
    source_timestamp: datetime
    state: BeliefState = BeliefState.RAW
    confidence: float = 0.0
    validated_by: Optional[str] = None
    validation_timestamp: Optional[datetime] = None
    superseded_by: Optional[str] = None
    revision_of: Optional[str] = None  # parent belief ID

    def can_drive_action(self) -> bool:
        """Only action-safe entries can drive side-effecting tool calls."""
        return self.state == BeliefState.ACTION_SAFE

    def can_retrieve(self) -> bool:
        """All states except revoked are retrievable for context."""
        return self.state != BeliefState.REVOKED

    def can_write(self) -> bool:
        """Only committed+ entries can propagate beliefs to memory."""
        return self.state in (
            BeliefState.COMMITTED,
            BeliefState.ACTION_SAFE,
        )


class MemoryTransactionLog:
    """
    Append-only log of all belief lifecycle events.
    Enables full replay and audit trail.
    """

    def __init__(self):
        self.entries: list[BeliefRecord] = []

    def write(self, record: BeliefRecord) -> None:
        # Every write starts as TENTATIVE — never committed immediately
        record.state = BeliefState.TENTATIVE
        self.entries.append(record)

    def validate(self, record_id: str, checks: dict) -> bool:
        """
        Run automated validation checks.
        Returns True if all checks pass.
        """
        record = self._get(record_id)
        passed = all(checks.values())
        record.state = BeliefState.VALIDATED if passed else BeliefState.QUARANTINED
        record.validated_by = "automated"
        record.validation_timestamp = datetime.utcnow()
        return passed

    def commit(self, record_id: str, confidence: float) -> None:
        record = self._get(record_id)
        assert record.state == BeliefState.VALIDATED, "Can only commit validated records"
        record.confidence = confidence
        record.state = BeliefState.COMMITTED

    def promote_to_action_safe(self, record_id: str) -> None:
        record = self._get(record_id)
        if record.can_drive_action():
            record.state = BeliefState.ACTION_SAFE

    def revoke(self, record_id: str, superseded_by: str) -> None:
        """Mark a committed belief as revoked and superseded."""
        record = self._get(record_id)
        record.state = BeliefState.REVOKED
        record.superseded_by = superseded_by

        # Create the superseding record with lineage
        superseding = self._get(superseded_by)
        superseding.revision_of = record_id

    def _get(self, record_id: str) -> BeliefRecord:
        return next(e for e in self.entries if e.id == record_id)


# Usage guard in the agent loop
def execute_with_belief_guard(log: MemoryTransactionLog, belief_id: str, tool_fn):
    belief = log._get(belief_id)

    if not belief.can_write():
        raise BeliefNotActionableError(
            f"Belief {belief_id} is in state {belief.state.value} "
            f"— cannot drive memory write. Validate first."
        )

    return tool_fn()
```

### Key invariants

1. **No automatic promotion.** A write never becomes `action_safe` without passing through validation. Not even slowly. Not even if confidence is high.
2. **Quarantine is a sink, not a filter.** Entries that fail validation do not get retried automatically. They require either a new observation or manual review.
3. **Revocation creates lineage.** When a belief is revoked, the superseding belief points back to it. The full audit trail is reconstructable.
4. **Staged for high-stakes.** Entries that would drive irreversible actions (payments, deletions, external API calls) should go through `staged` → manual review before `committed`.

## Receipt

> Verified 2026-07-31 — Primary sources extracted: MemTX (arXiv:2607.23929, Jul 2026) from Pavamana AI Labs proposes the 8-state belief lifecycle with quarantine/superseded/revoked states. The Hard 70% post (pavamana.ai, May 2026) documents the three corruption paths (hallucination, bad tool result, planted record) and the compounding pattern. MemTX evaluation on TravelPlanner shows 91.3% belief accuracy vs 64.8% baseline. arXiv:2605.16746 (May 2026, State Contamination in Memory-Augmented LLM Agents) independently confirms the failure mode. TOKI (arXiv:2606.06240) bitemporal operator algebra for contradiction resolution is a complementary approach.

## See also

- [S-1189 · The Memory Integrity Gate](stacks/s1189-the-memory-integrity-gate-when-your-agents-memory-starts-lying-to-itself.md) — memory evolution and distortion over time; this entry covers the transactional prevention mechanism
- [S-1052 · The Cascade Stack](stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — provenance tagging across handoffs; complements the record-commit pattern
- [S-1047 · The Agentic Dead Letter Queue](stacks/s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — checkpoint/replay patterns; this entry adds the belief-state dimension to recovery
