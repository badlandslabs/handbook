# S-683 · Memory Arbitration: When Your Agent Knows But Doesn't Recall

Your agent has the memory. It was written there two sessions ago. A semantic search confirms it exists. And yet at the moment of decision, the agent acts as if it never knew — re-asking the user, violating a stated preference, repeating a mistake. The gap is not storage. The gap is between retrieval and context.

This is the **memory arbitration problem**: retrieved memories compete for a finite context window, and the winner is determined by embedding similarity — not by what the agent actually needs in this moment.

## Forces

- **Semantic search returns the most *similar* memory, not the most *important* one.** A user's explicit constraint ("never delete files in /data") lives in a 2-year-old conversation that no current query semantically resembles. The vector store returns nothing relevant; the agent acts without it.
- **LLMs bury information in the middle.** Liu et al. (2023) showed models attend unevenly to context — start and end positions get priority. A critical fact retrieved at position 2,000 tokens in a 128K context may be functionally invisible.
- **Top-K retrieval ignores compounding importance.** If you retrieve the top 20 memories by cosine similarity, you can still miss the one fact that should override everything else — because it ranked 21st on similarity and 1st on importance.
- **Memory poisoning exploits similarity ranking.** An eTAMP attack injects high-similarity, low-importance poison into the memory store. Semantic search dutifully returns it. The agent acts on the poisoned memory. Deduplication (S-150) handles exact collisions but not near-duplicate poisoning.
- **No source of truth in context assembly.** The orchestrator injects memories, conversation history, system prompt, and tool results — each from different pipelines — without an arbitration layer that says "this fact overrides that one."

## The move

Add an explicit **importance score** (0–10) to every memory entry. At retrieval time, combine embedding similarity with importance in a weighted scoring function. At context assembly time, use importance to resolve position and priority conflicts. Treat memory arbitration as a first-class pipeline stage, not a side effect of semantic search.

### Step 1 — Tag importance at write time

```python
class MemoryEntry:
    content: str
    embedding: list[float]
    importance: int          # 0–10, set at write time
    category: str            # "constraint", "preference", "fact", "episode"
    source_session: str
    written_at: datetime

# Importance assignment follows these rules:
#   10 = explicit user constraint ("never…", "always…", "do not…")
#    8 = foundational identity (name, role, organizational context)
#    6 = strong preference or established pattern
#    4 = general fact or episode
#    2 = transient or low-confidence
#    0 = scratch / intermediate — can be dropped under pressure
```

### Step 2 — Score retrieval with importance-weighted ranking

```python
def score_memory(entry: MemoryEntry, query_embedding: list[float], alpha: float = 0.7) -> float:
    """
    Combine embedding similarity with importance.
    alpha=0.7: similarity dominates. alpha=0.3: importance dominates.
    Tune based on your domain — high-stakes domains need higher alpha on importance.
    """
    sim = cosine_similarity(query_embedding, entry.embedding)

    # Normalize importance to [0, 1]
    norm_importance = entry.importance / 10.0

    # Importance gets a non-linear boost: importance² penalizes low-importance more
    importance_boost = norm_importance ** 2

    return alpha * sim + (1 - alpha) * importance_boost


def retrieve_memories(query: str, top_k: int = 20, alpha: float = 0.7) -> list[MemoryEntry]:
    query_embedding = embed(query)
    candidates = vector_db.search(query_embedding, top_k * 3)  # over-fetch
    scored = [(score_memory(e, query_embedding, alpha), e) for e in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]
```

### Step 3 — Enforce importance at context assembly

```python
def assemble_context(
    retrieved: list[MemoryEntry],
    max_context_tokens: int,
    constraint_budget: int = 512,      # tokens reserved for importance=10 facts
    enforce_minimum: bool = True,
) -> list[MemoryEntry]:
    """
    Arbitration layer: ensure importance=10 facts always make it to context,
    then fill remaining budget with scored memories.
    """
    constraints = [e for e in retrieved if e.importance >= 10]

    remaining = max_context_tokens - constraint_budget
    others = [e for e in retrieved if e.importance < 10]

    # Truncate others to remaining budget, keeping highest scores
    others_token_budget = remaining
    selected_others = []
    for entry in sorted(others, key=lambda e: (e.importance, len(e.content)), reverse=True):
        entry_tokens = estimate_tokens(entry.content)
        if others_token_budget >= entry_tokens:
            selected_others.append(entry)
            others_token_budget -= entry_tokens
        elif enforce_minimum:
            break  # stop before violating constraint budget

    return constraints + selected_others
```

### Step 4 — Protect against poisoning (the importance gate)

```python
def write_gate(entry: MemoryEntry, session_context: str) -> bool:
    """
    Before writing to the memory store, verify the entry isn't poisoned.
    Check: importance matches the content's actual stakes.
    """
    explicit_constraint_phrases = ["never", "do not", "always", "must not", "under no circumstances"]
    is_explicit_constraint = any(phrase in entry.content.lower() for phrase in explicit_constraint_phrases)

    if is_explicit_constraint and entry.importance < 10:
        # Flag for human review — an explicit constraint tagged below 10 is suspicious
        send_for_review(entry, reason="low_importance_on_explicit_constraint")
        return False

    if entry.importance >= 8 and entry.source_session != session_context:
        # High-importance memory from another session needs provenance
        entry.provenance = "cross_session_verified"
    return True
```

### Tuning guidance

| Domain | α (similarity weight) | Constraint budget | Notes |
|--------|-----------------------|-------------------|-------|
| Code generation / dev tools | 0.5 | 256 tokens | Accuracy matters; importance overrides similarity |
| Customer support | 0.7 | 384 tokens | Prioritize stated preferences and constraints |
| Research / analysis | 0.6 | 512 tokens | Facts compete; let importance break ties |
| High-stakes / compliance | 0.3 | 768 tokens | Safety constraints always win |

> Receipt pending — verification requires a live memory store with importance-weighted retrieval benchmarked against baseline top-K on a representative eval set.

## See also
- [S-09 · Memory Systems](s09-memory-systems.md) — the three cognitive types that memory stores must handle
- [S-150 · Prompt Context Block Deduplication](s150-prompt-context-block-deduplication.md) — deduplication at assembly time; complements arbitration
- [S-314 · Agent Memory Layer Architecture](s314-agent-memory-layer-architecture.md) — the broader memory pipeline this arbitration layer fits into
- [F-194 · Agentjacking: MCP Tool Response Poisoning](../forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — cross-agent memory poisoning the write gate must guard against
- [S-150 · Prompt Context Block Deduplication](s150-prompt-context-block-deduplication.md) — deduplication at assembly time; complements arbitration
- [S-314 · Agent Memory Layer Architecture](s314-agent-memory-layer-architecture.md) — the broader memory pipeline this arbitration layer fits into
- [S-09 · Memory Systems](s09-memory-systems.md) — the three cognitive types that memory stores must handle
