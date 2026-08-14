# S-2607 · The Agentic Memory Stack — Beyond the Context Window

Your agent works perfectly in the demo. The user comes back the next day, types "continue where we left off," and the agent has no idea who they are. It re-explains the company, the preferences, what broke last time — again. Every session starts from zero. That is not a model capability problem. It is a memory architecture problem.

## Forces

- Context windows do not survive session restarts (deployments, crashes, timeouts) — a fresh instance is always a blank slate
- Prompt stuffing raw history into context costs $3+ per million tokens; production traces hit 80–120K tokens within 2–3 weeks of operation, and 100 users × 5 sessions/day = $1,500/day in input tokens alone
- Four memory types have stabilized in the 2025–2026 landscape (working, episodic, semantic, procedural), each with different access patterns, decay policies, and storage backends — conflating them is a common source of bugs
- Multi-agent pipelines are especially fragile: if agent A remembers something agent B doesn't, you get silent contradictions that are hard to trace
- Cross-tenant memory leakage is a production compliance risk that is easy to miss until GDPR auditors arrive

## The move

Layer your agent's memory into three tiers, each with a distinct retrieval mechanism and storage backend:

**Short-term (working memory) — conversation buffer scoped to the current session.**
Use an in-memory or Redis-backed conversation buffer. This is what the agent reads before every turn. Keep it lean: summarize older turns rather than appending raw history, or use a sliding window. At 10–15 conversation turns, summarize; at 30+, the buffer is already corrupting retrieval quality.

**Long-term (persistent memory) — facts, preferences, and accumulated context across sessions.**
Store as structured records (SQL rows, JSON documents, or Markdown files) with a dual retrieval path: vector similarity for semantic recall AND keyword/structured filters for exact-match lookups. Use a fact-extraction pipeline on write: the agent's output is parsed for named facts, deduplicated, and upserted — not just dumped as raw text. This is what separates production memory from a fancy text file.

**Team/shared memory — for multi-agent systems.**
A shared store (PostgreSQL, Redis, or a vector DB) that all agents query before acting. Without this, agent A's memory and agent B's memory diverge silently within the first few turns. The pattern: each agent prepends a "memory context" block to its system prompt, fetched from the shared store on every invocation.

**Key architectural decisions:**
- **Write path:** extract → deduplicate → rank by salience → store. Never write raw conversation dumps.
- **Read path:** hybrid retrieval — BM25/keyword filters for exact-match plus vector similarity for semantic recall. Recency bias matters: recent memories score higher.
- **Scope isolation:** user_id and session_id are first-class filter dimensions, not afterthoughts. Memory for user A must not appear in user B's context.
- **Forgetting:** time-based decay or importance-based eviction keeps memory bounded. Not every fact needs to live forever.

## Evidence

- **HN Show HN (DiffMem, 902 stars):** Git-based differential memory using Markdown files + `git diff/log/blame` for retrieval — no vectors, no embeddings. Powers Annabelle on WhatsApp/Messenger with "persistent memory across thousands of conversations." The retrieval agent explores the repository via shell commands; the git history itself encodes temporal relationships. — [github.com/Growth-Kinetics/DiffMem](https://github.com/Growth-Kinetics/DiffMem)
- **Engineering blog (Abhishek Chauhan, May 2026):** After hitting the memory wall on RevAgent (sales reps re-explaining pipeline context) and BandiFinder (users re-specifying procurement criteria), benchmarked Mem0 at 6,719–6,956 avg tokens/query vs 25,000+ for full-context retrieval. Key insight: "External memory is the only production-viable path" beyond demos. — [abhishekchauhan.it — Mem0/Zep/LangMem comparison](https://www.abhishekchauhan.it/blog/agent-memory-mem0-zep-langmem-production)
- **HN discussion (Gibson AI — Memori, 136 points):** "You could tell an agent, 'I don't like coffee,' and three steps later it would suggest espresso again. It wasn't broken logic, it was missing memory." Argued SQL as the practical backbone — joins, indexes, and structured records for entity storage outperform noisy vector retrieval for exact facts. — [news.ycombinator.com/item?id=45329322](https://news.ycombinator.com/item?id=45329322)
- **Research survey (Perea.ai, May 2026):** Established memory as the "third production infrastructure layer" after MCP and observability. Benchmarked vector DB hierarchy: Qdrant for hot-path (<100ms SLA), Weaviate for tool registries, pgvector for <10M vectors, Pinecone for managed scale. Four-type taxonomy (working/episodic/semantic/procedural) now dominant across the field. — [perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)
- **GitHub (agentic-memory, YaoS-Code):** Production-grade PostgreSQL + pgvector + bge-m3 memory backend as an OpenClaw plugin. Unifies workspace files and conversation history under one backend instead of separate silos. Redis for short-lived context and deduplication, pgvector HNSW index for similarity search, tsvector for full-text. — [github.com/YaoS-Code/agentic-memory](https://github.com/YaoS-Code/agentic-memory)
- **GitHub (Cognee, 30K stars):** Open-source AI memory platform combining vector embeddings with knowledge graph reasoning. Has a published research paper (arXiv 2505.24478) on optimizing the interface between knowledge graphs and LLMs for complex reasoning. Operates through four mechanisms: Recall, Evaluate, Capture, Consolidate — with nightly processes that reinforce, decay, prune, and merge memories. — [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee)

## Gotchas

- **Scope leakage is silent and catastrophic.** Always scope retrieval by user_id and session_id at the query layer — not just at the display layer. A memory from user A in user B's context is a GDPR event.
- **Raw history dumps are not memory.** Writing the entire conversation transcript to a vector store produces noisy retrieval, high token costs, and zero structure. Extract facts, deduplicate, rank by importance.
- **Context windows do not survive restarts.** If your agent restarts mid-task, any state held in memory is gone unless it's persisted externally. Design for crash-and-recover, not for uninterrupted runtime.
- **Multi-agent memory divergence.** In a pipeline of agents, each agent's memory diverges unless they share a common store. The fix is not better prompting — it is a shared retrieval step at the top of every agent's turn.
- **Vector similarity alone misses exact facts.** "I don't like coffee" as a semantic query against a vector store returns noise. Exact-match retrieval (SQL WHERE, keyword search) is the reliable path for preference and rule storage; vector similarity is for knowledge and conceptual recall.
