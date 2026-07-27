# S-1706 · The Memory Scarcity Stack — When Your Agent Wakes Up Amnesiac

Every new session starts from zero. You spent three hours last week mapping the codebase. Today the agent asks where the tests live. You corrected the same preferences yesterday. The model weights haven't changed — the agent is stateless by design. Memory is not a feature the model gives you. It is infrastructure you must build.

## Forces

- **LLMs are fundamentally stateless.** The context window is a whiteboard that wipes on session end. There is no continuity unless you explicitly create it. This is not a bug; it is a property that gives LLMs predictability and privacy, but it imposes repeated context costs every session.
- **Context window is a scarce resource.** Anthropic's engineering team frames context engineering as optimizing the *utility* of every token, not just filling the window. Bloat, irrelevant detail, and unstructured retrieval degrade the model's signal-to-noise ratio — the "Lost in the Middle" problem causes ~30% information loss in ultra-long contexts without proper management.
- **The sophistication of your memory layer does not guarantee its effectiveness.** Letta's benchmarking found agents on `gpt-4o-mini` using plain filesystem storage achieve **74.0% accuracy** on the LoCoMo memory retrieval benchmark, outperforming Mem0's specialized graph variant at 68.5%. Agent capability matters more than retrieval mechanism.
- **Persistent memory is a new attack surface.** ArXiv 2607.14611 (UW, July 2026) demonstrates that malicious payloads planted in memory files (CLAUDE.md, behaviors.md) can persist across sessions and attack future interactions — analogous to stored XSS. Injecting new content is hard; payloads already in files reliably exploit current and future sessions.

## The move

The memory stack is a layered hierarchy, not a single component. Each layer serves a different retention purpose with different read/write mechanics:

1. **Tier 1 — Ephemeral / Working Memory (context window).** The agent's immediate scratchpad. Use it for task state, not permanent knowledge. Flush to persistent storage at session end.
2. **Tier 2 — Structured Project Memory (markdown files: CLAUDE.md, MEMORY.md).** Human-authored or agent-discovered facts about the project. Load at session start. Claude Code auto-loads the first 200 lines of `MEMORY.md`. Anthropic's memory hierarchy supports Enterprise → Project → User levels. Keep files under 200 lines to avoid context bloat.
3. **Tier 3 — Semantic Long-Term Memory (vector store or knowledge graph).** Searchable fact store. Mem0 uses extracted entity facts in a vector DB. Zep uses Graphiti temporal knowledge graphs to track fact evolution (user "lives in Berlin" → user "moved to Munich"). Choose based on whether you need fact versioning or just recall.
4. **Tier 4 — Episodic Memory (conversation logs, summaries).** Store what happened, not just what was learned. Letta agents store full conversation histories in SQLite; Engram stores in `~/.engram/`. Session-end consolidation (extract key decisions, preferences, open questions) is the critical step most teams skip.
5. **Tier 5 — Security Gate on Memory Reads.** Validate and sanitize all memory file contents before injecting into context. The arXiv paper shows payloads already planted in memory files successfully attack agents across multiple sessions. Treat memory as untrusted input, not trusted state.

## Evidence

- **Research paper:** Letta's benchmarking blog — GPT-4o-mini agents with plain filesystem storage score 74.0% on LoCoMo vs. Mem0 graph variant at 68.5%, demonstrating that simpler retrieval often beats complex infrastructure — [Letta Blog](https://www.letta.com/blog/benchmarking-ai-agent-memory/), Aug 12, 2025
- **HN Show:** Neural Ledger System (Show HN) — built specifically to solve session amnesia in coding agents; files issue where every new session loses SSH config, DB credentials, and deployment targets — [HN #47940150](https://news.ycombinator.com/item?id=47940150)
- **Security research:** arXiv 2607.14611 — "Bad Memory" paper (UW) demonstrates persistent prompt injection via memory files against Claude Code and Codex across 4 models; payloads in CLAUDE.md persist across sessions — [arXiv](https://arxiv.org/abs/2607.14611), July 16, 2026
- **Engineering guide:** Anthropic's context engineering post — context refers to the set of tokens included when sampling from an LLM; the engineering problem is maximizing utility per token; key principle: smallest possible high-signal token set — [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), Sep 29, 2025
- **Comparison analysis:** AI Workflow Lab — Mem0 (entity extraction + vector DB), Letta (MemGPT-inspired memory block API), Zep (Graphiti temporal KG) — [AI Workflow Lab](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026), May 25, 2026
- **Open source:** Engram — universal memory layer for agents using SQLite locally, MCP tools for 10 memory operations, session-end consolidation hooks — [GitHub tstockham96/engram](https://github.com/tstockham96/engram)
- **HN Show:** Mnemory — open-source persistent memory for agents using structured storage and selective retrieval — [HN #47995527](https://news.ycombinator.com/item?id=47995527)

## Gotchas

- **Don't stuff the context window with full conversation history.** The "Lost in the Middle" effect means the model loses ~30% of information from the middle of long contexts. Consolidate at session end into structured facts, not raw transcripts.
- **Session-end consolidation is the step most teams skip.** You have to explicitly extract: what changed, what was decided, what's still open, what preferences were expressed. Without this step, your vector store is just a noisy transcript database.
- **Memory files are an attack surface, not just storage.** Any untrusted content that reaches a memory file can persist and attack future sessions. Validate memory file contents before injection; consider read-only memory layers for externally-sourced content.
- **The benchmark winner (filesystem) doesn't mean skip memory infrastructure.** Letta's finding is that *agent capability* drives the 74% score, not the storage mechanism. An agent that knows how to search files effectively will outperform a bad agent with a knowledge graph. Invest in both the agent's memory behavior and the infrastructure.
- **Fact decay is real.** "User prefers dark mode" and "User prefers light mode" can both surface from a vector search unless your framework reconciles contradictions. Zep's temporal knowledge graph addresses this; simple stores do not.

## Receipt

> Verified 2026-07-27 — Letta blog (Aug 12, 2025): GPT-4o-mini agents with filesystem storage achieved 74.0% on LoCoMo vs. Mem0 graph at 68.5% — agent capability matters more than retrieval mechanism. Engram MCP tools confirmed on GitHub tstockham96/engram. arXiv 2607.14611 (Gadgil et al., UW, submitted Jul 16, 2026): malicious payloads planted in memory files persist across sessions and successfully attack future agent interactions on Claude (Anthropic) and ChatGPT (OpenAI) systems. Code example is illustrative; not benchmarked against live Letta or Mem0 deployment.
