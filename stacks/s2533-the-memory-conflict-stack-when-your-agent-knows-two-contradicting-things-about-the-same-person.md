# S-2533 · The Memory Conflict Stack — When Your Agent Knows Two Contradicting Things About the Same Person

Your agent has been running for 30 days. It remembers that the user's name is Alice Chen. It also remembers that the user's name is Bob Martinez. It retrieves both on different queries and uses whichever one surfaced first. The user has never mentioned Bob. Alice never mentioned changing her name. The agent is not hallucinating — it genuinely stored two conflicting facts about the same entity and has no mechanism to choose between them. This is the memory conflict problem: persistent agents accumulate conflicting knowledge across sessions, and without explicit conflict resolution, the system silently picks winners based on retrieval order rather than truth.

The MemConflict framework (arXiv:2605.20926, Tao et al. 2026) is the first diagnostic benchmark to taxonomize memory conflicts operationally. It identifies three distinct conflict types that each require different resolution logic. Understanding which type you have is the first step toward fixing it.

## Forces

- **Memory systems grow faster than they are governed.** Every session adds facts, preferences, and summaries to persistent storage. Most systems write without checking whether the new information contradicts what is already stored. Over time, conflicts accumulate silently — the agent retrieves conflicting facts without knowing they conflict.
- **Retrieval rank determines truth, not accuracy.** Vector similarity and recency bias in retrieval mean the most recently retrieved or most semantically similar memory wins — regardless of whether it is the correct version. A conflict between "Alice lives in NYC" and "Alice moved to SF" resolves to "SF" simply because SF was stored more recently or embedded more similarly to the query. This is a selection failure, not a hallucination.
- **Temporal validity windows are rarely enforced.** Agents treat all stored facts as equally valid regardless of when they were recorded. A preference expressed in session 3 may have been superseded in session 17. Without validity tracking, the system cannot distinguish "current truth" from "superseded state."
- **Conflicts propagate downstream and launder themselves.** A multi-agent system where one agent resolves a conflict and writes the resolution to shared state propagates that resolution — and any error in it — to all downstream agents. The Hallucination Laundry Problem (S-1067) applies here: a conflict resolved incorrectly looks identical to a conflict resolved correctly from every downstream consumer.

## The move

### Classify the conflict type first

| Conflict Type | Root Cause | Resolution Principle |
|---|---|---|
| **Dynamic** | State changed since last record | Prefer the temporally latest fact |
| **Static** | Factual error or mis-read | Use source authority ranking |
| **Preference** | Multiple conflicting preferences | Apply recency + context relevance |

### Layer 1 — Conflict Detection at Write Time

Before storing a new memory item, check for conflicts against existing memories for the same subject. Do not store facts — store fact trees:

```python
class MemoryItem:
    subject: str
    predicate: str
    value: Any
    timestamp: datetime
    source_session: str
    validity_window: Optional[tuple[datetime, datetime]] = None
    superseded_by: Optional[str] = None

def store_memory(subject, predicate, value, session_id, timestamp):
    # Check for existing conflicting facts about this subject
    existing = memory_store.query(subject=subject, predicate=predicate)
    
    for item in existing:
        if item.value != value:
            # Conflict detected — classify and resolve
            conflict_type = classify_conflict(item, value)
            resolved = resolve_conflict(item, value, conflict_type)
            
            if resolved == "new_wins":
                item.superseded_by = f"{subject}:{predicate}:{timestamp}"
                memory_store.update(item)  # mark old as superseded
                memory_store.insert(MemoryItem(
                    subject=subject, predicate=predicate, value=value,
                    timestamp=timestamp, source_session=session_id
                ))
            elif resolved == "keep_existing":
                pass  # don't overwrite
            elif resolved == "flag":
                yield ConflictFlag(subject, predicate, item.value, value)
                # Surface to user or human review queue
```

### Layer 2 — Validity Window Tracking

