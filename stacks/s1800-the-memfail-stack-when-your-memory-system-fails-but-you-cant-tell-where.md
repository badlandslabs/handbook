# S-1800 · The MemFail Stack — When Your Memory System Fails but You Can't Tell Where

Your agent contradicts itself across sessions, stores facts it later can't recall, and overwrites new information with old. You tear apart the retrieval pipeline. You swap the vector database. You add a graph layer. Nothing changes — because you don't know which operation is broken. Your memory system is a black box and the failure is invisible from the outside.

## Forces

- **Memory systems are tested end-to-end but designed in layers.** You measure "does the agent remember X?" but can't attribute the failure to summarization, storage, or retrieval — the three operations that compose every memory system.
- **The same mechanism that makes memory efficient introduces failure.** Compression strips details. Storage overwrites or accumulates stale facts. Retrieval returns plausible-but-wrong matches. Each operation's optimization is another's failure mode.
- **Aggregate accuracy hides everything.** A memory system scoring 80% on QA looks healthy. But it might be getting 80% for the wrong reasons — e.g., nailing retrieval on easy queries while silently failing summarization on complex ones.
- **No single architecture dominates.** Graph-based systems excel at causal reasoning but collapse on coexisting facts. Vector-based systems handle semantic retrieval but struggle with temporal ordering. Hybrid systems carry both failure modes.
- **MemFail (arXiv:2605.26667, Garg et al., UC Berkeley, May 2026) is the first systematic diagnostic.** It decomposes memory systems operation-by-operation and isolates 12+ concrete failure modes — the framework this entry is built on.

## The move

Treat every memory system as three distinct operations. Test each independently. Fix the right one.

### 1. Decompose the black box

Every LLM memory system does exactly three things:

| Operation | Input | Output | What can go wrong |
|-----------|-------|--------|-------------------|
| **Summarization** | Raw history *H* | Compressed *H'* | Over-summarization strips critical details; under-summarization doesn't free context budget |
| **Storage** | Compressed *H'* + existing memory *M* | Updated memory *M'* | Old facts not retracted on update; memory grows unbounded; conflicting facts coexist |
| **Retrieval** | Query *Q* + memory *M* | Retrieved chunk(s) *R* | Semantic similarity ≠ relevance; temporal recency not weighted; hallucinated retrieved facts |

If your agent gives a wrong answer, exactly one of these three failed. You need to know which.

### 2. Diagnose with targeted probes

Test each operation in isolation before tuning anything:

```python
# Summarization probe
history = load_recent_session()
summary = summarizer.compress(history)
print("Summary retains:", extract_entities(summary))
print("Original had:", extract_entities(history))

# Storage probe — does new overwrite old?
store("Alice works on ML", timestamp=t1)
store("Alice moved to infra", timestamp=t2)
retrieved = retrieve("Alice's team")
assert "infra" in retrieved  # Fails if storage didn't overwrite

# Retrieval probe — does similarity capture relevance?
store("Password policy: 12+ chars", category="security")
store("Character count 12", category="design")
query = "password minimum length"
results = retrieve(query)
# Top result might be "design" if cosine similarity dominates
```

### 3. The 12 failure modes (MemFail taxonomy)

**Summarization failures (4):**
- **Attribution collapse** — agent loses the source of a fact in compression
- **Temporal flattening** — sequence and recency of events are lost
- **Entity merging** — distinct people/objects conflated
- **Sentiment overwrite** — nuanced context stripped to neutral tone

**Storage failures (4):**
- **Stale fact persistence** — new information stored but old contradictory fact not retracted
- **Conflict accumulation** — multiple contradictory facts coexist in memory
- **Memory bloat** — unbounded growth without eviction policy
- **Categorical drift** — memories stored under wrong categories degrade retrieval

**Retrieval failures (4):**
- **Semantic drift** — retrieved chunks are high-similarity but low-relevance to query intent
- **Temporal inversion** — newer (often more relevant) facts ranked below older ones
- **Chunk fragmentation** — related facts split across non-adjacent chunks, no single retrieval captures them
- **Hallucinated retrieval** — memory system returns fabricated content as retrieved fact

### 4. Pick architecture based on failure profile

| Failure you're seeing | Architecture to try |
|----------------------|-------------------|
| Attributing old facts as current | Graph-based (StructMem-style) with temporal edges |
| Agent contradicts itself | Versioned storage with conflict detection |
| Relevant facts never retrieved | Hybrid vector + keyword search with recency boost |
| Context window fills fast | Aggressive summarization with entity保留 policy |
| Hallucinated memory content | Retrieval-grounded generation — verify before surfacing |

### 5. The MemFail test suite

```bash
# From https://github.com/ishirgarg/MemFail
git clone https://github.com/ishirgarg/MemFail.git
cd MemFail && python -m pytest tests/  # targets summarization/storage/retrieval failures
```

Run it against your memory system. The output tells you which operation is your bottleneck — before you spend three weeks tuning the wrong one.

## Receipt

> Verified 2026-07-29 — MemFail paper (arXiv:2605.26667, Garg/Kolhe/Song/Zhao, UC Berkeley, May 2026) extracted in full. GitHub repo (https://github.com/ishirgarg/MemFail) confirmed with MIT-licensed code + datasets. Digital Applied "Context Engineering Playbook" (May 2026) confirms +39% lift from context editing + memory tiering. Redis Labs blog (July 2026) confirms "bigger context window won't fix memory" — separate persistence layer required. The New Stack "Context Layer Bottleneck" (July 18, 2026) confirms infrastructure-level context management is now the differentiator.

## See also

- [S-991 · The Agent Memory Stack](/stacks/s991-the-agent-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — memory architecture foundations
- [S-999 · The Orchestration and Memory Stack](/stacks/s999-the-orchestration-and-memory-stack-when-your-agent-needs-to-know-what-it-already-knew.md) — cross-session memory patterns
- [S-1002 · The Memory Consolidation Debt Stack](/stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — symptom-level consolidation failures
- [S-1239 · The Runtime Verification Loop](/stacks/s1239-the-runtime-verification-loop-when-your-agent-validates-itself-at-every-step.md) — inline step verification
