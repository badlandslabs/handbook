# S-973 · The Agent Memory Architecture Stack — When Your Agent Forgets Everything Between Sessions

LLMs are stateless. Every inference starts from zero. An agent that can't remember what it agreed to in turn 7, what the user told it last Tuesday, or which approach it already ruled out — is a demo, not a product.

## Forces

- **Context windows are finite but memories compound.** A 200K-token window fills fast when you accumulate conversation history. At scale, naive accumulation produces 9.87s median latency vs 1.44s with a proper memory system.
- **Retrieval is the hard part, not storage.** Most teams grab a vector DB and call it done. Storage solves nothing if the retriever surfaces irrelevant memories or the agent can't synthesize across episodic, semantic, and procedural memory types.
- **Three memory tiers compete for a single context budget.** Working memory (context window), session memory (per-job state), and long-term memory (persistent facts) all compete for the same limited space — and the right answer changes per turn.
- **Memory without governance is a liability.** GDPR right-to-be-forgotten, user identity across sessions, and stale hallucinated facts — uncurated memory turns into legal and accuracy risk.

## The Move

Build a three-tier memory architecture modeled on cognitive science: episodic (what happened), semantic (what is true), and procedural (how to act). Then manage the context budget through a write-select-compress lifecycle.

### Tier 1 — Working Memory (Context Window)
- The LLM's context window is RAM, not storage. It holds the current turn, recent tool outputs, and a compressed digest of relevant long-term memories.
- Budget the window: at session start, synthesize a WARM digest (~1,500 tokens) from disk — pinned facts, open threads, top-scored memories. Leave COLD storage (full-text archive, e.g. SQLite FTS5) queryable but never loaded wholesale.
- At 50% context fill: checkpoint. At 70%: aggressive compact. At session end: flush durable facts to long-term store.

### Tier 2 — Episodic Memory (What Happened)
- Store interaction history as structured events: who, what, when, outcome. Not raw chat logs — distilled facts about decisions and events.
- **Scope chains with inheritance** (e.g., same person, different roles per project) and bitemporal history (old facts archived, not deleted) distinguish real systems from a fancy filing cabinet.
- Example: Agent Recall uses SQLite-backed scoped entities, relations, and slots; at session start an LLM summarizes relevant facts into a structured briefing instead of dumping raw data.
- Source: *Show HN: Agent Recall* — https://news.ycombinator.com/item?id=47165501

### Tier 3 — Semantic + Procedural Memory (What Is True / How to Act)
- Semantic: domain facts, user preferences, learned truths. Stored as vector embeddings with multi-signal retrieval (semantic similarity + BM25 + entity linking).
- Procedural: agent instructions, system prompts, tool definitions, learned behaviors. Often stored as structured files (`.rules/`, `MEMORY.md`, `SESSION-STATE.md`) rather than embeddings.
- The write path goes through consolidation — not direct writes from the turn loop. This prevents noise accumulation and enables importance-weighted decay.
- Pinned memories never expire. Frequently-used memories survive. Stale ones fade.

### The Retrieval Loop
1. **Write:** Capture durable facts as they appear. Route to episodic or semantic tier.
2. **Select:** At each turn, query both tiers. Use the query itself as the retrieval signal — not a fixed top-K.
3. **Compress:** Summarize retrieved memories before injecting into context. A 10-entry retrieval list might compress to 3 sentences.
4. **Isolate:** Separate factual memory from system instructions. Don't let retrieved facts drift tool definitions.

## Evidence

- **Survey paper:** *Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers* (Du, arXiv:2603.07670, March 2026) — the canonical taxonomy: working/short-term/long-term/episodic/semantic/procedural across six categories.
- **Production benchmark:** Full-context accumulation vs memory systems: median latency 9.87s → 1.44s (12x improvement), ~90% token savings. — https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem
- **Vendor landscape:** Mem0 (vector-first, 92.5% LoCoMo, 48K+ GitHub stars), Zep/Graphiti (temporal knowledge graph for "what was true in Q1?"), Letta (MemGPT evolved, OS-tiered runtime). — https://www.agenticwire.news/article/mem0-zep-letta-agent-memory
- **HN community pattern:** AgentKeeper, Agent Recall, ConPort, and Magic Context all independently converged on the same solution: scoped entity stores + structured briefing synthesis + MCP tool interface. — https://news.ycombinator.com/item?id=47217244
- **Context engineering framework:** Lance Martin (June 2025) formalized the write-select-compress-isolate lifecycle. Andrej Karpathy's framing: "LLMs are like a new kind of OS — the context window is RAM." — https://rlancemartin.github.io/2025/06/23/context_engineering/

## Gotchas

- **Dumping a vector DB into an agent isn't a memory architecture.** It solves retrieval geometry, not memory purpose. The agent still doesn't know which memories to surface, when, or how to synthesize conflicting ones.
- **Stale memories are hallucination fuel.** If a memory is retrieved but the agent can't verify its recency or relevance, it will treat it as ground truth. Bitemporal history (record time vs event time) is the mitigation.
- **Context compaction kills implicit memory.** Coding agents (Claude Code, Cursor, etc.) periodically compact context — implicit learnings vanish unless explicitly saved to a durable memory store. Magic Context disables built-in compaction and owns memory end-to-end to prevent this.
- **Memory scope leakage.** `user_id` and `agent_id` scopes composed at retrieval are easy to get wrong — wrong user gets wrong memories. Validate scope chains explicitly, not via shared namespace.
- **Right-to-be-forgotten isn't automatic.** If you're storing semantic memories about users, you need deletion at the entity level, not just the record level. Most vector DBs don't support this cleanly.
