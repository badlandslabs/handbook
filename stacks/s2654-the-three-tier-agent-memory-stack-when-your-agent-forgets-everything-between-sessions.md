# S-2654 · The Three-Tier Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent ran beautifully for 45 minutes yesterday. Today it has no idea who the user is, what project they were working on, or that it spent two hours debugging a flaky API. LLMs are stateless by default — each request starts from scratch. The moment you close the session, everything dissolves.

## Forces

- **Context windows don't persist across sessions.** Frontier models have 200K–1M token windows, but they reset on every API call. A user returning three days later gets a brand-new agent, not a familiar one.
- **Memory tools are everywhere but evaluation is sparse.** Mem0, Zep/Graphiti, Letta, LangMem, and a dozen vector DB backends all promise production-ready memory — but Letta's own benchmarks show a plain filesystem scores 74% on memory tasks, beating specialized memory libraries. Complexity is not automatically earning its keep.
- **The "just use vectors" answer is wrong in both directions.** Pure vector retrieval is noisy (lost-in-the-middle, semantic drift), but dismissing it means giving up on natural-language querying. Teams oscillate without a framework.
- **Episodic vs. semantic vs. procedural is not academic — it maps directly to infrastructure choices.** Storing conversation logs differently than consolidated facts differently than tool definitions is a real engineering decision with real cost and performance implications.

## The move

The production memory stack for agents has converged on a **three-tier architecture** that mirrors cognitive science (Tulving's 1972 taxonomy: episodic, semantic, procedural) with concrete infrastructure backing each tier:

**Tier 1 — Episodic Memory (event log, dual-indexed)**
- Stores every interaction as a dated, scoped event: `[user_id, session_id, timestamp, role, content, tool_calls, outcome]`
- Dual-indexed: temporal (for "what happened in the last session?") and embedding (for "what was said about project X?")
- Production default: Zep/Graphiti (temporal knowledge graph with validity windows) or Mem0 with `run_id` scope
- Use Postgres + `pgvector` for under-$50/month self-hosted; switch to Qdrant when you need sub-30ms p99 under concurrent load
- Critically: this is an *audit log*, not a fact store. Don't trust it for facts — trust it for what happened.

**Tier 2 — Semantic Memory (consolidated facts, structured)**
- Extracted facts, entities, preferences, and rules promoted from episodic memory by a consolidation step (typically an LLM call at session end or on a schedule)
- Stored in a structured store: SQL (Memori/Gibson AI's approach — joins and indexes beat fuzzy retrieval for known entities), a key-value store (Redis), or a graph store for relationship-heavy domains
- The key insight from HN discussion: SQL beats vectors for entity recall when the schema is known. "User prefers dark mode" is a row, not a cosine similarity.
- Mem0's multi-signal retrieval (semantic + BM25 + entity linking) handles the cases where you don't know the schema in advance.

**Tier 3 — Procedural Memory (how the agent works)**
- System prompts, tool definitions, skill library, agent configuration
- Version-controlled in code. Deployed, not learned. Changes go through code review.
- This is the most stable tier — it rarely changes within a deployment cycle
- LangMem (LangChain's memory library) targets this tier: manages what system context to include at each turn

**The hot/cold checkpoint layer (often overlooked)**
- Separate from the three tiers above: checkpoint state for mid-run pause and resume
- Hot: Redis for <1ms checkpoint writes under concurrent multi-agent load
- Warm: Postgres for durable, queryable pause/resume with audit trail
- Cold: file-based (Markdown or binary format) for long-term run reconstruction after crash
- The benchmark finding: SQLite is fine for single-agent local dev; Redis is mandatory in production with concurrent agents

**Memory consolidation — the "reflect" step**
- Session-end LLM call that extracts facts from the just-completed session and writes them to semantic memory
- Implemented by Claude Diary, fsck.com's episodic memory, claude-mem, and Letta's reflection system
- This is where noise gets filtered before it pollutes semantic memory

## Evidence

- **Letta benchmark (2025):** Letta agents with GPT-4o-mini using simple filesystem storage achieved 74.0% on LoCoMo memory benchmark — beating Mem0 Graph variant at 68.5%. Key finding: "A well-designed agent, even with simple filesystem tools, is sufficient to perform well on retrieval benchmarks." — [Letta Blog](https://www.letta.com/blog/benchmarking-ai-agent-memory/), August 12, 2025
- **HN production post (2026):** Gibson AI built Memori — a multi-agent memory engine using SQL instead of vectors or graphs. Their reasoning: vector retrieval is noisy and loses structure, graph DBs are hard to scale, but SQL gives joins, indexes, and the ability to promote important facts to permanent memory. 136 points, 63 comments. — [Hacker News](https://news.ycombinator.com/item?id=45329322)
- **Independent comparison (March 2026):** Vectorize benchmarked Mem0 vs. Zep/Graphiti across recall, cost, and architecture. Mem0 uses dual-store (vector + knowledge graph, Pro tier); Zep/Graphiti uses temporal knowledge graph with first-class validity windows. LongMemEval: Mem0 49.0%, Zep/Graphiti 63.8% (GPT-4o). Mem0 has 21 framework integrations and 20 vector backends; Zep targets "what was true when?" with temporal reasoning. — [Vectorize](https://vectorize.io/articles/mem0-vs-zep)
- **Engineering post (2026):** Slava Dubrov's Market Analyst Agent uses a three-tier architecture: Redis for hot per-conversation checkpoint state, Qdrant for cold cross-session fact retrieval, and Markdown files for human-inspectable document memory. Benchmark finding: "SQLite is fine for single-agent; Redis is mandatory for concurrent multi-agent production." — [Market Analyst Agent Blog](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture/)
- **Market survey (2026):** Perea.ai's research report on production agent memory identifies four frameworks that "pulled ahead of competitors" (Mem0, Zep/Graphiti, Letta, LangMem) and establishes the vector DB hierarchy: Qdrant for hot path (26–29ms p99 under 10-agent concurrent load), Weaviate for tool registries, pgvector for under-10M records, Pinecone for managed simplicity. — [Perea.ai Research](https://www.perea.ai/research/agent-memory-production), May 2026

## Gotchas

- **Don't store facts in episodic memory and expect semantic recall.** The episodic store is an audit log. If you need "user prefers dark mode," extract it to semantic memory via a consolidation step — don't just retrieve the raw conversation.
- **The "reflect" step is easy to skip and expensive to skip.** Without session-end consolidation, semantic memory accumulates noise and episodic memory grows unbounded. Both degrade agent quality over time. Budget the LLM call.
- **SQLite is a trap for production.** Fine for local dev and single-agent. The moment you have concurrent agents writing checkpoints, SQLite's locking becomes a bottleneck. Redis gives you 100% SLA compliance vs. 0.5% with SQLite under concurrent load.
- **Vectors alone fail entity lookup.** If the user says "my company" or "the plan I upgraded to," semantic vector search struggles. SQL-backed semantic memory with indexed entity columns (user_id, preference_key, project_id) handles these queries with O(1) precision.
- **Procedural memory needs version control discipline.** When your tool definitions and system prompts live in a database and are modified at runtime, you lose reproducibility. Treat Tier 3 like code: review changes, roll back cleanly.
