# S-1161 · The Memory Tier Stack — When Your Agent Forgets Everything Between Sessions

[Your agent was brilliant in the demo. A fresh session starts and you re-explain the same context. The agent re-asks questions you answered last week. It suggests the approach you already rejected — without knowing why. Every session starts from zero. The amnesia isn't a bug; it's the default. The fix is an explicit memory tier: a system that decides what to store, how to structure it, when to retrieve it, and when to overwrite it.]

## Forces

- **Context window is finite and fragile.** Chroma's research documents "context rot" — LLM performance degrades measurably as input tokens grow, even on trivial tasks. You cannot keep everything in the prompt. — [Chroma Research: Context Rot, July 2025](https://research.trychroma.com/context-rot)
- **The architecture-question has no consensus answer.** Four leading open-source systems — Letta, Mem0, Graphiti, Cognee — answer the same design question four different ways. All run paid cloud services alongside open-source versions. — [Code Pointer: Agent Memory Systems, May 2026](https://codepointer.substack.com/p/agent-memory-systems-and-knowledge)
- **Simple beats sophisticated in benchmarks.** Letta's filesystem agent achieved 74.0% on LoCoMo (a multi-session recall benchmark) using basic file operations with GPT-4o mini — outperforming Mem0's specialized graph variant at 68.5%. The agent's capability matters more than the retrieval mechanism. — [ASCII News: Letta Filesystem Beats Specialized Memory, Jan 2026](https://ascii.co.uk/news/article/news-20260119-9a3c9838/simple-filesystem-beats-specialized-memory-tools-in-agent-be)

## The Move

Build an explicit memory tier with three layers. The key move: treat memory as infrastructure, not as prompt engineering.

**The three-layer architecture:**

- **Working memory (in-context):** Truncate to the top-N most recent + most relevant items. Set a hard budget (e.g., 4,096 tokens) and enforce it. Do not let the context grow unbounded — Chroma's data shows linear degradation.
- **Semantic memory (stored facts):** Facts the agent learns about users, projects, preferences. Store with timestamps and importance scores. On retrieval, rank by recency_weight + semantic_similarity. A 48-hour half-life is a common default — the Letta tutorial repo uses `recency_half_life_hours=48`. — [GitHub: Agent Memory System Tutorial, 2025](https://github.com/serhii-kucherenko/agent-memory-system)
- **Procedural memory (how to act):** Project rules, coding standards, rejected approaches with rationale. The agentmemory.md project ships ready-to-use CLAUDE.md rule files that teach agents to fetch and store memories automatically. — [GitHub: agentmemory, 2026](https://github.com/tonyzorin/agentmemory)

**The retrieval rule:** Multi-signal fusion. Semantic similarity (embeddings), BM25 keyword matching, and entity matching scored in parallel, then fused. Mem0's v3 architecture calls this "multi-signal retrieval." Single-signal vector search misses 30-40% of relevant hits on queries with keyword mismatches.

**The staleness rule:** Temporal reasoning is the hardest open problem (Mem0's ECAI 2025 paper flags it explicitly). Store events with timestamps. On update, do not overwrite — append the new fact with a timestamp and let retrieval rank by recency. This is the difference between a memory system and a cache.

**The MCP integration:** Memory as an MCP server makes it tool-agnostic. hmem ships as an MCP server backed by SQLite, enabling portable memory across Cursor, Claude Code, and Claude Desktop on the same machine. One database, all agents. — [HN: Hmem MCP, 2025](https://news.ycombinator.com/item?id=47103237)

## Evidence

- **Letta benchmark result:** 74.0% on LoCoMo (multi-session recall, 1,540 questions) using GPT-4o mini with plain filesystem operations — beating Mem0 Graph's 68.5%. Agent architecture beats retrieval sophistication. — [ASCII News, Jan 2026](https://ascii.co.uk/news/article/news-20260119-9a3c9838/simple-filesystem-beats-specialized-memory-tools-in-agent-be)
- **Mem0 evaluation (ECAI 2025):** The Mem0 paper at ECAI 2025 introduced LoCoMo, LongMemEval, and BEAM as standard benchmarks. Mem0 managed cloud scored 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query. The open-source SDK scores directionally similar but lower (proprietary optimizations are cloud-only). — [arXiv:2504.19413](https://arxiv.org/html/2504.19413v1), [Mem0 Blog: State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **MemoryHub production pattern:** One API, multiple agents. MemoryHub uses namespaces per user + categories per memory type (preference, decision, context). Importance scores (1-5) weight retrieval. Ships with FastAPI server + Python SDK + Docker. — [GitHub: Atum246/memoryhub](https://github.com/Atum246/memoryhub)

## Gotchas

- **Overwriting vs. appending:** Most naive implementations overwrite facts. Letta's core_memory_replace is a plain text swap — the old fact disappears with no record it existed. Use timestamped appends and let retrieval handle recency ranking instead.
- **Context dilution is silent:** The agent doesn't know it's forgetting. Chroma's research shows performance degrades gradually — not at a cliff. Set explicit truncation budgets and log when memories are evicted.
- **Vendor lock-in sneaks in:** If your memory lives in one agent's context, it's locked to that tool and that machine. The hmem pattern (SQLite + MCP server) solves portability: memory survives tool and machine changes. — [HN: Hmem MCP, 2025](https://news.ycombinator.com/item?id=47103237)
- **Entity linking is not free:** Mem0's v3 removed explicit graph structures from the open-source version. Entity linking across memories (for multi-hop retrieval) requires either a graph database (Graphiti/Zep) or an LLM call per memory item — both add latency and cost.
- **Token budget is a first-class concern:** At 6,900 tokens/query (Mem0's managed platform average), 1,000 daily users costs ~$0.14/day in retrieval tokens alone before response generation. At enterprise scale, memory retrieval is a material cost center.
