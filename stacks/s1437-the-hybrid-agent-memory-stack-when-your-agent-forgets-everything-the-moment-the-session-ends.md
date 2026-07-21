# S-1437 · The Hybrid Agent Memory Stack — When Your Agent Forgets Everything the Moment the Session Ends

Your agent spent 45 minutes yesterday learning that this codebase uses `Decimal` for all financial types, that the team prefers PRs under 400 lines, and that the `auth/` module was refactored last quarter. Today it opened the repo and behaved as if none of that had ever happened. Every session starts at zero. Nothing compounds. This entry covers the tiered memory architecture that makes agents actually remember — across sessions, users, and time.

## Forces

- **Context windows don't solve this.** A 1M-token window still resets between sessions. The model processes each request independently with no knowledge of what happened yesterday, last week, or three months ago. Pushing the entire history into context is economically untenable at scale — input tokens dwarf compute costs.
- **"Lost in the middle" persists.** Even with massive context, attention degrades. The right fact from a 200-token ago is not the same as the right fact from a 200,000-token ago. Agents hallucinate the same mistakes repeatedly.
- **No single store is right for everything.** Fast recall needs vector similarity search. Precise lookups need KV. Relational reasoning needs a graph. Real agents use all three — and the dominant production pattern is a hybrid that layers them.
- **The agent must manage its own memory.** Memory is not just storage — it is an active system the agent writes to, reads from, and organizes. Frameworks that treat memory as a passive store (dump everything, retrieve everything) produce bloated context and poor recall.

## The Move

The production memory stack is a **three-tier hybrid architecture** with an agent-managed forgetting policy:

**Tier 1 — Working memory (always in context):** The agent's current conversation turns plus a curated core memory block. This is the "desk" — what the agent is actively thinking about right now. Sized strictly (typically 2-4KB of key facts). If it grows beyond the limit, the agent decides what to evict.

**Tier 2 — Episodic + Semantic retrieval (hybrid search):** Past interactions and extracted facts stored in a dual-store system. Vector search provides semantic recall ("what did we decide about the payment flow last month?"). KV or relational store provides exact-state lookups ("what is the user's current subscription tier?"). Knowledge graph provides relational reasoning ("who approved this change and what else did they touch?"). Retrieved results are re-ranked and injected into context at session start and periodically during long tasks.

**Tier 3 — Archival / Procedural memory (cold storage):** Everything else. Letta calls this "archival memory" — memories too low-priority to fit in Tier 2 but accessible if the agent explicitly queries them. This prevents the useful-from-yesterday from crowding out the critical-from-five-minutes-ago.

**Forgetting is not optional — it is a feature.** Explicit forgetting policies (TTL-based, relevance-threshold-based, or agent-decided) prevent memory bloat. Systems like `agentmemory` compress raw tool observations into structured facts on session end, achieving 95.2% R@5 on the LongMemEval benchmark while reducing token-per-session overhead by 92%.

**The cross-framework consensus on four memory types:**
- **Working** — current session state, context window resident
- **Episodic** — specific past events, stored with timestamps in a temporal knowledge graph
- **Semantic** — extracted facts, preferences, and knowledge, stored as facts in a vector store
- **Procedural** — the agent's own instructions and learned behaviors, versioned and hot-swappable

## Evidence

- **Blog post (Letta):** Rearchitecting Letta's Agent Loop — MemGPT's core insight was treating memory as an OS-style hierarchy (core + archival), not a flat log. Letta extends this with the agent actively deciding what to store, retrieve, and forget via tool calls, not被动 injection. — https://www.letta.com/blog/letta-v1-agent

