# S-1085 · The Three-Tier Memory Stack — Why Your Agent Forgets and How to Stop It

Your agent completed a 45-minute research pipeline yesterday. Today the user asks for an update. Without a persistent memory layer, you restart from zero, burn another 45 minutes of API calls, and the agent still doesn't know the user prefers conservative risk assessments. The fix isn't a bigger context window. It's externalizing memory across three tiers that serve different jobs.

## Forces

- **The context window is volatile RAM, not a filing cabinet.** It vanishes on process restart. Treating it as durable storage leads to context hallucination, redundant API calls, and broken continuity across sessions.
- **One memory store doesn't fit all needs.** A vector database for semantic recall is the wrong tool for sub-millisecond working state. A Redis instance can't do semantic search. Teams that pick one and force-fit it to all three needs end up with either slow retrieval or lost checkpoints.
- **Checkpoint granularity is a production survival question.** A crash mid-pipeline with no checkpoint means restarting the entire workflow. The right checkpointing strategy (per-node vs. per-stage) changes the recovery time and the serialization cost.
- **Memory grows unbounded without a retention policy.** Agents accumulate facts every session. Without summarization, consolidation, or eviction, the retrieval payload grows past context limits and retrieval latency degrades.
- **Episodic and semantic memory serve different recall triggers.** Episodic memory recalls "what happened in session 7." Semantic memory recalls "what do I know about the user's risk tolerance." Mixing them into one store makes both queries slower and less precise.

## The move

Build a three-tier memory architecture matched to access patterns, latency requirements, and durability needs:

**Tier 1 — Hot (Working Memory): Redis or in-process dict**
- What it holds: current task state, active goals, last N tool outputs, intermediate reasoning artifacts
- Access pattern: read/write on every node step — sub-millisecond latency required
- Durability: ephemeral is acceptable for hot state (it gets checkpointed below); Redis for cross-process, in-memory for single-process
- Checkpoint strategy: serialize the full graph state after each node transition (LangGraph's `MemorySaver` in dev, `RedisSaver` in prod)
- What goes here: `thread_id`, `current_plan`, `completed_steps`, `pending_steps`, `last_tool_result`

**Tier 2 — Warm (Episodic Memory): PostgreSQL with structured schema**
- What it holds: full conversation history, decision traces, user corrections, task outcomes — everything you might need to replay or audit
- Access pattern: fetch on session resume, query for historical context on new task initiation
- Durability: ACID required — this is your source of truth for what happened
- Schema pattern: sessions table (session_id, user_id, started_at, ended_at, outcome), messages table (session_id, role, content, tool_calls, timestamp), decisions table (session_id, reasoning, choice, rationale)
- Consolidation: periodically summarize old message batches into distilled summaries; keep raw logs for audit, push summaries into cold tier

**Tier 3 — Cold (Semantic Memory): Vector database over structured store**
- What it holds: learned facts, user preferences, domain knowledge — things recalled by meaning, not by session
- Access pattern: semantic search on new task start, inject top-K results into system prompt or tool context
- Options: pgvector (self-hosted, Postgres), Qdrant, Pinecone, Weaviate, Chroma — pgvector wins on operational simplicity when you already use Postgres
- Retrieval: embed query → vector search → inject top 5-10 memories into context; tag memories with user_id + type (preference/fact/constraint) for metadata filtering
- Retention: Mem0 (51K+ GitHub stars) is the most-widely-adopted open-source layer for this — handles episodic/semantic/procedural memory with configurable retention policies

**Putting it together — the retrieval pipeline on new task start:**
1. Load working memory from Redis (thread_id → deserialized state)
2. Query episodic memory for session history with this user (PostgreSQL filter by user_id)
3. Query semantic memory for relevant learned facts (vector search by task query)
4. Inject working memory (current state) + episodic context (what happened recently) + semantic facts (what we know about this user/task) into the context
5. Agent resumes from hydrated state

**Temporal for durable execution (complements the memory stack):**
- When workflows span hours or cross infrastructure restarts, Temporal's durable execution handles checkpointing and retry natively
- Saga pattern for compensation when a step fails mid-workflow — roll back side effects rather than just retrying
- Combine: Temporal for workflow durability + Redis/Postgres for cross-session memory + vector DB for knowledge — each layer owns what it's good at

## Evidence

- **Blog post (slavadubrov.github.io):** Three-tier memory taxonomy — hot (Redis, <1ms) for working state, warm (PostgreSQL) for episodic history, cold (vector DB) for semantic knowledge. Checkpoints at each critical node enable resume from nearest checkpoint after failure. — https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture
- **Blog post (sitepoint.com):** "The context window functions like volatile RAM: a scratchpad that vanishes the moment the process ends. It is not a filing cabinet, and treating it as one leads to context hallucination, redundant API calls, and broken continuity across sessions." Recommends LangGraph checkpointer ladder: MemorySaver (dev) → SqliteSaver → PostgresSaver/RedisSaver (prod). — https://www.sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres/
- **Blog post (ActiveWizards, 2026):** Checkpointer selection matrix: MemorySaver for tests only (never prod), SqliteSaver for single-process servers, PostgresSaver for multi-instance deployments, RedisSaver when you need sub-millisecond throughput. Key insight: state should NOT hold data that doesn't affect routing decisions — binaries, large documents, and DB query results belong in external stores, referenced by ID. — https://activewizards.com/blog/langgraph-state-management-checkpointing-recovery-and-the-persistence-layer-decision
- **Blog post (AI Kick Start):** Mem0 architecture overview — 50-60K GitHub stars, handles semantic + episodic + procedural memory. Layered retrieval pipeline: short-term (Redis, 24h TTL) → long-term (vector DB) → episodic (structured store) → procedural (tool definitions). Summarization runs periodically to compress episodic → semantic. — https://aikickstart.com.au/news/mem0-architecture-how-agent-memory-works
- **Research paper (Atlan, citing arXiv:2404.00573):** Ablation study on generative agents simulation — removing the consolidation/reflection mechanism destroyed emergent coordination behaviors including a spontaneously organized Valentine's party. Consolidation (episodic → semantic synthesis) is the single most impactful component for believable agent behavior. Enterprise parallel: an agent that sees three pipeline incidents on the same table should develop a semantic understanding that "this table's ingestion is fragile." — https://atlan.com/know/episodic-memory-ai-agents/

## Gotchas

- **Never use MemorySaver in production.** Pod restarts wipe all active threads. Teams that discover this the hard way scramble to reverse-engineer a migration from zero checkpoints.
- **Serialization bloat kills checkpoint performance.** Storing full conversation history inside the graph state at every node floods the checkpoint store. Keep state lean — store references (IDs, keys) not data. Offload documents and large outputs to external storage.
- **Vector retrieval doesn't understand recency.** A 2-year-old fact about the user's preferences ranks the same as a recent one if the embedding similarity is high. Always filter by recency or inject freshness scores into retrieval ranking.
- **The memory stack adds latency on task start.** Hydrating from Redis → querying Postgres → querying vector DB → injecting into context adds 50-200ms before the agent even starts reasoning. Profile this; some teams pre-fetch and cache the warm tiers asynchronously.
- **Schema migrations on episodic stores are painful.** Unlike vector stores where data is append-only, PostgreSQL-backed episodic memory needs schema evolution as your agent's state shape changes. Use migrations (Alembic, Prisma Migrate) and never mutate historical rows.
