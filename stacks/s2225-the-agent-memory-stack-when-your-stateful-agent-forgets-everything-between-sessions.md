# S-2225 · The Agent Memory Stack — When Your Stateful Agent Forgets Everything Between Sessions

Your agent just spent 40 minutes traversing a codebase, identifying 18 files that need refactoring, and building a coherent plan. Then it hits a token limit, crashes, or the user closes the session. On next launch: blank slate. No memory of the codebase, no record of the 18 files, no idea where it left off. This is the default state of every LLM agent. The memory stack is what fixes it.

## Forces

- **Stateless by design vs. persistent by necessity.** LLMs are stateless functions. Every invocation starts from zero. But production agents need to remember user preferences, work-in-progress state, prior decisions, and accumulated knowledge across weeks of operation.
- **Context window vs. cumulative history.** Every fact you inject into the prompt costs tokens. Long-running agents accumulate history faster than their context windows can hold it — and naive retrieval shoves everything in, burning tokens on repeated context.
- **Complexity vs. practicality.** Letta's own benchmarks show a plain filesystem scoring **74% on memory tasks**, beating specialized vector-store libraries. Yet the moment you need cross-session continuity, multi-agent shared state, or crash recovery, you need something purpose-built.
- **The storing-doesn't-understand problem.** In conventional memory pipelines, the system that stores knowledge (chunking + embedding pipeline) is disconnected from the system that uses it (the LLM). They optimize for different things. The retrieval failure mode is a semantic mismatch: the agent stores a nuanced finding, the pipeline chunks it differently, and the next retrieval returns a tangentially related fragment.
- **Token economics.** Context retrieval alone consumes **30–40% of agent context windows** (Parcle, 2026). Full retrieval pipelines (embed + rerank + LLM) cost **$0.002–0.01 per query** at low volume, scaling to thousands per month at enterprise scale. Teams consistently underestimate this by 5–30x.

## The Move

**Build a layered memory architecture that separates retrieval urgency from storage permanence.**

### 1. Separate working memory from long-term memory

Working memory (short-term, within-session) stays in fast storage — a JSON state object, SQL table, or in-process dictionary. Long-term memory lives in a persistent store — vector database, knowledge graph, or flat files. The agent decides which layer to read from based on task stage, not session age.

### 2. Use Tulving's taxonomy as your schema

Three proven memory types map directly to production needs:

- **Episodic memory** — vector-indexed interaction history. Stores what happened, when, and in what sequence. Enables "as I mentioned before" recall.
- **Semantic memory** — structured knowledge base. Stores facts, preferences, and ground truth. Enables "the user prefers this API style."
- **Procedural memory** — stored agent behaviors and skills. The agent improves at tasks over time by recording what worked.

Additional layers practitioners add: **tool memory** (which tools succeed in which contexts), **entity memory** (user/org/project facts), and **summary memory** (compressed versions of long conversations).

### 3. Implement the "reflect" pattern at session boundaries

Before a session ends, run a reflection pass: the agent reads recent interactions and writes condensed summaries, extracted facts, and updated preferences back to long-term memory. This is the single most validated improvement pattern — implemented by Claude Diary, fsck.com's episodic memory, claude-mem, and Letta's server-side reflection.

### 4. Deduplicate context before retrieval

The dominant token waste in agentic systems is repeated context — the model re-reading the same facts, tool schemas, and conversation history across turns. Parcle (2026) cut **>60% of tokens from agentic tasks** through context deduplication alone. The pattern: maintain a canonical context store, compute diffs against what's already been injected, and only retrieve deltas.

### 5. Store memories as human-readable markdown

ByteRover (ByteDance, April 2026) argues for abandoning vector stores entirely in favor of LLM-curated markdown files. The same LLM that stores knowledge also reads and curates it — eliminating the semantic mismatch where the storing system doesn't understand what it stores. This approach scores competitively on memory benchmarks while eliminating an entire infrastructure dependency.

### 6. Use hybrid search for episodic recall

Single-hop retrieval (vector similarity) misses temporal relationships. Combine embedding similarity with BM25 full-text search and temporal ranking (recency × strength). Formative Memory models this as memory strength that increases with use and decays with disuse — unused memories fade, nightly consolidation prunes and merges them.

### 7. Plan for crash recovery from day one

Store a serialized state checkpoint alongside every memory write. On restart, the agent reconstructs its position from the checkpoint, queries memory for surrounding context, and resumes mid-task rather than re-executing from scratch. The agentmemo.ai blog (2026) documents a code review agent that wasted $5 in API calls re-reviewing 50 files after a crash — a problem checkpointed memory would have eliminated.

