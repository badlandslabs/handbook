# S-1105 · The Tiered Memory Stack — When Your Agent Is a Goldfish

Your coding agent correctly builds on context from this morning's session. It has no idea what you worked on yesterday. Same task, new session — you repeat the same preamble about your tech stack, your code conventions, your preferences for error handling. The agent is stateless by default, and statelessness is not a feature for agents that are supposed to *know* you. This is the stack for building a persistent memory system that actually survives across sessions.

## Forces

- **Context windows are finite but work is not.** A 128K-token window feels like plenty — it isn't. Models degrade in attention quality long before hitting token limits, and raw context size compounds noise faster than signal.
- **"Just use a bigger context" doesn't solve memory.** Bigger windows store more conversation history but don't help the model retrieve relevant facts efficiently. Loading 50 turns of chat history often produces *worse* personalized responses than a 3-paragraph profile.
- **The tool-lock-in trap.** CLAUDE.md only works in Claude Code on one machine. Switching to Cursor or moving to a new laptop erases everything. Memory tied to a tool is not persistent memory.
- **Compression is lossy.** Summarization-based compaction strategies can silently collapse exact-value preferences, hard constraints, and architectural decisions — the agent keeps running while losing critical context.
- **Flat memory stores collapse under load.** Putting every fact, observation, and preference in a single undifferentiated list makes retrieval noisy and eviction arbitrary.

## The Move

The dominant production pattern is a **three-tier memory hierarchy** inspired by operating system memory management (popularized by Letta/MemGPT). The agent's context window is RAM; a database is disk; the agent itself decides what to page in and out. Alongside tiering, teams use **progressive disclosure** — loading memory in layers as the session demands it — and **fact extraction** — converting raw conversation into clean, deduplicated memories before embedding.

**Concrete implementation:**

- **Core memory (always in context):** Small fixed block — agent persona + current user facts + active task. Typically 2–8KB. Persisted as structured text/markdown in a SQLite file, reloaded on session start.
- **Recall memory (session-scoped retrieval):** Vector-store-backed semantic search over recent conversation history. PostgreSQL/PGvector, Qdrant, or local SQLite+FTS5. Retrieved on demand, not always in context.
- **Archival memory (cross-session persistence):** Large persistent store for older sessions, past decisions, and accumulated knowledge. Often a SQLite file, markdown store, or graph database. The agent pages content in when semantically relevant.
- **Fact extraction pipeline:** Before storing anything, run extraction to convert raw messages into clean facts. Mem0 (and others) do this automatically — deduplication runs on `add()`, so what gets embedded is a clean fact, not a raw message.
- **Hybrid retrieval:** Combine vector similarity + keyword/FTS5 search. SQLite-FTS5 with BM25 ranking outperforms pure vector retrieval for agent memory use cases where exact terminology matters (function names, code patterns, error messages).
- **Forgetting policy:** Explicit decay or eviction. YourMemory (open source, MCP-compatible) uses "biologically-inspired decay" — memories fade when unused. Manual reflection (`/diary`, `/reflect` commands) is also common as a deliberate tradeoff between automation and accuracy.
- **Compression at threshold, not at limit:** Two-layer compaction: first pass at 50% of context window, safety net at 85%. Setting both at the same threshold causes premature compression on every turn.

## Evidence

- **Letta (formerly MemGPT) — OS memory architecture:** UC Berkeley research project that coined the "LLM OS" analogy. Agents manage their own core memory (persona + user info, always in context) and archival memory (external database, paged in on demand). 22,960 GitHub stars, production deployments. — [letta.com](https://www.letta.com)
- **Hmem — Cross-tool SQLite memory for coding agents:** MCP server storing persistent hierarchical memory in a local `.hmem` SQLite file. Works across Claude Code, Cursor, Windsurf, and OpenCode on any machine. Solves the tool-lock-in problem: memory is not tied to the IDE. — [github.com/Bumblebiber/hmem](https://github.com/Bumblebiber/hmem) — [HN Show HN](https://news.ycombinator.com/item?id=47103237)
- **AgentKeeper — Four-stage cognitive persistence:** Recent HN Show HN project explicitly solving cross-session memory for AI agents via progressive retrieval and structured persistence. — [HN Show HN](https://news.ycombinator.com/item?id=47217244)
- **sqlite-memory — Local-first markdown memory:** MIT-licensed SQLite extension providing persistent, searchable memory for agents. Combines semantic search with FTS5 hybrid retrieval. Entire knowledge base in one portable `.db` file. — [github.com/sqliteai/sqlite-memory](https://github.com/sqliteai/sqlite-memory)
- **fsck.com episodic memory for Claude Code:** Jesse Vincent built a system that archives all previous Claude Code conversations into a SQLite database with FTS5, enabling semantic search over episodic memory. Cross-project recall — the agent can remember a technique tried in one project while working in another. — [blog.fsck.com/2025/10/23/episodic-memory](https://blog.fsck.com/2025/10/23/episodic-memory)
- **Letta benchmark — Filesystem beats specialized vector stores on memory tasks:** Letta's own benchmarks show a plain filesystem scores 74% on memory tasks, beating specialized vector-store libraries. — [Letta documentation](https://github.com/letta-ai/ezra/blob/main/reference/2026-02/letta_memory_systems.md)
- **Three-tier hierarchical memory:** CallSphere documents promotion rules and eviction policies for working → short-term → long-term tier transitions. Critical for agents running across days or weeks. — [callsphere.ai/blog](https://callsphere.ai/blog/hierarchical-memory-ai-agents-working-short-long-term-tiers)

## Gotchas

- **Compressing context hides its own failure.** Most context compression failures don't look like failures — the agent keeps running. The context shrinks silently. Verify that hard constraints and architectural decisions survive compaction.
- **Context dilution in long sessions.** The agent "forgets" decisions made hours ago as earlier context is silently pushed out. Not a crash — a slow drift. Implement explicit checkpointing (progress files, decision logs) for long-horizon tasks.
- **Tool-lock-in masquerading as memory.** If your "memory" only works inside one agent framework or on one machine, it is not persistent memory — it is a local cache. The MCP standard is emerging as the cross-tool transport layer for this.
- **Vector retrieval without keyword fallback.** Pure semantic search misses exact terminology matches. Hybrid retrieval (vector + FTS5 BM25) is the production norm for agent memory because code patterns, error messages, and function names are terminologically specific.
- **Forgetting is a feature, not a bug.** Not everything should survive. Unused memories accumulating forever create retrieval noise. An explicit decay or manual reflection policy prevents the memory store from becoming a data graveyard.
