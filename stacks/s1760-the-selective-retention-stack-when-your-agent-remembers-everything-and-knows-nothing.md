# S-1760 · The Selective Retention Stack

When your agent has been running for three weeks and knows every conversation it ever had — but cannot reliably tell you what city the user lives in, what the project deadline is, or whether their shipping address was updated. More memory, worse answers. The problem is not capacity. It is curation. Your agent is storing everything and prioritizing nothing, so when it retrieves, it surfaces the factually wrong memory with the same confidence as the correct one.

## Forces

- **Retention is cheap; retrieval is expensive.** Storing a chat message costs bytes. Retrieving from a flooded memory store costs you the correct answer — because similarity search returns the most semantically similar result, not the most temporally valid one.
- **Contradiction accumulates silently.** A user changes their address twice. A product price updates. A feature gets renamed. Each version lives in memory with equal standing. The agent does not know which is current and does not know it is wrong until it confidently gives outdated information.
- **Importance and recency are orthogonal signals.** The most important fact (user's name) and the most recent fact (what they said ten minutes ago) are different things. Systems that only weight recency bury durable knowledge; systems that only weight importance cannot adapt to change.
- **The agent has no curation agency by default.** Most memory systems are passive stores — they accept writes and serve reads. The agent does not decide what to keep, what to compress, or what to invalidate. The result is a memory that grows but does not improve.

## The Move

The pattern is **tiered memory with active curation** — not a flat vector store, but a lifecycle-aware system where memories move through tiers and are actively consolidated, compressed, or discarded.

**Tier 1 — Working buffer (always in context):** Keep the last N messages and a small set of explicitly pinned facts (user identity, current task, active project). This is cheap to keep fresh and expensive to pollute. No retrieval needed — it's always present.

**Tier 2 — Selective episodic memory (queryable, bounded):** Store events, not transcripts. Each memory entry is a structured fact — who, what, when, subject, and an importance score assigned at write time. Importance scoring at ingestion: user corrections, explicit preferences, and decision outcomes get high scores; casual mentions get low scores. Cap the total episodic store (e.g., 500 facts per user) and enforce it.

**Tier 3 — Compressed semantic memory (periodic consolidation):** Run a nightly or per-session consolidation pass. Group related episodic entries, compress repeated themes into summaries, and promote high-importance facts to a flat "known facts" store. Old episodic entries that have been successfully compressed are evicted. This is the "sleep consolidation" step — borrowed from the Complementary Learning Systems theory in cognitive science.

**Tier 4 — Retrieval with recency weighting:** At query time, score candidates by both semantic similarity AND recency AND importance. Pure vector similarity is time-blind — a stale fact that uses the right words beats a current fact that doesn't. Mem0's 2026 analysis showed a 0.15 score gap between top candidates that vanishes without recency weighting. Recent memories get up to a 1.5× boost; idle ones floor at 0.3×. These multipliers are tuned per use case, not hardcoded.

**Contradiction handling over deletion:** When a new memory contradicts an existing one, do not delete the old fact — mark it superseded with a timestamp and provenance link. This preserves the audit trail (useful for debugging, compliance) and enables the agent to reason about change over time. Zep's Graphiti backend implements this as a first-class concept and scores 63.8% on temporal-retrieval benchmarks versus 49.0% for pure vector extraction — a 15-point gap on the exact capability production agents need.

**Agent-directed curation:** Give the agent tools to edit its own memory blocks — not just read and write, but compress, flag as uncertain, and mark for review. Letta's architecture makes this explicit: the agent manages its own core memory blocks and decides what persists. The framework pages in and out of context; the agent decides what to page.

## Evidence

- **Benchmark analysis:** On LongMemEval (multi-turn conversational recall), Zep/Graphiti scores 71.2% versus Mem0 at 66.9% on LOCOMO. OMEGA reaches 95.4% on LongMemEval, Mastra's Observational Memory 94.87% — but these benchmarks measure recall competency, not cost, lineage, or contradiction rate. — [memnode benchmark analysis, May 2026](https://memnode.dev/articles/agent-memory-benchmarks-2026-real-numbers)

- **Production failure pattern:** "A user tells your AI agent they live in San Francisco. A few weeks later, they mention relocating to Boston. Your memory system now has two facts. The next time the agent needs to answer 'where does this user live,' it picks whichever fact has the higher cosine similarity to the query embedding. Sometimes that is Boston. Sometimes it is San Francisco. The agent does not know it is wrong. It just answers with full confidence." — [widemem.ai contradiction analysis, March 2026](https://widemem.ai/blog/contradictions)

- **Three-pattern taxonomy:** AgenticWire's 2026 comparison identifies three production patterns: vector-first extraction and retrieval (Mem0, drop-in, AWS SDK alignment), graph-native temporal knowledge (Zep/Graphiti, for facts that change over time), and OS-tiered context management (Letta, for agents that self-manage memory paging). — [AgenticWire, June 2026](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory)

## Gotchas

- **Stacking two recency biases over-corrects.** If your application already multiplies similarity by a recency weight, enabling memory decay stacks two recency signals. Mem0's documentation specifically calls out that the combined behavior can bury useful older facts — test the interaction, not each component in isolation.
- **Hierarchical summarization loses granularity before you want it to.** Summarizing a 50-message conversation into one fact loses the ability to ask "what specifically did the user say about the API timeout?" Compression ratios that look reasonable in eval will fail in production on edge cases.
- **Importance scoring at ingestion is fragile.** If the agent is writing its own importance scores, it will score most things as important (it has no evolutionary pressure to forget). Force a budget — only the top N% of scored memories survive ingestion, or enforce a per-session write cap.
- **Benchmarks don't measure the failure mode that will hurt you.** LOCOMO tests multi-session conversational recall. It does not measure contradiction rates, memory latency, cost-per-query, or whether the system handles fact invalidation. Build your own golden dataset for your specific use case.
