# S-2233 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent ran beautifully in testing. You closed it, came back the next morning, and it had no idea who you were, what it had done yesterday, or what it had learned. Every morning it starts as a stranger. This is not a bug — it is the default state of an LLM. The memory layer is the missing piece that separates a stateless responder from a persistent, learning agent.

## Forces

- **Context windows reset with each API call.** An LLM has no memory between requests by design. Each new call starts from scratch unless you explicitly reconstruct context.
- **Sessions don't survive days or workstations.** Closing a tab, restarting, or switching machines wipes everything. Agents deployed across time zones or async workflows need memory that outlives any single session.
- **The hybrid storage trap.** Teams reach for vector embeddings for everything, then discover that temporal relationships, identity continuity, and structured facts need graph or key-value stores. No single backend covers all memory types.
- **Memory staleness is invisible until it bites.** Old memories surface in wrong contexts, pollute new sessions, and create subtle semantic drift that is hard to detect without explicit evaluation.
- **Tool-siloed memory fragments context.** Claude Code, Cursor, and Codex each have good internal memory, but context does not transfer between them. A developer who switches tools loses everything they accumulated.

## The Move

Implement a layered memory architecture modeled on the three-tier taxonomy that the production agent ecosystem converged on by 2025-2026. Treat episodic, semantic, and procedural memory as distinct concerns with distinct storage backends.

**Episodic memory — record what happened**
- Store specific past events: tool call sequences, task outcomes, user interactions
- Backends: vector stores (Pinecone, Qdrant, Milvus), or structured KV stores for exact-time queries
- Retrieval: semantic similarity search + temporal filtering (filter by "last 7 days," "same project")
- Write on task completion, not continuously — episodic stores bloat fast

**Semantic memory — store what you know**
- Store facts, preferences, learned policies, accumulated knowledge
- Backends: knowledge graphs (Neo4j, Memgraph) or hybrid vector-graph stores for relationship-aware retrieval
- Retrieval: entity-centric queries ("what does this user prefer?") that require graph traversal
- LLM-managed extraction: run the agent's output through an extraction step that pulls facts into the graph

**Procedural memory — encode how to act**
- Store agent skills, prompt fragments, tool selection policies, recovery routines
- Backends: versioned prompt registry, skill definitions, policy files — not a database query
- Retrieval: rule-based or a separate "skill selector" LLM call that decides which procedure applies
- Update on explicit skill improvement, not dynamically — procedural memory that changes mid-session creates nondeterminism

**The session bridge — reconstruct state at session start**
- On every new session: query episodic store (recent history) → pull semantic facts (user preferences, project state) → load active procedures
- Token budget discipline: set a max memory tokens budget (e.g., 4K-8K) and fill from highest-priority tiers first
- Summary-first: if episodic store has too many entries, summarize older entries before loading into context

**The write-back contract**
- Write to episodic memory at task boundaries, not every tool call
- Write to semantic memory only when the LLM explicitly produces a fact worth preserving
- Write to procedural memory on deliberate skill improvement, never as a side-effect of a single run

## Evidence

- **GitHub repo / Mem0 architecture:** Mem0 (62,660 stars, Apache 2.0) implements a hybrid vector-graph-key-value store with three scoping levels (user, session, agent). Their April 2026 algorithm update pushed LoCoMo scores from 71.4 → 92.5 and LongMemEval from 65.8 → 94.4 at ~7K tokens/query. Paper: arXiv:2504.19413 — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Technical blog / Redis stateful systems guide:** Redis's guide to AI agent memory (2026) establishes the five architectural patterns: in-context working buffer, session state store, semantic memory (vector), episodic store, and procedural memory. Notes that even with 200K-token context windows, memory architectures remain necessary for cross-session persistence and selective retrieval efficiency — [https://redis.io/blog/ai-agent-memory-stateful-systems/](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- **Technical blog / ML Mastery five patterns:** Five patterns covering both state (ephemeral, updated during task) and memory (cross-boundary persistence). Argues the state-memory cycle: read from memory at start → update state during task → write select state back to memory at end. Critical point: treating all memory the same way leads to either memory loss or unbounded context growth — [https://machinelearningmastery.com/5-architectural-patterns-for-persistent-memory-and-state-in-ai-agents/](https://machinelearningmastery.com/5-architectural-patterns-for-persistent-memory-and-state-in-ai-agents/)
- **Primary source / Claude Code memory system:** Anthropic's Claude Code ships four memory scopes (managed policy → user → project → local) plus Auto Memory that captures session learnings to `~/.claude/projects/<project>/memory/`. MEMORY.md loads first 200 lines or 25 KB at session start. Per-repository by default, not semantic vector retrieval. The Dreams pipeline (Research Preview) consolidates across memory stores — [https://vectorize.io/articles/claude-code-memory](https://vectorize.io/articles/claude-code-memory)
- **Personal project / mnemo:** Open-source centralized memory for coding assistants that solves the tool-silo problem — context trapped in Claude Code, Cursor, and Codex doesn't transfer between them. Stores memory as Markdown files in a versioned store, with a shared API layer. Built by Tiago Oliveira — [https://tiago.sh/blog/a-memory-that-follows-me.html](https://tiago.sh/blog/a-memory-that-follows-me.html)
- **Benchmark landscape:** LoCoMo (1,540 questions, 4 categories, multi-session recall), LongMemEval, and BEAM now define the measurement landscape. Mem0's April 2026 algorithm is the current top reported: 92.5 on LoCoMo, 94.4 on LongMemEval — [https://mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **GitHub repo / Agent Memory Techniques:** NirDiamant/Agent_Memory_Techniques (846 stars) documents 30 distinct memory techniques across 6 families: short-term context management, long-term storage, cognitive architectures, retrieval patterns, framework integrations (Letta, Zep, Graphiti, MemGPT), and production deployment patterns — [https://github.com/NirDiamant/Agent_Memory_Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques)

## Gotchas

- **Reaching for vector search for everything.** Vector similarity is great for semantic recall but can't answer "what happened in the last 24 hours" or "which tasks has this user completed." Temporal filtering, graph traversal, and key-value lookups each solve problems vector search can't.
- **Writing to memory on every tool call.** Episodic memory grows unbounded and you end up with a context that's mostly history, not action. Write at task boundaries (success, failure, explicit user signal).
- **No staleness management.** Old memories that contradict current context are worse than no memory. Implement TTLs, relevance scoring, or periodic re-evaluation of stored facts.
- **Assuming memory improves with scale.** Episodic and semantic stores accumulate near-duplicates and contradictions over months. Budget for memory compaction — summarize, merge, or prune periodically.
- **Treating memory as a database.** Procedural memory is not a query — it is a policy. Storing "how to do X" as facts you retrieve misses the point; it should be encoded as versioned skill definitions with explicit update procedures.
