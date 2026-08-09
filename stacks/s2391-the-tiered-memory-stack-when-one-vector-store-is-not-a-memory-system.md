# S-2391 · The Tiered Memory Stack — When One Vector Store Is Not a Memory System

Your agent forgets what it knew two sessions ago. Your first instinct: add a vector database. You embed everything, retrieve on query, and call it memory. Six months later, the agent still doesn't know that user X prefers summary emails, or that feature Y was deprecated in March. You have a retrieval system. You don't have memory.

## Forces

- **LLMs are zero-state by default.** Every API call starts from scratch. The only "memory" that exists at inference time is what you stuff into the context window. There is no persistent brain inside the model.
- **Context window economics punish accumulation.** At GPT-5.4 pricing, context above 272K tokens costs 2x. At $0.01/M tokens for embedding, a 50-message session costs ~$0.50 in retrieval vs ~$5.00 stuffed directly — a 10x cost difference. Simply keeping more history costs more on every call.
- **"Lost in the middle" is structural, not marginal.** Research (arXiv:2407.16833, arXiv:2501.01880) confirms that even with massive context windows, model accuracy degrades for information embedded in the middle of long contexts. Larger windows don't fix this — they make it worse.
- **Retrieval quality ≠ memory quality.** A vector store retrieves relevant chunks. It does not know which facts are current, which are contradicted by later events, or which user preferences were overridden. Without temporal and semantic metadata, retrieval is guesswork.
- **Context rot is real.** Practitioners at Atlan (April 2026) and Zylos Research (May 2026) both observe that as sessions grow, agents appear to deprioritize instructions nominally present in the context window — not because the tokens disappeared, but because the model's attention diffuses.

## The Move

Separate memory into distinct tiers by access pattern, latency requirement, and retrieval mechanism. Do not use one system for everything.

**Hot checkpoint store** — durable, per-session state for pause-and-resume. Use Postgres or Redis checkpoint tables. The agent writes its current state (tool progress, mid-task variables, cursor positions) as structured rows keyed by session ID. Resume means reading rows, not re-running tools. Latency target: <10ms. Durability: ACID.

**Cold semantic store** — cross-session facts, preferences, and knowledge in a vector-capable backend (pgvector, Qdrant, or Pinecone). Every memory entry carries structured metadata: source session, creation timestamp, validity window, entity scope. Retrieval is filtered by recency and scope before semantic similarity runs. Do not store without metadata — an undated fact retrieved 18 months later is a liability.

**Document memory** — human-readable, LLM-editable markdown wiki for project knowledge, architectural decisions, and shared team context. The agent can read it and write to it. Karpathy's LLM Knowledge Base pattern (April 2026) applies this at personal scale: raw sources → LLM-curated markdown wiki → query-time retrieval, with full traceability from every claim back to its source. For curated personal-scale knowledge (~100 articles, 400K words), Karpathy notes this "avoids the overhead and complexity of a full RAG stack."

**Working memory compaction** — within a session, run selective summarization after every N messages or N tokens. Compress the conversation history into a structured session summary (task, decisions made, open items, user preferences surfaced). Keep the summary in context; drop the full history. This is not a memory store — it is context budget management.

**Structured fact store** — separate from the vector store for facts that must be accurate and updatable: user preferences, feature flags, entity schemas. Use Postgres rows with explicit UPDATE semantics, not embeddings. A preference like "user X wants YAML output" belongs in a key-value table, not a fuzzy retrieval system.

## Evidence

- **Engineering blog:** Slava Dubrov's "AI Agent Memory Architecture: Checkpoints and Vector Stores" (Feb 2026) documents the hot/cold split explicitly: "In production it is not one vector database — it is a mix of hot checkpoints, cold semantic/structured stores, and human-readable document memory." Provides `BaseStore` API with `InMemoryStore`, `PostgresStore`, and `AsyncRedisStore` implementations — treating them as separate tiers with different persistence characteristics. — [https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture)
- **Research + practitioner:** Andrej Karpathy's "LLM Wiki" pattern (April 2026) demonstrates a three-layer architecture — raw sources, LLM-maintained markdown wiki, schema config — that bypasses vector retrieval for curated personal-scale knowledge. Reports VentureBeat: handles ~100 articles and 400K words without a vector database, with full traceability from every AI claim back to its source. — [https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- **Production comparison:** Zylos Research's "Context Window Economics" (May 2026) quantifies the cost gap: token stuffing costs 10x more than vector retrieval at scale, but retrieval requires maintaining a separate infrastructure with its own failure modes. Their recommendation — tiered architecture with prompt caching amortizing stable content at ~90% discount — matches what LangGraph's `InMemoryStore`, pg-agent-memory, and Mem0 all implement in practice. — [https://zylos.ai/en/research/2026-05-27-context-window-economics-persistent-agents/](https://zylos.ai/en/research/2026-05-27-context-window-economics-persistent-agents/)

## Gotchas

- **Don't store facts in a fuzzy retrieval system.** User preferences, feature flags, entity schemas are updated, not retrieved. Use a structured store with explicit UPDATE semantics. Vector similarity is wrong for data that must be accurate and current.
- **Retrieval without temporal metadata produces stale answers.** A memory from a deprecated feature recalled in a current session is worse than no memory — it looks authoritative and is wrong. Every entry needs at minimum a `created_at` and a `valid_until`.
- **Putting everything in the context window is not a memory architecture — it's a debt instrument.** The cost compounds, the latency grows, and the model's attention diffuses. It works for demos. It fails at scale.
- **The forgetting-curve approach (Ebbinghaus decay) is promising but unproven in production.** YourMemory reports +16pp recall improvement over Mem0 on LoCoMo benchmark and 52% recall with biological decay on the HN demo, but the benchmark covers a narrow task type. Treat decay as an interesting direction, not a production default.
- **Local-first memory systems (CASCADE, OpenMemory) trade infrastructure complexity for privacy and latency.** The 5–10ms latency claim from CASCADE is real for SQLite-first designs, but zero-network dependency means no cross-device sync. A coding agent that forgets everything when you switch laptops is not solved by being local.
