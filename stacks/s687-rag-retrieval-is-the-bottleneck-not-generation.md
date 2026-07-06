# S-687 · RAG Retrieval Is the Bottleneck, Not Generation

Naive RAG fails to surface the right passage on ~40% of real enterprise queries. A smarter model just hallucinates more confidently from wrong context. Production RAG is a retrieval engineering problem.

## Forces

- **Vector search misses exact matches.** Exact keyword matches — case numbers, product IDs, proper nouns — don't live in embedding space. Dense vector retrieval alone systematically fails on the queries that matter most in enterprise settings.
- **Chunk boundaries destroy context.** Fixed-size chunking splits sentences, cuts relationships, and discards document-level structure. The retrieved chunk is semantically correct but contextually incomplete.
- **The retrieval–generation coupling is backwards.** Teams optimize the LLM first and treat the retriever as a black box. In production, bad retrieval is the cause; bad generation is the symptom.
- **Naive RAG doesn't scale with query diversity.** A corpus tuned for one query style breaks for another. Without evaluation loops on the retriever, you don't know it's broken until users complain.

## The move

Production RAG is a three-stage pipeline with evaluation gates at each boundary.

**Stage 1 — Chunking that preserves semantic units.**
- Target 500–1,500 tokens per chunk; 10–20% overlap between adjacent chunks.
- Prefer semantic chunking (by section, paragraph, or logical boundary) over fixed-size splitting.
- Use parent-child chunking: small child chunks for retrieval (detailed), large parent chunks for generation (complete context).
- Apply contextual embeddings: prepend a summary of the parent document before embedding the child chunk so each vector captures its role in the whole.

**Stage 2 — Hybrid retrieval with Reciprocal Rank Fusion.**
- Combine dense vectors (semantic similarity) with BM25 sparse vectors (exact keyword matching) in a single query pipeline.
- Fuse results with RRF: `score = Σ 1/(k + rank_i)` where k=60. This consistently outperforms either method alone — hybrid measures ~66% MRR versus ~57% for vector-only in production corpora.
- Retrieve top 50–100 candidates from the hybrid index; feed all into the reranker.

**Stage 3 — Cross-encoder reranking under a token budget.**
- Pass the top 50–100 candidates through a cross-encoder reranker (e.g., Cohere Rerank v3, BGE-Reranker).
- Keep top 5–10 after reranking. Truncate the final context to ~8K tokens even on million-token models — more context dilutes signal.
- Make the reranker swappable behind one config flag; don't hardcode the vendor.

**Evaluate the retriever separately from the generator.**
- Score retriever quality with RAGAS retrieval metrics (context precision, context recall) independently of generation quality.
- Track top-1 cosine similarity weekly against a golden query set. Embedding models drift; queries evolve; the retriever silently degrades.

**Lock down access before optimizing retrieval.**
- Multi-tenant RAG requires RBAC at query time: filter the candidate pool by user roles *before* retrieval, not after.
- Chunk-level metadata (author, department, classification) must be indexed alongside the vector for access control to be enforceable.

## Evidence

- **Engineering blog (AxisCore):** Production RAG failures map to five failure modes — wrong chunks (vector miss), wrong documents (filter bug), latency budget exceeded, context contamination, and embedding drift. The fix for wrong chunks is hybrid search + chunk size tuning. — [axiscoretech.com/blog/llm-agents/rag-architectures](https://axiscoretech.com/blog/llm-agents/rag-architectures)
- **Research post (Ilir Ivezaj):** Naive single-index RAG fails ~40% of real enterprise queries. Hybrid BM25 + dense with RRF fusion measures 66% MRR versus 57% vector-only. Cross-encoder reranking over top 50 candidates cuts the failure rate further. Recommended chunking: 500–1,500 tokens, 10–20% overlap. — [ilirivezaj.com/ai/rag-architecture](https://ilirivezaj.com/ai/rag-architecture)
- **Engineering guide (AI Thinker Lab):** The two cheapest RAG upgrades that fix most failures: hybrid retrieval (dense + BM25) and a reranker. These ship before any model change. The guide catalogs 8 RAG patterns on a complexity ladder; most teams should stay at level 2 (hybrid + reranker) until they have evaluation data justifying level 3+. — [aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)

## Gotchas

- **Embedding model lock-in is invisible until it hurts.** Switching your embedding model invalidates your entire vector corpus. Version your embeddings; rebuild the index when upgrading.
- **Reranking latency is non-trivial.** A cross-encoder call over 50 candidates adds 200–500ms. Profile it separately; stream the LLM response while the reranker runs.
- **Context window ≠ useful context.** Assembling 128K tokens of retrieved chunks doesn't improve answers past ~8K; it dilutes signal and inflates cost. Hard cap the assembled context.
- **Gold query sets decay.** User queries evolve. Re-annotate your evaluation set quarterly, or your retriever metrics will look healthy while users get worse answers.
