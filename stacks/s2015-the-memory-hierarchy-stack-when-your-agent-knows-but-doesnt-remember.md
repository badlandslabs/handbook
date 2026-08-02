# S-2015 · The Memory Hierarchy Stack — When Your Agent Knows But Doesn't Remember

Your agent reasons well, calls tools correctly, and follows instructions. But by Tuesday it has forgotten what the user said on Thursday, re-asks the same clarifying questions, and re-derives a plan it already built last week. The context window is a CPU cache — fast and ephemeral — not a database. This entry covers the four-tier memory taxonomy that production teams converged on, the frameworks that implement each tier, and the storage backends that keep retrieval fast enough to matter.

## Forces

- **Context is not memory.** A 1M-token context window does not solve the memory problem — it shifts where you fail. Context degrades in accuracy as it fills, and everything in it evaporates on session reset. Treating context as memory produces agents that are expensive AND forgetful.
- **Each tier has different access patterns.** Working memory needs sub-millisecond latency (it's always in context). Episodic memory needs semantic retrieval on a cold query. Semantic memory needs relational lookups. Procedural memory needs versioning and audit. No single storage backend is optimal for all four.
- **Memory errors compound.** A wrong episodic retrieval poisons downstream reasoning. An uncorrected semantic fact becomes accepted truth. A failed procedural recall makes the agent re-attempt a failed method. Memory systems need explicit forgetting, not just addition.
- **Extraction quality dominates retrieval quality.** The bottleneck is rarely the vector search — it's what you decided to store in the first place. Teams over-invest in retrieval algorithms and under-invest in write-time validation.

## The move

Implement a four-tier memory architecture that mirrors cognitive science. Each tier has a distinct storage backend, retrieval rule, and write policy:

- **Working memory** — holds active task state, intermediate reasoning, and in-flight tool results. Lives in the context window (always available, no retrieval needed). Size-bounded by token budget; use smart truncation that preserves first and last turns and offloads the middle to episodic storage. *Storage: in-process/LangGraph state object.*

- **Episodic memory** — summaries of past sessions and events. Retrieved by semantic similarity to the current query. The write path extracts structured summaries from working memory on session close, not raw chat logs. *Storage: vector store (Qdrant for hot/low-latency, pgvector for under-10M records).*

- **Semantic memory** — extracted facts about users, entities, and the world that persist across sessions. Retrieved by entity type and relevance score, not raw similarity. Schema-validated on write. Includes explicit update and delete operations — facts become stale. *Storage: relational schema + vector hybrid (Mem0 dual-store, or Weaviate for graph-adjacent entities).*

- **Procedural memory** — learned agent policies, successful execution patterns, and SOPs. Stored as versioned documents the agent retrieves on intent match. This is the newest tier and the one Microsoft Foundry highlighted in June 2026 as the key to agent reliability — agents that know facts but not procedures still fail complex workflows. *Storage: versioned documents in git or a document DB.*

For write-time quality, use explicit "remember" tool invocations with schema validation rather than automatic extraction from every turn. Run a periodic consolidation job that deduplicates entries, reconciles conflicting facts, and expires sessions older than the relevance window.

## Evidence

- **Production case study (Arize/Alex agent):** Arize's AI agent Alex handles observability trace analysis. The team hit a vicious loop where the agent's context was dominated by the data it was analyzing. Their three-part fix: smart truncation (first+last 100 chars stored, middle offloaded), separating context from memory management, and delegating heavy data ops to sub-agents. "Context engineering has become more critical than prompt engineering — a shift apparent in mid-2025." — Salian, Head of Product, Arize. — [ZenML LLMOps Database / Arize production case study](https://www.zenml.io/llmops-database/context-management-and-memory-strategies-for-production-ai-agents)

- **Benchmark comparison (Mem0 vs Zep/Graphiti):** Independent evaluation on the LongMemEval benchmark (temporal, multi-hop, and knowledge-update query types): Mem0 scored 49.0% versus Zep at 63.8% (GPT-4o base). However, Mem0's self-reported LoCoMo score is 92.5% and LongMemEval 94.4% using their own token-efficient algorithm (<7,000 tokens per retrieval vs 25,000+ for full-context approaches). Zep's graph-native temporal modeling with validity windows on all edges suits CRM and support use cases; Mem0's dual vector+KG store (Pro tier) and managed AWS Agent SDK integration suit personalization. — [Vectorize.io independent comparison](https://vectorize.io/articles/mem0-vs-zep), [Innobu enterprise comparison](https://www.innobu.com/en/articles/agent-memory-2026-mem0-letta-zep-hermes-openclaude-comparison.html)

- **Engineering diagnosis (Netflix senior engineer):** A Netflix engineer spent weeks debugging an agent that repeated completed steps, re-fetched seen data, and ignored tool outputs — despite a 1M-token context window. Root cause: "The problem was not context window capacity. The problem was me treating the context window as memory." Resolution: explicit five-layer separation (sensory, working, episodic, semantic, procedural) with forgetting policies and lifecycle governance per layer. — [HackerNoon / Sreekanth Ramakrishnan, Netflix](https://hackernoon.com/why-your-ai-agent-keeps-forgetting-even-with-1m-tokens)

## Gotchas

- **Do not store raw chat logs as episodic memory.** Raw logs are large, noisy, and retrieve poorly. Extract structured summaries on session close — the summarization step is where the signal survives.
- **Do not skip the delete operation.** Mem0, Zep, and Letta all support memory deletion, but teams only use add. Stale facts and superseded sessions accumulate and eventually pollute retrieval. Explicit forgetting is part of the memory lifecycle.
- **Vector DB selection matters at scale.** Qdrant leads on hot-path latency; pgvector wins under 10M records with existing Postgres infra; Weaviate suits hybrid BM25+vector queries; Pinecone is the managed option with tradeoffs on cost and portability. The storage backend is not interchangeable — pick based on your retrieval pattern, not brand recognition.
- **Procedural memory is the most under-implemented tier.** Most teams build three tiers and stop. Microsoft's June 2026 Foundry post identified procedural memory (retaining successful execution patterns) as the missing layer for enterprise reliability — facts without procedures still produce agents that know what to do but can't execute it consistently.
