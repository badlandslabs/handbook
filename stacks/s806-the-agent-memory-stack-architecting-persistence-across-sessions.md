# S-806 · The Agent Memory Stack: Architecting Persistence Across Sessions

Your agent just spent 20 minutes learning your codebase, your preferences, and the bug you're chasing. Then the session ended. The next session starts from zero. Every. Single. Time. The agent has no memory — not because it can't have one, but because you haven't built the layer that gives it one.

## Forces

- **Stateless by default vs. stateful by necessity** — LLMs treat every call as new unless you explicitly inject history. Context windows are finite and expensive; you can't just stuff 100k tokens of prior conversation into every prompt.
- **"Lost in the middle"** — LLMs struggle to retrieve facts buried in long prompts even with 1M+ token windows. Simply expanding context didn't solve the problem, it moved it downstream.
- **The memory taxonomy is unsettled** — episodic, semantic, procedural, core, archival, recall. Every framework invents its own tier names. Picking the wrong tier structure wastes engineering effort and produces brittle systems.
- **Memory is now an attack surface** — memory poisoning (planting instructions that survive across sessions) achieves >95% injection success rates against production agents. A memory layer without sanitization is a persistence vulnerability.

## The Move

Build a tiered memory architecture with three canonical layers. Don't try to collapse them into one storage system — each tier has different access patterns, latency requirements, and retrieval semantics.

**1. Working/context memory (fast, in-prompt)**
- Conversation buffer + immediate task state. Lives in the system prompt or prepended to each turn.
- Typical size: 2–8 KB. Think of it as RAM.
- Managed by: the orchestration layer, not the agent itself. The LLM doesn't page this in and out — the framework does it automatically.
- *Pattern to use:* Simple rolling window or last-N-messages. Don't over-engineer this tier.

**2. Episodic/session memory (medium speed, searchable)**
- Raw events, decisions, and conversation logs from a session or group of sessions.
- Retrieval: hybrid search (vector similarity + keyword/BM25 + FTS5) — not vector search alone. Single-strategy vector search misses exact-matches and numerical facts.
- Storage: SQLite (single-node, <100K memories) or Redis (distributed, latency-sensitive). Both outperform dedicated vector DBs for this tier's access patterns.
- *Pattern to use:* Every N turns, distill the conversation into structured episodic facts. Engram calls this "consolidation" — raw episodes → semantic knowledge, same as human memory.

**3. Long-term/semantic memory (slow, deep retrieval)**
- Persisted facts, preferences, procedures, and learned workflows. Survives session boundaries.
- Retrieval: retrieval-augmented — fetch relevant memories before each LLM call, inject as context. The retrieval query is typically the current user intent or task description.
- Storage: Dual-store (vector DB + knowledge graph) or pure temporal graph. Mem0's Pro tier and Zep/Graphiti both use this hybrid approach. Pure vector search alone loses temporal ordering and entity relationships.
- *Pattern to use:* The agent decides what to store via function calls (`core_memory_replace`, `archival_memory_insert`, etc.). Letta's OS-virtual-memory metaphor — the LLM itself pages between tiers. This is the most powerful but highest-overhead pattern; use it when session depth exceeds what fits in context.

**4. Memory sanitization (mandatory gate)**
- Before writing to any persistent tier, sanitize the content. Memory poisoning (OWASP ASI06, 2026) plants instructions in memory that survive across sessions and execute when semantically triggered.
- Input: validate and strip any content that could be interpreted as a memory-format directive (e.g., "remember that you should...", "for future reference, always...").
- Treat external tool responses and uploaded documents as untrusted input to the memory tier.

## Evidence

- **Show HN — Engram (2025):** A persistent memory MCP server for AI coding agents that distills raw conversation episodes into structured semantic facts, detects contradictions (supersedes stale facts automatically), and uses spreading activation (walks the entity graph on recall instead of flat vector search). — [HN thread](https://news.ycombinator.com/item?id=47116615), [GitHub](https://github.com/tstockham96/engram)
- **Show HN — Mengram (2025):** Three-tier memory model (semantic/episodic/procedural) where procedures evolve on failure — when a workflow fails, the agent records what went wrong and updates the procedure for next time. — [HN thread](https://news.ycombinator.com/item?id=47151177), [GitHub](https://github.com/alibaizhanov/mengram)
- **LangGraph agent with Redis memory (2025):** Production-ready example showing the retrieval → analysis → memory_save pipeline. Redis stores vector embeddings + session state; the agent fetches past context before each turn and writes new memories after. — [GitHub](https://github.com/Ofekirsh/langgraph-agent-memory)
- **Letta social agent (2025):** Stateful agent on Bluesky using Letta's three-tier (Core, Recall, Archival) memory. The agent accumulates knowledge across sessions and develops a stable persona. — [GitHub](https://github.com/letta-ai/example-social-agent)
- **Mem0 vs Zep comparison (2026):** Mem0 (dual-store vector + KG) leads on GitHub stars (~48K) and token-efficient retrieval (92.5% on LoCoMo, <7K tokens/retrieval). Zep/Graphiti (temporal knowledge graph) leads on temporal reasoning (63.8% vs 49.0% on LongMemEval) and is superior when "what was true at time X?" is a frequent query. — [vectorize.io comparison](https://vectorize.io/articles/mem0-vs-zep)
- **Memori (Rust, 2025):** Show HN project using SQLite + FTS5 full-text + 384-dim vector embeddings in one file. No API keys, no cloud, no external vector DB. Hybrid search combines FTS5 + vector similarity. — [HN thread](https://news.ycombinator.com/item?id=47223089)
- **Memory poisoning research (2026):** Christian Schneider's analysis documenting >95% MINJA injection success rates against production agents, OWASP ASI06 as top agentic risk for 2026, and the architectural requirements for defense (input sanitization, validity windows, memory audits). — [christian-schneider.net](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents)

## Gotchas

- **Single-strategy vector search is insufficient.** Vector similarity alone misses exact-matches, numerical facts, and temporal relationships. Use hybrid search (RRF-ranked combination of vector + keyword + BM25) for episodic recall. Pure vector DBs like Pinecone or Chroma are the wrong tool for this tier — SQLite with FTS5 or Redis covers most production needs without the operational overhead.
- **Context stuffing doesn't scale.** Sending 100k tokens of conversation history for a 50-token response is financially unsustainable and introduces "lost in the middle" retrieval failures. Tier your memory and retrieve selectively.
- **Memory poisoning is a real production risk, not theoretical.** A document uploaded today can plant instructions that execute two weeks later when a semantically-unrelated trigger phrase appears. Every persistent memory tier must treat external input as untrusted.
- **Don't store everything.** Raw conversation logs have low retrieval value and high poisoning risk. Consolidate to structured facts (who, what, when, outcome) before writing to persistent tiers.
- **The agent doesn't need to own memory paging at small scale.** Letta's OS-virtual-memory metaphor (LLM-managed tiered paging via function calls) is powerful for deep long-horizon agents. For simple agents, a two-tier system (context buffer + episodic store with periodic consolidation) is sufficient.
