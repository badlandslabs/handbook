# S-774 · RAG Is a Control Loop, Not a Pipeline

The moment you frame RAG as a sequential pipeline — embed, store, retrieve, generate — you lose the ability to catch retrieval failures before they become hallucinations. Teams that treat it as a control loop with self-correction at each stage consistently outperform those that don't.

## Forces

- **Naive retrieval is everyone's starting point and everyone's liability.** Embed top-K, stuff into context, generate. It works at small scale. It fails silently at scale — wrong chunks, stale chunks, hallucination seeds — and you won't know until a user complains.
- **Pipeline framing removes agency from the retrieval step.** A pipeline has no gate between "retrieved" and "generated." A control loop has a relevance check, a faithfulness check, and a re-retrieval trigger. The difference is structural.
- **Most teams upgrade complexity before fixing fundamentals.** They jump to GraphRAG or multi-agent orchestration before adding a reranker — which costs nothing and fixes 70% of their retrieval failures first.
- **The evaluation gap is structural.** Classic RAG has no automatic flag for "the chunk is topically relevant but the specific claim inside it is wrong." Agentic RAG with a self-check loop catches this. Classic RAG does not.

## The move

Shift RAG from pipeline to control loop. Layer these changes in order of cost and impact:

- **Add a reranker first.** Hybrid retrieval (dense + BM25) + a reranker like Cohere Rerank v3 fixes the majority of retrieval failures before you touch anything else. This is the single highest-ROI change most teams skip.
- **Gate between retrieval and generation.** A lightweight relevance grader that scores each chunk before context injection. If a chunk scores below threshold, re-retrieve or expand the query. This single gate caused a 60–70% drop in hallucination-inducing retrievals in one production system.
- **Allocate token budgets to agents, not entire tasks.** Agentic RAG with role-specialized agents (Planner at 30%, Retriever at 40%, Generator at 30%) outperforms single-agent pipelines on complex queries because each stage can self-correct independently.
- **Add a faithfulness checker downstream.** A judge model that reviews generated output against retrieved context — not just the prompt. Ship no answer that scores below a faithfulness threshold.
- **Instrument the loop.** Every retrieval, every re-rank, every re-retrieval trigger, every faithfulness score — all logged. You cannot fix what you cannot see.
- **Only reach for GraphRAG when you have cross-document "connect-the-dots" questions.** Microsoft open-sourced it in July 2024. It earns its cost on questions where the answer spans multiple documents and requires synthesizing relationships. It adds overhead for simple lookups and most Q&A workloads.

## Evidence

- **Blog post (AIThinkerLab, June 2026):** Agentic RAG with knowledge graphs cut hallucination by ~62% across 47 production deployments (May 2026 MLOps Community benchmark). Hybrid retrieval + reranker identified as the highest-ROI first upgrade. — [https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns)
- **Engineering blog (Falcon Labo / iwajunnews, May 2026):** "Once we added a relevance grader between retrieval and generation — Corrective RAG — we saw a 60–70% drop in hallucination-inducing retrievals. That single change reframed how I think about RAG: it's not a pipeline, it's a control loop." — [https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026](https://iwajunnews.com/2026/05/19/agentic-rag-multi-agent-orchestration-in-production-what-we-actually-learned-in-2026)
- **Technical post (FutureAGI, 2025):** Documented a production failure where an agent retrieved 8 chunks, used 6, and fabricated the seventh fact entirely. No span scored faithfulness. No judge gated the answer. The root cause: no self-check loop between retrieval and generation. — [https://futureagi.com/blog/agentic-rag-systems-2025](https://futureagi.com/blog/agentic-rag-systems-2025)

## Gotchas

- **Embedding model sets the ceiling.** OpenAI text-embedding-3-large (64.6 MTEB) is the safe default; Qwen3-Embedding-8B tops the multilingual leaderboard at 70.58. Switching embedding models requires re-embedding your entire corpus — pick deliberately, not by default.
- **pgvector is sufficient until ~5–10M vectors.** Beyond that, dedicated vector databases (Pinecone, Qdrant) earn their cost. Most teams switch too early or never switch.
- **Agentic RAG adds latency and cost.** Each self-correction loop is an additional LLM call. For high-volume, low-stakes Q&A, a simpler pipeline may be the right call. Gate the control loop, don't apply it everywhere.
- **LangGraph leads observability.** LangSmith traces every graph node — which node failed, what state it received, what it returned. For control loop debugging, this matters more than framework velocity.
