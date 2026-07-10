# S-924 · The Retrieval Decision Stack — When Your Agent Decides What to Search

You have a question. Your agent needs to answer it from your knowledge base. The obvious move is to embed the query, retrieve chunks, and generate. But the harder question is: should it retrieve at all? And if so, from which source, using which strategy, and how many times? In agentic retrieval, those decisions are the agent's job.

## Forces

- Classic RAG is fast and cheap (1 LLM call, 1 retrieve pass) but fails silently on complex queries — it embeds multi-part questions as a single vector and returns unrelated chunks.
- Agentic RAG makes 3–8 LLM calls and 2–6 retrieval passes per answer. Cost increases 3–5x. The tradeoff pays off only when the question is genuinely multi-hop or ambiguous.
- The most dangerous failure mode isn't a crash — it's a confident answer built on partial context. The retriever misses a chunk, but the generator fabricates a coherent answer that still "passes" a faithfulness check because it didn't contradict what it did receive.
- Teams measure generation quality but skip retrieval-stage metrics. A pipeline can score 0.91 on faithfulness while context recall sits at 0.62 — the retriever silently missing the second statute on multi-hop legal questions.
- BM25 still outperforms dense-vector-only retrieval on exact-term queries in 2025–2026 benchmarks, despite being a 1994 algorithm. The two signals are complementary, not competing.

## The Move

**Route first, retrieve second.** Before any retrieval happens, the agent classifies intent and decides the retrieval strategy. This single decision determines your latency ceiling, token cost, and accuracy ceiling.

### The decision taxonomy

- **Direct answer** — query is factual, answerable from parametric knowledge. Skip retrieval entirely. Saves tokens and latency.
- **Single-source retrieval** — one retrieval pass, one generate. Classic RAG. Fast, predictable, auditable.
- **Decomposed multi-hop** — break the query into sub-questions, retrieve for each, synthesize. Agent controls the loop, maintains state across hops.
- **Multi-source parallel** — same query hits vector DB, keyword index, and external API simultaneously, fused via RRF or weighted combination.
- **Iterative refine** — retrieve → evaluate relevance → rewrite query → retrieve again. Loop until faithfulness gates are met or step budget exhausted.

### Hybrid retrieval is the baseline, not the feature

Don't choose between BM25 and dense vectors. Combine them via Reciprocal Rank Fusion (RRF), then apply a cross-encoder reranker. RRF sidesteps the score-incompatibility problem that breaks naive weighted combinations — it works on ranks only.

```python
# RRF fusion: k=60 is the standard rank constant
def rrf_fusion(results_a, results_b, k=60):
    scores = defaultdict(float)
    for rank, doc_id in enumerate(results_a):
        scores[doc_id] += 1 / (k + rank + 1)
    for rank, doc_id in enumerate(results_b):
        scores[doc_id] += 1 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)
```

BM25 handles exact-match queries (product codes, proper nouns, regulation numbers). Dense vectors handle semantic similarity (paraphrased intent, conceptual matches). Neither alone covers both.

### Self-check gates the answer, not the retrieval

The agent drafts a response, then a second LLM call evaluates: does the draft directly answer the user's question? Are every claim and number grounded in the retrieved context? If not, the agent re-retrieves or rewrites rather than shipping a confident fabrication.

Self-RAG (from Sakana AI) reduced unsupported predictions from 20% to 2% by adding this critique step. The key is evaluating the *grounding*, not the fluency.

### Context precision beats context recall as the first signal

Context precision measures whether the *relevant* chunks are ranked at the top of the retrieved set. A high recall score with low precision means you retrieved the right documents but buried the useful chunks under noise. In agentic RAG, context bloat is the real enemy — it dilutes the signal and burns tokens.

### Instrument both stages independently

Track retrieval metrics (context precision, context recall, BM25 score, reranker score) separately from generation metrics (faithfulness, groundedness, answer relevance). A dashboard showing only generation quality will miss retriever regressions that silently erode accuracy.

## Evidence

- **Engineering blog — FutureAGI:** Five patterns ship in 2026: query rewriting/decomposition, multi-hop with state, tool routing across retrievers, self-check on draft, re-retrieval on failure. Classic RAG makes 1 retrieval call per turn; agentic makes 1–6, dynamically. — [futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)

- **Engineering blog — Adaline Labs:** Intent classification + query routing reduced production costs by 40% and latency by 35% by skipping unnecessary retrievals. The orchestration layer classifies user intent before deciding whether to retrieve, call tools, or answer directly. — [labs.adaline.ai/p/building-production-ready-agentic](https://labs.adaline.ai/p/building-production-ready-agentic)

- **Engineering blog — linesNcircles:** Classic RAG gives predictability; agentic RAG gives adaptability. Enterprise teams choose based on SLA strictness, regulatory audit requirements, and query complexity distribution. Agentic RAG fails on latency variance — a deep research query can take 15–30 seconds vs. 2–5 seconds for a simple lookup. — [linesncircles.com/Blog/Enterprise/RAG_vs_Agentic_RAG_2026](https://linesncircles.com/Blog/Enterprise/RAG_vs_Agentic_RAG_2026)

- **Survey/benchmark — AgenticRAG (softwarejc):** Agentic RAG taxonomy: single-agent, multi-agent, hierarchical, corrective, adaptive, and graph-based. Corrective RAG uses a critic model to identify when retrieval failed and triggers re-retrieval. Self-RAG (Sakana AI) achieved 2% unsupported prediction rate vs. 20% baseline. — [github.com/softwarejc/AgenticRAG](https://github.com/softwarejc/AgenticRAG)

- **Blog — Tian Pan:** BM25 still outperforms billion-parameter dense retrievers on exact-term queries in production benchmarks. Hybrid search (BM25 + dense + RRF) is the practical default because real queries span both signal types. — [tianpan.co/blog/2026-04-12-hybrid-search-in-production-bm25-still-wins](https://tianpan.co/blog/2026-04-12-hybrid-search-in-production-bm25-still-wins)

## Gotchas

- **Routing to "no retrieval" is underrated.** Simple factual queries often answer correctly from parametric memory. Intent classification that routes these to direct answer saves 40–70% of retrieval cost for roughly 30% of queries in production systems.
- **Step budgets prevent runaway loops.** Without a hard limit (e.g., max 3 re-retrieval cycles), an agent can loop indefinitely on edge cases. Set the budget, track it in traces, and alert when it triggers.
- **Context bloat kills agentic RAG.** HyDE, multi-query expansion, and multi-hop all multiply retrieved context. If you're not pruning irrelevant chunks before the generate step, you're paying for noise. Parent-child chunking or reranker-based pruning is the fix.
- **Faithfulness checks without recall checks miss the real failure.** A faithfulness score measures whether the answer matches the context — not whether the context was complete. Measure both.
- **BM25 tuning is often skipped and shouldn't be.** The k1 and b parameters in BM25 affect term frequency saturation and document length normalization. Defaults (k1=1.5, b=0.75) are reasonable starting points, but domain-specific tuning — especially for short-field retrieval — moves precision meaningfully.
