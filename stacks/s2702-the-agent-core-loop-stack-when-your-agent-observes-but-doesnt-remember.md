# S-2702 · The Agent Core-Loop Stack

When your agent answers correctly once and forgets everything the next session — or worse, remembers the wrong things and makes confident errors on fresh inputs.

## Forces

- **Perception without memory is just a fancy chatbot** — an agent that observes and reasons but writes nothing to persistent storage is stateless; every new session starts from zero
- **Memory and reasoning fight for context space** — stuffing long-term memory into the reasoning window burns tokens; stuffing it all into short-term buffer loses it between sessions
- **The loop must close at every turn** — agents that perceive, plan, and act but never update their memory are reactive, not agentic; they repeat the same failures across sessions
- **Storage choices ripple through latency and cost** — vector similarity search is powerful but adds 50–200ms of retrieval latency; in-memory buffers are fast but volatile
- **Memory writes are easy, retrieval is the hard part** — getting data back at the right moment, with the right scope, is a retrieval engineering problem, not a storage problem

## The move

Break agent memory into **two operational tiers** with distinct storage, retrieval, and update semantics:

- **Short-term / session buffer** (ephemeral): in-memory or Redis with TTL, holds the current conversation context and working state. Writes synchronously on every turn. Fast, cheap, transient — dropped when the session ends or TTL expires.
- **Long-term / persistent store** (durable): vector database (Pinecone, Milvus, Qdrant, Weaviate) or Postgres+pgvector, holds cross-session knowledge. Writes asynchronously via a background worker that condenses session buffers into summaries or embeddings. Indexed by user, topic, or time window.

The agent reads **both on every turn**: the session buffer provides immediate context; the vector store provides historical grounding. The agent never blocks on long-term writes — that's the background worker's job.

Forcing functions that make this explicit:

- **Memory read on every turn:** query both stores before the reasoning step, not just at session start
- **Memory write after tool execution:** update session buffer immediately; trigger async condensation after meaningful state changes
- **Namespace or tag by user/entity:** long-term memory must be retrievable per-user, not globally — shared memory between users causes contamination
- **Session buffer TTL:** set 30–60 min TTL on Redis session keys; they must expire to avoid unbounded growth
- **Condensation trigger:** run the summarizer when the session buffer exceeds ~4K tokens of recent history, not just at session end
- **Memory retrieval with scope:** use metadata filters (user_id, topic, recency) on vector search so the agent gets relevant history, not all history

## Evidence

- **Blog post:** Redis's "AI Agent Architecture" (2026) describes the dual-tier pattern explicitly — "short-term memory uses in-memory data structures for instant access while long-term memory uses vector search" — and names Redis Vector Library as the unified backing store for both tiers. Redis added hybrid search combining vector similarity with full-text and attribute filtering in a single query engine. — [https://redis.io/blog/ai-agent-architecture/](https://redis.io/blog/ai-agent-architecture/)
- **Engineering post:** Markaicode's "LangChain Agent Memory Architecture: Production Design" (July 2026) gives the exact architecture for 100K+ conversations: "Redis ephemeral session buffer (TTL-based) + Pinecone long-term vector store (namespaced per user) + background worker for async condensation." Recommends skipping the vector store entirely under ~10K conversations and using a single Redis instance with TTL eviction instead. — [https://markaicode.com/architecture/ai-agent-memory-architecture](https://markaicode.com/architecture/ai-agent-memory-architecture)
- **Survey:** A December 2025 Tsinghua University survey taxonomizes agent memory into three categories — factual memory, experiential memory, and working memory — and finds that production agents implementing multiple memory types show measurably better task completion on multi-session benchmarks. Cross-referenced via Let's Data Science's "AI Agent Memory Architecture: From Zero to Production" (2026). — [https://letsdatascience.com/blog/ai-agent-memory-architecture](https://letsdatascience.com/blog/ai-agent-memory-architecture)
- **Taxonomy:** arXiv:2601.12560v1 ("Agentic AI: Architectures, Taxonomies, and Evaluation") formalizes the six-component agent loop: Perception, Memory, Action, Profiling (core components) + Planning, Reflection (cognitive architecture). Organizes the full literature around how concrete systems are built, deployed, and evaluated — grounded in a POMDP control loop. — [https://arxiv.org/html/2601.12560v1](https://arxiv.org/html/2601.12560v1)

## Gotchas

- **Writing to both stores synchronously** — if your agent awaits the vector store write, you've added 50–200ms per tool call. Always write long-term memory asynchronously with a queue or background task.
- **Flat vector embeddings miss relationships** — semantic similarity finds "the last time we discussed pricing" but misses "the last time this user's account was suspended." Combine vector search with structured metadata filtering for relational queries.
- **Memory contamination across users** — if your vector store has no per-user namespacing and you retrieve without user_id filtering, the agent may surface another user's sensitive context. Namespacing is not optional.
- **The condensation worker is the forgotten service** — teams build the read path carefully but ship the background summarizer as a TODO. Without it, the session buffer grows unbounded and the agent loses the ability to reason about past sessions once the buffer fills.
- **TTL too short loses useful history** — a 15-minute TTL sounds efficient but means the agent forgets mid-conversation context after any latency hiccup. 30–60 minutes is the common range; tune by observing session re-engagement patterns.