Facts have validity windows. "User prefers dark mode" was true from March to July. "User prefers light mode" is true from July onward. Without temporal tracking, both are equally valid at query time:

```python
# Temporal validity: dynamically prefer the most recent relevant fact
def retrieve_memory(subject, predicate, query_time: datetime):
    candidates = memory_store.query(subject=subject, predicate=predicate)
    
    # Filter to items whose validity window contains query_time
    valid = [
        c for c in candidates
        if c.validity_window is None 
        or c.validity_window[0] <= query_time <= c.validity_window[1]
    ]
    
    # If no validity-windowed items, fall back to recency
    if not valid:
        valid = sorted(candidates, key=lambda c: c.timestamp, reverse=True)
    
    # Conflict = 2+ items still valid after filtering
    if len(valid) > 1:
        raise MemoryConflictError(
            subject=subject, predicate=predicate,
            candidates=valid
        )
    
    return valid[0] if valid else None
```

### Layer 3 — Source Authority Ranking for Static Conflicts

When a fact disagreement is not a state change but a factual error (one version is simply wrong), temporal recency does not help. Rank by source authority:

```python
SOURCE_AUTHORITY = {
    "direct_user_input": 1.0,
    "confirmed_action": 0.9,
    "document_scan": 0.7,
    "inferred_preference": 0.5,
    "cross_session_carryover": 0.3,
}

def resolve_static_conflict(candidates: list[MemoryItem]) -> MemoryItem:
    scored = [(SOURCE_AUTHORITY[c.source_type] * recency_weight(c), c) 
              for c in candidates]
    scored.sort(reverse=True)
    return scored[0][1]
```

### Layer 4 — Conflict Audit Log

Every resolution decision gets logged. This is not just for debugging — it creates the feedback signal for improving the resolver:

```python
def log_resolution(subject, predicate, winner, losers, strategy, confidence):
    audit_log.insert(ConflictResolution(
        subject=subject,
        predicate=predicate,
        winner_id=winner.id,
        loser_ids=[l.id for l in losers],
        strategy=strategy,       # "temporal_latest", "authority_ranked", etc.
        confidence=confidence,   # 0.0–1.0
        resolved_at=datetime.now(),
        reversible=True,         # flag if future evidence could overturn
    ))
```

Marking resolutions as `reversible=True` is the critical signal: dynamic conflicts can be re-broken by new facts. Static conflicts resolved via authority are low-reversibility. The audit log feeds back into evaluator data — every resolved conflict is a training example for the next resolver.

### Layer 5 — HaluMem Diagnostic Evaluation

Run the operation-level evaluation from HaluMem (arXiv:2511.03506) to identify which stage of your memory pipeline is producing conflicts. The three stages are:

- **Storage hallucinations** — what you write to memory is wrong
- **Retrieval hallucinations** — the right memory exists but the wrong one surfaces
- **Reasoning hallucinations** — both memories are retrieved correctly but the agent reasons to the wrong one

Most teams optimize for one stage (usually storage) and leave the others unmeasured. MemConflict covers stages 1 and 2 specifically; combine it with HaluMem's reasoning-stage diagnostics for full coverage.

## Receipt

> Verified 2026-08-12 — Memory conflict taxonomy from MemConflict (arXiv:2605.20926, Tao et al. 2026) and HaluMem (arXiv:2511.03506, Chen et al. 2025). Three conflict types confirmed (dynamic/static/preference). Validity window and source authority patterns implemented in representative Python. No live deployment data — receipt pending production validation.

## See also

- [S-1067 · The Hallucination Laundry Problem](s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — downstream propagation of incorrect resolutions
- [S-1002 · The Memory Consolidation Debt Stack](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — the write-path symptom this addresses at storage time
- [S-1020 · The Tiered Memory Stack](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — episodic/semantic/procedural tiering that makes conflicts harder to detect without explicit cross-tier resolution
- [S-1043 · The Dreaming Pattern](s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — consolidation cycles that can accidentally resolve conflicts incorrectly if no explicit resolver exists
