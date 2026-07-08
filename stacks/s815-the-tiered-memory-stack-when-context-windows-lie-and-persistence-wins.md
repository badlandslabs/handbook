# S-815 · The Tiered Memory Stack: When Context Windows Lie and Persistence Wins

An agent that works great on day one and fails on day thirty isn't a model problem — it's a memory architecture problem. The context window is working memory, not memory. Treating it as the persistent store causes token bloat, degraded reasoning, and agents that forget the moment a session ends. The tiered memory stack gives agents a real memory system: working, short-term, and long-term tiers that know what to keep, what to compress, and what to archive.

## Forces

- **The context window is a lie you tell yourself** — it feels like memory because it's always there. But it's a fixed-size scratchpad, not a store. When it fills, you lose information. When you over-fill it to avoid losing information, reasoning quality degrades. "Lost-in-the-middle" accuracy drops 30–50% on facts buried in large contexts.
- **Automatic memory writes create noise** — capturing everything is easy. Filtering for signal is hard. The naive path (store all conversation history in a vector DB) produces a bloated retrieval corpus that dilutes relevance and drives up latency.
- **Cross-session identity is unsolved** — the memory model assumes a stable user_id. Anonymous sessions, multi-device users, and mixed auth flows mean two interactions from the same person may land in separate memory stores. No canonical solution exists.
- **Memory staleness is dangerous in high-stakes domains** — a memory about a user's employer is accurate until they change jobs. Decay handles low-relevance memories. Confidently-wrong high-relevance memories are an open problem with no clean solution.
- **The cost of getting memory wrong scales with usage** — one estimate puts raw token re-processing at 19.5M+ tokens/year for a busy coding agent, versus ~170K tokens/year with selective memory retrieval. That's a 100x cost difference.

## The Move

Build a three-tier memory architecture with explicit data flows between tiers:

- **Tier 1 — Working Memory (context window):** System prompt + current conversation turn + actively-retrieved long-term facts. Strict size budget. Nothing stays here by default.
- **Tier 2 — Short-Term Memory (session store):** Rolling summary of the current session's events, decisions, and pending tasks. Compressed via LLM summarization on a configurable cadence (every N messages or tokens). Evicts to long-term on session end.
- **Tier 3 — Long-Term Memory (persistent store):** Extracted facts, preferences, and lessons across all sessions. Two sub-layers: (a) **core memory / semantic store** — structured key-value facts about the user or task, kept in a relational DB; (b) **archival store** — raw conversation summaries, past tool outputs, and lower-priority material, kept in a vector store or object storage. Paging between tiers is either LLM-directed (MemGPT/Letta model) or rule-based (timestamp, relevance score, access frequency).

Key implementation decisions:
- **Memory writes are deliberate, not automatic.** Every write to Tier 3 goes through an extraction step: what fact is this, and is it worth keeping? This prevents corpus bloat.
- **Retrieval is by relevance, not recency.** Use semantic similarity search (vector embeddings) for long-term retrieval. Overlay recency and access-frequency signals as ranking boosts.
- **The agent triggers its own memory management.** Following the MemGPT/Letta "LLM OS" model: the agent receives a system prompt that teaches it to call memory tools (e.g., `core_memory.search`, `archival_memory.insert`) when it encounters information worth preserving or needs information it doesn't have in context.
- **Tier transitions are compressed.** Raw conversation → session summary → extracted facts. Each transition loses detail but gains signal density. The token cost of a fact is a fraction of the raw tokens that produced it.
- **Memory is provider-agnostic.** Store facts as structured records with a provider-independent schema. The extraction and retrieval logic stays the same when switching models or contexts.

## Evidence

- **GitHub README / Benchmark Report:** AgentMemory (24.8k stars) reports 95.2% R@5 on LongMemEval (coding agent benchmark), 98.6% R@10, 88.2% MRR. Token savings: 19.5M+ tokens/year (paste full context) → ~170K tokens/year (selective memory retrieval) → ~10/year (local embeddings). — [github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **AWS Blog / Engineering Post:** Letta builds production agents with Amazon Aurora PostgreSQL + pgvector for long-term memory. All agent state (messages, tools, memory) persists in the database. Aurora provides six-way replication across three AZs, up to 256TB storage, and automatic scaling via Aurora Serverless. — [aws-news.com / Letta Aurora PostgreSQL](https://aws-news.com/article/2025-11-26-how-letta-builds-production-ready-ai-agents-with-amazon-aurora-postgresql)
- **Letta Creator (Reddit r/AI_Agents, 2y ago):** "Unlike other frameworks, Letta is very focused on persistence and having 'agents-as-a-service.' This means that all state (including messages, tools, memory, etc.) is all persisted in a DB. So all agent state survives provider switches and restarts." — [reddit.com/r/AI_Agents/comments/1glzob6](https://www.reddit.com/r/AI_Agents/comments/1glzob6/tutorial_on_building_agent_with_memory_using_letta)
- **Blog / Engineer Analysis:** Three-tier memory design: working memory (context window, hard cap), short-term (session store with LLM summarization), long-term (vector RAG + structured key-value). Author notes "lost-in-the-middle" accuracy drops 30–50% on large context windows. — [mikul.me/blog/agent-memory-systems-short-term-long-term](https://www.mikul.me/blog/agent-memory-systems-short-term-long-term)
- **Research / Benchmark Report:** Mem0's state-of-the-art scores: 92.5 on LoCoMo, 94.4 on LongMemEval at ~6,900 tokens/query. Biggest gains: +29.6 points temporal reasoning, +23.1 points multi-hop. Open problems flagged: cross-session identity resolution, temporal abstraction at scale, memory staleness in high-relevance facts. — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)

## Gotchas

- **Don't store everything in the vector DB.** A raw conversation dump in pgvector produces a noisy corpus that degrades retrieval precision. Extract facts first, store facts second.
- **Memory staleness has no automatic fix.** Set explicit TTLs or staleness indicators for facts that can go stale. High-confidence facts about people, organizations, or preferences need manual or triggered invalidation.
- **Context window pressure corrupts memory retrieval.** When the context window is near-full, models prioritize recent turns over retrieved facts. Budget the window explicitly: what fraction is system prompt, what is working context, what is retrieval output?
- **Cross-session identity breaks the memory model silently.** If you can't reliably link a user's second session to their first, you're running two separate agents with separate memories, not one agent with persistence.
- **LLM-as-memory-manager adds latency and cost.** The self-directed paging model (MemGPT/Letta) works but introduces a tool-call overhead on every memory operation. Rule-based tier transitions are cheaper but less adaptive.