- **Comparison analysis (Vectorize):** Mem0 vs Letta comparison shows Mem0 (~48K GitHub stars, Apache 2.0, $24M Series A) as a pluggable memory layer with simple `add()`/`search()` API and dual vector + KG storage. Letta is an agent runtime — it is the stack, not a component you bolt on. Zep uses Graphiti, a temporal knowledge graph where time is a first-class dimension, achieving 63.8% on LongMemEval (vs Mem0's 49.0%) because validity windows resolve contradictions across fact updates. — https://vectorize.io/articles/mem0-vs-letta and https://vectorize.io/articles/mem0-vs-zep

- **Engineering guide (jobsbyculture.com):** LangMem (LangChain's memory module) replaces deprecated `ConversationBufferMemory` as the LangGraph-native solution. For LangGraph users, LangMem is the path of least resistance. The guide emphasizes that the dominant production pattern is tiered: always-in-context core + vector-store retrieval + explicit forgetting policy. — https://jobsbyculture.com/blog/ai-agent-memory-systems-guide-2026

- **HN "Show HN" (agent-memory.dev):** "Agent Memory gives AI coding agents persistent memory across sessions with hybrid search and a 4-tier pipeline. 95.2% recall, 92% fewer tokens per session." Supports Claude Code, Cursor, GitHub Copilot CLI, and 13+ other agents via MCP. Benchmarked against Mem0 (81.4%), Letta (73.8%) on LongMemEval-S R@5. — https://www.agent-memory.dev/docs/introduction

- **HN "Show HN" (feelingsonice/MemoryBank):** Show HN for cross-agent unified memory written in Rust. Addresses "context rot" — the degradation of agent recall quality as session history grows. Rust chosen for predictable latency and low memory overhead in long-running agent deployments. — https://news.ycombinator.com/item?id=47644841

- **Engineering post (StreamZero):** "95% of 'AI agents' deployed today are still glorified chatbots with amnesia." Production agents with proper memory achieve 3-5x higher task completion rates and 70% cost reduction via semantic caching. The key insight: AWS Bedrock AgentCore succeeds because it ships with memory-as-a-first-class primitive, not as an afterthought. — https://streamzero.com/blog/posts/deep-dives-tools-technologies-architectures/memory-architecture-for-agents

- **GitHub repo (NirDiamant/Agent_Memory_Techniques):** 30 runnable notebooks across six families: short-term (conversation buffers), long-term (vector stores, knowledge graphs), cognitive architectures (hierarchical/reflective), retrieval & routing, production frameworks (Mem0, Letta, Zep, Graphiti), and evaluation. The decision tree shows the branching logic: "Need to manage current chat?" → short-term. "Need to persist across sessions?" → long-term. "Need the agent to organize its own memory?" → cognitive architectures. — https://github.com/NirDiamant/Agent_Memory_Techniques

- **Blog (arunangshudas.com):** "The majority of real-world agents do not make the choice of a single one. Hybrid memory systems merge several types into layered systems. One popular architecture is to use KV memory as state, vector memory as recall, and graph memory as reasoning. Such a mixed solution is representative of human cognition: fast facts, hazy memories, and organized knowledge functioning in the same direction." — https://arunangshudas.com/blog/ai-agent/memory-for-agents-vector-kv-graph/

## Gotchas

- **thread-id vs user-id scoping.** The most common production memory bug: using `thread-id` (session-scoped) when you mean `user-id` (cross-session). ConversationBufferMemory is deprecated in LangChain ≥0.3.1 — switch to LangGraph checkpointers or LangMem.
- **Pushing full history into context is not memory — it is bloat.** The correct pattern is selective retrieval, not dump-and-hope. Without a retrieval strategy (semantic search, recency weighting, reranking), you get the cost of long context without the precision.
- **Forgetting is load-bearing.** Memory systems that never evict grow until retrieval latency kills performance. TTLs, relevance thresholds, or agent-decided eviction are not optional cleanup — they are part of the retrieval quality contract.
- **Dual-store mismatch.** Mem0's knowledge graph is Pro tier only ($249/mo). If you need relational reasoning, the free tier of Mem0 may not deliver it — Zep's Graphiti makes temporal KG the core, not an upsell.
- **Context window ≠ memory ≠ persistence.** These are three separate concerns. A 128K context window solves how much you can fit into one response. Memory solves how you store across sessions. Persistence solves how you survive restarts. Conflating them is the root of most "we have memory but it still forgets" issues.
