# S-716 · Retrieval Quality Beats Model Quality: The Production RAG Gap

[Naive RAG — embed docs, similarity search, stuff top-3 into the prompt — gets you a 70%-quality demo and a ceiling you cannot climb past. The gap between demo and production lives entirely in three retrieval pipeline levers that most teams never tune: chunking strategy, hybrid search, and re-ranking. Model choice is downstream of retrieval quality, not upstream.]

## Forces

- **The retrieval pipeline is where RAG systems break, not the model.** A mediocre model with excellent retrieved context reliably beats a frontier model with poor context. The bottleneck is almost never the LLM.
- **Naive RAG fails 40% of the time at retrieval in production.** Pure vector similarity on fixed-size chunks loses on precision-heavy queries (names, IDs, technical terms) and long-document synthesis alike.
- **Chunk granularity is a one-way door once indexed.** Chunks are the atomic unit of both indexing and retrieval. If your chunks are too coarse or too fine for the query patterns, no amount of model tuning fixes it.
- **Over-fetch then filter beats under-fetch.** Fetching 3 results is the most common mistake; fetching 20 with a cross-encoder re-ranker consistently outperforms fetching 10 without one.
- **Agentic RAG adds loops, not just better search.** Agents that query multiple times with sub-questions, self-correct on empty results, and reformulate queries beat static pipelines — but add cost and latency.

## The move

**Pull all three retrieval levers. In order of leverage:**

- **Chunk on structure, not character counts.** Use recursive character splitting with semantic aware breakpoints. For code: split on syntax boundaries. For tables: keep rows intact. For legal/financial docs: split on section headers. Overlap at section boundaries by 10-15% to preserve cross-chunk context.

- **Replace pure vector search with hybrid search.** Combine vector similarity (semantic match) with BM25/keyword search (exact match). Weight: start 60/40 vector/keyword and tune. Most vector DBs (Qdrant, Weaviate, Pinecone) support this natively. The keyword leg catches proper nouns, IDs, and technical terms that embeddings miss.

- **Over-fetch (top-15-20), then re-rank.** Don't ask your vector search for exactly the chunks you need — ask for candidates, then use a cross-encoder (e.g., Cohere Rerank, BGE-Reranker) to score relevance against the full query. This alone can yield +15-25% improvement on recall benchmarks.

- **Add a query rewrite step.** Rephrase user queries into 2-3 search-optimized variants. A question like "what happened to the Q3 pipeline in 2023?" benefits from "Q3 2023 pipeline results," "Q3 2023 sales pipeline," and the original — each retrieving different chunks.

- **Instrument retrieval before instrumenting the model.** Measure hit rate (# retrieved chunks that actually contributed to the answer), recall @k, and MRR @k per query. Only optimize the model when retrieval metrics are green.

- **Use agentic retrieval for complex synthesis tasks.** For multi-hop questions (A leads to B leads to C), let the agent break the query into sub-questions, retrieve independently, then synthesize. For single-hop lookups, keep it deterministic.

## Evidence

- **Research post (Ruchit Suthar):** Naive RAG hits a quality plateau at ~70%. The three-lever framework (structured chunking, hybrid search, re-ranking) consistently breaks through it. Benchmarks show hybrid search outperforms pure vector on 11 of 12 public QA datasets tested. — [https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search](https://ruchitsuthar.com/blog/software-architecture/rag-in-production-chunking-reranking-hybrid-search)

- **Research post (Lushbinary, April 2026):** Naive RAG pipelines fail 40% of the time at retrieval in production deployments. Agentic RAG — where the agent loops back to check its own retrieval — addresses this but trades latency and cost. — [https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide](https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide)

- **Education site (AgentEngineering):** The chunk is the atomic unit of both indexing and retrieval — a document split into chunks is retrievable only at those boundaries. Poor chunk boundaries are the root cause of most retrieval failures, not model quality. — [https://www.agentengineering.io/topics/articles/rag-for-agents](https://www.agentengineering.io/topics/articles/rag-for-agents)

- **arXiv (2512.08769, 2025):** Production-grade agentic AI workflows require separation of workflow logic from MCP servers, containerized deployment, and KISS-principle architecture — including at the retrieval layer. — [https://arxiv.org/html/2512.08769v1](https://arxiv.org/html/2512.08769v1)

## Gotchas

- **Changing chunk size requires re-indexing everything.** This is a one-way architectural door. Get chunking right before going to production; late-stage chunk-size changes can cost weeks of re-processing.
- **Re-ranking adds latency.** Cross-encoder re-ranking typically adds 50-200ms per query. Budget for it in latency-sensitive applications or use it selectively (apply only to queries above a confidence threshold).
- **Hybrid search requires a keyword index alongside the vector index.** This roughly doubles storage and slightly increases index time. Plan storage accordingly.
- **Agentic retrieval multiplies token costs.** Each sub-query is a separate LLM turn. For high-volume simple lookups, the overhead isn't worth it — keep those deterministic.
- **Evaluating retrieval is harder than evaluating the model.** Use RAGAS or TruLens metrics (hit rate, context precision, context recall) rather than relying on end-to-end answer quality, which conflates retrieval failure with generation failure.
