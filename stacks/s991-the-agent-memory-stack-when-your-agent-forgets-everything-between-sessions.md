# S-991 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent completed a complex multi-day task last week. Today it starts from scratch, asks for the same context it asked for two days ago, and has no memory that a design decision was already made. For single-turn queries this doesn't matter. For persistent agents — coding assistants, copilots, ongoing workflows — statelessness is a dealbreaker. Memory is what transforms a clever chatbot into a coherent collaborator.

## Forces

- **Context is finite and degrades before it fills** — degradation starts at 50-60% window fill; "lost in the middle" means information buried mid-context gets ignored even when there's room left; models attend to start/end positions disproportionately
- **Long sessions accumulate garbage** — every tool result, every API call response, every intermediate thought adds noise; a coding agent that reads five files can burn 81% of its context on tool results alone
- **Short-term and long-term memory are different problems** — keeping context alive within a session (window management) uses different tools than persisting learned facts across sessions (semantic memory)
- **Compression is destructive by default** — naive summarization loses specificity; "remember the key decisions" is not the same as remembering which decision was made on which day and why it was later revised
- **Temporal facts require temporal reasoning** — "what was our return policy before March?" needs validity windows, not flat vector retrieval

## The move

Build a four-layer memory hierarchy and manage context proactively — not when it runs out, but when it starts degrading.

### Layer 1 — Working memory (always-in-context)

- Small, high-value slot that never gets evicted: current task goal, active constraints, in-progress decisions
- Session start re-injects a structured briefing from prior memory rather than dumping raw history
- Proactive rotation triggers at ~60% context fill, not 90% — degradation precedes exhaustion

### Layer 2 — Episodic memory (session artifacts)

- Structured summaries of completed sessions: what was done, what remains, what changed
- Written by the agent at session end, not by a separate summarizer
- Includes a working-state snapshot that feeds into the next session's startup sequence
- Git commits serve as a recovery mechanism: descriptive commit messages let agents revert bad state changes

### Layer 3 — Semantic memory (cross-session facts)

- Extracted facts, preferences, and learned patterns stored in a retrieval layer
- Facts include validity windows: true "from X until Y," not just current state
- Deduplication across sources prevents the same fact from accumulating multiple conflicting embeddings
- For personalization: vector similarity search. For institutional knowledge: temporal knowledge graphs that track when facts changed

### Layer 4 — Procedural memory (agent instructions)

- The agent's own learned behavior patterns, not just system prompts
- Self-modifying within constraints, versioned so incorrect changes are reversible

### Compaction strategies (pick one, commit to it)

| Strategy | Mechanism | Trade-off |
|---|---|---|
| **Precision cascade** (Claude Code) | Three-tier eviction: scratch → recent → archive; preserves cache prefixes | Complex, requires careful boundary definition |
| **Handoff memo** (Codex CLI) | Session end writes a structured summary; next session reads it cold | Simple, loses mid-session state entirely |
| **Stepped governance** (OpenCode) | Non-destructive; context rotates out but remains retrievable | Higher storage overhead, full audit trail |

### Technology choices that have proven out

- **Mem0** — managed memory layer, 80% token reduction on retrieval, 19 vector store backends, fastest integration path, weakest on temporal reasoning
- **Letta** (formerly MemGPT) — full agent runtime with OS-style memory management, strong archival/retrieval tiers, best for explicit memory management needs, ~22K+GitHub stars
- **Zep** — temporal knowledge graph via Graphiti engine, stores facts with validity windows, LongMemEval score 63.8% vs Mem0's 49.0%, best for changing institutional knowledge
- **Hindsight** (Vectorize.io) — MIT-licensed, achieves 91.4% on LongMemEval, strongest on temporal fact tracking
- **foldcrumbs/engram** — file-based approach, no vector DB, no external service, agent uses grep for recall, local LLM for async distillation only; minimal infrastructure, maximum portability
- **LangGraph + checkpointers** — thread-based state persistence with configurable backends (MemorySaver for dev, Redis/DynamoDB for production)
- **TencentDB-Agent-Memory** — 4-tier progressive pipeline, zero external API dependencies, evaluated on SWE-bench (50 consecutive tasks per session): +9.93% success rate, −33% token consumption

## Evidence

- **Benchmarks:** TencentDB Agent Memory measured on SWE-bench (50-task continuous sessions) shows +9.93% success rate and −33.09% token consumption with memory plugin. On WideSearch: +51.52% success rate, −61.38% tokens. On PersonaMem (long-term personalization): 48% → 76%. — [TencentDB-Agent-Memory GitHub README](https://github.com/TencentCloud/TencentDB-Agent-Memory)
- **Framework comparison:** Zep's Graphiti (temporal knowledge graphs) scores 63.8% on LongMemEval vs Mem0's 49.0%. Hindsight scores 91.4%. The gap is entirely in temporal fact tracking — Mem0 treats all facts as equally current. — [AI Agent Memory Architecture Guide 2026](https://baeseokjae.github.io/posts/agent-memory-architecture-guide-2026)
- **Production impact:** Adding a memory context layer to a Snowflake data agent produced 20% accuracy improvement and 39% fewer tool calls. Mem0 reports up to 80% prompt token reduction through memory compression. — [AI Magicx / Zylos Research](https://www.aimagicx.com/blog/ai-agent-memory-systems-persistent-brain-2026), [Zylos Research](https://zylos.ai/en/research/2026-05-05-ai-agent-context-window-management-compaction-continuity-cost)
- **HN discussion:** Hmem (hierarchical MCP memory server) solves cross-tool context dilution — agents forget not just between sessions but within sessions as context silently pushes out earlier decisions. Uses SQLite-backed knowledge graph with scoped entities, relations, and bitemporal history. — [Show HN: Hmem](https://news.ycombinator.com/item?id=47103237)

## Gotchas

- **"Lost in the middle" starts at 50K tokens** — do not wait for 90% fill; proactive rotation at 60-65% is the production-safe threshold
- **Vector similarity search can't answer "before X date"** — if your agent needs to know what a policy was last month (not what it is now), you need temporal knowledge graphs, not flat vector stores
- **Compression preserves confidence, not correctness** — a summarizer that collapses "we decided to use Postgres after evaluating MongoDB, MySQL, and SQLite" into "we use Postgres" loses the reasoning that would prevent re-evaluating the same choice
- **Mem0 vs Letta is a category difference, not a feature comparison** — Mem0 is a memory layer you bolt on; Letta is an agent runtime you build inside. Migrating from one to the other means rebuilding your agent loop, not just swapping a library
- **Session-end writes are not optional** — agents that only write memory at rotation time lose all state from the current rotation window if they crash before the next rotation completes
