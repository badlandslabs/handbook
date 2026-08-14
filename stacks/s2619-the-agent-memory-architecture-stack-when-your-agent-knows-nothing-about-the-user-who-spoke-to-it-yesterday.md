# S-2619 · The Agent Memory Architecture Stack — When Your Agent Knows Nothing About the User Who Spoke to It Yesterday

Your agent aced the demo. On day three in production, a user comes back and the agent greets them like a stranger, asks for information it already collected, and contradicts something it said last week. The model is the same. The context window is the same. The agent is stateless by default — every session starts from scratch, and the impressive reasoning you saw in testing was built on a foundation of forgetting.

This is the agent memory problem: giving agents persistent, useful memory across sessions without drowning them in irrelevant context or breaking their ability to reason.

## Forces

- **Context window pressure vs. memory depth** — the more an agent remembers, the less room it has for reasoning. You can't just pour every past interaction into the prompt.
- **Retrieval noise vs. retrieval miss** — too little memory and the agent repeats itself; too much and it loses the thread in a haystack of semi-relevant past context.
- **Storage simplicity vs. cognitive sophistication** — a plain filesystem beats specialized memory on basic benchmarks, but real multi-session agents in complex domains need more.
- **Decay vs. permanence** — memories that never fade crowd out relevant context; memories that fade too fast lose the value of persistence.
- **Architectural depth vs. operational complexity** — OS-inspired tiered memory (core/recall/archival) mirrors how humans work, but adds significant implementation overhead.

## The move

Build a tiered memory architecture that matches retrieval cost to retrieval need. The pattern has three layers that appear across MemGPT/Letta, Mem0, and the research literature:

**Layer 1 — Working / Core Memory (always in context)**
- The agent's active scratchpad: current task state, user identity, session goals
- Tiny by design (2–8 KB equivalent). This is what the model reasons over directly.
- Updated on every significant action or conversation turn
- In MemGPT/Letta: "core memory." In elfmem: the SELF frame with permanent decay (~80K hour half-life)

**Layer 2 — Episodic / Recall Memory (retrieved on demand)**
- What happened in past sessions: facts about the user, past problems solved, preferences
- Stored in a vector database (or SQLite-backed BM25+embedding hybrid for lightweight setups)
- Retrieved via semantic similarity at the start of each session and on conversation turns
- Formative Memory (OpenClaw) adds association expansion: single-hop neighbors of matched memories are pulled in too
- elfmem's adaptive decay: memories reinforced through successful use grow stronger; memories that mislead fade

**Layer 3 — Archival / Summary Memory (cold storage)**
- Deep history, learned policies, long-horizon patterns that don't need to be in working memory
- Accessed rarely, when the agent explicitly searches or when a new task matches an old one
- MemGPT/Letta models this as a tier the agent "pages" in via tool calls
- Formative Memory runs a nightly consolidation: raw facts merge into summaries, associations strengthen

**Retrieval strategy — don't dump, surface**
- Query-time retrieval is the leverage point: hybrid search (embedding similarity + BM25 keyword) outperforms either alone
- Association expansion (pulling neighbors of top matches) is a key differentiator in biological-memory models
- MEMTIER (Bronislav Sidik & Prof. Lior Rokach, arXiv:2605.03675v1) found that weighted retrieval ranked by memory strength — not raw relevance — improved accuracy from 0.050 to 0.382 (+33 pp) on long-running agents using Qwen2.5-7B

**The benchmark reality check**
- Letta's benchmarking (August 2025) found that a Letta filesystem agent on `gpt-4o-mini` scored 74.0% on LoCoMo — outperforming Mem0 Graph (68.5%) on this benchmark
- The takeaway: retrieval strategy matters more than storage sophistication for benchmark performance
- But MEMTIER's results show the gap closes on harder tasks: when agents run for 72+ hours, tool success rates degrade 14 percentage points without structured memory management

## Evidence

- **Research paper (arXiv):** MEMTIER tiered memory architecture reduced tool execution accuracy degradation from 14 pp to near-zero over 72-hour windows; PPO-trained retrieval policy improved accuracy from 0.050 to 0.382 on Qwen2.5-7B — [arXiv:2605.03675v1](https://arxiv.org/pdf/2605.03675v1)

- **GitHub (MIT):** elfmem — adaptive memory with self-persisting identity, SQLite-backed, built from 26 structured explorations; implements the SELF Frame concept with permanent (~80K hour half-life) identity anchoring and adaptive decay for knowledge — [github.com/emson/elfmem](https://github.com/emson/elfmem)

- **GitHub (MIT):** Formative Memory — OpenClaw plugin implementing biological forgetting curves; nightly consolidation merges raw facts into summaries; recall uses hybrid embedding+BM25 search with association expansion — [github.com/jarimustonen/formative-memory](https://github.com/jarimustonen/formative-memory)

- **Engineering blog:** Letta benchmarking found filesystem storage (74.0% on LoCoMo) outperformed specialized graph memory (68.5%) on standard benchmarks; argues memory effectiveness depends more on agent context management than retrieval mechanism — [letta.com/blog/benchmarking-ai-agent-memory](https://www.letta.com/blog/benchmarking-ai-agent-memory/)

- **Engineering blog:** Mem0 vs Letta architectural comparison — Mem0 is a pluggable memory layer (bolt-on), Letta is an OS-inspired agent runtime; Mem0 reports 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query with hardest open problems being cross-session identity, temporal abstraction, and memory staleness — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)

- **Comparison article:** Vectorize.io architectural comparison of Mem0 vs Letta (2026): Mem0 uses passive extraction + semantic search (graph on Pro); Letta uses agent self-editing of tiered memory blocks — [vectorize.io/articles/mem0-vs-letta](https://vectorize.io/articles/mem0-vs-letta)

## Gotchas

- **Starting simple is underrated.** The Letta benchmark result (filesystem beats graph on LoCoMo) means you should prototype with a plain SQLite + vector store before reaching for a specialized memory framework. Complexity is not free.
- **Staleness is the silent killer.** Memory that was true last month may be wrong today. Formative Memory's nightly consolidation and elfmem's adaptive decay are both attempts to solve this — without a decay mechanism, stale memories actively mislead the agent.
- **Context pollution is real.** Over-retrieval (bringing in too many semi-relevant memories) degrades agent reasoning. The fix is ranking by memory strength or recency, not just semantic similarity — which MEMTIER's weighted retrieval demonstrates empirically.
- **Cross-session identity is unsolved.** Knowing that "this user is the same person who used the agent 6 months ago" requires stable user identification, not just semantic memory retrieval. This remains an open engineering problem in most deployments.
