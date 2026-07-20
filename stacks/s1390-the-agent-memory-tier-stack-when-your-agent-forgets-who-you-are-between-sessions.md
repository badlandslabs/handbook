# S-1390 · The Agent Memory Tier Stack — When Your Agent Forgets Who You Are Between Sessions

Every restart, every crash, every deployment wipes the slate clean. Your users have to re-explain their preferences, your agent rediscover the same context, and your carefully crafted workflow starts from zero. You assumed the context window was memory — it is not. It is short-term working memory, the equivalent of what a human holds between two sentences. Real memory lives elsewhere.

## Forces

- **Context window is not memory.** A sliding context window for 180K tokens means your oldest turns — the ones that defined the session — silently drop first. Teams have shipped agents that verified against the oldest turn, then silently lost it, then kept running without noticing. The context window is a cache, not a store.
- **The obvious approach (store conversation history + retrieve) has hidden costs.** Naive vector retrieval over raw conversation turns produces noisy, redundant, hallucination-prone context. Without a consolidation pipeline, memory grows unbounded and retrieval quality degrades.
- **Episodic, semantic, and procedural are three distinct storage problems.** Putting all three in a vector store produces the worst of all worlds: slow queries, no audit trail, no version control, no schema enforcement. Each tier has a natural substrate and a natural access pattern.
- **The write path is as important as the read path.** Without consolidation — summarization, deduplication, schema validation — the memory store fills with drift, repetition, and stale facts that corrupt future reasoning.

## The Move

Separate agent memory into three distinct tiers, each with its own storage substrate, access pattern, and write pipeline.

**Episodic tier — store what happened.** Raw experience records: conversation turns, tool interactions, task outcomes, timestamps. Stored in a vector database (Pinecone, Weaviate, Qdrant) with structured metadata (user ID, session ID, task type, outcome, sentiment). This is the retrieval-augmented foundation — when the agent needs to recall "what did we do last time?" it searches episodic memory.

**Semantic tier — store what is true.** Extracted facts about users, entities, preferences, and domain knowledge. Stored in a relational schema (PostgreSQL with pgvector, SQLite) that you can query, join, audit, and backfill. This is source-of-truth storage — when the agent needs "what is this user's subscription tier?" it queries structured memory. Episodic memory feeds semantic memory through a consolidation pipeline: a nightly or on-demand job extracts facts, deduplicates, resolves conflicts, and writes to the semantic store.

**Procedural tier — store how to act.** Policies, system prompts, behavioral rules, learned strategies. Stored as versioned documents (Markdown files, JSON schemas, or a policy database with version history). This is what the agent retrieves on-demand: "how do we handle a refund request for this customer tier?" The agent calls an explicit `remember` tool with schema-validated input, and a periodic consolidation job verifies entries against the source-of-truth system.

**Working memory — transient state during execution.** Lives in the orchestrator's state object (LangGraph `StateGraph`, LangChain memory objects, or a dedicated state store). This is the scratchpad: current task progress, intermediate reasoning steps, active tool context. It does not survive restarts. This is where most teams mistakenly stop — they have working memory but nothing beneath it.

**The consolidation pipeline connects episodic → semantic.** On a schedule (nightly batch or on-demand on session end): extract facts from episodic records, run deduplication, resolve contradictions (e.g., user said they prefer email but also said they hate email — flag for clarification), write to semantic store. Without this step, semantic memory goes stale and episodic noise accumulates indefinitely.

## Evidence

- **Engineering blog — AppScale (May 2026):** Documents the episodic/semantic/procedural three-tier pattern as the 2026 production standard, with explicit answers to FAQ including "why is context window plus vector store not a memory architecture?" — [AppScale Blog](https://appscale.blog/en/blog/agent-memory-architecture-episodic-semantic-procedural-the-three-tier-pattern-2026)
- **r/LocalLLaMA discussion (Jan 2026):** Practitioners sharing real approaches to persistent memory — from storing conversation history and doing retrieval over it, to structured knowledge graphs, to simple AGENTS.md files in project roots for human-scale projects. Key insight: local model users (constrained by token budgets) resort to AGENTS.md + work logs as a manual procedural memory fallback. — [r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1rsm45d/how_are_people_handling_persistent_memory_for_ai/)
- **Alex Spyropoulous (Sept 2025):** Production agentic memory with three execution planes — real-time (≤4s attribute extraction + semantic search), daily (consolidation + attribute generation), and weekly (full re-indexing + compression). Targets >90% context relevance, sub-4s P95 latency, majority cache-hit rate. Explicitly calls out the consolidation pipeline as the write path that most teams skip. — [Alex Spyropoulous](https://alexspyropoulos.com/posts/demystifying-agentic-memory)
- **arXiv 2512.12686 — Memoria (Dec 2025):** Academic survey formalizing episodic, semantic, and procedural memory layers for scalable, personalized conversational AI. — [arXiv](https://arxiv.org/abs/2512.12686)

## Gotchas

- **Do not skip the consolidation pipeline.** Episodic → semantic is not automatic. Without it, you have raw noisy logs that degrade retrieval quality over time, not memory that gets smarter.
- **The `remember` tool must be schema-validated.** Letting the agent write arbitrary structured memory without validation produces corruption that propagates into future reasoning. Validate on write, consolidate on schedule.
- **Context window is your cache, not your store.** If all memory lives in the context window, you lose it on every restart, every crash, and every long task that consumes tokens faster than you summarize. The tiers underneath are what make memory durable.
- **Procedural memory needs versioning.** Behavioral rules change. If your agent retrieves "how we handle billing" from a policy document and you updated that policy last week, it needs to retrieve the current version. Unversioned procedural memory silently goes stale.
- **Audit semantic memory for right-to-be-forgotten compliance.** Episodic can be deleted on user request, but semantic facts about users may constitute personal data. The semantic tier must support deletion and provenance tracking, not just writes and reads.
