# S-1255 · The Agent Memory Stack — When Your Agent Forgets What It Already Knows

You built a customer support agent. It verified a user's account on Tuesday. On Friday, it asked them to verify again. The agent isn't broken — it lost the verification turn when its sliding context window moved on. The information didn't disappear from the world. It disappeared from the agent's memory.

## Forces

- **Context window ≠ memory.** A 200K-token window is L1 cache — fast, ephemeral, and bounded. Memory lives somewhere else. Treating the window as durable storage is the root cause of most memory failures.
- **Accumulation vs. retrieval cost.** Storing everything is free. Retrieving the right thing at the right time costs money and latency. Naive "stuff it all in" strategies hit token limits and accuracy degradation.
- **Forgetting is harder than remembering.** Teams build storage easily. They underinvest in retrieval ranking, decay policies, and compaction logic — then wonder why the agent "remembers" useless facts and loses critical ones.
- **Context rot is invisible.** When a sliding window drops the oldest turn, nothing breaks. The agent just acts as if that turn never happened. No error. No log. Silent amnesia.

## The Move

Treat memory as a first-class system with distinct layers, each with its own storage, retrieval, and eviction strategy.

**1. Separate short-term (working) from long-term (durable) memory.**
Short-term: conversation turns in the current session, kept in context. Long-term: everything that needs to survive across sessions — user facts, past interactions, learned preferences. Never conflate the two.

**2. Use a 3-type cognitive model (episodic, semantic, procedural).**
- *Episodic* — "what happened in this interaction" (conversation logs, event traces)
- *Semantic* — "what the agent knows about this user/domain" (extracted facts, preferences, summaries)
- *Procedural* — "how to do this task" (agent instructions, tool definitions, workflows)

**3. Offload to external stores; retrieve on demand.**
Don't keep everything in context. Store in Postgres, SQLite, Redis, or a vector DB (pgvector, Qdrant, Chroma). Retrieve relevant facts at turn time based on query similarity + recency. This is L2/L3 cache, not context stuffing.

**4. Layer retrieval by latency and cost.**
Fastest (free): static files loaded at session start (CLAUDE.md, system prompts). Medium (file read, ~50ms): wiki articles, project docs. Slowest (vector query, ~20ms): semantic search across long-term memory. Budget your token spend per layer.

**5. Implement recency-weighted retrieval.**
Rank memories by a composite score: topical relevance (80%) + freshness (20%). A memory's freshness halves over a configurable half-life (default ~48 hours). This mirrors the Ebbinghaus forgetting curve — frequently accessed memories stay prominent, stale ones fade.

**6. Build a compaction / summarization pipeline, not just accumulation.**
Summarize episodic turns into semantic facts before the window closes. Chunk summaries into retrievable units. A memory system that only grows is a log, not memory.

## Evidence

- **Engineering blog (Tianpan.co, April 2026):** "A 1M-token context window is not a memory system." Documents the three-type model (episodic/semantic/procedural), with production guidance: build full context baseline first, measure it, then replace specific failure modes with targeted retrieval. — [tianpan.co/blog/long-term-memory-types-ai-agents](https://tianpan.co/blog/long-term-memory-types-ai-agents)

- **Practitioner incident (AmtocSoft, April 2026):** Real incident at a fintech support team — agent told a customer his account was unverified four months after verifying it. Root cause: sliding context window dropped the oldest (verification) turn. Key quote: "Context window is L1 cache. Memory must live in L2/L3 stores." — [amtocsoft.blogspot.com/2026/04/ai-agent-memory-patterns](https://amtocsoft.blogspot.com/2026/04/ai-agent-memory-patterns-semantic.html)

- **GitHub architecture (futhgar/agent-memory-architecture, 2026):** 6-layer memory architecture for coding agents: CLAUDE.md → path-scoped rules → auto-memory → wiki → Qdrant vector search → MSAM cognitive memory. Includes latency profile table (0ms for static files, ~20ms for vector queries, ~50ms for file reads). — [github.com/futhgar/agent-memory-architecture](https://github.com/futhgar/agent-memory-architecture/blob/main/docs/architecture.md)

- **GitHub repo (srinivasraom/agent_memory):** Production-grade persistent memory using PostgreSQL + pgvector. Seven memory types, structured summarization, semantic tool retrieval, complete memory-aware agent loop. — [github.com/srinivasraom/agent_memory](https://github.com/srinivasraom/agent_memory)

- **Framework (Letta/MemGPT, 22K+ GitHub stars):** Implements OS-like memory hierarchy for agents — core memory (in-context, like RAM) and archival memory (external storage, like disk). Agents page memories in and out. Open-source Apache 2.0. — [github.com/letta-ai/letta](https://github.com/letta-ai/letta)

- **Industry stat (AgentMarketCap, April 2026):** "65% of agent failures were attributable to context drift or memory loss during multi-step reasoning, not underlying model capability." — [agentmarketcap.ai/blog/2026/04/11/agent-context-engineering-sliding-windows-memory-2026](https://agentmarketcap.ai/blog/2026/04/11/agent-context-engineering-sliding-windows-memory-2026)

## Gotchas

- **Sliding window drops turn-by-turn with no signal.** The agent doesn't know it forgot. Add explicit memory checkpoints at key interaction milestones (verification complete, order placed, issue resolved) and store them in durable memory, not just context.
- **Context window expansion doesn't solve memory problems.** Larger windows delay failure, not prevent it. The AmtocSoft incident happened with a 180K-token window. The real fix is off-window storage with retrieval, not bigger windows.
- **RAG ≠ memory.** RAG retrieves static documents. Memory retains *learned* facts — preferences, past interactions, extracted entities. A RAG-only agent still forgets your name between sessions.
- **Forgetting policies are as important as storage policies.** Without decay, retrieval gets noisy. Without compaction, context inflation continues. Measure retrieval precision over time and tune recency weight and half-life accordingly.
