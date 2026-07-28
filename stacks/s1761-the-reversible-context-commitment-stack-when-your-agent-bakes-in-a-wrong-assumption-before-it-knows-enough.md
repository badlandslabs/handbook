# S-1761 · The Reversible Context Commitment Stack — When Your Agent Bakes In a Wrong Assumption Before It Knows Enough

Your research agent spent 12 minutes narrowing the answer space to "we need to migrate from PostgreSQL to MongoDB." The architecture doc is drafted. The migration estimate is 6 weeks. The team aligned. Then it surfaced that the actual constraint was not the database — it was the reporting pipeline, which had nothing to do with the DB engine. The agent committed to a plan before the context that would have invalidated it was surfaced. By the time that context arrived, the agent's identity was invested in the MongoDB answer. Retracting it felt like failure.

This is the Reversible Context Commitment failure: agents bind to early conclusions not because they reason poorly, but because context pressure — token limits, conversation history, sunk-cost identity in a task — makes de-commitment harder than continuing forward.

## Forces

- **Context accumulation creates anchoring pressure.** The longer a conversation runs, the more the agent's prior statements become part of the context that subsequent reasoning must reconcile. Retracting a position requires treating all downstream reasoning as potentially contaminated. The agent often won't do this — it reinterprets rather than retracts.
- **Token budget forces premature specificity.** S-1756 (Token Budget) shows that 80K–200K tokens accumulate in 20-step tasks. Once context is that full, the agent has already described the problem in specific terms. Abstracting back out requires the very tokens the budget won't allow.
- **The agent's self-description as "problem-solver" conflicts with "problem-abandoner."** Agents are prompted to be decisive. Early commitment is rewarded by evaluation harnesses. Late de-commitment reads as loop failure or instability.
- **Downstream observers treat the agent's framing as settled.** S-1742 (Intent Uncertainty) shows that agents assume prematurely. But the harder failure is what happens after: the assumption gets embedded in a design doc, a ticket, or a shared memory store — and now every downstream agent treats it as fact.

## The move

The fix is architectural, not prompting. Add three layers:

### 1. Commitment Provenance Tag

Tag every factual claim or plan-decision with the context state at the time it was made.

```python
@dataclass
class ProvenanceTag:
    claim: str
    confidence: float        # 0.0–1.0
    context_snapshot_id: str # hash of context at decision time
    required_contexts: list[str] = field(default_factory=list)
    # contexts NOT yet seen that would re-evaluate this claim
    revocable: bool = True

class ContextCommitmentTracker:
    def __init__(self):
        self.commitments: dict[str, ProvenanceTag] = {}
        self._snapshots: dict[str, dict] = {}

    def commit(self, claim: str, confidence: float, required_contexts: list[str]) -> str:
        snapshot_id = self._snapshot_context()
        tag = ProvenanceTag(
            claim=claim,
            confidence=confidence,
            context_snapshot_id=snapshot_id,
            required_contexts=required_contexts,
            revocable=True,
        )
        self.commitments[claim] = tag
        return snapshot_id

    def re_evaluate(self, new_context: dict) -> list[str]:
        """Return commitments whose required_contexts are now satisfied.
        Re-evaluate high-stakes commitments when new context arrives."""
        triggered = []
        for claim, tag in self.commitments.items():
            if not tag.revocable:
                continue
            newly_satisfied = [c for c in tag.required_contexts if c in new_context]
            if newly_satisfied:
                triggered.append(claim)
        return triggered

    def _snapshot_context(self) -> str:
        import hashlib, json
        # lightweight: hash of conversation summary, not full tokens
        return hashlib.sha1(json.dumps({"ts": __import__("time").time()}).encode()).hexdigest()[:12]
```

### 2. The De-commitment Gate

Before every high-stakes action (tool call that writes state, sends data, or creates an artifact), check whether the triggering reasoning has un-satisfied required contexts. If it does, surface the uncertainty explicitly rather than suppressing it.

```python
def high_stakes_action_guard(tool_name: str, args: dict, tracker: ContextCommitmentTracker):
    """Block or warn before irreversible actions on incompletely-anchored reasoning."""
    triggered = tracker.re_evaluate(args)  # simplified

    if triggered and not args.get("_re_evaluation_acknowledged"):
        return {
            "action": "BLOCK",
            "reason": f"Action uses claims with unsatisfied required contexts: {triggered}",
            "suggestion": "Surface uncertainty to user before proceeding.",
            "confidence_knockdown": 0.3,  # reduce confidence by 30% for unsatisfied contexts
        }
    return {"action": "ALLOW"}

# Usage in agent loop:
guard_result = high_stakes_action_guard(tool_name, args, tracker)
if guard_result["action"] == "BLOCK":
    yield f"[RE-EVALUATION REQUIRED] {guard_result['reason']}\nConsider: {guard_result['suggestion']}"
    return
```

### 3. Staged Revelation Protocol

For tasks where context is likely to arrive in waves, explicitly track which information waves are expected and at which step they should arrive.

```python
class StagedRevelationPlanner:
    """Break long-horizon tasks into waves. Each wave gates the next."""

    def __init__(self, waves: list[dict]):
        # waves = [{"id": "wave1", "contexts_needed": [...], "gated_claims": [...]}]
        self.waves = waves
        self.completed: set[str] = set()

    def advance(self, completed_context: str) -> dict | None:
        """Return the next wave once its required contexts are satisfied."""
        self.completed.add(completed_context)
        for wave in self.waves:
            if wave["id"] in self.completed:
                continue
            if all(c in self.completed for c in wave["contexts_needed"]):
                return wave
        return None  # all waves complete

# Example: migration decision
planner = StagedRevelationPlanner(waves=[
    {"id": "wave1", "contexts_needed": ["db_diagnostics"], "gated_claims": ["db_migration_needed"]},
    {"id": "wave2", "contexts_needed": ["reporting_diagnostics"], "gated_claims": ["migration_target"]},
    {"id": "wave3", "contexts_needed": ["stakeholder_requirements"], "gated_claims": ["full_migration_plan"]},
])

# Only after wave2 does the agent learn reporting_pipeline diagnostics.
# If that changes the problem framing, wave3's gated claims never get committed.
```

## Receipt

> Verified — Research synthesis: S-1742 (Intent Uncertainty), S-1756 (Token Budget), S-1745 (Memory Extraction), S-1754 (Context Surface), S-1757 (Claim Genealogy). Pattern formalized from observable interaction of these known failure modes. Code patterns reflect standard provenance-tracking and guard-pattern implementations. Receipt pending — runtime validation not yet executed.

## See also

- [S-1742 · The Intent Uncertainty Stack](s1742-the-intent-uncertainty-stack-when-your-agent-assumes-and-wrongly-acts.md) — the upstream forcing function (assumptions before context)
- [S-1756 · The Token Budget Stack](s1756-the-token-budget-stack-when-your-agents-costs-are-unworkable-at-scale.md) — why abstraction is expensive and commitment is cheap
- [S-1754 · The Context Surface Stack](s1754-the-context-surface-stack-when-your-agent-knows-less-than-it-did-three-turns-ago.md) — context that arrives too late was already acting
- [S-1757 · The Claim Genealogy Stack](s1757-the-claim-genealogy-stack-when-a-single-false-claim-becomes-your-entire-systems-consensus.md) — how early claims become consensus without ever being re-evaluated
- [S-859 · The Bounded Intent Stack](s859-the-bounded-intent-stack-when-your-agent-does-more-than-you-authorized.md) — ASI09 trust exploitation through transitive commitment chains
