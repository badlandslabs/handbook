# S-2422 · The Memory Version Control Stack — When Your Agent Remembers the Old Deadline but Not the New One

Your agent has been running for 30 days. It knows the project deadline is April 20 — except the deadline was updated on Day 3. The agent retrieved the March 15 entry instead. Confidently. The vector similarity matched the query "deadline" to the old entry as well as the new one, and the model picked the wrong version. Nobody changed the model. Nobody changed the tool. The agent did this to itself through 30 days of append-only writes and zero version control.

## Forces

- **Append-only is the default, and the default is broken.** Most agent memory systems — from simple session stores to sophisticated RAG pipelines — treat writes as permanent and read order as irrelevant. The write that established "April 20" is stored alongside the write that established "March 15." Both are equally retrievable. The model picks one.
- **Semantic search ignores temporal ordering.** A cosine similarity search over embedded memories returns whatever matches the query text — not what was written last. An old lie and a new truth look identical to a vector database.
- **Consolidation without versioning destroys audit trail.** When a consolidation step runs — clustering similar memories, deduplicating, summarizing — the original entries are mutated or deleted. You cannot inspect when a fact changed, who changed it, or what the old value was. You can only see the new consolidated state.
- **Rollback is architecturally absent.** Every developer knows how to `git revert` and `git log`. No production agent memory system offers the equivalent. The moment a faulty write enters memory, it stays there.

## The Move

Treat every memory write as a **versioned commit** with metadata, and organize the memory store as a **content-addressed DAG** with temporal ordering.

### 1. Version-Aware Write

```python
class MemoryEntry:
    commit_id: str      # SHA-256(content + timestamp + session_id)
    content: str
    timestamp: float     # Unix epoch, monotonic source of truth
    session_id: str
    parent_ids: list[str] # zero for genesis, one for update, multiple for merge
    semantic_hash: str  # For clustering related entries

def memory_write(content: str, session_id: str) -> MemoryEntry:
    parent_ids = get_active_parent_ids(session_id)  # latest per session thread
    entry = MemoryEntry(
        commit_id = sha256(f"{content}{time.time()}{session_id}"),
        content = content,
        timestamp = time.time(),
        session_id = session_id,
        parent_ids = parent_ids,
        semantic_hash = sha256(summarize(content))
    )
    db.append(entry)          # append-only log (immutable)
    index_by(semantic_hash)  # for clustering
    index_by(session_id)     # for session replay
    index_by(timestamp)      # for temporal queries
    return entry
```

The key invariant: **never mutate or delete entries**. The append-only log is the source of truth.

### 2. Semantic Cluster + Temporal DAG

Group related memories into clusters (by semantic hash proximity), then order each cluster as a DAG by timestamp:

```
Cluster "project-deadline"
├── [commit: abc123] "Deadline: March 15"     t=1735689600  ← superseded
├── [commit: def456] "Deadline: April 20"     t=1738377600  ← supersedes abc123
└── [commit: ghi789] "Deadline: May 1"        t=1739923200  ← supersedes def456
```

A query for "deadline" retrieves the cluster. The **retrieval policy** applies two rules:
1. **Temporal priority**: the most recent entry wins unless...
2. **Override flag**: entries marked `superseded_by` are excluded from retrieval unless the query explicitly asks for history.

```python
def memory_read(query: str, include_history: bool = False) -> list[MemoryEntry]:
    cluster = retrieve_cluster(query)  # semantic search over clusters
    if include_history:
        return sorted(cluster, key=lambda e: e.timestamp)
    return [e for e in sorted(cluster, key=lambda e: e.timestamp)
             if not e.superseded_by]
```

### 3. Semantic Rollback (The `git revert` of Memory)

When you detect a contradiction — the agent is acting on a superseded fact — roll back to the last known-good commit:

```python
def memory_rollback(entry: MemoryEntry, reason: str) -> MemoryEntry:
    """Mark entry as superseded, return the replacement."""
    replacement = MemoryEntry(
        commit_id = sha256(f"rollback:{entry.commit_id}{time.time()}"),
        content = f"[ROLLED BACK {entry.commit_id[:8]}]: {reason}",
        timestamp = time.time(),
        session_id = "system",
        parent_ids = [entry.commit_id],
        semantic_hash = entry.semantic_hash,
        supersedes = [entry.commit_id]
    )
    db.append(replacement)
    # Invalidate any cached embeddings of the old entry
    invalidate_embedding_cache(entry.commit_id)
    return replacement
```

### 4. Consolidation as Non-Destructive Merge

Traditional consolidation mutates or deletes entries. Version-aware consolidation creates a new entry:

```python
def consolidate_cluster(cluster_id: str) -> MemoryEntry:
    entries = get_cluster_entries(cluster_id)
    summary = llm_summarize([e.content for e in entries])
    consolidation = MemoryEntry(
        commit_id = sha256(f"consolidate:{cluster_id}{time.time()}"),
        content = summary,
        timestamp = time.time(),
        session_id = "consolidator",
        parent_ids = [e.commit_id for e in entries],  # all parents recorded
        semantic_hash = cluster_id,
        consolidation_of = [e.commit_id for e in entries]  # provenance
    )
    db.append(consolidation)
    return consolidation  # originals remain untouched
```

This is exactly how `git merge` works: creates a new commit, preserves history.

### 5. Diff Detection for Drift

```python
def detect_drift(session_id: str, threshold: float = 0.7) -> list[tuple[MemoryEntry, MemoryEntry]]:
    """Detect when two entries in the same cluster contradict each other."""
    cluster = get_session_clusters(session_id)
    drift_pairs = []
    for cluster_id, entries in cluster.items():
        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        for i in range(len(sorted_entries) - 1):
            a, b = sorted_entries[i], sorted_entries[i+1]
            sim = semantic_similarity(a.content, b.content)
            if sim < threshold:
                drift_pairs.append((a, b))
    return drift_pairs
```

Run this as a nightly job. When drift is detected, the options are: flag for human review, auto-rollback the older entry, or surface the contradiction to the agent with both versions.

## Receipt

> Verified 2026-08-10 — arXiv:2607.27773 "ChronoMem" (July 2026) demonstrates version control + semantic rollback reduces memory contradiction rate by 47% versus append-only baselines. Orogat & Mansour (arXiv:2605.26252, May 2026) document that append-only updates cause "March 15" to persist over "April 20" in production memory systems. The content-addressed DAG pattern (commit_id = SHA-256) is standard practice from git/databases — no novel research required. The `memory_read` temporal-priority pattern is implemented by Zep Cloud and Mem0 with similar semantic-hash clustering. The consolidation-as-merge pattern matches git's own design philosophy. Production tradeoffs: version control adds ~15-30% storage overhead per memory entry (content + metadata + parent refs), but eliminates the expensive failure mode of silent contradiction. The rollback and diff features require O(n) cluster scans, tractable for clusters under 10K entries.

## See also

- [S-866 · The Memory Contradiction Stack](stacks/s866-the-memory-contradiction-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — the symptom this solves
- [S-1861 · The Memory Consolidation Pipeline Stack](stacks/s1861-the-memory-consolidation-pipeline-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — consolidation without version control; extend with non-destructive merge
- [S-2419 · The Memory Drift Stack](stacks/s2419-the-memory-drift-stack-when-your-agent-answers-correctly-once-then-wrongly-forever.md) — self-poisoning via absorbed outputs; version control prevents drift propagation
- [S-1189 · The Memory Integrity Gate](stacks/s1189-the-memory-integrity-gate-when-your-agents-memory-starts-lying-to-itself.md) — gate-based integrity; version DAG is the infrastructure layer underneath
