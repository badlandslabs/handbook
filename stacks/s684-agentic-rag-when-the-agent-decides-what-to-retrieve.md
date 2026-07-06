# S-684 · Agentic RAG: When the Agent Decides What to Retrieve

Naive RAG pipelines query → embed → top-k → generate. They work until the corpus is complex, the question is ambiguous, or the answer requires synthesis across disjoint sources. Agentic RAG puts the LLM in charge of the retrieval loop — decomposing queries, routing to specialized indexes, re-planning mid-flight, and validating results before generation. The quality gain is real (90–95% precision vs 70–80% for naive). So is the cost: 10× more tokens per query. Most teams apply agentic RAG everywhere and pay for simplicity they didn't need.

## Forces

- **Naive RAG ceilings out at 70–80% precision.** Complex questions — multi-hop, ambiguous scope, cross-document synthesis — fail predictably when a fixed top-k is the only retrieval strategy. The failure mode is confident hallucination, not obvious silence.
- **Agentic RAG costs 10× per query.** The plan-execute-replan loop, self-query router, and validation step each add LLM calls. For the ~60% of queries that are single-hop factual lookups, you're paying 10× for quality you already had.
- **LLM-controlled retrieval introduces non-determinism.** A fixed pipeline is debuggable. A loop where the agent decides "should I search again?" is harder to reproduce, test, and monitor.
- **Routing decisions require typed schemas at every boundary.** The retrieval agent's output must match the index's expected input format. Schema drift between agents silently degrades retrieval quality.

## The Move

The core technique: route each query to the appropriate retrieval strategy before committing to a pipeline. Use a classifier or LLM router to determine complexity, then dispatch to naive, advanced, or agentic retrieval. Only escalate to agentic patterns for multi-hop, ambiguous, or cross-index queries.

- **Self-query router:** The agent inspects the query and decides which tool/index to call — not a fixed pipeline. "Is this asking about a specific date range? Filter by metadata. Is it asking for a comparison? Parallel retrieval across two indexes."
- **Plan-execute-replan loop:** Generate a retrieval plan, execute it, then re-evaluate whether results are sufficient. If insufficient, replan and retry. This handles queries where the initial plan was wrong.
- **Validation before generation:** After retrieval but before generation, run a lightweight check: "Does the retrieved context actually answer the question?" If not, trigger a second retrieval pass.
- **Hybrid search as the default retrieval primitive:** Combine dense vector similarity with sparse BM25 keyword matching. Neither alone covers all query types; hybrid covers more. Most production systems use this as the base regardless of RAG paradigm.
- **Graduated escalation, not all-or-nothing:** Single-hop factual → naive RAG. Multi-hop or ambiguous → advanced RAG (hybrid + re-rank). Complex synthesis or uncertain scope → agentic RAG. Route at the ingress, not after retrieval fails.
- **Typed schemas at every agent boundary:** Define the output schema of the retrieval agent and the input schema of each index explicitly. Version both. Untyped handoffs are the primary cause of silent degradation in multi-step retrieval.

## Evidence

- **Benchmark:** Agentic RAG achieves 90–95% precision vs naive RAG's 70–80% ceiling, at a cost multiplier of 10× per query. ~60% of production queries require only single-hop retrieval. — *Agentic RAG in 2026: Architecture Patterns, Frameworks & When to Use It* — https://jobsbyculture.com/blog/agentic-rag-guide-2026
- **Enterprise survey:** 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025 (Gartner). RAG architecture evolution mirrors this: naive pipelines fail predictably, agentic control loops are the production response. — *Multi-Agent Systems: Architecture Patterns for Production AI* — https://www.raftlabs.com/blog/multi-agent-systems-guide
- **Naive RAG failure modes:** "Naive pipelines fail 40% of the time at retrieval" in production against real document corpora (legal contracts, technical manuals, earnings transcripts). The failure is not random — it follows a pattern predictable enough to design against. — *RAG Production Guide 2026: Retrieval-Augmented Generation* — https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide

## Gotchas

- **Don't apply agentic RAG to every query.** The 10× cost multiplier is only justified for complex, multi-hop, or ambiguous queries. Implement routing at ingress — a simple classifier or even a keyword heuristic can route 60% of traffic to cheaper naive retrieval.
- **Re-rankers add latency but not as much as a failed generation.** After hybrid retrieval, a cross-encoder re-ranker (e.g., Cohere Rerank, BGE Reranker) reorders the top-20 results into top-5 with actual relevance scoring. Cost: ~2–3s latency. Benefit: measurable precision lift. This is standard in advanced and agentic RAG.
- **Context window pollution.** The retrieval agent's prior context accumulates across the plan-execute-replan loop. Monitor context length per session and implement truncation or summarization for long-running retrieval threads.
- **Evaluation gap in retrieval.** RAGAS, Trinity, andARES provide retrieval-specific metrics (context precision, answer faithfulness, citation accuracy) that standard LLM benchmarks miss. 89% of teams have observability but only 52% have evals — the gap is especially pronounced in retrieval quality monitoring.
