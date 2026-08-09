# S-2386 · The Memory Taxonomy Stack — When Your Agent Forgets Everything the Moment the Session Ends

An agent that can't remember preferences from last Tuesday, loses track of a half-finished task across sessions, and treats every new conversation like it just booted from the factory. You need long-term memory — but the architecture you pick will determine whether you ship a useful persistent agent or a complex system that's slower and worse than a text file.

## Forces

- **Context windows are large but expensive.** Ultra-long context (1M tokens in Claude Opus 4.6) doesn't eliminate the need for structured memory — loading everything into context is economically impractical and degrades retrieval quality. Production systems use a "hot/cold" memory hierarchy to manage this.
- **Specialization beats simplicity — sometimes.** Mem0 delivers 26% accuracy boost and 90% token savings over naive approaches, per their benchmarks. But Letta's own benchmarking found a plain filesystem scores 74% on LoCoMo, beating Mem0's reported 68.5% with the graph variant. The retrieval mechanism matters less than how the agent uses it.
- **Three tiers, no consensus.** The field converged on episodic / semantic / procedural memory from Tulving's 1972 taxonomy, but implementations differ wildly — from markdown files on disk to temporal knowledge graphs tracking fact provenance over time.
- **Consolidation cost is real.** A full retrieval pipeline (embed + rerank + LLM) costs roughly $0.002–0.01/query at low volume, scaling to thousands/month at enterprise scale. This shapes whether you consolidate synchronously or asynchronously.

## The Move

The three-tier memory taxonomy is the baseline vocabulary. Pick your implementation layer by layer, starting from the simplest that works:

1. **Episodic memory** (what happened): store conversation logs and interaction records. Simplest implementation: append-only JSON or markdown files per session. Production upgrade: Mem0, Letta, or Zep for automatic fact extraction and temporal queries.
2. **Semantic memory** (what is known): extracted facts, preferences, learned patterns. Backed by vector stores (Chroma, Qdrant, PGVector) for semantic search. Mem0's core strength — automatic fact extraction reduces manual schema.
3. **Procedural memory** (how to act): system prompts, agent instructions, tool definitions. Implemented as editable markdown files (CLAUDE.md), agent config objects, or Letta's memory-block API.

4. **The reflect pattern (session-end consolidation):** At session end, trigger a reflection step where the agent extracts key facts, identifies unresolved state, and writes updates to the appropriate memory tier. Implemented in Claude Diary, fsck.com's episodic memory, and claude-mem. OpenDream (MIT) does this across any LLM session locally using SQLite.
5. **Hot/warm/cold retrieval control:** Search the most relevant memories first, fall through to broader searches. Return as soon as a satisfactory answer is found — don't exhaustively search all tiers on every query.
6. **Consolidation scheduling:** Three patterns in production — time-based (simple but wasteful), event-triggered (responsive but potentially too frequent), and hybrid (timer rescheduled on activity — consolidates only during quiet periods, analogous to sleep). LangMem implements fully asynchronous background consolidation, eliminating latency impact entirely.
7. **Storage backing**: start with SQLite for single-agent/single-user cases (Remembrane: one SQLite file, zero deps). Upgrade to Postgres + PGVector for multi-tenant production. Avoid hosted vector DBs until you have retrieval latency problems.

## Evidence

- **Research blog:** Letta's own benchmarking found their agents running on `gpt-4o-mini` achieved **74.0% accuracy** on LoCoMo using simple file storage — outperforming Mem0's reported 68.5% with the specialized graph variant. The conclusion: agent capability matters more than the retrieval mechanism. — [Letta Blog, Aug 2025](https://www.letta.com/blog/benchmarking-ai-agent-memory/)
- **Comparison analysis:** AI Workflow Lab's May 2026 comparison of Mem0, Letta, and Zep shows Mem0 leads on latency (~80–200ms async) and simplicity, Letta wins on editable memory blocks for long-running agents, and Zep is purpose-built for temporal fact queries (e.g., "what changed in the last 30 days"). — [AI Workflow Lab](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Primary source research:** A December 2025 synthesis covering 60+ sources found three consolidation scheduling patterns in production use, with hybrid (timer + event) being most common, and identified that memory decay, temporal weighting, and consolidation are active research frontiers drawing from cognitive science. — [GitHub Gist, spikelab](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **Show HN:** AgentKeeper solves cross-session memory persistence by managing core context across provider switches and restarts, storing a "cognitive core" that survives infrastructure changes. — [HN Show HN](https://news.ycombinator.com/item?id=47217244)
- **Show HN:** Remembrane — agent memory in one SQLite file, zero infrastructure dependencies. Built because the author found hosted APIs, vector databases, and frameworks "felt like too much for what is usually a few facts." — [HN Show HN](https://news.ycombinator.com/item?id=49207194)

## Gotchas

- **Don't start with a vector database.** Mem0 and Letta both outperform naive RAG, but a plain filesystem already gets you to 74% on benchmarks. Add complexity when you hit a real retrieval failure, not preemptively.
- **No relevance filtering is the most common filesystem failure.** Without it, all memories load into context every session regardless of relevance — the opposite of the efficiency you're trying to achieve. Always implement a retrieval filter step before context injection.
- **"Reflect" without a budget cap burns tokens.** Each consolidation step calls the LLM. In high-volume systems, make it fully async (background job) and rate-limit by conversation, not globally.
- **Memory platforms break on provider switches.** If your agent switches from Claude to GPT mid-session, raw conversation history often fails to parse. Use structured extraction (JSON facts) rather than raw logs for cross-provider portability.
- **Benchmarks like LoCoMo measure retrieval, not usefulness.** An agent that retrieves 74% of relevant facts but ignores them or acts incorrectly still fails. Treat memory benchmarks as a floor, not a ceiling.
