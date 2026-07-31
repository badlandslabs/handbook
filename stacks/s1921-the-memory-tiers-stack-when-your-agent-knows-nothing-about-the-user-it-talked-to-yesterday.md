# S-1921 · The Memory Tiers Stack — When Your Agent Knows Nothing About the User It Talked to Yesterday

Your agent handles a support conversation on Monday, builds rapport, learns the user's setup, and resolves their issue. On Tuesday the user returns. The agent greets them like a stranger. The transcript from Monday is gone — not lost, but never stored in a form the application layer could retrieve. Every stateless LLM call returns good output; every agent that needs to compound knowledge across sessions is running on a blank slate unless you built the memory layer yourself.

## Forces

- **LLM calls are stateless by design.** The model retains nothing between calls. All "memory" is an illusion built by the application layer — you decide what to store, what to retrieve, and what to inject on the next turn. This means memory is an infrastructure problem, not a model problem.
- **Context window tension is brutal.** More injected memory → better agent decisions, but higher token cost and longer retrieval latency. Less memory → faster/cheaper, but the agent loses coherence across sessions. The ceiling on context window size does not solve this; it defers it.
- **Compression vs. preservation is a real trade-off.** Systems that aggressively compress (Mem0's summarization-based ADD-only extraction) achieve smaller context windows and lower per-query cost but risk losing critical detail. Systems that preserve everything hit storage costs and retrieval noise. No single strategy wins.
- **Most teams implement memory as a vector dump, not a retrieval system.** Storing full conversation transcripts in a vector database and retrieving by cosine similarity is not memory architecture — it is a transcript that sometimes answers the right question.

## The move

The field has converged on a **two-tier architecture** with four memory types:

**Tier 1 — Working memory (session-scoped):** The current context window. Zero infrastructure, perfectly accurate, zero-latency. Dies when the session ends. Strategy: use truncation or LLM-guided summarization before hitting context limits (~8-16 turns before depletion at 128K tokens with tool-heavy agents).

**Tier 2 — Persistent memory (cross-session):** The four subtypes that need explicit storage:

- **Episodic** — What happened: time-stamped event log of interactions, tool calls, and decisions. Analogy: ship's log or court transcript. Stored in append-only event stores with timestamps and provenance.
- **Semantic** — What is true: extracted facts, user preferences, generalized knowledge. Stored as structured records (entity-relationship), not raw transcripts. Mem0's ADD-only extraction algorithm (one LLM call, no UPDATE/DELETE) accumulates without overwriting — from 71.4 to 92.5 on LoCoMo, 67.8 to 94.4 on LongMemEval (April 2026).
- **Procedural** — How to: agent skills, workflows, behavioral patterns. MCP tool registries, prompt templates, and behavioral policies.
- **Preference** — Who prefers what: a structured overlay on top of semantic memory, with trust levels and expiry.

**The retrieval pipeline:**

1. On every turn, retrieve from semantic + episodic stores (hybrid search: vector similarity + BM25 keyword match + entity linking)
2. Inject top-K relevant memories into working memory before the next LLM call
3. After every significant interaction, extract new facts and update episodic log
4. Enforce TTL policies — not everything should persist forever

**Storage tier selection:**

- **< 10M memory items:** pgvector on Postgres with HNSW indexing (IVFFlat for write-heavy loads)
- **Multi-tenant or high-scale:** Dedicated vector DB (Qdrant for hot path, Weaviate for tool registries, Pinecone for managed simplicity)
- **Embedded/edge:** sqlite-vector (vectors as BLOBs in SQLite — zero infrastructure, no separate vector DB process)
- **Framework route:** Mem0 (framework-agnostic, Apache 2.0, 62K GitHub stars), Letta (agent-state-native, Mem0 integration), Zep/Graphiti (temporal graph for episodic recall)

**The five fields every memory record needs:** ownership (who), provenance (source), trust level (how reliable), TTL (when it expires), and correction path (how to update or delete). Without these, your memory system accumulates noise indefinitely.

## Evidence

- **Framework comparison (landscape):** Mem0 (62K stars), Letta (agent-state-native), Zep/Graphiti (temporal graph), OpenMemory (4.3K stars, Apache 2.0, multi-sector memory with fact/event/preference/feeling + associative waypoint graphs) — agent memory is a verified production category with active tooling across all deployment scales. — [AI Field Notes comparison, Michael Nemtsev, June 21, 2026](https://www.michaelnemtsev.com/memoryagents)
- **Benchmark results:** Mem0's April 2026 algorithm update (ADD-only extraction, single-pass, no UPDATE/DELETE) moved from 71.4 → 92.5 on LoCoMo, 67.8 → 94.4 on LongMemEval, 48.6 on BEAM 10M — all at < 7K tokens retrieval, < 1.1s p50 latency. — [Mem0 GitHub README / AgentMarketCap, April 13, 2026](https://github.com/mem0ai/mem0)
- **Production architecture walkthrough:** Postgres + pgvector as agent memory substrate with HNSW indexing, hybrid search (vector + BM25), tenant-safe schema with provenance/trust/TTL fields, and retention/deletion policies. — [Stanley Yang, AI Agent Memory with Postgres and pgvector](https://stanleycyang.com/writing/ai-agent-memory-postgres-pgvector)
- **Real-world HN discussion:** "Show HN: Formative-memory" — open-source memory plug-in with associations, forgetting, and synthesis — surfaced active developer interest in memory systems that go beyond retrieval. — [Hacker News, Show HN, ~79 days ago](https://news.ycombinator.com/item?id=48048647)

## Gotchas

- **Storing transcripts instead of extracted facts is the dominant anti-pattern.** Embedding full conversation history and retrieving by cosine similarity is not memory architecture — it's a transcript that accidentally matches. Semantic memory requires an LLM extraction step (or a human annotation step) to convert raw dialogue into structured facts with provenance.
- **Forgetting is a feature, not a failure.** Systems that never expire memories accumulate stale data that degrades retrieval quality. Every memory item needs a TTL or a relevance decay mechanism. OpenMemory's approach (recency + importance weighting) and TTL-enforced schemas both address this.
- **Multi-tenant memory requires explicit isolation.** In production, a memory record must carry both user ownership and tenant ID. Hybrid search on shared vector infrastructure can leak results between tenants if the schema doesn't enforce row-level filtering on ownership at query time.
- **The retrieval step is the bottleneck, not the storage step.** Teams obsess over which vector DB to use but ship with no retrieval strategy beyond top-1 cosine match. Effective retrieval combines vector similarity, keyword BM25, entity linking, and temporal recency — in that order of impact for most agent workloads.
