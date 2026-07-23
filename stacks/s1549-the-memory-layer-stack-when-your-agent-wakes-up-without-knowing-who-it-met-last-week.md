# S-1549 · The Memory Layer Stack — When Your Agent Wakes Up Without Knowing Who It Met Last Week

Your AI agent aced the last session — it knew the user's name, remembered their preference for Python over TypeScript, and referenced the bug they filed on the auth module. This session, it starts cold. It has no idea any of that happened. That's not a model limitation. That's an architecture gap.

## Forces

- **Vector stores solve recall but lose structure.** Semantic similarity search is powerful for knowledge retrieval, but "user prefers async communication" as a 384-dimensional vector loses the entity, the attribute, and the temporal context you actually need.
- **Long context windows have a middle-blind-spot.** Research consistently shows LLMs underperform on information in the middle of very long contexts (the "Lost in the Middle" problem). Putting everything in context is not a memory solution — it's context debt.
- **Memory-as-vector-store is expensive at scale.** Pinecone p95 latency runs 25–50ms; SQLite FTS5 queries 4,300 memories in under 1ms. Most agents don't need semantic similarity search — they need exact fact lookup.
- **The three-tier taxonomy is real but implementation varies.** Episodic (what happened), semantic (what I know), and procedural (how I do things) map cleanly to cognitive science, but production systems disagree sharply on storage backends and retrieval strategies.
- **Indie devs and enterprises have converged on different answers.** Solo developers increasingly choose SQLite+FTS5. Enterprises choose hybrid vector-graph stacks with Mem0 or equivalent managed layers.

## The Move

**Layer your memory explicitly, and match each layer to the right storage primitive.**

- **Tier 1 — Working memory (ephemeral):** JSON scratchpad the LLM reads and writes directly. Structured, not free-text. Survives prompt changes in ways that embedded instructions don't. Cleared on session end.
- **Tier 2 — Episodic memory (session-persistent):** What happened in this session. Compressed summaries or structured timestamped observations stored in SQLite. FTS5 enables full-text search without a vector DB. Scope to user_id or project_id for isolation.
- **Tier 3 — Semantic memory (cross-session persistent):** Facts about the world and the user. This is where vector stores earn their cost — for semantic recall ("what does this user typically work on?"), not exact lookup. Hybrid SQLite+Chroma/Qdrant is the production standard.
- **Tier 4 — Procedural memory (agent behavioral):** How the agent approaches problems. Stored as system prompts, tool definitions, and learned workflows. Version-controlled, not learned.

**On retrieval:** Push relevant memories into context at session start via an "AI briefing" — run a small LLM call over the episodic store to produce a compact summary, not a raw data dump. The agent reads the summary; retrieval is the model's job.

**On storage backend selection:** SQLite is the correct default for local/indie workloads. It handles < 100K memories with sub-millisecond FTS5 queries, requires zero infrastructure, and works offline. Graduate to a vector DB (Qdrant, Pinecone, Weaviate) only when semantic similarity search across > 50K items is a demonstrated bottleneck.

**On staleness:** Every memory system needs an expiry or compression policy. Bitemporal design — archiving old values instead of overwriting — lets you query "what did I know at time T?" The HN post by Arindam1729 (10 months ago, 136 points) reported that naive overwrites were the top complaint in SQL-based memory systems.

## Evidence

- **HN Show HN post:** AgentKeeper — cognitive persistence layer for AI agents, addressing memory loss when switching providers or sessions. Published ~32 days ago, directly solving cross-session persistence. — [https://news.ycombinator.com/item?id=47217244](https://news.ycombinator.com/item?id=47217244)
- **HN Show HN post:** Hmem — persistent hierarchical memory for AI coding agents via MCP. Stores memories locally in SQLite with a 5-level hierarchy (concept → entity → topic → note → raw). Solves context dilution (earlier context compressed/dropped silently) and tool lock-in (switching from Claude Code → Cursor loses memory). — [https://news.ycombinator.com/item?id=47103237](https://news.ycombinator.com/item?id=47103237)
- **HN discussion (136 points):** "Everyone's trying vectors and graphs for AI memory. We went back to SQL." Arindam1729 reported vectors lose structure, graphs are hard to maintain, and SQL with typed schema + full-text search covers most use cases at a fraction of the complexity. Top commenter noted SQLite FTS5 outperforms Pinecone on exact-attribute lookups by 2–3 orders of magnitude. — [https://news.ycombinator.com/item?id=45329322](https://news.ycombinator.com/item?id=45329322)
- **Mem0 GitHub README (61K stars):** Universal memory layer with 21 framework integrations (LangGraph, CrewAI, AutoGen, Vercel AI SDK) and 20 vector store backends. Reports 92.5 on LoCoMo and 94.4 on LongMemEval benchmarks — the current standard benchmarks for agent memory. — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **agent-recall GitHub:** SQLite-backed knowledge graph with scope-chain inheritance. Supports bitemporal storage (old values archived, not deleted), MCP-native with 9 memory tools, and AI briefing summaries instead of raw dumps. Designed for multi-agent agency workflows. — [https://github.com/mnardit/agent-recall](https://github.com/mnardit/agent-recall)
- **arXiv survey (2603.07670v1):** Comprehensive survey of memory for autonomous LLM agents (2022–2026) formalizing the four memory types, evaluation benchmarks, and emerging frontiers. Confirms three-tier episodic/semantic/procedural taxonomy as the production consensus. — [https://arxiv.org/html/2603.07670v1](https://arxiv.org/html/2603.07670v1)

## Gotchas

- **Don't store everything as vectors.** Entity attributes ("user_id=X, preference=async") should be typed columns in SQLite. Only store genuinely semantic content (free-text descriptions, summaries) in a vector index.
- **Context stuffing is not memory.** Prepending full conversation history to every prompt is a fragile, expensive pattern. The evidence shows it fails at scale and the fix is an explicit retrieval step.
- **Memory isolation is an auth concern, not a storage concern.** Scope memories by user_id/project_id at write time. A memory system that doesn't enforce scope boundaries is a data-leak system.
- **Observational memory formats beat free-text summaries.** Structured timestamped observations (`[2025-11-14] User prefers Python over TypeScript`) compress 10x better than narrative summaries and are precise enough for the model to reference in reasoning.
