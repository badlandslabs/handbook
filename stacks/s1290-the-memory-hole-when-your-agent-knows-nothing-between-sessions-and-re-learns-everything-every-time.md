# S-1290 · The Memory Hole — When Your Agent Knows Nothing Between Sessions and Re-Learns Everything Every Time

Your agent spent 20 minutes yesterday building a model of your codebase, your preferences, and the conventions it discovered. Today it starts from scratch. Same questions, same confusions, same redundant work. The session ended and the agent reset — not because of a crash, but because memory was never architected to survive it.

## Forces

- **Context window is finite but sessions are infinite** — the natural solution (keep everything in context) hits token limits and cost walls. The naive fix (dump everything in) makes the agent slow and expensive.
- **Memory is not one thing** — episodic history, structured facts, learned procedures, and active context are accessed differently, decay differently, and cost differently to store and retrieve.
- **Persistence is not the default** — LLM APIs are stateless. Every provider, every framework, every tool defaults to forgetting. You have to opt in to memory.
- **Context dilution eats the important parts first** — working memory pushes out earlier context silently. The agent doesn't know it's forgetting — it just stops acting like it knows things.

## The Move

Build a **tiered memory architecture** that maps memory types to the right storage and retrieval pattern. The industry converged on four types (arXiv 2603.07670) with distinct requirements:

### The four-tier memory model

- **Working memory** — active context window. Zero persistence. The agent holds only what it needs right now. Truncate aggressively.
- **Episodic memory** — interaction history. Stored in a vector database (Qdrant for hot path, pgvector for <10M vectors). Retrieved via semantic similarity on each new turn. Grows unbounded without consolidation.
- **Semantic memory** — structured facts, preferences, learned entities. Stored in a relational DB with JSONB columns (Postgres) or a flat-file system the agent can read and write directly. Queried by type/schema, not just similarity.
- **Procedural memory** — learned patterns, skills, behaviors. Stored as cached few-shot examples in Redis or a compact prompt cache. Retrieved by trigger condition, not by query.

### Memory consolidation is the critical mechanism

Periodic background processing compresses episodic memories into semantic summaries. Without it, episodic storage grows without bound and retrieval noise overwhelms signal. Two approaches:

- **Hot path** — agent writes memories during conversation via a memory tool. Fast but noisy (agent must decide what's worth remembering).
- **Sleep-time compute** — a separate deep-agent reviews recent conversations between sessions, extracts key facts, and merges with semantic memory. Cleaner but adds latency.

### The plain-text + hybrid search pattern

A growing consensus (benchmarked at agent-memory.bruegs.com) favors **text files the agent can read and write directly**, with hybrid search (0.6 vector / 0.4 BM25) layered on top. Key findings: Qwen3 Embedding 0.6B runs locally via LM Studio with no API cost, token reduction of 84% on 100-turn context editing tests, and an 87% recall improvement on user preferences.

### Practical stack recommendations

| Need | Tool | Why |
|---|---|---|
| Hot-path episodic retrieval | Qdrant | Sub-10ms latency, managed tier available |
| Cross-session tool memory | Weaviate | Better for tool registries and entity graphs |
| <10M vectors, existing infra | pgvector | No new infrastructure |
| Managed simplicity | Pinecone | Fast setup, less ops control |
| Agent-owned flat files | Local `.md` / SQLite | Agent can read AND write; no embedding API needed |
| LLM-native memory management | Mem0 | Token-efficient leader (6,700 avg tokens/call vs 25,000+ full-context) |
| Temporal knowledge graphs | Zep/Graphiti | Excels at "what happened when" for agentic workflows |
| Stateful agent runtime | Letta (MemGPT) | Production-grade tiered memory with LLM-managed paging |
| LangGraph integration | LangMem | Zero-config memory for LangGraph deployments; async Postgres store for production |

## Evidence

- **Research paper:** The 2025-2026 landscape converged on four memory types with benchmarked vector-DB hierarchies and a 1,400+ star open-source library (LangMem, released Jan 2025) — *perea.ai Research, CC BY 4.0, 2026-05-07* — https://www.perea.ai/research/agent-memory-production
- **Benchmarking data:** Flat-file + hybrid search (0.6 vector / 0.4 BM25) with Qwen3 Embedding 0.6B achieved 74% LoCoMo benchmark, 87% recall improvement on user preferences, 113% improvement on sub-agent spawn rules, and 84% token reduction in 100-turn tests — *agent-memory.bruegs.com, 2026*
- **HN primary source:** Hmem (MIT) provides persistent hierarchical memory for coding agents via MCP, storing memory in local SQLite and solving both context dilution (earlier decisions silently pushed out) and vendor/machine lock-in — *Show HN, Bumblebiber, 2026* — https://news.ycombinator.com/item?id=47103237

## Gotchas

- **Retrieval strategy must match memory type** — using the same vector similarity search for episodic history, structured facts, and procedural patterns is the most common architectural mistake. Each type has a different access pattern and expected freshness.
- **Unbounded storage will kill you** — episodic memory grows with every conversation. Without consolidation, you get storage bloat and retrieval noise. Quotas per user/org and periodic compression are not optional in production.
- **Vendor lock-in is real** — if memory is stored in a tool-specific format, switching agents or models means losing context. Flat-file formats (`.md`, SQLite) that the agent can read directly are more portable than opaque proprietary stores.
- **Hot-path vs. sleep-time is a trade-off, not a preference** — hot-path (write during conversation) is fast but requires the agent to self-report what's worth remembering (unreliable). Sleep-time (batch between sessions) is cleaner but adds latency before the agent can use new memories. Most production systems run both.
