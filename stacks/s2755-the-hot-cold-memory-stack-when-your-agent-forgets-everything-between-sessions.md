# S-2755 · The Hot-Cold Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent aced the demo. Three weeks into production, it keeps asking the same questions it asked on day one. It forgot the bug you debugged together. The architecture decision. The customer's name. Every session starts from zero. This is the persistent memory problem: the gap between what fits in a context window and what survives between sessions.

## Forces

- **Token economics punish context stuffing.** A 200K-token context window sounds generous, but at $3–15/M tokens for frontier models, a fully-populated context costs $0.60–4.50 per turn. Teams that stuff everything in context window blow through budgets; teams that stuff nothing lose continuity.
- **Retrieval latency is a user experience problem.** Sub-100ms memory retrieval is the production bar (per Brandon Lincoln Hendricks' production context management research, 2026). Vector store round-trips add 50–200ms on average. Cold storage adds seconds. An agent that pauses to "remember" feels broken.
- **The three failure modes are all different.** Memory that doesn't persist (amnesia) is different from memory that persists the wrong thing (confabulation), which is different from memory that never gets retrieved (oblivion). Most teams solve one and break another.
- **Tiered storage adds operational complexity.** Hot/Warm/Cold/Frozen tiers (per Redis agentic architecture guide, 2026) solve the latency/economics tradeoff but introduce cache coherency, staleness, and tier-migration bugs that a flat KV store never had.

## The Move

Implement a four-tier hot-to-cold memory architecture that matches retrieval latency to access frequency. Most production systems converge on this pattern:

- **Hot tier (in-process, <1ms):** Working memory — current task context, active plan, recent tool results. Stored as structured objects in memory, not in context. The agent writes here freely; this tier is volatile and bounded (typically 4–16KB of structured state).
- **Warm tier (vector store, <20ms):** Semantic memory — embeddings of recent conversations, extracted facts, entity descriptions. Queried via similarity search on each turn. Persists across sessions. Typical stack: pgvector, Qdrant, or Weaviate with a reranker on top.
- **Cold tier (object store / KV, <200ms):** Episodic memory — full conversation logs, tool execution traces, task completions. Retrieved by explicit query or policy (e.g., "load last session's context if same user"). Stored as JSON or Parquet in S3/R2.
- **Frozen tier (archive, seconds):** Procedural and declarative knowledge — learned procedures, policies, accumulated entity knowledge. Rarely accessed but never discarded. Used for onboarding a new agent instance or recovering from corruption.

**The key implementation insight** from AgenticMemory's v3 architecture (Agentra Labs, 2026): use a single portable `.amem` file with BLAKE3 integrity chains as the append-only log. Five indexes — temporal, semantic, causal, entity, procedural — sit on top. This means "the log is the database," not a SQL table or a vector store. Crash recovery is a replay, not a restore.

**On retrieval:** query all relevant tiers in parallel, merge by recency and relevance, cap at context window budget. The Mem0 2026 benchmarks (LoCoMo, LongMemEval) show hybrid BM25+vector search at 10.83ms for 100K nodes — acceptable for warm tier. Don't query cold tier on every turn; use policy triggers (user ID change, task boundary, explicit recall).

**On writes:** don't write everything. Agent trajectories generate enormous logs. Mem0's procedural memory pattern (2026) shows that ingesting full conversation logs is wasteful — extract decisions, corrections, and procedures instead. A 10-minute coding session produces 50KB of tokens but yields ~2KB of durable memory facts.

## Evidence

- **GitHub (AgenticMemory):** Agentra Labs' agentic-memory repo (Rust core, Python SDK, MCP server) implements the four-tier hot→warm→cold→frozen pattern with BLAKE3 integrity chains and five indexes. Benchmarks show 276ns node add, 3.4ms depth-5 graph traverse, 10.83ms hybrid search at 100K nodes. — [https://github.com/agentralabs/agentic-memory](https://github.com/agentralabs/agentic-memory)
- **Research (Brandon Lincoln Hendricks, 2026):** Documents the Hot→Warm→Cold production state architecture with sub-100ms retrieval targets, noting that "treating state as just stored conversation history is like using a Ferrari as a golf cart." Emphasizes that hot state must be structured objects, not embedded strings. — [https://brandonlincolnhendricks.com/research/agent-state-persistence-patterns-production-context-management](https://brandonlincolnhendricks.com/research/agent-state-persistence-patterns-production-context-management)
- **Industry (Redis blog, 2026):** Five agentic architecture patterns documented: reactive agent, planning agent, reflective agent, hierarchical agent, and collaborative multi-agent. Identifies memory systems as the component that separates agents from stateless chatbots, with sub-loop vs. outer-loop planning as the key architectural split. — [https://redis.io/blog/agentic-ai-architecture-examples/](https://redis.io/blog/agentic-ai-architecture-examples/)
- **Framework (Mem0, 2026):** Mem0's state-of-memory report shows 21 frameworks integrated, 20 vector stores supported, and benchmark scores of 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query. Procedural memory (extracting learned procedures from trajectories, not storing raw logs) is the newest capability. — [https://mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **HN Show HN (architsingh15, 2026):** "Every Claude Code session starts from zero. It doesn't remember the bug you debugged yesterday, the architecture decision you made." Shows practitioner demand for cross-session persistence via a Rust-based MCP memory layer. — [https://news.ycombinator.com/item?id=47223089](https://news.ycombinator.com/item?id=47223089)

## Gotchas

- **Writing everything creates a retrieval-augmentation trap.** If you store 100% of agent output, you retrieve 100% of it — and spend context window budget on noise. Extract facts and decisions, not transcripts.
- **Vector similarity is not semantic relevance.** A query about "database performance" may retrieve a conversation about sports cars if the embedding is close enough. Always layer a reranker or keyword filter on top of vector results.
- **The cold tier goes stale.** If warm and cold tiers diverge (e.g., warm has the entity updated, cold still has the old version), the agent may act on stale facts. Implement TTL-based invalidation or version-linked entries.
- **Crash recovery must be tested under load.** The "log is the database" pattern is elegant but recovery time grows with log size. AgenticMemory uses a WAL (write-ahead log) for crash recovery, but a 500MB log still takes seconds to replay.
- **Memory poisoning is real.** MemGhost (S-2752) covers this in detail, but the specific gotcha for tiered memory: if an adversarial fact gets stored in warm tier (vector store), semantic similarity won't flag it as anomalous. Gate writes with a lightweight verification step before the memory enters the warm tier.
