# S-1948 · The Memory Stack — When Your Agent Forgets Everything Between Sessions

You shipped a prototype. It works great within a session. Then the user comes back tomorrow and the agent has no idea who they are, what they were working on, or what decisions were made. Session context evaporates because LLMs are stateless functions. This is the memory problem.

## Forces

- **Latency vs. richness** — loading comprehensive memory on every request is expensive; loading nothing means starting from zero
- **Semantic retrieval vs. temporal retrieval** — vector similarity finds "what sounds like this" but fails on "what happened last Tuesday"; time-indexed retrieval handles recency but not topic drift
- **Complexity vs. capability** — pgvector + Redis + knowledge graph is powerful but ops-heavy; plain markdown is simple but limited
- **Append-only vs. reconciliation** — memories accumulate forever until context windows overflow; but overwriting risks losing audit trails
- **Agent-write vs. plugin-write** — trusting the agent to write its own memory introduces format drift, omissions, and self-serving edits

## The Move

Build a two-layer memory architecture: **short-term** (session-scoped, checkpointed) and **long-term** (cross-session, retrievable). Separate episodic memory (what happened, indexed by time) from semantic memory (what is true, indexed by meaning).

Key implementation moves:

- **Short-term lives in checkpoints.** Use LangGraph checkpointing or equivalent for the active session. This is the working memory — active plan, current task state, reasoning scratchpad. Cleared or archived when the session ends.
- **Episodic memory uses structured event records, not raw text.** Store `{timestamp, task_id, event_type, summary, outcome}` as structured data. Dual-index: time-ordered for recency queries ("what did we do Thursday?"), embedding-indexed for semantic queries ("did we discuss the billing API?").
- **Semantic memory uses a separate store.** Factual knowledge about the user, their preferences, their domain — not raw conversation logs. pgvector on PostgreSQL is the production standard for teams already on Postgres; plain JSON/markdown namespaces work for simpler stacks.
- **Plugin writes, agent reads.** The agent never writes to memory. A separate process extracts, classifies, and stores memories from conversation transcripts. This is the single most important reliability guarantee in the system.
- **Treat forgetting as a feature.** Set retention policies: summaries replace full transcripts after N turns, low-relevance memories expire first, knowledge conflicts trigger reconciliation rather than accumulation. Mem0's 2026 algorithm (hierarchical single-pass extraction + multi-signal retrieval) scored 92.5 on LoCoMo and 94.4 on LongMemEval using only ~6,900 tokens/query — evidence that selective memory beats comprehensive retention.

## Evidence

- **Survey paper:** The arXiv:2512.13564 consensus taxonomy (47 researchers, Dec 2025/Jan 2026) establishes three axes for agent memory — forms (token-level, parametric, latent), functions (factual, experiential, working), and dynamics (formation, evolution, retrieval). "Traditional taxonomies such as long/short-term memory have proven insufficient." — [arXiv:2512.13564](https://arxiv.org/abs/2512.13564)
- **Benchmark data:** Mem0's 2026 algorithm achieves state-of-the-art on two production memory benchmarks: 92.5 LoCoMo, 94.4 LongMemEval, at ~6,900 tokens/query — proving selective retrieval outperforms full-context approaches on both quality and cost. — [Mem0 State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Production blueprint:** PostgreSQL 15+ with pgvector 0.6 as the memory store, Redis for step leasing and session queuing. Bottlenecks appear at PostgreSQL connections and pgvector search latency (~48ms p95) before Redis or workers saturate. Recommend PgBouncer and read replicas from day one. — [Markaicode: PostgreSQL Agent Architecture](https://markaicode.com/architecture/agent-architecture-with-postgres)
- **Tooling pattern:** Jannhsu/agent-memory (11 stars, MIT) implements agent-reads/plugin-writes with plain markdown — no vector DB, no embeddings. Identity, knowledge, preferences, and lessons stored as structured YAML-frontmatter markdown files. Agent explicitly forbidden from writing to its own memory files. — [GitHub: Jannhsu/agent-memory](https://github.com/Jannhsu/agent-memory)
- **HN discussion:** Hopsule solves architecture decision persistence — turns team decisions into machine-readable rules that AI coding tools must follow, preventing drift from session to session. — [HN Show: Hopsule](https://news.ycombinator.com/item?id=47415402)

## Gotchas

- **Semantic vector retrieval is not enough for episodic queries.** "What happened in our last session?" is a temporal query, not a semantic one. If your episodic store only has embedding indexes, it will fail on recency-dependent questions. Dual indexing (time + embedding) is the minimum viable episodic layer.
- **Agent-write memory introduces corruption.** Agents skip writes when busy, break formats under pressure, and introduce duplicates. The agent should consume memory, not produce it.
- **Unbounded accumulation has real costs.** Every stored memory costs tokens on retrieval. Without active forgetting, context costs grow unboundedly until the model starts hallucinating to stay under limits.
- **Knowledge conflicts accumulate silently.** If session 3 says "the user prefers Python" and session 7 says "the user prefers Node", a naive vector store returns both. You need explicit conflict resolution or the agent acts on stale preferences.
- **Don't add pgvector until you need it.** For most agents under 1000 sessions, a JSON store with namespace/key structure and date-based filtering is faster to build and easier to debug than a full vector pipeline.
