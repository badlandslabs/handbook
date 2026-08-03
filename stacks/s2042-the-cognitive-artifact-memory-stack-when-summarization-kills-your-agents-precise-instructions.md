# S-2042 · The Cognitive Artifact Memory Stack

Your agent forgets the exact constraint you gave it three days ago. Not because memory failed — because summarization killed it. "Use type hints everywhere" becomes "user prefers type hints." A deadline of "3pm Friday" becomes "user is in a hurry." The instruction lives on; the precision is gone.

## Forces

- **Truncation is catastrophic** — dropping early turns erases founding context (project setup, user identity, domain assumptions)
- **Summarization is lossy** — LLMs smooth over specifics: exact values, conditional constraints, boundary cases
- **RAG over conversation history is noisy** — raw retrieval finds mentions but misses temporal relationships ("the second approach we ruled out")
- **Naive compression at scale is unaffordable** — every compression pass costs a full context re-read
- **Context windows are finite** — 2M tokens is not infinite, and long conversations grow faster than they compress

## The move

**Extract structured cognitive artifacts instead of compressing conversation history.** Treat long conversations like a team's whiteboard, not a transcript.

### The artifact taxonomy

| Artifact type | What it captures | Example |
|---|---|---|
| **Decision** | A resolved choice | "→ Chose Postgres over MongoDB: better JSON support" |
| **Fact** | Verified user-provided data | "API key lives in `env.API_KEY`" |
| **Reminder** | User-specified constraint or preference | "Always use `--dry-run` flag first" |
| **Ruling** | Explicitly rejected option with reason | "✗ Rejected Tailwind: user wants CSS modules" |
| **Commitment** | Agent's stated plan or commitment | "I will refactor `auth.py` before touching the API" |

### The extraction pattern

1. **At decision points**: When the model produces a non-trivial output, extract the key decisions and facts embedded in it into a structured artifact store
2. **On conversation turn**: After each exchange, extract new artifacts — don't summarize what was said, extract what was decided
3. **On context pressure**: When approaching context budget, don't summarize — instead surface the artifact graph and let the model rehydrate from structured memories

### The retrieval layer

```python
# Hybrid retrieval over cognitive artifacts
def retrieve_artifacts(query: str, turn_context: str) -> list[Artifact]:
    # Semantic match — what artifacts are relevant to this query?
    semantic_hits = vector_store.similarity_search(query, k=8)

    # Keyword anchor — preserve exact phrasing matches
    keyword_hits = bm25.search(query, k=4)

    # Temporal gate — was this artifact created before current turn?
    temporal_hits = [a for a in semantic_hits
                    if a.created_at < current_turn_id]

    # Deduplicate semantic + keyword overlaps
    fused = fusion.rerank(semantic_hits, keyword_hits, temporal_hits, k=6)
    return fused
```

### The preservation check

Before compressing a conversation segment, verify the artifacts survive:

```python
def preservation_check(conversation_segment: list[Turn],
                       artifacts: list[Artifact]) -> dict:
    """Does the artifact graph faithfully represent the segment?"""
    recall = measure_recall(conversation_segment, artifacts,
                            metric="exact_match")  # Target: >90%
    precision = measure_precision(conversation_segment, artifacts,
                                metric="no_hallucination")  # Target: >95%

    if recall < 0.90 or precision < 0.95:
        return {"status": "FAIL", "recover": True,
                "missing": find_gaps(conversation_segment, artifacts)}
    return {"status": "PASS"}
```

### The temporal graph

Artifacts aren't a flat list — they form a temporal graph with three edge types:

- **precedes**: This ruling predates that decision
- **supersedes**: This decision replaces a prior ruling
- **depends_on**: This decision requires that fact

```python
# Example graph query: "What did we rule out for this project?"
 rulings = graph.query_edges(
     type="supersedes",
     filter=lambda e: e.source.project_id == current_project
 )
 ruled_out = [e.source for e in rulings]
```

## Receipt

> Verified 2026-08-02 — Researched arXiv:2601.00821 (CogCanvas, Tao et al., 2026). Core finding: standard summarization achieves 19.0% exact match recall on constrained preferences vs 93.0% for CogCanvas. GraphRAG baseline: 70.0% exact match. The pattern distills three principles: (1) extract decisions over summarization, (2) preserve verbatim grounding rather than paraphrasing, (3) use temporal graph edges to preserve the "why we ruled this out" lineage. Production pattern confirmed via Mem0, Graphiti, and agent-memory-architecture-research.md analysis. Pattern connects to S-02 (context budget — this is the content-side complement), S-1189 (memory integrity — artifact provenance is a subset of integrity gates), S-2034 (memory stratification — artifacts live in the semantic layer between episodic and procedural).

## See also

- [S-02 · Context Budget](s02-context-budget.md) — context management is the other half of this problem
- [S-1189 · The Memory Integrity Gate](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — artifact provenance is governance-gated memory
- [S-2034 · The Agent Memory Stratification Stack](s2034-the-agent-memory-stratification-stack-when-your-agent-forgets-everything-the-moment-the-session-ends.md) — artifacts fit between episodic and procedural layers
