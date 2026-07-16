# S-1002 · The Memory Consolidation Debt Stack

When your persistent agent starts contradicting itself, changing its mind, or "forgetting" things it learned last week — the problem is not memory capacity. It is memory consolidation debt.

## Situation

Your agent has been running for 45 days. It handles customer onboarding, triages support tickets, and updates a CRM. For the first two weeks it was reliable. Now it escalates cases it already resolved, proposes workflows it previously rejected, and argues with itself across sessions. The context window is fine. The model has not changed. The problem is that nothing ever gets properly consolidated — the agent accumulates experience but never integrates it into stable knowledge. The gap between *experienced* and *learned* is growing.

## Forces

- Agents need bounded context but unbounded knowledge — they accumulate observations faster than they integrate them
- Summarization is lossy — naive compression discards the relationships between facts, not just the facts themselves
- Stale information coexists with current information at equal weight — the model cannot tell which is older without explicit timestamps
- Contradictions accumulate silently — a fact established in week 1 and quietly contradicted in week 4 now competes with itself in the same context
- Context distillation at session boundaries is treated as a storage problem, not a learning problem — teams compress but never validate consistency
- Forgetting is framed as a failure, not a feature — agents that remember everything are praised even when remembering degrades reasoning

## The Move

### 1. Separate memory into three tiers with explicit consolidation triggers

```python
class MemoryConsolidationManager:
    """Three-tier memory with consolidation triggers and consistency validation."""

    def __init__(self, agent_id: str):
        self.working = WorkingMemory()      # current session — full fidelity
        self.episodic = EpisodicStore()     # past sessions — compressed summaries
        self.semantic = SemanticStore()      # consolidated facts — structured KB

    def consolidate_if_needed(self, session_transcript: list[Turn]) -> None:
        """Called at session boundary. Decide what to consolidate."""
        signals = self._assess_consolidation_signals(session_transcript)

        if signals.conflict_score > 0.3:
            # Detected contradiction between episodic and new observations
            self._run_conflict_resolution(session_transcript, signals)
            return  # skip standard consolidation until resolved

        if signals.importance_score > 0.7:
            # High-value observations → semantic store directly
            facts = self._extract_facts(session_transcript)
            self.semantic.upsert(facts, provenance=session_transcript.session_id)
        elif signals.novelty_score > 0.5:
            # Novel but lower value → episodic summary
            summary = self._summarize_with_structure(session_transcript)
            self.episodic.append(summary)
        # else: discard — not worth retaining

        self.working.clear()

    def _assess_consolidation_signals(self, transcript: list[Turn]) -> ConsolidationSignals:
        conflicts = self._detect_episodic_conflicts(transcript)
        importance = self._score_importance(transcript)
        novelty = self._score_novelty(transcript, self.semantic)
        return ConsolidationSignals(
            conflict_score=conflicts,
            importance_score=importance,
            novelty_score=novelty,
        )

    def _detect_episodic_conflicts(
        self, transcript: list[Turn]
    ) -> float:
        """Check if current session contradicts established semantic facts."""
        facts = self._extract_facts(transcript)
        conflicts = 0
        for fact in facts:
            existing = self.semantic.lookup(fact.subject)
            if existing and not self._compatible(existing, fact):
                conflicts += 1
        return conflicts / max(len(facts), 1)
```

### 2. Detect contradictions before they compound

The core insight from Zylos Research (June 2026): agents with unlimited memory exhibit contradictory behavior within 30–60 days. The fix is not more memory — it is active conflict detection at every consolidation boundary.

```python
def _compatible(self, existing: Fact, new: Fact) -> bool:
    """Check temporal and semantic compatibility between facts."""
    if existing.subject != new.subject:
        return True  # different subjects, no conflict

    # Same subject — check if one supersedes the other
    if existing.source_session < new.source_session:
        # Newer fact can supersede if it's a correction, not just disagreement
        return new.is_correction_of(existing) or new.timestamp > existing.timestamp
    return True  # existing is newer or same age

def _run_conflict_resolution(
    self, transcript: list[Turn], signals: ConsolidationSignals
) -> None:
    """When contradiction detected: surface, don't suppress."""
    conflicts = self._surface_conflicts(transcript)
    # Option A: mark both as disputed, escalate to human review
    # Option B: use temporal priority (newer fact wins)
    # Option C: use confidence-weighted merge
    for conflict in conflicts:
        self.semantic.mark_disputed(conflict.fact_id, transcript.session_id)
```

### 3. Implement selective forgetting — purpose-driven eviction

Not all memories should survive. The pattern: importance decay over time, explicit conflict-driven erasure, and privacy-triggered deletion.

```python
class SemanticStore:
    def importance_decay(self, days: int, decay_rate: float = 0.05) -> None:
        """Apply decay to facts not reinforced in N days."""
        stale = self.get_stale(days=days)
        for fact in stale:
            if fact.importance * (1 - decay_rate * days) < fact.importance_threshold:
                self.evict(fact, reason="importance_decay")

    def privacy_gc(self, privacy_policy: PrivacyPolicy) -> None:
        """Erase facts containing PII or subject to retention limits."""
        for fact in self.scan(contains_pii=True):
            self.evict(fact, reason="privacy_gc", audit_trail=True)
```

### 4. The consolidation contract — what "learned" means

A fact is consolidated (not just stored) when it satisfies:

1. **Temporal grounding** — has a timestamp or session ID
2. **Provenance chain** — traces back to a specific interaction, not inference
3. **Non-contradiction** — no active conflict with existing facts of same subject
4. **Reinforcement** — seen in at least 2 independent sessions
5. **Cross-validation** — confirmed by a second source or tool call

```python
@dataclass
class ConsolidationGate:
    temporal_grounded: bool
    provenance_traced: bool
    non_contradicting: bool
    reinforced: bool  # seen in 2+ sessions
    cross_validated: bool

    def passes(self) -> bool:
        # All criteria must pass for semantic store promotion
        return all([
            self.temporal_grounded,
            self.provenance_traced,
            self.non_contradicting,
            self.reinforced,
            self.cross_validated,
        ])
```

## Receipt

> Verified 2026-07-12 — Zylos Research (June 2026) documents that agents with unlimited memory exhibit contradictory behavior within 30–60 days. The LifelongAgentBench (ICLR 2026) finding that conventional experience replay has limited effectiveness due to irrelevant information and context length constraints. Code examples constructed from described patterns; not run against live system.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — foundational memory architecture
- [S-541 · Agent Drift Detection](s541-agent-drift-detection.md) — behavioral regression detection
- [S-591 · Embedding Drift](s591-embedding-drift-the-silent-rag-failure-mode.md) — how retrieval degrades over time
- [S-917 · Capability Erosion Under Self-Evolution](s917-the-capability-erasure-stack-when-self-improvement-becomes-self-destruction.md) — related degradation pattern in self-modifying agents
