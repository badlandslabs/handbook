# S-1619 · The Agentic Memory Stack — When Your Agent Wakes Up With Amnesia Every Session

Every Claude Code session starts fresh. Every new conversation is a stranger. You re-explain the project conventions you explained last week. The agent discovers the same bug youdebugged together two months ago — as if for the first time. The context window is finite, the session boundary is real, and the most expensive thing your agent does is repeat itself. This is the agentic memory problem: giving agents persistent, useful memory across sessions without drowning them in noise.

## Forces

- **Context is expensive and finite.** A 200K-token context window fills fast with conversation history. Loading everything costs tokens, increases latency, and degrades model performance — studies show context utilization and output quality have an inverse relationship past ~60-70% of available tokens.
- **Memory layers have conflicting requirements.** You want persistence (survives sessions), relevance (only what's useful right now), and low token cost — but optimizing for one usually hurts another. No single memory type solves everything.
- **The framework landscape fragmented mid-2025.** Gen 1 frameworks (Mem0, Letta, Zep, Graphiti) each made bet-the-company architectural choices. Gen 2 (Mastra OM, MemOS, Hindsight) emerged with different primitives. Choosing wrong means a painful rewrite.
- **Auto-memory writes too much.** When agents manage their own memory, they tend toward comprehensive logging over targeted knowledge. A MEMORY.md file that grows to 500 lines defeats its own purpose — the agent can't load it all without burning its context budget.

## The Move

Build a layered memory architecture where each layer has a distinct persistence contract, token budget, and load trigger. Stack from static to dynamic:

1. **Layer 1 — Static / Declarative (zero cost, always loaded).** CLAUDE.md at `~/.claude/` and `<project>/` levels. These files load every session regardless of conversation length. Purpose: conventions, working style, critical warnings. Typical size: ~50-120 lines combined. Do NOT put conversation history here — this is for things that never change.

2. **Layer 2 — Structured Auto-Memory (bounded load).** The agent's auto-written summary (e.g., MEMORY.md in Claude Code). Loads first ~200 lines automatically — beyond that, it's opt-in per session. Purpose: project state, recent discoveries, current blockers. Enforcement: hard cap on auto-load region. If memory exceeds the cap, it's a signal to write narrower notes instead of longer ones.

3. **Layer 3 — Semantic / Episodic Memory (query-triggered).** Vector-searchable storage of past interactions, decisions, and artifacts. Loaded on demand when a session query matches historical content. Frameworks handle this: Mem0 (AWS-selected, ~40% token reduction vs. full history), Zep (temporal knowledge graphs), Letta (tiered core/archival blocks), Graphiti (episodic-to-semantic extraction). Purpose: "have we solved this before?" lookups. Budget: typically last 10-30 relevant chunks, not full history.

4. **Layer 4 — Procedural Memory (behavioral).** Stored tool-use sequences, agent execution patterns, workflow templates. Not facts or history — *how* things get done. Purpose: replaying known workflows without re-deriving them. Often implemented as MCP server state or saved agent skill definitions.

5. **Layer 5 — Working Memory (session-scoped).** Active context during a session: current task state, subagent outputs, intermediate results. This is the only layer that doesn't persist. Budgeted explicitly as a percentage of context — some teams set a rule that working memory must not exceed 40% of available tokens, leaving headroom for retrieval and reasoning.

The critical discipline: **each layer has a load rule and a budget.** If auto-memory exceeds its cap, prune before adding more. If semantic retrieval returns >N chunks, re-rank. If working memory creeps past threshold, trigger compaction. Most teams that fail at agent memory fail because they treat all layers the same — they dump everything into context or nothing persists between sessions.

## Evidence

- **Claude Code's 4-layer architecture (documented, 2026):** The most concrete public implementation of this layered approach. Layer 1 (CLAUDE.md) persists across sessions and survives compaction. Layer 2 (MEMORY.md auto-memory) auto-loads first 200 lines. Layer 3 (Memory Tool via `memory_20250818` API) enables explicit cross-session writes. Layer 4 (subagent memory stores) gives each spawned agent its own persistent knowledge. Described as "most developers use at perhaps 10% of its capability" — the gap is configuration, not architecture. — [orchestrator.dev — Claude Code & Agent Memory: Best Practices for 2026](https://orchestrator.dev/blog/2026-04-06--claude-code-agent-memory-2026)

- **Mem0 production validation (AWS-backed, 2025):** AWS selected Mem0 as the exclusive memory provider for its AWS Agent SDK. Production users (Sunflower healthcare platform, Browserbase headless browser agents, OpenNote) report ~40% token cost reduction versus full chat history — because semantic retrieval returns targeted chunks instead of entire conversation logs. Letta's own benchmark found that a plain filesystem memory scored 74% on memory task benchmarks, beating several specialized vector-store libraries — a signal that architectural simplicity often beats framework complexity. — [LLM Agent Research — Production Adoption](https://lin-guanguo.github.io/llm-memory-research/production-adoption.research/)

- **Memory taxonomy operationalized (academic → production, 2025):** A survey of 45+ sources maps Tulving's memory taxonomy (semantic, episodic, procedural) onto agent infrastructure. Semantic memory = extracted facts and preferences (Mem0 key-value, Zep knowledge graphs). Episodic memory = temporally-dated interaction histories (Graphiti episodic extraction, Letta block tiers). Procedural memory = behavioral patterns and tool sequences (MCP state stores, saved skill definitions). The finding that cuts across sources: the teams shipping production agents don't pick one framework — they compose layers. Mem0 for semantic retrieval, Zep for temporal relationships, Letta for self-editing inner monologue, plus a thin declarative layer at the base. — [GitHub — Agent Memory Techniques (30 notebooks)](https://github.com/NirDiamant/Agent_Memory_Techniques)

## Gotchas

- **Don't let auto-memory grow unbounded.** An agent that writes 300 lines to MEMORY.md every session will eventually have a memory file larger than its useful context window. Set a hard cap on auto-load lines and force selective pruning.
- **Semantic retrieval without re-ranking is noise.** Raw vector similarity returns chunks that contain keywords but miss intent. Layer a re-ranking step or enforce a strict chunk-size budget (top 10-15 chunks max) to prevent context flooding.
- **Memory layers don't share schema.** Each framework (Mem0, Letta, Zep, Graphiti) has its own memory format. If you switch frameworks, you may lose queryable history. Treat memory storage as a schema dependency — it needs versioning and migration tooling just like a database.
- **Cross-agent memory requires explicit synchronization.** When multiple agents work on the same project, their individual memory stores diverge unless there's a shared write-back protocol. The practical solution: a shared declarative layer (CLAUDE.md equivalent) that all agents read, with per-agent ephemeral layers for session-scoped work.
