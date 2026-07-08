# S-836 · The Tiered Memory Stack — When a Million-Token Context Is Not the Same as Memory

You bought a model with a 1M-token context window and assumed your agent would remember everything across long sessions. Six months in, you discover it has no memory at all — every restart wipes it clean, it loses track of declared goals halfway through a workflow, and it keeps re-asking for information the user provided two sessions ago.

## Forces

- **Context windows are stateless scratchpads, not memory.** Every API call starts at zero. A 1M-token window means you can stuff more history in, not that the model *remembers* across sessions. (MachineLearningMastery, 2026)
- **Full history loading is economically irrational at production scale.** A 600K-token context on every agent turn compounds quickly at frontier API prices. Teams paying this bill are burning money on repeated re-reading. (AgentMarketCap, Apr 2026)
- **Retrieval ≠ memory.** Vector similarity search solves "find relevant text." It does not solve "what was true about this user three months ago and when did it change?" — the temporal consistency problem. (AgenticWire, Jun 2026)
- **Attention degrades mid-context.** Models perform worse on information placed in the middle of long contexts than on information at the beginning or end ("lost in the middle"). This isn't a fixable bug — it's architectural. (MachineLearningMastery, 2026)

## The Move

Build a **tiered memory architecture** with three distinct layers, each serving a different function. No single layer — not even a large context window — handles all three.

### The three layers

| Layer | What it stores | Where it lives | Retrieval |
|---|---|---|---|
| **Working memory** | Current session state, intermediate reasoning, active goals | Context window (always in-prompt) | Direct |
| **Episodic memory** | Timestamped conversation events, session logs | Vector store + structured DB | Semantic search + time filter |
| **Semantic memory** | Extracted atomic facts, user preferences, learned patterns | Dedicated memory store | Multi-signal retrieval |

A fourth layer — **procedural memory** — appears in more sophisticated systems: the agent's own instructions, learned behaviors, and identity statements, stored separately from user data.

### Practical implementation

- **Start with semantic extraction over raw history.** Don't store full conversation logs; run an extraction step after each session turn that pulls atomic facts ("user prefers concise responses," "current project uses pytest"). Store facts, not transcripts.
- **Use temporal awareness for retrieval.** Pure vector search ignores *when* something was true. For user preferences and facts that evolve, append timestamps and filter by recency or relevance-window. Zep and Graphiti approach this with temporal knowledge graphs. (AgenticWire, Jun 2026)
- **Write durable goal documents.** At task inception, serialize the declared goal, constraints, and definition of "done" as a markdown file. Re-read this file at every major decision point. This survives context resets and provider switches. (Zylos Research, Apr 2026)
- **Enforce an explicit forgetting policy.** Without one, memory grows unbounded and retrieval quality degrades. Common approaches: LRU eviction by access time, consolidation (merge similar facts), and importance scoring (facts used frequently get priority). (Jobs by Culture, Jun 2026)
- **Reconstruct context at cold start.** When an agent wakes fresh, it needs to pull relevant memories before acting. Query episodic + semantic stores with the current task context, inject the top-K relevant memories into the initial prompt. (ctxdc.com, Jan 2025)

## Evidence

- **Engineering blog — 3-layer model:** Tacnode describes production agents needing three distinct memory layers: episodic (conversation history), semantic (extracted facts), and state (live operational context), unified under a single substrate. "Most teams only build one layer — usually a vector database — which is why agents fail in production." — tacnode.io, Feb 2026
- **Framework comparison — benchmark divergence:** Mem0 self-reports 94.4% on LongMemEval; an independent replication of its algorithm scored ~49%. The gap is retrieval strategy — Mem0 uses vector-only search; top-scoring systems (Hindsight, 94.6%) run semantic, keyword (BM25), knowledge graph traversal, and temporal reasoning in parallel. (AgenticWire, Jun 2026)
- **BEAM benchmark — context windows fail at contradiction resolution:** The BEAM benchmark (designed for million-token conversations) reveals that even the largest context windows struggle to maintain globally consistent state when earlier facts conflict with later updates. This is a fundamental limitation of stateless scratchpad architecture. (AgentMarketCap, Apr 2026)

## Gotchas

- **"We use a vector database" is not a memory strategy.** It is a retrieval primitive. Without extraction, temporal tracking, and tiering, you're building a search engine, not memory.
- **Storing raw conversation history scales poorly.** Transcripts grow linearly with session length; semantic extraction grows with *events and facts*, which is typically 10–100× smaller. Start with extraction.
- **Vendor benchmarks for memory systems are unreliable.** Run your own retrieval eval on your own data before committing to a platform. (AgenticWire, Jun 2026)
- **Personality and goal drift compound over time.** Long-running agents (>3 months) measurably regress toward generic assistant baselines without explicit identity and goal re-enforcement. This is a month-three-plus phenomenon that launch testing misses. (Zylos Research, Jun 2026)
