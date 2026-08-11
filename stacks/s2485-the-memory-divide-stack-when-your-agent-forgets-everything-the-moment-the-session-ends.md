# S-2485 · The Memory Divide Stack — When Your Agent Forgets Everything the Moment the Session Ends

A user returns after two weeks. The agent greets them like a stranger. No recall of their name, their preferences, their last project, or the conversation they had last month. Every session starts from zero — context window scrubbed, history gone, relationship reset. This is the default state of LLM agents, and it is the single most common complaint in production agent deployments. The fix is a multi-tier memory architecture, but "add a vector store" is where most teams go wrong.

## Forces

- **Context windows are expensive at volume.** A 200K-token context stuffed with conversation history costs 10x what a 10K-token context with precisely the right facts costs. Premium context pricing punishes brute-force approaches. (Source: [DevToolLab, 2026](https://devtoollab.com/blog/ai-agent-memory-architecture))
- **"Add a vector database" is necessary but not sufficient.** Vector retrieval finds similar text, not useful facts. Most agents that "add memory" end up with a graph that collapses into a single `RELATES_TO` relationship type — technically stored, operationally unreachable. (Source: [Daily Dose of Data Science, June 2026](https://blog.dailydoseofds.com/p/schema-guided-agent-memory-for-production))
- **Memory drift is silent and cumulative.** Without schema constraints, agents extract facts inconsistently across sessions. The same user preference gets stored as "prefers dark mode," "dark theme," "DM: on," and "user likes dark mode" — four different representations that will never be unified by a vector query. (Source: [Synthara Technologies, May 2026](https://www.syntharatechnologies.com/blog/agent-memory-architectures))
- **Context overflow kills long sessions.** Without explicit memory management, agents lose early context as new tokens fill the window — the "lost in the middle" phenomenon. MemGPT (now Letta) was built specifically to address this: the agent manages its own memory tiers via explicit function calls, treating the LLM like an OS with virtual memory. (Source: [MemGPT research, UC Berkeley](https://research.memgpt.ai/))

## The move

Build a four-tier memory system where each tier serves a distinct purpose and is implemented with the right storage for that tier. These tiers are not interchangeable — each compensates for a different failure mode of the others.

**Working memory — always in context, always structured.**
- In-process state (LangGraph state, conversation buffer with `deque`) for current task tracking
- JSON scratchpad the LLM reads and writes, not free-text prompts to "remember"
- Retained within the active session only; discarded on session end
- Key rule: keep it structured. Structured state survives prompt engineering changes; free-text state drifts. (Source: [Let's Data Science](https://letsdatascience.com/blog/ai-agent-memory-architecture))

**Episodic memory — what happened before.**
- Vector-indexed summaries of past sessions stored in a vector database (Qdrant, Weaviate, or PGvector)
- Retrieved by cosine similarity to the current query — "has this user asked about this before?"
- Each entry includes metadata: timestamp, session ID, outcome (succeeded/failed), user rating
- Compression: raw conversations are summarized into dense notes, not stored verbatim. Full logs are archived but not retrieved on every call. (Source: [Synthara](https://www.syntharatechnologies.com/blog/agent-memory-architectures))

**Semantic memory — durable facts about this user and the world.**
- Extracted entities, preferences, and constraints stored in a relational schema (Postgres with structured columns), not just vectors
- Retrieved by entity lookup + relevance scoring, not similarity search alone
- Schema-constrained extraction: provide the LLM with a typed schema before extraction, so "prefers dark mode" is always stored as `{theme: "dark"}` regardless of how the user phrased it. This is the fix for memory drift. (Source: [Daily Dose of Data Science](https://blog.dailydoseofds.com/p/schema-guided-agent-memory-for-production))
- Temporal awareness matters: Zep (a production memory service) uses a temporal knowledge graph to maintain historical relationships — "Jane upgraded Pro in August 2025 and again in November 2025" is more useful than two flat facts. (Source: [Zep Blog, January 2025](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/))

**Procedural memory — how to do things.**
- Versioned documents (git repo or structured DB) for agent instructions, tool-use playbooks, and learned workflows
- Retrieved by intent classification + role matching, not semantic similarity
- This is where CLAUDE.md and AGENTS.md files live — declarative memory injection that has proven its value as a lightweight, zero-infrastructure approach for simpler agents. (Source: [Zylos Research, April 2026](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge))

**The routing layer — Memory Node.**
- A central coordinator that decides which tier to read from and write to on each turn
- On every request: (1) query semantic memory for user facts, (2) query episodic memory for related past sessions, (3) inject working memory from current session, (4) check procedural memory for relevant workflows
- Latency budget this at <200ms total retrieval or the user notices. (Source: [Micheal Lanham, Substack, February 2026](https://micheallanham.substack.com/p/memory-architecture-for-production))

## Evidence

- **Letta (formerly MemGPT) production deployments:** CallSphere ran Letta in production for over a year and found that five patterns consistently separated stable deployments from memory drift: pinning runtime versions, making state durable from week 2 (not month 6), wiring up evals before features, using schema-guided extraction, and budgeting retrieval latency. "The cost of bolting on durable state at month 6 is roughly 5x the cost of getting it right at week 2." (Source: [CallSphere, April 2026](https://callsphere.ai/blog/td30-fw-memgpt-in-production-2026-lessons-learned-honest))
- **Zep temporal knowledge graph benchmark:** Zep's graph-based architecture outperformed MemGPT on the Deep Memory Retrieval (DMR) benchmark by 23% while reducing response latency by 90%. The key advantage: temporal edges ("user X did Y at time T") enable reasoning that pure vector retrieval cannot support. Open-sourced as Graphiti. (Source: [Zep Blog, January 2025](https://blog.getzep.com/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/))
- **Enterprise adoption pattern:** Synthara's analysis of production agent deployments found that systems implementing all four memory tiers showed measurably better task completion on multi-session benchmarks. Two-tier systems (working + episodic only) showed good single-session performance but degraded significantly on cross-session continuity tasks. (Source: [Synthara Technologies, May 2026](https://www.syntharatechnologies.com/blog/agent-memory-architectures))

## Gotchas

- **Schema drift is the silent killer.** If you don't constrain extraction schemas, the same fact gets stored 10 different ways across 100 sessions. Fix it at write time, not at query time.
- **Retrieval latency compounds.** Each memory tier adds a round-trip. Four tiers × 50ms each = 200ms before the LLM even gets the context. Profile your retrieval path; the vector search is usually the bottleneck.
- **Forgetting is a feature, not a bug.** Don't store everything. Implement a relevance threshold: facts below a recency or importance score get archived, not retrieved. MemGPT/Letta's archival memory tier exists precisely so the agent doesn't retrieve every conversation from 2023 on every query.
- **Context window is not memory.** Ultra-long context (1M tokens) helps with complex single-session tasks but does not substitute for persistent memory. The practical conclusion from 2025–2026 production deployments: long context is expanded working memory, not long-term memory. (Source: [Zylos Research](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge))
