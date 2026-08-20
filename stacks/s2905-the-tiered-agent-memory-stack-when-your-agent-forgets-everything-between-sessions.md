# S-2905 · The Tiered Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

The first serious production agent most teams build lasts about six months before users start complaining. Not about accuracy. Not about latency. About the fact that the agent forgets everything between sessions. The fix is not a bigger context window — it is a tiered memory architecture that treats episodic, semantic, and procedural memory as distinct systems with different storage, retrieval, and lifecycle properties.

## Forces

- **Vector-store bloat.** Teams that dump everything into one vector database watch retrieval quality degrade as the index grows past 50M chunks. Latency climbs past 2 seconds. The vector vendor bill exceeds the LLM bill. The root cause is not the vector store — it is treating all memory as one type.
- **Context window is not memory.** The context window is working memory, not durable storage. Stuffing session history into it to simulate memory causes token bloat, latency spikes, and degraded recall quality on exactly the facts that matter most.
- **Memory without consolidation grows linearly.** Every session adds to memory with no mechanism to summarize, rank, or expire. After 12 months the agent is retrieving thousands of semi-relevant entries instead of the three that actually matter.
- **Procedural vs. episodic confusion.** Storing "how we handled the Postgres migration last March" next to "user prefers Markdown output" treats two fundamentally different memory types as interchangeable.

## The move

Split agent memory into three distinct tiers, each with its own storage, retrieval, and lifecycle properties.

**Tier 1 — Episodic memory (what happened).** Interaction logs, completed tasks, past episodes. Stored in a vector database with semantic search (Qdrant, Pinecone, or pgvector). Key property: retrieve by similarity to the current situation. Write via background consolidation that compresses raw sessions into distilled summaries. Deduplicate aggressively (cosine similarity threshold ~0.92). Implement importance scoring: recency (50%) + access frequency (20%) + outcome quality (20%) + explicit user flag (10%).

**Tier 2 — Semantic memory (what is true).** Structured facts, user preferences, entity relationships, project ground truth. Stored in a relational store (Postgres JSONB) or graph database (Neo4j, Graphiti). Key property: exact-match retrieval and relationship traversal. Write via extraction at task completion or via background summarization of episodic summaries. Quotas per user/org prevent unbounded growth — enforce a token ceiling (target ~1500 tokens per retrieval call, ~7000 tokens per query in production systems).

**Tier 3 — Procedural memory (how to do it).** Agent skills, workflows, project-specific rules, coding conventions. Stored as editable files (Markdown, YAML, JSON) that load into the system prompt at session start. Key property: loaded at bootstrap, not retrieved at query time. Git-backed for version history and diff-based learning. A coding agent's MEMORY.md, Cursor's notepad, or Cline's memory bank are all primitive procedural memory — the difference is whether they are searchable and version-controlled.

**Memory consolidation** is the critical process that prevents linear growth. Run it asynchronously after each session: distill episodic logs into semantic summaries, score for importance, merge redundant entries, expire trivial context. The consolidation algorithm determines long-term quality more than the retrieval algorithm.

**Retrieval at session start:** query all three tiers, merge by relevance-weighted score, inject into working context. Keep the combined retrieval under ~8K tokens. The agent then operates in-context with full cross-session context.

## Evidence

- **GitHub README:** `kavishj/Persistent-Memory` — self-hosted episodic/semantic/procedural memory engine with configurable HNSW parameters (ef=128 for semantic, 64 for episodic/procedural), importance-weighted retrieval, and dedup at 0.92 cosine similarity. Uses 384-dim embeddings (all-MiniLM-L6-v2). Explicit numeric constants for reranker weights (retrieval=0.50, importance=0.30, recency=0.20). — [github.com/kavishj/Persistent-Memory](https://github.com/kavishj/Persistent-Memory)
- **Benchmark data:** Mem0's April 2026 algorithm upgrade demonstrates the cost of not tiering — full-context baselines require ~26,000 tokens per conversation, while their tiered approach achieves 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens per query. Cross-session identity, temporal abstraction, and memory staleness remain open problems per their 2026 state report. — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Real-world failure case:** A SaaS team six months into production had 92 million vector chunks, 2+ second retrieval latency, and a vector vendor bill exceeding their LLM bill. The fix was not a bigger index — it was sorting what was stored by memory type and routing each to the appropriate storage tier. — [bipi.in/blog/agent-memory-persistence-patterns](https://bipi.in/blog/agent-memory-persistence-patterns)
- **LangGraph documentation:** LangGraph 1.0+ (October 2025) treats short-term memory as part of agent state persisted to a database via checkpointer, and long-term memory as separate Store abstractions with namespace-based scoping per user or agent. LangMem provides reusable primitives (semantic, episodic, procedural) on top of the Store API. — [docs.langchain.com/oss/python/langgraph/add-memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- **Coding agent specialist:** `agentmemory` (27K GitHub stars) specifically targets coding agents — captures agent actions via background server, compresses to searchable memory, injects at session start. Reports ~170K tokens/year savings vs. full-context approaches. Benchmarks 95.2 R@5 on LongMemEval-S vs. competitors at 68-86%. — [github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)

## Gotchas

- **Dumping everything in one vector store is not a memory architecture — it is a storage problem waiting to happen.** The symptom is slow retrieval; the root cause is undifferentiated storage. Sort by memory type first.
- **Memory without forgetting amplifies noise.** Without consolidation and expiration, episodic memories accumulate indefinitely. Retrieval at session start returns a thousand semi-relevant entries instead of the three that matter. Build importance scoring and TTL floors from day one.
- **Procedural memory is not read-only.** Teams that treat learned rules as immutable end up with stale conventions. Git-back procedural memory and let agents update it via structured diffs, not raw overwrites.
- **Cross-session identity is unsolved.** Matching a user across sessions without explicit identifiers remains an open problem. Don't assume the memory system knows who it is talking to — wire identity from the application layer.
