# [S-1189] · The Memory Integrity Gate — When Your Agent's Memory Starts Lying to Itself

You shipped a customer-support agent with a memory layer. After 60 days it starts making confident, wrong decisions — citing past resolutions it never reached, following workflows it tested and rejected, applying lessons from poisoned interactions. The retrieval traces are clean. The embedding quality is fine. The problem is that your memory system is **evolving** — and evolution without governance produces lies.

The distinction that changes everything: static RAG has no feedback loop. What you retrieve was what you stored. Evolving memory introduces a temporal feedback loop — what you retrieve was *processed* from something you stored, and that processing may have distorted it. Retrieval accuracy metrics miss this entirely.

## Forces

- **Memory evolution and execution share the same system.** Most architectures couple memory rewrite with inference. When the agent rewrites its own memory based on its own outputs, errors compound — a hallucination becomes a "fact" the next consolidation cycle locks in.
- **Retrieval accuracy ≠ memory integrity.** Every benchmark optimizes for "did the right thing come back?" But the failure mode in evolving memory is corruption *before* retrieval — wrong entries written, distorted summaries stored, conflicting beliefs both retrieved as true.
- **Governance at read-time is too late.** Access control and provenance checks on retrieval are necessary but insufficient. By the time you verify a retrieved entry, the damage is done if the entry was already written.
- **Stability-plasticity tradeoff is structural, not tunable.** Agents need to update memory (plasticity) to adapt. They also need stable knowledge that survives consolidation (stability). Treating this as a knob to tune produces systems that either freeze or drift — never both.

## The Move

**Decouple memory evolution from execution. Gate consolidation, not just retrieval.**

### 1. The Three-Point Failure Map

Evidently corrupt memory produces failures at three distinct points:

**Input ingestion** — malicious or hallucinated content becomes "valid knowledge." Unlike prompt injection (session-scoped), this persists into future sessions. MemoryGraft (Dec 2025) demonstrated >95% injection success against production agents using this vector.

**Consolidation processing** — each summarization pass introduces distortion. After N consolidation cycles, "the API uses exponential backoff with jitter" becomes "the API sometimes backs off." The delta compounds silently because summaries read fine in isolation.

**Retrieval conflict** — multiple entries from different consolidation cycles contradict each other, both retrieved as valid. The agent outputs whatever the ranker surfaces, unaware the runner-up was the truth.

```
Ingestion → [Poisoning] → Consolidation → [Semantic Drift] → Retrieval → [Conflict/Hallucination]
     ↑                                                              ↓
     └────────── Feedback Loop (errors compound) ←──────────────────┘
```

### 2. The Consistency Gate

Before any consolidation cycle runs, verify the proposed write. Three checks:

```python
# 1. Provenance: was the source material trustworthy?
def verify_provenance(entry, session_context):
    return entry.source_trust_score > THRESHOLD
    # Enforce: only consolidate from sessions that succeeded
    # Reject: entries sourced from failed/hallucinated sessions

# 2. Consistency: does this contradict established facts?
def verify_consistency(entry, semantic_memory):
    contradictions = query_semantic_memory(entry.fact_set, mode='contradiction')
    if contradictions:
        escalate_to_human()  # don't auto-resolve conflicts
    return len(contradictions) == 0

# 3. Temporal Decay: has this entry been consolidated too many times?
def verify_decay(entry):
    return entry.consolidation_count < MAX_CONSOLIDATION_PASSES
    # After N passes, lock the entry or compress to immutable snapshot
```

### 3. Temporal Decay Modeling

Not TTL-based expiry — structural decay. Each consolidation pass reduces fidelity. Model it explicitly:

```python
# Ebbinghaus-informed: memory value degrades exponentially with consolidation passes
# AND with time since last reinforcement
def memory_weight(entry, now):
    base = entry.importance_score
    consolidation_decay = DECAY_BASE ** entry.consolidation_count
    temporal_decay = 1 / (1 + DECAY_RATE * days_since(entry.last_accessed))
    retrieval_priority = base * consolidation_decay * temporal_decay
    
    # Lock entries that have been consolidated > 5× past their novelty
    if entry.consolidation_count > 5 and entry.novelty_score < 0.2:
        return retrieval_priority, LOCKED
    return retrieval_priority, WRITABLE
```

Different fact types need different decay profiles: user preferences → never decay, TTL ∞; ephemeral workflow state → decay in days; tool-call patterns → decay in weeks with outcome reinforcement.

### 4. Outcome-Gated Reinforcement

Most memory systems store what happened. The gap is storing *whether it worked*:

```python
# After task completion, write back outcome
def record_outcome(memory_entry_id, task_id, success, user_rating, corrected_output):
    entry = memory.get(memory_entry_id)
    entry.outcome_history.append(Outcome(
        success=success,
        user_rating=user_rating,
        corrected_output_hash=sha256(corrected_output) if corrected_output else None,
        timestamp=now()
    ))
    
    # Suppress entries that consistently produce failures
    if failure_rate(entry.outcome_history) > 0.3:
        entry.retrieval_score *= SUPPRESSION_FACTOR
        log_alert(f"Memory entry {entry.id} suppressed: {failure_rate:.1%} failure rate")
```

This is the largely-unexplored gap in production: outcome-weighted retrieval that surfaces memories *that led to good results*, not just memories that matched the query.

### 5. Immutable Snapshot Layer

For high-stakes facts (user identity, compliance rules, security boundaries), write once to an immutable layer:

```python
# High-assurance facts: written once, never consolidated
IMMUTABLE_MEMORY_TYPES = {
    'user_identity_assertions',
    'compliance_rules',
    'security_boundaries',
    'approved_workflow_signatures'
}

def write_memory(entry, memory_type):
    if memory_type in IMMUTABLE_MEMORY_TYPES:
        entry.layer = IMMUTABLE
        entry.consolidation_count = 0
        entry.lock()
    else:
        entry.layer = EVOLVING
    return store(entry)
```

The evolving layer degrades; the immutable layer does not. On conflict, immutable wins.

## Receipt

> Verified 2026-07-16 — Research sourced from: arXiv:2603.11768v2 "Governing Evolving Memory in LLM Agents" (Lam et al., Jinan University, May 2026); Mnemoverse AI Memory Landscape 2026; Vektor Memory State of AI Agent Memory (May 2026); CallSphere Ebbinghaus Decay (Apr/Jun 2026); A-MEM (Passion Labs, Jan 2026). No prior handbook entry covers governance-gated memory evolution (decoupled from execution). S-820 covers poisoning at ingestion; S-1002 covers consolidation debt; S-1043 covers dreaming cycles; I-079 covers confabulation; none cover the SSGM three-point failure map + consistency gate architecture.

## See also

- [S-820 · The Memory Poisoning Defense Stack](/stacks/s820-the-memory-poisoning-defense-stack-four-layers-against-asi06.md) — ingestion-layer poisoning; this entry covers what happens *after* poison is written
- [S-1002 · The Memory Consolidation Debt Stack](/stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — the debt problem; this entry covers the governance mechanism to prevent it
- [S-1043 · The Dreaming Pattern](/stacks/s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — consolidation cycle design; this entry covers the gate that guards the cycle
