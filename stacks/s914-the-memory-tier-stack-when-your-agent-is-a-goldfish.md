# S-914 · The Memory Tier Stack — When Your Agent Is a Goldfish

Agents that can't remember are expensive to run and painful to use. They repeat the same mistakes across sessions, lose track of decisions made days ago, and treat every conversation like it's Day 1. The memory tier stack is the architectural pattern that separates agents with compounding intelligence from agents that reset to zero every turn.

## Forces

- **Context window vs. durable memory** — Expanding context length doesn't solve the amnesia problem. A 1M-token context window is a scratchpad, not a memory system. The moment the session ends, everything in it is gone unless you deliberately persist it.
- **Retrieval complexity vs. task fit** — Specialized vector stores, knowledge graphs, and memory frameworks exist. But Letta's own benchmarks show plain filesystem storage scoring 74% on the LoCoMo memory benchmark — beating some specialized vector solutions. The right answer depends on your workload, not the shiniest library.
- **Hot vs. cold trade-off** — Fast, in-process memory (Redis, Postgres checkpoints) handles pause/resume within a session. Cross-session durability (vector stores, file systems) handles the "what did we decide last week?" problem. Most teams over-invest in cold storage and under-invest in hot checkpoints.
- **The three-tier split** — Cognitive science maps well onto agent architecture: working memory (current step), short-term/episodic (current thread), and semantic/document (cross-session). Treating all three as one bucket leads to either under-retrieval or noisy retrieval.

## The Move

Use a three-tier memory architecture matched to retrieval speed and persistence needs:

- **Hot memory (working/short-term):** Redis or Postgres checkpoints for thread-level pause/resume. LangGraph's built-in checkpoint system handles this natively for LangGraph users. Latency target: <10ms retrieval. Used for: current task state, mid-session decisions, scratchpad.
- **Cold memory (episodic/semantic):** Vector store (Qdrant, pgvector) or key-value store (Redis) for cross-session fact recall. Embed the last N conversation turns, or extracted facts. Latency target: 50-200ms. Used for: user preferences, prior decisions, project context.
- **Document memory (semantic/persistent):** Human-readable files (Markdown, JSON) that the agent reads and writes directly. The agent can inspect its own memory — no opaque database. Used for: institutional knowledge, project summaries, "how we do things here" docs.

The "reflect" pattern (popularized by MemGPT/Letta) adds a periodic summarization step: after N turns, the agent extracts key facts and writes them to the persistent store, rather than embedding raw conversation chunks.

For teams choosing a framework: Mem0 (vector-first, lightweight), Letta (MemGPT-derived, OS-tiered memory blocks), and Zep (temporal knowledge graph via Graphiti) are the three serious production choices. Mem0 and Letta are better for personal agents; Zep's graph approach handles complex entity relationships better.

## Evidence

- **Benchmark:** Letta's own evaluation found that agents using only file-based conversation storage scored 74.0% on LoCoMo — outperforming several specialized vector-store memory solutions. The finding challenges the assumption that more complex retrieval always wins. — [Letta Blog: Benchmarking AI Agent Memory](https://www.letta.com/blog/benchmarking-ai-agent-memory/), Aug 2025
- **Architecture breakdown:** Three-tier split (hot checkpoints, cold vector/KV stores, document memory) is documented across production implementations. LangGraph's checkpoint system covers the hot layer; Qdrant or Redis covers cold; Markdown files cover the document layer. Each tier matches a retrieval speed requirement. — [slavadubrov.github.io: AI Agent Memory Architecture 2026](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture), Feb 2026
- **Production impact:** Agents with proper memory systems show 3–5x higher task completion rates and 70% cost reduction via semantic caching (avoiding redundant LLM calls on repeated queries). 95% of deployed "AI agents" in 2026 still lack cross-session memory, making this a major differentiator. — [StreamZero: Memory Architecture for AI Agents: The 2026 Production Stack](https://streamzero.com/blog/posts/deep-dives-tools-technologies-architectures/memory-architecture-for-agents), 2026

## Gotchas

- **Over-embedding:** Storing raw conversation chunks in a vector store fills up quickly and produces noisy retrieval. Extract structured facts instead, or use a summarization step (the reflect pattern). Raw chunk storage is the beginner mistake.
- **Forgetting to handle contradictions:** When a user says "I moved to Berlin" but earlier said "I live in New York," naive vector retrieval returns both facts. Frameworks like Zep (knowledge graph) and Mem0 (fact extraction) handle this better than raw embedding — but any system needs a strategy for staleness.
- **Hot memory neglected:** Teams spend months on their vector store and RAG pipeline but don't implement session checkpoints. If the agent crashes mid-task, they lose everything. Redis or Postgres checkpoints cost 30 minutes to set up and prevent total session loss.
