# S-2215 · The Context Window Cliff Stack — When Your Agent Is Silently Forgetting What It Was Doing

Your multi-step research agent completes steps one through six flawlessly. Step seven contradicts step two. Step eight confidently cites a tool that doesn't exist. Step nine submits a report that looks polished but is disconnected from the original question. Nothing crashed. No error was thrown. Your monitoring dashboard is green. The agent simply forgot — and kept going anyway.

This is the context window cliff: the moment an agent's accumulated context exceeds its effective reasoning capacity. The agent doesn't fail gracefully. It makes confident, wrong decisions based on partial information — and you won't know until the output lands.

## Forces

- **Attention degrades before the token limit hits.** Models don't process all tokens equally — attention concentrates on the beginning and end of the input, so middle positions receive less reliable processing. By the time you hit the token ceiling, degradation has already started.
- **Context windows reset across sessions.** Every API request starts from scratch. Without an explicit memory layer, an agent running Monday has zero knowledge of what it did Friday.
- **Larger windows don't solve the problem.** 128K, 200K, even 1M token contexts are marketing ceilings, not engineering guarantees. Effective reasoning bandwidth is far smaller, and adding more context actively dilutes signal-to-noise.
- **The blank-slate problem compounds with team size.** A coding agent re-explained to every session loses institutional knowledge: architecture decisions, naming conventions, bug context. Teams report spending the first 5 minutes of every session re-establishing what the previous session already established.
- **Three memory tiers compete for the same slot.** Working memory (context window), episodic memory (session history), and semantic memory (stored knowledge) all compete for the same in-context real estate, and each tier has different retrieval characteristics.

## The Move

The core technique: **treat memory as a retrieval problem, not a storage problem.** Don't dump everything into context — store selectively and retrieve on demand. Specific tactics:

- **Three-tier memory architecture mirrors cognitive science.** Working memory (current turn, model context, no persistence), episodic memory (session events, tool calls, observations — compressed and stored after session), and semantic memory (facts, preferences, learned patterns — persisted across sessions). Each tier has different latency, capacity, and retrieval characteristics.
- **Use hybrid retrieval instead of vector-only search.** A single dense embedding search yields ~20% hit@1 on agent-issued queries. Fusing dense embeddings + sparse keyword + substring search via Reciprocal Rank Fusion (RRF) doubles hit@1 to 60% and recall@5 to 80% — without requiring a vector database at all.
- **Compress episodic memory after each session, not at session start.** agentmemory (26K+ GitHub stars) captures tool calls, code changes, and decisions during the session, then compresses them into structured memory entries. The next session receives only the most relevant compressed entries, not raw transcripts.
- **Anthropic's "dreaming" pattern for continual memory improvement.** Out-of-band batch process where dedicated review agents scan session transcripts, identify recurring patterns and knowledge gaps, and propose updates to the semantic memory layer. Separates the memory write from the active task path to avoid adding latency.
- **CLAUDE.md and .cursorrules cap out at ~200 lines and go stale.** Built-in files work for static preferences but cannot capture dynamic session context, recent tool outcomes, or evolving decisions. Production memory systems need versioning, TTLs, and staleness detection.
- **Context budget as first-class engineering.** Treat in-context tokens as a scarce resource with an explicit budget. Track which files, memory entries, and tool outputs are actively contributing to current reasoning, and evict low-signal content before degradation begins.

## Evidence

- **GitHub repo (26.6K stars):** agentmemory — persistent memory for AI coding agents, captures and compresses session observations, 95.2% R@5 retrieval accuracy, supports 32+ agents including Claude Code, Codex CLI, Cursor — [https://github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **Engineering blog (Anthropic Applied AI, Sept 2025):** "Effective Context Engineering for AI Agents" — evolved from simple markdown file injection to file-system memory with versioning, concurrency controls, and "dreaming" (batch review of session transcripts to improve semantic memory) — [https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- **GitHub gist (benchmark):** RRF fusion over curated corpora doubles hit@1 vs. dense-only retrieval (60% vs 20%), with working implementation in agentic-task-system — [https://gist.github.com/renezander030/41af917a5ae84a42b5912bc20a5db615](https://gist.github.com/renezander030/41af917a5ae84a42b5912bc20a5db615)
- **Blog post (tianpan.co, April 2026):** The Context Window Cliff — describes the progressive failure pattern where first steps are excellent, middle steps drift, and final steps are coherent but disconnected from the original objective — [https://tianpan.co/blog/2026-04-14-the-context-window-cliff](https://tianpan.co/blog/2026-04-14-the-context-window-cliff)

## Gotchas

- **Don't confuse context window size with reasoning capacity.** A 200K token window does not mean 200K tokens of reliable reasoning. Budget for effective bandwidth (typically 10–20% of the nominal ceiling), not the headline number.
- **Static CLAUDE.md-style files become stale liabilities.** Without staleness detection, the agent acts on outdated context as if it were current. Add timestamps or version hashes to memory entries and check freshness before retrieval.
- **Compression before retrieval kills signal.** Raw session transcripts are too noisy for in-context injection, but aggressive compression discards the decision context that made previous actions correct. Preserve the *why*, not just the *what*.
- **Cross-session identity is unsolved for multi-agent fleets.** When multiple agents share a knowledge base, distinguishing which agent's context applies to which task requires explicit permissioning and namespace isolation — a problem most memory systems don't address.
