# S-1512 · The RAM-Not-Storage Stack — When Your Agent Forgets Everything Between Sessions

Your agent works fine for 20 messages, then starts contradicting itself, repeating steps, and losing the user's name. The context window filled up. Everything before it is gone. The fix is not a bigger model — it's a memory architecture.

## Forces

- **The context window is volatile, not persistent.** Builders treat it like a database. It clears at session end. Confusing it for storage causes the most common production failure mode in agents — not bad prompts, not weak models, but memory architecture bugs that look like intelligence failures.
- **Token cost grows with everything in context.** A naive "store every message" approach costs ~9,000 tokens per session (linear growth) and degrades retrieval quality. Semantic memory costs ~500 tokens per user (flat). The difference is architectural, not parametric.
- **Memory has a retrieval problem, not just a storage problem.** Putting facts in a vector store and always retrieving them produces noise. Getting the right memory at the right time — without flooding context with irrelevant detail — requires a tiered architecture, not a single index.
- **Cross-session continuity vs. context dilution.** Agents that remember everything equally end up remembering nothing useful. Important decisions from hour-old sessions get lost in a sea of recent trivia.

## The Move

Build a four-tier memory architecture. Treat the context window as **working memory (RAM)** and external storage as **persistent storage**. Never treat them as the same thing.

### 1. Working Memory — in-process, volatile

Keep only the current task state in the active context. This is not stored anywhere — it's in LangGraph state, tool state, or in-process variables for the current execution.

- Store only: current goal, active plan, most recent tool results, the last 3-5 exchanges
- Clear aggressively on session end — this is the RAM, not the hard drive
- Use structured state (not raw message dumps) so the agent can reason about what's there

### 2. Episodic Memory — session summaries, stored externally

Capture what happened in each session without storing every message. A summary of decisions made, outcomes reached, and open threads — stored in a vector store with session metadata (date, user, task type).

- After each session: run a consolidation step that extracts key facts, decisions, and outcomes from the raw conversation
- Store structured summaries (not raw transcripts) — reduces ~9,000 tokens/session to ~500 tokens/session
- Retrieve by semantic similarity to the current task, not by recency alone

### 3. Semantic Memory — extracted facts about the user and world

Parse episodic summaries and ongoing interactions into a relational or graph store of facts: user preferences, known constraints, prior projects, stated goals. This is what the agent uses to feel like it "knows" the user.

- Extract at session close, not at query time — avoids repeated LLM overhead
- Store in a schema: `(entity, attribute, value, confidence, source_session)`
- Retrieve by entity + relevance, not by embedding similarity alone — keyword + vector hybrid wins

### 4. Procedural Memory — learned routines, not remembered facts

Capture *how* to do things, not *what* happened. Successful trajectories become reusable patterns: the right sequence of tool calls for a task type, the validation checks that caught failures, the policy steps that avoided violations.

- Microsoft Foundry (June 2026) surfaces this from trajectory analysis: ingest agent runs, identify successful patterns, extract "when to use" + "what to do" items
- Store in versioned documents (git or DB) — update when the procedure changes, not when a conversation happens
- Retrieve by intent + role classification, not by topic similarity

### 5. The retrieval layer — memory at query time

Memory exists only when it surfaces. Use a two-stage retrieval: (1) semantic search against episodic + semantic stores, (2) rerank by relevance to the current task. Inject only the top-K most relevant items — not everything that matched.

- Lazy loading beats eager loading: fetch memory on first turn, not at session start
- BM25 + vector hybrid retrieval outperforms either alone (agentmemory benchmark, 95.2% R@5)
- Budget tokens for memory injection — track it, cap it, price it per user

## Evidence

- **arXiv (Mem0, April 2025):** Introduces Mem0 as a scalable memory-centric architecture that dynamically extracts, consolidates, and retrieves salient information from conversations — addressing the fixed-context-window problem as a memory engineering problem, not a model problem. Validated on LOCOMO benchmark. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)
- **GitHub / HN (agentmemory, 25,509 stars):** Open-source persistent memory for coding agents with a pipeline that deduplicates observations, strips secrets, compresses to structured facts, and indexes in BM25 + vector + graph. Reports 92% fewer input tokens per session vs. naive context stuffing, 95.2% R@5 on LongMemEval-S. Cross-agent via MCP + REST. — [github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **HN Show HN (hmem, 2025):** MCP server for hierarchical persistent memory in a local SQLite file. Identifies "context dilution" as the primary failure mode — context window compression silently drops earlier decisions without error — and "vendor lock-in" as secondary. Solves cross-tool portability. — [HN #47103237](https://news.ycombinator.com/item?id=47103237)
- **Microsoft Foundry Blog (June 2026):** Enterprise memory update introducing procedural memory extraction from agent trajectories. Analyzes successful and failed runs to build "when to use" + "what to do" knowledge — directly addressing the pattern where agents know facts but skip correct procedures. — [devblogs.microsoft.com/foundry/memory-build2026](https://devblogs.microsoft.com/foundry/memory-build2026)
- **Remery Blog / Synthara (2025):** Production pattern analysis showing three-tier memory with per-user quotas to prevent unbounded growth. Synthara's four-tier breakdown (working/episodic/semantic/procedural) cross-validates with Mem0's architecture and Microsoft Foundry's procedural extraction. — [remery.ai/blog](https://remery.ai/blog/agent-memory-architecture-persistent-context-systems) | [syntharatechnologies.com/blog](https://www.syntharatechnologies.com/blog/agent-memory-architectures)

## Gotchas

- **"Store everything" doesn't scale.** Naive message dumping costs ~9,000 tokens/session and degrades retrieval. Always consolidate to structured summaries before storing.
- **Retrieval quality is the real bottleneck.** A full vector store of memories is not better than an empty one if retrieval returns irrelevant results. Invest in retrieval architecture (hybrid BM25+vector, reranking) as much as storage.
- **Context dilution is silent.** The agent doesn't know it forgot — it keeps acting confidently on incomplete context. Build explicit memory audits: log what was injected at each turn, compare against what was retrieved.
- **Procedural memory is the most neglected tier.** Most teams build episodic + semantic and stop. But agents that know facts but execute wrong procedures are a distinct failure mode — address it with trajectory analysis and pattern extraction.
- **Cross-session continuity breaks at tool boundaries.** The agent that works in Claude Code loses all memory in Cursor. Use MCP-based or REST-based memory servers that survive tool and machine transitions.
