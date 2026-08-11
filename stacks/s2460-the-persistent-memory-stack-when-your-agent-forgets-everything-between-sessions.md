# S-2460 · The Persistent Memory Stack — When Your Agent Forgets Everything Between Sessions

You shipped a customer support agent. On Tuesday it helps a user troubleshoot their integration. On Thursday the same user calls back and the agent has no idea what happened. It asks for the same information again. The user is frustrated. The agent rebuilt context from scratch — again. The problem isn't the model. It's that your agent has no memory.

## Forces

- **Context windows are finite and expensive** — a 200K-token window sounds large until you're paying to refill it on every call for facts the agent already learned last week.
- **The taxonomy is still settling** — working, episodic, semantic, procedural memory mean different things to different frameworks, and teams waste months on the wrong abstraction.
- **Simple solutions sometimes beat specialized ones** — Letta's own benchmarks show a plain filesystem scoring 74% on memory tasks, outperforming dedicated vector-store libraries for common cases.
- **Memory corruption is invisible** — an agent with poisoned or drifted memory doesn't error out; it confidently acts on wrong premises, and nobody notices until a customer complains.
- **Four serious frameworks compete** — Letta, Mem0, Zep/Graphiti, and LangMem each make different trade-offs between infrastructure complexity, recall quality, and operational overhead.

## The Move

### Layer the four memory types explicitly

Production agents need all four, not just one:

- **Working memory** — context window, hard cutoff at token limit; this is where the agent thinks in-session.
- **Episodic memory** — timestamped records of specific events, dual-indexed by time and embedding; "what happened in session 14."
- **Semantic memory** — consolidated facts extracted from episodes; "the user prefers Markdown output" (stable across sessions).
- **Procedural memory** — how to use tools, agent self-model; "I call the search tool by passing a query string."

### Default to filesystem for low-stakes, escalate to dedicated infrastructure for high-stakes

A `CLAUDE.md` or `PROJECT_MEMORY.md` file in the repo scores 74% on Letta's memory benchmarks for typical project-scoped tasks. The overhead of Postgres + vector store + a framework like Mem0 is only worth it when you have:
- Multi-session user relationships where recall accuracy directly impacts revenue
- Regulatory requirements for auditable memory state
- >10K queries/day where retrieval latency matters

### Use session-end reflection ("the reflect pattern")

After each session, run a lightweight LLM pass that extracts new facts, updates preferences, and summarizes what was learned. This is what Claude Diary, fsck.com's episodic memory, and claude-mem all implement. It's cheap (runs once per session, not per turn), reduces context refill costs on the next session by 30-60%, and is the single highest-ROI pattern in production memory systems.

### Back episodic recall with a dual index (time + embedding)

Pure semantic search misses recency. Pure time ordering misses relevance. Production-grade recall chains both: "give me facts from the last 7 days that are semantically similar to the current query." Zep, Graphiti, and Mem0 implement this natively.

### Make memory decay explicit

Without decay, episodic memory grows unbounded and signal-to-noise degrades. The standard approach: salience score each episode at write time, apply time-decay weighting at read time, and periodically compact low-salience entries. Most teams skip this and are surprised when a 6-month-old fact resurfaces as if it's current.

### Wire in observability at the memory layer

Track what was recalled at each turn, what was written to memory, and whether the recall improved the next interaction. If you can't answer "did memory help?" with data, you're flying blind. LangSmith, Langfuse, and Phoenix traces all support memory-span instrumentation.

## Evidence

- **HN Discussion:** A contractor on HN described building a text-to-SQL agent for ~10,000 B2B users that recovered from errors, auto-created visualizations, and had a FAQ component — all as "a bunch of prompts conditionally slapped together in a call graph." No memory framework, just careful prompt engineering with conditional branching. — [Ask HN: Examples of agentic LLM systems in production? — Hacker News, Dec 2024](https://news.ycombinator.com/item?id=42431361)

- **Research Survey:** A December 2025 survey paper (arXiv 2603.07670) stabilized the four-type memory taxonomy. The same survey found that retrieval pipeline cost (embed + rerank + LLM) runs roughly $0.002–0.01 per query at low volume, scaling to thousands per month at enterprise scale. — [Agent Memory in Production — Perea.ai Research, 2026](https://www.perea.ai/research/agent-memory-production)

- **Benchmark Finding:** Letta's own evaluation showed plain filesystem-based memory scoring 74% on memory tasks — beating specialized vector-store memory libraries for common cases. The "reflect" session-end learning loop is documented as standard practice across Claude Diary, fsck.com episodic memory, and claude-mem. — [A memory architecture for agentic system — GitHub Gist, 2025](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

## Gotchas

- **Don't reach for a memory framework on day one.** If your agent runs <100 sessions/day and doesn't have cross-session user relationships, a markdown file or SQLite table with the last 20 interactions will likely suffice. Memory infrastructure adds operational complexity that needs justifying.

- **Memory poisoning is silent.** A corrupted fact won't error out — it just quietly misdirects future reasoning. Build periodic sanity checks: "given these 10 recent memories, what would you predict about this user?" and compare against ground truth.

- **The framework migration trap is real.** Multiple HN commenters and Cleanlab's 2025 survey noted teams moving from LangChain to Azure or back within 2 months. Before committing to a memory framework, validate that it won't become another migration. Mem0, Letta, Zep, and LangMem are all young — pick based on your existing stack, not benchmarks.

- **Token accounting must include memory refill cost.** A session that re-loads 50K tokens of episodic memory before answering a 500-token question costs 100x more than the same question without memory. Model this explicitly in your cost estimation.
