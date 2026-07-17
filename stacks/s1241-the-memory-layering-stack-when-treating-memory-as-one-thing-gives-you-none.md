# S-1241 · The Memory Layering Stack: When Treating Memory as One Thing Gives You Nothing

An agent with a frontier-class model and no persistent memory is a genius with amnesia. It gives a brilliant answer today and greets you as a stranger tomorrow. But the solution isn't to bolt on "a vector database." The right architecture depends on what you're remembering, how recently, and how much it matters. The teams that get this right use layered memory — and they treat each layer as a distinct engineering problem.

## Forces

- **Token budget vs. recall quality** — pulling everything from a vector store at once can blow your context budget faster than the session window saves you
- **Simplicity vs. capability** — RAG on a vector DB is overkill for simple key-value facts; plain filesystem markdown beats specialized systems on straightforward retrieval tasks
- **Freshness vs. completeness** — facts change over time; an agent that remembers "user prefers npm" from six months ago may actively harm the current session
- **Privacy vs. cloud convenience** — keeping memory local (MCP-based, SQLite) is increasingly the default for personal agents; cloud memory services mean your agent's context lives on someone else's infrastructure
- **Singletons vs. architectures** — most frameworks ship "memory" as a monolithic feature; real production systems need tiered storage with eviction, summarization, and conflict resolution

## The move

**Layer memory into three tiers, each with its own storage and retrieval strategy:**

- **L1 — Persistent Facts (Working Memory):** User preferences, active project goals, agent instructions. Store as structured key-value (SQLite, JSON, or a markdown file). Cost: ~20-80 tokens per retrieval. Loaded at session start. Examples: `CLAUDE.md` for personal agents, a preferences table for production bots. This is the most-queried, highest-value tier — keep it small, structured, and always in context.

- **L2 — Episodic / Conversational Memory (Context Window Fodder):** What happened in recent sessions, past decisions, conversation summaries. Retrieve on-demand via semantic search (vector embeddings + BM25 hybrid) or SQLite FTS. Mem0's benchmark shows fused scoring (semantic + BM25 + entity matching) delivers +29.6 points on temporal queries and +23.1 on multi-hop reasoning over pure vector search. Load the top N results; let the LLM filter relevance.

- **L3 — Archival / Cold Storage:** Full session logs, old conversations, project documentation. Store as compressed JSONL or a flat SQLite archive. Query only on explicit cross-session questions ("what did we do about X last quarter?"). Tools like `claude-vault` (SQLite + FTS5, single binary, zero deps) or fsck.com's episodic memory MCP (conversation archive → SQLite → semantic search) handle this tier.

**MCP is now the standard delivery mechanism for memory.** Both personal agents (Claude Code, Cursor, Windsurf) and production systems expose memory via MCP servers. Hmem, OpenMemory, Mnemory, and Memory-MCP all expose `store`/`query` tools over local SQLite or HTTP — no cloud required. Anthropic, OpenAI, and Microsoft all support MCP as a first-class integration path.

**Temporal knowledge graphs are the next architectural leap.** Systems like Zep (Graphiti) and OpenMemory track how facts change over time — not just that a user preference exists, but when it changed and why. This handles the staleness problem that pure RAG can't: if "user prefers npm" was overridden by "switch all projects to pnpm," a temporal graph preserves the timeline and knows pnpm is current. Mem0's knowledge graph nodes provide a similar capability for production stacks.

## Evidence

- **Research finding (Letta):** Plain filesystem scores 74% on agent memory tasks, beating specialized vector-store libraries in head-to-head comparison. Complexity doesn't always win — match the tool to the problem class. — [MemNexus blog, citing Letta research](https://memnexus.ai/blog/2026-05-23-ai-agent-memory-architecture)

- **Production comparison (Mem0 vs Zep):** Mem0 (51.8K GitHub stars) uses vector embeddings + optional knowledge graph nodes; benchmarks show 92.5 on LoCoMo at ~6,900 tokens/query. Zep uses a temporal knowledge graph (Graphiti) and scores 63.8 on LongMemEval but handles fact-versioning natively — if a user preference changes, Zep tracks when. For teams choosing: Mem0 OpenMemory wins for local/MCP/local-dev use; Zep Cloud wins for temporal reasoning at scale. — [RockB comparison guide](https://baeseokjae.github.io/posts/mem0-vs-zep-production-guide-2026)

- **Real-world episodic memory (fsck.com):** Jesse Vincent built a production episodic memory MCP for Claude Code that archives all conversations from `~/.claude/projects` into SQLite with vec0 embeddings. Started as a "feelings journal for Claude," grew to include engineering notebook, user-information notebook, and cross-session search. Key quote: "You only get memories when the journaler realizes what they've just done is worth writing down." — [blog.fsck.com, 2025-10-23](https://blog.fsck.com/2025/10/23/episodic-memory.md)

## Gotchas

- **Don't load L2 at session start** — vector retrieval is expensive (tokens + latency) and most sessions don't need historical context until a specific question triggers it. Load L1 (preferences, system instructions) at start; retrieve L2 on demand.
- **Fact staleness kills agents** — an agent acting on outdated preference memory can be worse than one with no memory. If your system doesn't track when facts changed, add TTLs or re-validation steps before acting on old facts.
- **The MCP memory server is not the memory itself** — MCP is the transport; you still need a storage backend, retrieval strategy, and eviction policy. "I added an MCP server" is not a memory architecture.
- **Context dilution is silent** — long conversations get compressed by the model, and the agent doesn't tell you what's been dropped. Use explicit summarization at session boundaries rather than relying on passive context management.
