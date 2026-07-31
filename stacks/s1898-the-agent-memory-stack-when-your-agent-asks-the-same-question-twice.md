# S-1898 · The Agent Memory Stack: When Your Agent Asks the Same Question Twice

Your agent runs for three hours and forgets what it agreed to in turn 7. It restarts and re-derives the same plan. It loses a customer preference from last quarter because the session ended. This is not a model problem. It is a memory problem: no architecture for what to remember, how, and for how long.

## Forces

- **The forgetting gradient** — context window holds the present turn perfectly, nothing before it reliably. The moment a session ends, the agent resets to zero unless memory is explicitly persisted.
- **Hot vs. cold state tension** — working state (active plan, tool results) needs millisecond access; cross-session facts need durable storage. These access patterns are fundamentally different and want different backends.
- **Retrieval cost vs. recall quality** — loading all memory into every call burns tokens and latency. Loading too little means the agent acts without context. The right slice is non-obvious and changes as the agent's task grows.
- **The stale-memory trap** — agents with persistent memory learn outdated facts and act on them confidently. Without a temporal invalidation strategy, memory becomes liability.
- **Context window is finite but memory is not** — naive teams add vector search over everything and end up with retrieval results that are semantically relevant but factually superseded.
- **Four distinct memory types, one storage layer** — cognitive science (working/episodic/semantic/procedural) says these have different properties. Most teams conflate them and suffer for it.

## The move

Separate memory by **temperature** — the frequency and latency of access. Then implement a session-end **reflect** step that converts episodic experience into durable semantic memory.

**Layer 1 — Working memory (hot):** The context window itself. Manage it explicitly with truncation strategies, priority ordering of tool results, and hard limits on what enters. This is free but requires discipline. LangGraph's `MemorySaver` checkpoint is the standard in-process implementation for this layer.

**Layer 2 — Checkpoint state (warm):** Pausable, resumable agent state stored in a checkpoint store. LangGraph checkpointers (Redis, Postgres, SQLite) serialize channel values and let you resume from a specific thread_id. This is the "save game" layer — it survives restarts but is not semantic. Use for multi-hour tasks that might be interrupted.

**Layer 3 — Cross-session memory (cold):** The durable store of facts, preferences, and learned patterns. The 2026 production stack converges on four frameworks:
- **Mem0** (62K GitHub stars, YC S24): Retrieval-focused, multi-tier (user/agent/session), scores 92.5 on LoCoMo and 94.4 on LongMemEval benchmarks. Best for personalization and fast time-to-value. April 2026 algorithm update significantly improved scores.
- **Zep/Graphiti** (from getzep, 1.8K stars): Temporal knowledge graphs with MCP server. Scores 63.8% vs Mem0's 49.0% on LongMemEval's temporal-retrieval subtask. Best when point-in-time correctness matters (e.g., "what was the user's job title in January?").
- **Letta** (formerly MemGPT, open-source): OS-inspired hierarchy — main context / recall storage / archival storage — where the agent manages its own memory via tool calls. Best for long-running stateful agents where the agent needs introspective control over what it stores.
- **LangMem** (LangChain-native): First-class memory primitives embedded in LangGraph's storage layer. Provides hot-path retrieval tools and background memory-updating tools. Best when already using LangChain/LangGraph.

**Layer 4 — Document memory (ambient):** Human-readable files (CLAUDE.md, project READMEs, decision logs) that the agent can read at will. Surprisingly effective — Letta benchmarks show a plain filesystem scoring 74% on memory tasks, beating some specialized vector-store libraries. Use for stable knowledge that changes rarely.

**The reflect step:** At session end, the agent runs a reflection pass — it reviews what happened, extracts facts to persist, identifies what it got wrong, and writes to the cross-session store. This is the pattern behind Claude Diary, fsck.com, and claude-mem. It converts experience into memory rather than letting it evaporate.

**The invalidation rule:** Every memory entry gets a timestamp and version. Before retrieval, the agent or the retrieval layer checks for superseded facts. Graphiti's temporal edges handle this structurally. Mem0's rewind API supports point-in-time queries.

## Evidence

- **HN Ask post (2025):** Developer building infrastructure for LLM agents describes the recurring failure: "vague memory leads to vague behavior, long memory pollutes context, duplicate entries make retrieval worse." The solution was a typed memory system with explicit lifecycle management. — [Hacker News](https://news.ycombinator.com/item?id=46742800)
- **GitHub / arXiv (April 2025):** Mem0 research paper ("Building Production-Ready AI Agents with Scalable Long-Term Memory") reports April 2026 algorithm: 92.5 on LoCoMo (up from 71.4), 94.4 on LongMemEval, 64.1 on BEAM (1M context). Y Combinator-backed, 62K stars. — [arXiv 2504.19413](https://arxiv.org/abs/2504.19413), [GitHub mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Engineering blog (Feb 2026):** Detailed walkthrough of checkpoint + vector + file-based hybrid architecture. Key finding: "separate memory by access pattern — hot is thread-level checkpoint state, cold is cross-session facts in a key-value or vector store, document memory keeps project knowledge in inspectable files." — [Edge of Context blog](https://slavadubrov.github.io/blog/2026/02/14/ai-agent-memory-architecture/)
- **Research comparison (2026):** Benchmark comparison of four frameworks: Mem0 92.5 LoCoMo / Zep 63.8% temporal retrieval / Letta OS-hierarchy / Cognee typed graphs. Key insight: "15-point gap on the exact capability (temporal correctness) that most production agents need." — [Particula.tech](https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026)
- **GitHub gist (Dec 2025):** Comprehensive survey of 45+ sources finds filesystem baseline scoring 74% on memory tasks, beating some vector-store libraries. Notes the "reflect" pattern (session-end learning loops) as emerging standard practice. — [GitHub Gist spikelab](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

## Gotchas

- **Don't load all memory into every call.** At 50+ memory entries, naive concatenation degrades model performance. Use retrieval to pull the top-K most relevant, then re-rank by recency and task relevance.
- **Temporal staleness is the #1 production failure mode.** The agent learns a preference, the user changes it, the agent still acts on the old one. Graphiti's temporal edges or Mem0's versioning solve this structurally; a flat vector store does not.
- **The reflect step is not optional.** Without session-end extraction, episodic experience evaporates. Most teams that add a vector store without a reflect step end up with a store full of noise that degrades retrieval quality over time.
- **Checkpoint state ≠ semantic memory.** LangGraph's MemorySaver gives you resumability (the agent can continue a paused task) but not recall (the agent doesn't know what it decided in a previous session about the user's preferences). These are different layers with different implementations.
- **Simple stacks beat complex ones at low volume.** A SQLite + filesystem baseline at ~$0.002/query beats a distributed vector cluster on cost and simplicity for teams under 10K daily active agents. Complexity enters when scale demands it, not before.