## Evidence

- **HN Ask Thread:** Practitioners overwhelmingly build custom memory layers on top of lightweight orchestrators. One respondent's multi-agent CRM pipeline manages state across conversations using a custom SQL-based solution because "there's absolute 0 framework out there that's good enough for serious work." — [HN: Multi-agent orchestration in production](https://news.ycombinator.com/item?id=47660705) | June 2026

- **Research paper:** ByteRover (ByteDance, April 2026) demonstrates that conventional memory-augmented generation fails through three critical failure modes: semantic fragmentation (embedding pipeline chunks knowledge differently than the LLM expects), lost coordination context (multi-agent memory stores data but not reasoning provenance), and recovery fragility (post-crash reconstruction requires the agent to infer state from disconnected fragments). Their solution: agent-native markdown storage with LLM-curated hierarchical context. — [ByteRover: Agent-Native Memory (arXiv:2604.01599)](https://arxiv.org/pdf/2604.01599v1)

- **Benchmarks:** Mem0's State of AI Agent Memory report (2026) shows the field standardized on three benchmarks — LoCoMo (1,540 questions), LongMemEval (500 questions), BEAM — with current top scores at 92.5 LoCoMo and 94.4 LongMemEval at ~6,900 tokens per query. Temporal reasoning (+29.6 points) and multi-hop reasoning (+23.1 points) are the biggest recent gains. The report covers 21 integrated frameworks and 20 vector stores. — [Mem0: State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)

- **Show HN:** Parcle cut >60% of tokens from agentic tasks via context deduplication, showing that the hidden cost in most AI budgets is not inference — it's retrieval overhead. Context caching and delta-only retrieval reduced agent costs by 70% in their benchmarks. — [HN: Context deduplication in agentic systems](https://news.ycombinator.com/item?id=48580512) | July 2026

- **Production comparison:** AI Workflow Lab's Mem0 vs. Letta vs. Zep comparison (2026) surfaces the managed vs. self-hosted tradeoff. Mem0 uses async writes and LLM-guided fact extraction, Letta runs as a stateful server with reflection endpoints, Zep specializes in temporal reasoning over conversation history. — [AI Workflow Lab: Agent Memory Compared](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)

- **GitHub repo:** agent-memory (srinivasraom) implements seven memory types across PostgreSQL + pgvector, with progressive lessons from simple conversational memory to complete memory-aware agent loops. — [Agent Memory: PostgreSQL + pgvector architecture](https://github.com/srinivasraom/agent_memory)

- **GitHub repo:** Engram (tstockham96) — open-source universal memory layer using local SQLite + spreading activation retrieval, benchmarks on LoCoMo showing competitive performance without vector store dependencies. — [Engram: Universal Memory Layer](https://github.com/tstockham96/engram)

- **GitHub repo:** Formative Memory (jarimustonen) — memory plugin for OpenClaw agents that models biological decay: memories strengthen through use, fade when unused, nightly consolidation prunes and merges. — [Formative Memory: Strength-based memory decay](https://github.com/jarimustonen/formative-memory)

## Gotchas

- **Vector stores solve retrieval but create semantic drift.** Embedding pipelines chunk and index knowledge in ways the LLM doesn't control. The agent stores a nuanced insight; retrieval returns a tangentially related fragment. ByteRover's diagnosis: "the system that stores knowledge does not understand it." Plain markdown files scored 74% on Letta's memory benchmarks — beating several vector-store approaches.
- **Memory staleness is an unsolved problem.** "User lives in Berlin" becomes false when they move. Vector similarity returns both old and new facts with equal confidence. No standard solution exists; Mem0's 2026 benchmark report flags cross-session identity, temporal abstraction at scale, and memory staleness as the three hardest open problems.
- **You will underestimate token costs.** Context retrieval consumes 30–40% of context windows per turn. Teams report actual costs running 5–30x initial estimates. Budget for retrieval infrastructure, not just inference.
- **The "reflect" pattern is cheap to implement and widely validated.** Don't skip it. Session-end summarization and fact extraction is the single lowest-effort, highest-impact improvement to long-term memory quality. The gap between agents with and without reflection is substantial and consistent across frameworks.
- **Multi-agent shared memory is not the same as single-agent memory.** Agent A stores a finding with reasoning and rationale. Agent B retrieves the data but lacks the why. Shared memory stores data — it does not transfer the understanding that produced it. Coordinate provenance alongside content.
