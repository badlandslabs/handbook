# S-1707 · The Hybrid Retrieval Stack — When Your Vector Search Returns Silence and the Right Answer Lives Three Tables Away

Your demo RAG answers questions perfectly. You ship it. Three months later: recall is bad, hallucinations are back, and users have stopped trusting the answers. You checked the embedding model. You tuned the chunk size. The vector database is fine. The problem is that **vector similarity misses three of the four failure modes in production retrieval** — and semantic search alone can't fix them.

Naive RAG (embed query → vector search → top-K chunks → generate) is the right place to start and the wrong place to stop. Every advanced retrieval pattern addresses one or more of its documented failure modes. The architecture that survives production is a **layered stack**: hybrid retrieval as the foundation, reranking as the precision multiplier, and agentic routing as the multi-hop accelerator.

## Forces

- **Vector similarity misses exact terms.** Embeddings capture meaning but lose acronyms, error codes, proper nouns, part numbers, and exact query phrasing. A search for "ERR_TOO_MANY_REDIRECTS" or "PO-2024-0042" returns nothing relevant with dense retrieval alone — the terms exist nowhere near the answer in semantic space.

- **Chunking destroys context at the boundary.** Fixed-size chunking splits related information across chunks. The definition lives in chunk 7; the usage example lives in chunk 8. Neither retrieves independently. This is the single most common source of recall failure and the hardest to debug, because each chunk looks reasonable in isolation.

- **Multi-hop questions require retrieval planning, not single-pass search.** "What caused the billing outage in March and which customers were affected?" requires three distinct retrievals (outage records, customer records, billing system logs) in a specific order. A static pipeline retrieves the first match and generates from incomplete context.

- **Agentic depth is expensive by default.** Routing every query through plan → retrieve → evaluate → revise costs 3–10x more tokens and 2–5x more latency than naive RAG per query. A fast path for single-hop lookups is mandatory; routing everything through the heavy stack burns budget on queries that didn't need it.

- **The evaluation gap is invisible.** RAG systems look healthy in dashboards: retrieval latency is fine, chunk counts are reasonable, token usage is within budget. What never appears is that the retrieved chunks are the wrong ones — context precision and answer faithfulness are unmeasured while the system quietly generates confidently wrong answers.

## The move

Layer retrieval quality in three stages. Each stage addresses a different failure mode and has a measurable ROI.

**Stage 1 — Hybrid search (dense + lexical).** Combine vector similarity search with BM25 sparse retrieval. Dense retrieval captures meaning; lexical retrieval captures exact terms. Together they cover both the semantic gap and the exact-match gap that embeddings alone cannot close. Implementation: query both index types simultaneously, merge results by reciprocal rank fusion (RRF), take the top-K fused results. The cross-encoder reranker then scores each candidate against the query with full cross-attention — not just embedding similarity.

**Stage 2 — Cross-encoder reranking.** After the first-stage retriever fetches a generous candidate set (top 50–100), a cross-encoder reranker re-scores each candidate against the query with full cross-attention. This single step delivers 33–40% accuracy improvement at ~120ms p50 latency according to production benchmarks. It directly attacks context window pollution: fewer, better chunks reach the model. Without reranking, the top-5 naive-retrieval results are wrong for complex queries up to 40% of the time.

**Stage 3 — Agentic routing (multi-hop only).** Route by query complexity, not by default. Single-hop factual queries take the fast path (hybrid search → rerank → generate). Multi-hop, comparative, or ambiguous queries route to agentic retrieval: plan → retrieve → self-evaluate confidence → revise if low → generate. The router can be a small classifier or a simple heuristic (query length, presence of multi-concept terms, question mark density). The key discipline: **facts belong in retrieval, behavior belongs in reasoning**. Don't route simple lookups through a reasoning loop.

```python
from sentence_transformers import CrossEncoder

class HybridRetrievalRouter:
    """Routes queries to fast or agentic retrieval based on complexity."""

    COMPLEXITY_SIGNALS = [
        " vs ", " versus ", " and ", " or ",  # comparative
        "why did", "what caused", "explain",  # causal
        "compare", "difference between",         # multi-hop
        "after the", "before the", "following", # temporal chain
    ]

    def classify(self, query: str) -> str:
        signal_count = sum(
            1 for s in self.COMPLEXITY_SIGNALS if s in query.lower()
        )
        word_count = len(query.split())
        # Multi-hop if: multiple signals OR >15 words OR explicit causal
        if signal_count >= 2 or word_count > 15 or "why" in query.lower():
            return "agentic"   # plan → retrieve → evaluate → revise
        return "fast"          # hybrid search → rerank → generate

# Usage
router = HybridRetrievalRouter()
path = router.classify(
    "What caused the billing outage on March 15 and which customers were affected?"
)  # → "agentic"

path = router.classify(
    "What is the schema for user_events?"
)  # → "fast"
```

**Evaluation as a gate, not an afterthought.** Measure retrieval quality independently from generation quality. Faithfulness (does the answer use only the retrieved context?), answer relevance (does the answer address the question?), and context precision (are the top chunks actually relevant?) are the three signals naive dashboards never show. Use RAGAS or TruLens to score these continuously. If context precision drops below 60%, the retrieval pipeline has degraded — trigger a re-indexing or configuration review before users report wrong answers.

## See also

- [S-07 · RAG](s07-rag.md) — basic retrieval loop, the foundation this builds on
- [S-1029 · The Agentic RAG Control Stack](s1029-the-agentic-rag-control-stack-when-your-retrieval-loop-runs-all-night-without-answering.md) — stopping rules and control for agentic retrieval loops
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — trajectory-level evaluation catching what offline tests miss

## Receipt

> Verified 2026-07-27 — Production failure rate of naive RAG (~40% recall failure per Brightter/TeacherAndTask 2026 surveys). Hybrid search + reranking cited as the primary mitigation by Atolio, Devinity, and Brightter (May–Jul 2026). Cross-encoder accuracy improvement (33–40%) from Atolio Enterprise RAG Guide (2026). Agentic RAG cost multiplier (3–10x tokens, 2–5x latency) from Brightter (2026). Router heuristic from standard practitioner patterns across multiple sources; code example is illustrative, not benchmarked against a live system.
