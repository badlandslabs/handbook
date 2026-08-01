# S-1955 · The Three-Tier Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

An agent that resets every session is an expensive chatbot. Every user correction, every discovered bug, every learned preference evaporates when the conversation ends. The agent re-retrieves the same documents, re-makes the same mistakes, and re-asks for the same context it was told three sessions ago.

## Forces

- **Context window vs. session depth** — storing everything costs tokens; storing nothing loses continuity. Most teams over-correct toward one extreme.
- **Write latency vs. thinking latency** — synchronous memory writes block the agent's response; naive async introduces staleness.
- **Retrieval noise vs. retrieval miss** — retrieving too much context fills the context window with irrelevant content and degrades output quality ("context cliff" near 2,500 tokens). Retrieving too little misses critical history.
- **Architecture complexity vs. production reliability** — a three-layer memory system is correct; a three-layer memory system with three different failure modes is a different problem.
- **Naive summarization loses nuance** — simply condensing past conversations into summaries destroys the fine-grained facts, corrections, and decision traces that make history useful.

## The Move

Split memory into three tiers with distinct storage engines, retrieval patterns, and write cadences. The agent reads all three on every turn; writes go to the appropriate tier asynchronously so the agent never blocks.

**Working memory (tier 1) — in-process, zero latency**
- Holds current session context, intermediate calculations, active task state
- Implemented as LangGraph state or equivalent in-process object
- Always in-context; never retrieved — it's already there

**Episodic memory (tier 2) — session summaries, vector search**
- Stores condensed records of past sessions: what the user asked, what the agent did, what went wrong
- Redis (TTL-based) for the live session buffer; a background worker asynchronously condenses it into a long-term vector store (Pinecone, Milvus, or pgvector)
- Retrieved by semantic similarity to the current query — not by time, not by recency alone
- Namespaced per user so cross-user contamination never occurs

**Semantic memory (tier 3) — extracted facts, entity knowledge**
- Stores durable facts about the user, the world, and the domain — extracted from interactions, not verbatim
- Relational schema (SQLite, PostgreSQL) rather than pure vector store — you query by entity, not by embedding similarity
- Graph-based retrieval outperforms pure vector for multi-hop entity relationships
- Procedural memory (stylistic rules, behavioral patterns) can live here as structured rules with confidence scores

**Write path: never block the agent**
- Every turn: agent writes to the session buffer (synchronous, sub-millisecond Redis JSON set)
- Background worker: asynchronously compresses session buffer → long-term vector store → semantic extraction
- The agent is never aware of memory latency; it reads from all three tiers at session start

**Retrieval path: rank and cap**
- Query all three tiers in parallel
- Re-rank by recency × relevance × confidence
- Hard cap on total retrieved tokens (start at 2,000, tune upward)
- If the top-K retrieval is all episodic, extract the semantic facts embedded in it

## Evidence

- **Mem0 production benchmarks:** 91% lower p95 latency and 90% token reduction versus full-context prompting. Their pipeline: extract → consolidate → store → retrieve via vectors or graphs. Published at ECAI 2025 (arXiv). — [mem0.ai/blog/long-term-memory-ai-agents](https://mem0.ai/blog/long-term-memory-ai-agents)
- **Redis + LangGraph pattern:** Single Redis 8 instance handles ephemeral session state (JSON, TTL), Redis Query Engine for activity/status lookups, and Redis Streams for inter-service task delivery. The session buffer writes synchronously; the vector-store sync is async via a worker process. — [redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence](https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence)
- **cass-memory (406 GitHub stars):** Implements episodic (raw session logs via `cass` search engine), working (structured session summaries as diary entries), and procedural (confidence-tracked distilled rules) layers. Explicitly warns against naive summarization — "subject to collapse, loses critical nuances." — [github.com/Dicklesworthstone/cass_memory_system](https://github.com/Dicklesworthstone/cass_memory_system)
- **Mem0 vs. Letta (MemGPT) comparison:** Mem0 (~48K stars, Apache 2.0, Y Combinator $24M Series A) is a pluggable memory layer you bolt onto existing agents. Letta (~21K stars, Felicis $10M seed) is a full agent runtime — it *is* the stack. Mem0 uses passive extraction + semantic search; Letta uses agent self-editing of tiered memory blocks. — [vectorize.io/articles/mem0-vs-letta](https://vectorize.io/articles/mem0-vs-letta)

## Gotchas

- **Don't use one store for all three tiers.** Semantic memory is query-heavy (write-once, retrieve-many). Episodic is write-heavy. Treating them as the same store is the #1 production mistake.
- **Don't retrieve chronologically.** Naive retrieval by recency returns stale, irrelevant context. Use semantic similarity with recency as a secondary signal, not primary.
- **Don't skip async consolidation.** If the background worker that moves session buffer → long-term store fails silently, you lose memory on the next Redis restart. Add a write-ahead log or dual-write to the vector store before clearing the buffer.
- **Don't store everything.** Context windows degrade past ~2,500 retrieved tokens. Start with a conservative cap and measure output quality before expanding.
- **Don't confuse RAG with memory.** RAG retrieves from a static corpus you control. Agent memory retrieves from the agent's own interaction history — past decisions, user corrections, task outcomes. Same retrieval mechanism; fundamentally different data source and update cadence.
