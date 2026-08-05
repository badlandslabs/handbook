# S-2185 · The Context Vaporization Stack — When Your Agent Forgets Everything the Moment the Session Ends

Your AI agent works beautifully for 20 minutes. It researched competitors, drafted an outline, remembered the user's project context, and was 80% done writing the report. Then the session expired, the process restarted, or the API rate-limited. The agent returns with no memory of any of it. The user starts over. After the third repetition, they stop using the product. This is the context vaporization problem — and most teams discover it only after their agent hits production scale.

## Forces

- **LLMs are stateless by design.** Each API call starts fresh. No yesterday, no last week. Context windows scaled to 1M+ tokens, but they still evaporate on process restart — a 1M-token window that lives only in RAM is worth exactly zero when the container restarts (Luong Hong Thuan, 2026).
- **Adding a vector DB is not the same as building memory.** Teams often answer "we use a vector database" when asked about agent memory. Vector databases solve retrieval. They don't solve memory — which requires distinct types of persistence with different access patterns, backends, and eviction policies (Xiaowei Jiang, Tacnode, Feb 2026).
- **The repetition tax is real and expensive.** Without persistent memory, every request must carry all relevant history. At 1,000 DAU × 5 interactions × 3,000 tokens = ~15M tokens/day in pure waste. At $3/M tokens: **$45/day wasted** on information the agent already processed (Luong Hong Thuan, 2026).
- **Memory failures are silent.** Unlike a crashed service, an amnesiac agent returns "success" — it generates a response. Users re-explain preferences, agents contradict earlier responses, and context resets without any clear signal to operators. Memograph CLI was built specifically to diagnose these quiet memory failures (Show HN, 2025).
- **The power-user cliff.** The Amnesia Loop punishes exactly the users who get the most value from the agent — they use it most frequently, build the most context, and lose the most when it evaporates. After 2-3 resets, power users stop using the agent entirely (Luong Hong Thuan, 2026).

## The Move

Build a four-layer memory architecture. Don't reach for one storage system — use the right tier for the right type of memory.

**1. Working memory = context window.** The LLM's immediate reasoning space. Hard token limit per turn. Nothing here survives a session restart.

**2. Episodic memory = conversation/event log.** Dual-indexed: timestamp + embedding. Stores what happened, when, with what salience. The layer that lets agents answer "what did we discuss last time?" Backends: Mem0 (62K GitHub stars, arXiv 2504.19413), Zep with Graphiti (arXiv 2501.13956), or raw Qdrant/pgvector. Target retrieval: under 7,000 tokens per call versus 25,000+ for full-context approaches (Mem0 benchmark).

**3. Semantic memory = consolidated facts.** Decontextualized, upserted knowledge about the user, project, or domain. Backends: Knowledge graphs (Zep/Graphiti's temporal knowledge graph), structured key-value stores, or Mem0's managed semantic layer. This is what most teams skip — they store conversation history but never extract and consolidate the facts from it.

**4. Procedural memory = skills and tool definitions.** Version-controlled config. System prompts, tool definitions, agent capabilities. Stored in git. Never evicted. Letta's Context Repositories (Feb 2026) treats this as a git-cloned repository on the local filesystem — agents can write scripts, spawn subagents, and process their own memory using standard Unix tooling.

**For cross-session persistence**, use Redis with LangGraph checkpointing (langgraph-checkpoint-redis, Redis Developer, 2025) for thread-level state. For multi-agent shared memory, use Redis cross-thread patterns or a shared vector store.

**The four production vector-DB tiers (Perea, 2026):**
- 2-49 agents, hot path: **Qdrant** (26-29ms p99, ~$45-96/month for 10M vectors)
- Tool/action registries: **Weaviate**
- Under 10M vectors, cost-sensitive: **pgvector**
- Managed cloud, minimal ops: **Pinecone**

## Evidence

- **Survey paper (arXiv 2603.07670, 2026):** Codified the four-type memory taxonomy (Working/Episodic/Semantic/Procedural) into a production architecture model. The framework is operationally justified — each type maps to a distinct storage backend, access pattern, and decay policy. Available at: https://arxiv.org/html/2603.07670
- **Letta blog (Feb 2026):** Context Repositories rebuild memory as a git-based local filesystem. Agents clone their memory, manage it with standard Unix tools, and push changes back. Solves the provider-lock-in problem where agents lose memory when switching LLM providers. Available at: https://www.letta.com/blog/context-repositories/
- **Perea.ai Research (May 2026):** "Memory is the third production infrastructure layer for agents — after MCP for tool access and observability for runtime visibility." Benchmarked Qdrant, Zep/Graphiti, Mem0, Letta, and LangMem. Identified three key failure modes: drift (agent misremembers facts over sessions), persistent poisoning (a single bad fact never fully cleared), and cross-context contamination (user data leaking between sessions). Available at: https://www.perea.ai/research/agent-memory-production
- **Show HN — Memograph CLI (2025):** "Agents don't fail loudly, they forget things quietly. Users re-explain preferences, agents contradict earlier responses, and context resets without any clear visibility into why." Built specifically to diagnose silent memory failures in production agents. Available at: https://news.ycombinator.com/item?id=47153242
- **Mem0 GitHub (62,488 stars, Apache-2.0):** The most-starred open-source memory layer. arXiv 2504.19413 documents its architecture: token-efficient retrieval at under 7,000 tokens per call versus 25,000+ for full-context. Available at: https://github.com/mem0ai/mem0

## Gotchas

- **Vector DB alone is not memory.** Storing conversation embeddings and retrieving them does not give an agent memory — it gives it a search engine. You still need extraction (turning conversation into facts), consolidation (merging facts, resolving conflicts), and retrieval ranking. Mem0 and Zep both solve this; raw Qdrant does not.
- **Context window ≠ persistent memory.** A 1M-token context window that lives only in RAM is still volatile. The window size race is orthogonal to the persistence problem. Scale your context window AND build persistence — they solve different problems.
- **The provider-lock-in trap.** AgentKeeper (Show HN, 2025) was built specifically because agents lose memory when switching LLM providers. If your memory is provider-native (e.g., Anthropic conversation history), you cannot switch providers without losing everything. Use an external memory layer that is provider-agnostic.
- **Silent failures are the default failure mode.** Unlike a crashed service, an amnesiac agent returns HTTP 200. There is no alert, no log line saying "context lost." You must instrument memory retrieval explicitly — track what was retrieved, when, and what the agent did with it. Perea's third failure mode (cross-context contamination) is particularly dangerous: a memory retrieval error can cause a user to see another user's data.
- **Semantic memory requires active maintenance.** Facts about a user or project change. Without a decay or overwrite policy, semantic memory grows stale. Zep/Graphiti's temporal knowledge graph handles this with timestamped edges — older facts can be shadowed without deletion. Without this, your agent will confidently cite facts that were true six months ago and are wrong today.
