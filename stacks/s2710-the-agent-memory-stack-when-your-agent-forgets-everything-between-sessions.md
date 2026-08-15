# S-2710 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent aced the codebase on Monday. On Tuesday it re-implemented the same function wrong in the same way it got wrong on Monday — because it has no memory of its own decisions, only context that got evicted when the window filled.

## Forces

- **Context compaction erases everything** — when the context window fills, the model drops the oldest tokens. Architectural decisions, task progress, learned patterns — gone. Re-instruction on every session is the floor, not the ceiling.
- **Three memory scopes, one system** — agents need ephemeral (working memory, per-turn), session (conversation history, per-session), and persistent (facts, learned patterns, cross-session) memory. Most implementations conflate all three, creating either memory bloat or memory loss.
- **Vector search is the default but not always right** — semantic retrieval solves recall for unstructured knowledge but adds latency, storage cost, and embedding-model dependency. Structured storage, key-value lookups, and three-layer architectures often outperform for agentic use cases.
- **Memory staleness is invisible until it bites** — an agent confidently acting on a fact about your infrastructure that changed six months ago is worse than an agent that doesn't know at all. Most memory systems have no staleness handling.

## The Move

Implement a **layered memory architecture** with distinct scopes, retrieval mechanisms, and eviction policies for each layer:

- **Ephemeral (working memory):** Pass full conversation history + relevant session facts into each prompt. No persistence — evict on session end. Purpose: what the agent is doing right now.
- **Session memory:** Store conversation summaries, tool call logs, and intermediate results in a session-scoped store (SQLite, Redis, or a JSON blob). Retain for the duration of a work session. Purpose: what the agent was doing in this session.
- **Persistent memory:** Store architectural decisions, project conventions, learned facts, and cross-session patterns in a long-lived store. Use structured key-value for decisions (fast, exact lookup) and vector search for broad knowledge retrieval. Purpose: what the agent has learned that survives restarts.

**The retrieval discipline that makes it work:**
- On session start: load CLAUDE.md / MEMORY.md + recent session summaries → warm context
- During session: write summaries every N turns or when context pressure builds
- On session end: write full session summary to persistent store, key facts to structured memory
- At query time: exact-match first (key lookup), then semantic search (vector), then session history

**Staleness handling:** tag memories with provenance and timestamp. On retrieval, filter by freshness or surface age to the agent. High-confidence facts about stable things (project conventions, team structure) age well. Facts about dynamic things (API versions, feature flags, infra state) decay fast.

## Evidence

- **arXiv survey (2026):** "MemoryArena" benchmark shows models scoring near-perfect on recall benchmarks plummet to 40–60% when memory must inform active decisions in multi-session agentic tasks. The gap between "has memory" and "doesn't" exceeds the gap between different LLM backbones. — [arXiv:2603.07670v1](https://arxiv.org/html/2603.07670v1)
- **GitHub — mneme:** A three-layer memory architecture (persistent facts, cross-session task tracking, ephemeral execution) that addresses context compaction by separating what survives forever from what only needs to survive the current session. Solves the "architectural decisions forgotten" symptom that plagues AI coding agents. — [CVPaul/mneme](https://github.com/CVPaul/mneme)
- **GitHub — futhgar/agent-memory-architecture:** A six-layer memory stack in active production use: CLAUDE.md + MEMORY.md at startup, path-scoped rules, wiki knowledge base, Qdrant semantic index, and a session database. Documents clear load-order, retrieval strategy, and use-case fit for each layer. — [futhgar/agent-memory-architecture](https://github.com/futhgar/agent-memory-architecture/blob/main/docs/architecture.md)
- **Microsoft Tech Community:** A production e-commerce memory system using SQL Server + Microsoft Agent Framework + FastAPI with three memory layers. Identifies the unsolved identity problem (no stable user identifier across sessions without auth) and memory staleness as open production problems. — [Microsoft Tech Community](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/give-your-e-commerce-app-a-memory-adding-agents-that-actually-remember-your-cust/4524021)
- **Memory benchmark landscape (2025–2026):** LoCoMo (2024), MemBench (2025), MemoryAgentBench (2025), and MemoryArena (2026) form a maturing evaluation stack. MemoryArena is the only benchmark embedding memory evaluation inside complete agentic tasks where later subtasks depend on earlier learning — exposing the difference between passive recall and decision-relevant memory. — [arXiv:2603.07670v1](https://arxiv.org/html/2603.07670v1)

## Gotchas

- **Don't use vector search as your only retrieval path.** Embedding models are imperfect — a query for "how we handle auth" may not surface a memory filed under "OAuth2 flow." Exact-match key-value lookups for structured facts (conventions, decisions, config) are faster and more reliable than semantic search alone.
- **Session summaries are lossy if done wrong.** Summarizing every 10 turns sounds safe but discards tool call details, intermediate reasoning, and error recovery steps that matter for agents doing coding work. Write summaries that preserve the *chain* of decisions, not just the outcomes.
- **Memory without a staleness policy is worse than no memory.** A confidently-wrong fact is more dangerous than an admission of ignorance. Timestamp all persistent memories and surface freshness to the agent, especially for infrastructure, API, and team-organization facts that change.
- **Don't conflate retrieval with update.** The write path (how facts enter persistent memory) is as important as the read path. A system that reads well but has no disciplined write policy accumulates noise that degrades retrieval quality over time.
- **Concurrency breaks single-writer assumptions.** If multiple agent sessions run concurrently (common in team contexts), a SQLite-backed memory store with single-writer semantics will corrupt or serialize. Use append-only logs or a DB with proper concurrency handling.
