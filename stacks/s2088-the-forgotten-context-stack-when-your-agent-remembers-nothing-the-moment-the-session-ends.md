# S-2088 · The Forgotten Context Stack — When Your Agent Remembers Nothing the Moment the Session Ends

Your agent figured out the user's preferred data pipeline in session one. By session three, it recommends a completely different approach — and when asked why, it can't say. That's not a reasoning failure. It's an architecture failure: your memory layer is either missing, fragmented, or siloed by tool.

## Forces

- **Context windows are cheap per-call but expensive to rebuild.** Accumulating history is free; retrieving the right slice of it at the right moment is a systems problem.
- **One-size-fits-all storage doesn't fit.** Checkpoint stores are write-heavy and low-latency; semantic memory is query-heavy and retrieval-optimized. Same database technology won't serve both well.
- **Tool lock-in poisons memory portability.** An agent's memories that live inside Claude Code or Cursor are trapped — switching tools wipes everything. This is agent lock-in wearing a memory mask.
- **Old facts are not equally valid facts.** A preference learned six months ago may have changed. Memory systems that don't model temporal validity propagate staleness as ground truth.

## The move

A three-tier memory architecture, each tier serving a distinct access pattern:

**Hot — Checkpoint Store (SQLite / Postgres / Redis)**
- Per-step state snapshots for pause/resume and fault recovery
- Write every tool call result, not just the conversation turns
- Use `langgraph.checkpoint.postgres` or equivalent: enables time-travel debugging and human-in-the-loop approval flows
- Latency target: <10ms reads, <50ms writes

**Warm — Episodic Memory (Vector DB + temporal ordering)**
- Conversation history, task outcomes, user corrections
- Embed with a fast model (e.g., `text-embedding-3-small`); store alongside timestamp and session ID
- Retrieval must weight recency and causal chain, not just semantic similarity — "last time we tried X" matters more than "something about X was mentioned"
- Backend options: Qdrant (default), Weaviate (scale), pgvector (Postgres users), Pinecone (zero-ops)

**Cold — Semantic / Procedural Memory (Knowledge graph or structured K/V)**
- Cross-session facts: user preferences, domain invariants, agent behavior patterns
- Temporal validity windows — facts have `valid_from` and optionally `valid_until`
- Framework options ranked by retrieval sophistication:
  - **Zep / Graphiti** (Apache 2.0, ~29K GitHub stars): Temporal knowledge graph — outperforms MemGPT on Deep Memory Retrieval benchmark, 18.5% accuracy improvement on LongMemEval with 90% latency reduction — [https://github.com/getzep/graphiti](https://github.com/getzep/graphiti)
  - **Mem0**: Key-value + vector hybrid; fastest onboarding; best for simple preference memory
  - **Letta (MemGPT)**: OS-like tiered memory hierarchy — core (in-context), archival (vector), recall (search) — treats context window like RAM
  - **Hmem**: MCP server with SQLite-backed hierarchical memory; enables cross-tool portability — [https://github.com/Bumblebiber/hmem](https://github.com/Bumblebiber/hmem)

**The cross-tool portability problem** is solved at the transport layer: if memory lives behind MCP, any MCP-compatible tool can access it. This is the most practical path to agent memory that survives tool switches.

## Evidence

- **GitHub / Research paper:** Zep team (arXiv 2501.13956, Jan 2025) demonstrated their Graphiti temporal knowledge graph outperforms MemGPT on the DMR benchmark and achieves 18.5% accuracy improvement with 90% latency reduction on LongMemEval — [https://arxiv.org/abs/2501.13956](https://arxiv.org/abs/2501.13956)
- **HN Show HN (Mar 2026):** Hmem launched with explicit framing of two unsolved problems — context dilution (memories silently disappear from long conversations) and tool lock-in (memory is trapped inside one tool on one machine) — [https://news.ycombinator.com/item?id=47103237](https://news.ycombinator.com/item?id=47103237)
- **Production guide (Jun 2026):** NiteAgent's survey of production patterns identifies the #1 mistake as using the same backend for checkpoint stores and semantic memory — opposite access patterns require opposite storage engines — [https://niteagent.com/blog/agent-memory-production-guide/](https://niteagent.com/blog/agent-memory-production-guide/)
- **Research survey (2026):** Perea.ai's ~6,800-word survey of production memory systems (CC BY 4.0) reports the 2026 framework landscape converged on 4 types (working, episodic, semantic, procedural) and 4 frameworks (Mem0, Zep/Graphiti, Letta, LangMem), with 4 vector DB options — [https://www.perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)

## Gotchas

- **Mixing checkpoint store and semantic memory.** Checkpoint stores are write-heavy (every step); semantic memory is query-heavy (many reads per interaction). SQLite for checkpoints is fine; SQLite for semantic retrieval at scale is not. Pick stores that match the access pattern.
- **Semantic similarity retrieval ignores temporal ordering.** A vector search for "pipeline" might surface a preference from 2024 over a correction from last week. Layer temporal bias on top of semantic ranking — recency weighting, session-ID filtering, or validity windows in a knowledge graph.
- **Memory poisoning is real and compounding.** A single bad correction in session one propagates into every future session until the memory is explicitly pruned. Build memory versioning and rollback, not just writes.
- **Context dilution is silent.** Unlike a crash or error, context dilution has no failure signal — the agent simply acts increasingly disconnected from reality. The only countermeasure is explicit instrumentation: log retrieval hit rates, track how much context was loaded at each step, alert on retrieval failures.
