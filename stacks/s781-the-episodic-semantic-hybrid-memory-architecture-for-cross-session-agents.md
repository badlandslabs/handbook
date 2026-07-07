# S-781 · The Episodic/Semantic Hybrid Memory Architecture for Cross-Session Agents

You built a stateless agent that passes every demo. Then a user comes back two weeks later and the agent has no idea who they are, what they tried before, or what the last three sessions established. The fix isn't a longer context window — it's a memory architecture.

## Forces

- Expanding the context window is a brute-force approach that hits latency, cost, and privacy walls — it doesn't scale beyond a single session
- Agents that store everything as unstructured text in a vector DB create retrieval chaos: noisy chunks, stale facts, no provenance
- Agents that only track conversation history lose cross-session continuity — every restart is a fresh agent
- The CoALA (Cognitive Architectures for Language Agents) paper established a tripartite memory model — episodic, semantic, procedural — but most production systems only implement one layer
- The gap between "it remembers this session" and "it remembers across months" is an architecture decision, not a model capability

## The move

Implement a **two-tier episodic + semantic hybrid** as the minimum viable cross-session memory architecture. The episodic tier is the append-only log of everything that happened. The semantic tier is the distilled, queryable knowledge extracted from those events. Keep them separate.

**Episodic memory (the ship log):**
- Append-only timeline: timestamps, task IDs, interaction events, tool call outcomes, observations
- Write-heavy, cheap storage (SQLite, Postgres, or a flat file per session)
- Deterministic retrieval by time or task ID — no embedding math required
- Serves as the authoritative audit trail for debugging and compliance

**Semantic memory (the knowledge library):**
- Facts, preferences, learned patterns, and cross-session conclusions extracted from episodic events
- Stored in a format the agent can inject into system prompts (structured JSON/dicts, not raw chunks)
- Queryable by topic, entity, or recency — this is where vector search or FTS adds value
- Has a TTL or decay mechanism: stale facts get archived or deleted, not silently retrieved

**The consolidation bridge:**
- A periodic process (nightly or on-demand) reads episodic logs and writes semantic updates
- LLM-driven extraction: the consolidation step uses an LLM to summarize what happened, extract key facts, and update semantic memory
- MemForge (salishforge/memforge) calls this "sleep cycles" — the system rewrites and strengthens memories based on retrieval frequency and outcome quality
- This is the step most teams skip, and the reason their semantic memory becomes a junk drawer

**Tool access pattern:**
- Agents interact with memory through MCP tools or SDK functions: `memory.put()`, `memory.get()`, `memory.search()`
- Lore (agentkitai/lore) adds cross-agent sharing: one agent publishes a lesson, others query it — prevents Agent B from re-discovering what Agent A already learned
- Agent-vfs (johannesmichalke/agent-vfs) wraps this in a filesystem abstraction — agents use `read`/`write`/`ls` against a virtual FS backed by SQLite or Postgres, because "agents already know files"

**PII and governance:**
- Automatic PII redaction at write time (Lore does this built-in)
- Memory Guardian (rishipratap10/memory-guardian) adds conflict detection between stored facts and explicit lifecycle management (decay + archival)
- Memory versioning so the agent can reason about when a fact changed

## Evidence

- **GitHub README + HN:** MemForge — self-improving agent memory with PostgreSQL-only stack, sleep cycle consolidation, 92% R@5 on LongMemEval. Source: https://github.com/salishforge/memforge + https://news.ycombinator.com/item?id=47698972
- **GitHub README:** Agent-vfs — persistent virtual filesystem for agents backed by SQLite or Postgres. Authors note "every coding agent that works well has converged on the same pattern: just use files." Source: https://github.com/johannesmichalke/agent-vfs + https://news.ycombinator.com/item?id=47273658
- **GitHub README:** Lore — cross-agent memory SDK with PII redaction, knowledge graph, TTL-based decay. Source: https://github.com/agentkitai/lore
- **Blog post:** Principia Agentica — "Episodic vs. Semantic, and the Hybrid That Works" (Sep 2025), establishes the two-paradigm framework with implementation patterns for each. Source: https://principia-agentica.io/blog/2025/09/19/memory-in-agents-episodic-vs-semantic-and-the-hybrid-that-works
- **Framework docs:** LlamaIndex Memory guide documents `BaseMemory` class with `put()`/`get()` interface; LangGraph checkpointer persistence for thread-scoped state; BotWire tutorial on adding persistent memory to MCP servers. Sources: https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/ + https://docs.langchain.com/oss/python/deepagents/memory + https://botwire.dev/articles/llamaindex-agent-memory

## Gotchas

- **Don't use vector search for everything.** Retrieval-augmented generation over raw episodic logs produces noisy results. Episodic retrieval should be by time or task ID; semantic retrieval is where similarity search earns its place.
- **Don't skip consolidation.** Storing raw events forever without a distillation step turns episodic memory into a write-only log that no one reads. The semantic extraction step is where memory becomes intelligence.
- **Don't forget TTL and decay.** Every stored fact has a half-life. A preference from 18 months ago is noise, not signal. Implement explicit archival or a retrieval-score mechanism that down-ranks old memories.
- **Don't store PII in raw form.** Agent memory accumulates personal information by default. Redact at write time, not at retrieval time — it's easier and reduces blast radius on data breaches.
- **Don't assume the agent will use memory correctly.** Memory must be explicitly injected into context. The agent needs a tool or instruction to query its own memory; having it stored is not enough.
