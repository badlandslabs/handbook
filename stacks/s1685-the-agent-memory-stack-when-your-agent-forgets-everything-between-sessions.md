# S-1685 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

You ship a powerful agent. It works great in a demo. Three days later the same user comes back and the agent greets them like a stranger, has no idea what project they're working on, and asks them to re-explain the context. This is the **stateless amnesia problem**: agents lose everything at session boundary, and the fix isn't obvious — do you dump everything in context, use a vector store, or build a memory system?

## Forces

- **Context windows are finite and expensive.** Storing full conversation history and project context works for a few turns, then collapses under token cost and model attention degradation. Pushing 200K tokens of memory to GPT-4o every query is not a memory architecture — it's a burn rate.
- **Vector similarity is not memory recall.** Embedding-based retrieval finds lexical neighbors, not causal chains. "The user mentioned the database migration last week" and "the user mentioned their cat named Migration last week" may score identically on cosine similarity. This is the "logical neighbor" problem that pure vector stores cannot solve.
- **Vendor lock-in corrodes memory fidelity.** Agents that store memory inside a provider's infrastructure (OpenAI memory, Claude memory) become prisoners of that provider's model, pricing, and availability. Cross-provider portability is now a real engineering requirement.
- **Forgetting is not always a bug.** Agents that remember everything equally produce verbose, unfocused context. The biological forgetting curve — discard low-utility memories, reinforce high-utility ones — is a legitimate architectural principle, not a hack.

## The move

Design a **layered memory architecture** with three distinct stores, each serving a different recall purpose:

- **Episodic memory** (session): full conversation history within a session. Stored in a fast, durable queue (Valkey, in-memory). Evicts on session end unless explicitly promoted.
- **Semantic memory** (facts): structured facts extracted from conversation — user preferences, project context, decisions made. Stored in a dedicated memory engine (Mem0, OpenMemory, custom). Queried on each new session to reconstruct relevant context.
- **Procedural memory** (instructions): system prompts, agent instructions, SOPs, tool definitions. Baked into the agent's system prompt or loaded from a configuration store. Changes infrequently.

**On retrieval**: use multi-signal query (not just vector similarity). Include recency, frequency of access, user identity, and temporal tags. The goal is surgical context injection — give the agent exactly what it needs for this turn, not everything it ever knew.

**On persistence**: prefer local-first (SQLite, Postgres, Valkey) over cloud-native managed services. Self-hosting memory is increasingly the default for teams that want portability and privacy. OpenMemory (4.3K+ stars) exemplifies this: SQLite-backed, no vendor lock-in, works with Claude Desktop, Copilot, and Codex.

**On forgetting**: implement active forgetting. Biological decay models — where memories have a "strength" score that degrades over time unless recalled — achieve near-double recall accuracy vs stateless vector stores. YourMemory (HN: 98 points, 53 comments) reports 52% Recall@5 on LoCoMo with ~84% less token waste vs storing everything forever.

**On cost**: Mem0 benchmarks show up to 90% token cost reduction when using a dedicated memory layer vs raw context stuffing, with sub-2-second retrieval times on standard vector stores.

## Evidence

- **Mem0 benchmark report (Jul 2026):** Token-efficient memory algorithm achieves 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens per query. Largest gains: +29.6 points on temporal reasoning, +23.1 on multi-hop reasoning. 21 framework integrations, 20 vector stores supported. — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Valkey + Mem0 integration post (May 2026):** Three-layer memory model (state/session/semantic) reduces token costs by up to 90% and keeps retrieval under 2 seconds. State memory implemented with Valkey + LangGraph checkpoints for workflow continuity and multi-agent shared state. — [valkey.io/blog/ai-agent-memory-with-valkey-and-mem0](https://valkey.io/blog/ai-agent-memory-with-valkey-and-mem0)
- **YourMemory HN Show (2025):** AI memory system using Ebbinghaus forgetting curve. Graph layer over vector store solves "logical neighbor" problem. Benchmarks: 52% Recall@5 (LoCoMo), 84.8% (LongMemEval), ~84% token waste reduction vs stateless storage. Local-first MCP server. — [news.ycombinator.com/item?id=47914367](https://news.ycombinator.com/item?id=47914367)
- **OpenMemory GitHub (Oct 2025):** Local-first memory engine for LLMs, 4.3K stars, Apache-2.0. SQLite/Postgres backend, works with Claude Desktop, GitHub Copilot, Codex. Positions as alternative to RAG pipelines and managed vector stores. — [github.com/CaviraOSS/OpenMemory](https://github.com/CaviraOSS/OpenMemory)
- **AgentKeeper HN Show (2025):** Cognitive persistence layer that stores facts independently of any LLM provider. Reconstructs context dynamically across provider switches, restarts, and crashes. — [news.ycombinator.com/item?id=47217244](https://news.ycombinator.com/item?id=47217244)
- **HatchWorks production patterns (Jan 2026):** Memory is a first-class architectural concern. Observability into what the agent remembered (and what it didn't) is as important as the memory itself. — [hatchworks.com/blog/ai-agents/orchestrating-ai-agents](https://hatchworks.com/blog/ai-agents/orchestrating-ai-agents)

## Gotchas

- **Storing everything is not memory architecture** — it's context window abuse. Measure token waste and recall precision. A memory system that returns 50 irrelevant facts alongside 2 relevant ones has failed.
- **Cross-session identity is unsolved.** Most memory systems treat "user_id" as a stable identifier, but real users have multiple devices, sessions, and contexts. Attribution across sessions remains an open problem per Mem0's 2026 report.
- **Memory staleness** causes real production failures. A fact remembered from a session three months ago may be outdated. Temporal metadata and active re-confirmation are needed — not just retrieval.
- **The memory layer is an attack surface.** Storing facts about users, projects, and decisions is sensitive data. Encryption at rest, access controls, and auditability belong in the memory architecture from day one, not bolted on later.
- **Benchmarks (LoCoMo, LongMemEval, BEAM) are still young.** The memory field is ahead of its measurement tools. Claimed numbers from vendors should be taken as directional, not precise — especially on temporal reasoning, which is where the hardest real-world failures occur.
