# S-2356 · The Memory Tier Stack — When Your Agent Knows Nothing About Yesterday

Every Claude Code session starts from zero. It doesn't remember the bug you debugged yesterday, the architecture decision you made last week, or the preference you corrected on Thursday. This is not a model limitation — the model is stateless by design. It is an architecture problem: the persistence layer sits outside the model, and teams that skip it pay in repeated onboarding cost, degraded cross-session reasoning, and agents that feel expensive instead of compounding.

## Forces

- **The context window is finite; the task horizon is not.** Agents need to hold scratch-pad state during a task (working memory) and durable state across sessions, days, and users (long-term memory). Most frameworks conflate these, and both suffer.
- **Naive RAG hits a recall ceiling.** Storing conversation chunks and retrieving them semantically produces noisy results. Production teams report that extracted-fact and graph-based memory outperform naive chunk-based RAG on memory benchmarks by 20–40 percentage points.
- **Facts decay; context doesn't know that.** A user's address, team structure, or project status changes. Pure vector search returns both the old and new fact with equal confidence unless the memory layer reconciles them. Validity windows and temporal reasoning are the gap.
- **The four memory types need four storage strategies.** Cognitive science splits memory into working (scratchpad), episodic (events), semantic (facts), and procedural (skills). Each has different access patterns, decay policies, and retrieval latencies. One vector store does not serve all four well.

## The Move

The production-ready memory stack has three tiers, applied in sequence:

- **Tier 1 — Working memory (in-context).** The conversation buffer and any scratchpad state the agent uses during task execution. No persistence needed; this lives in the context window. Cost: tokens. Latency: zero.
- **Tier 2 — Semantic retrieval (vector + fact extraction).** Once you have a knowledge base worth querying, add semantic retrieval over extracted facts — not raw conversation chunks. Frameworks like Mem0 handle fact extraction and embedding in one step. Use when: the agent needs to answer "what did we decide about X?" across sessions.
- **Tier 3 — Episodic long-term memory (temporal graph).** When cross-session personalization matters — user preferences, project state, evolving facts — add a temporal knowledge graph with validity windows. Zep's Graphiti tracks how facts change over time. Letta exposes explicit memory tiers (core vs. archival). Use when: "what was true in Q1?" or "what did the user correct last time?" matters.

The vector database hierarchy is settled: **Qdrant for 2–49 agents** (hot path, latency-sensitive), **Weaviate for 50+ agents** (tool registry, complex queries), **pgvector for under-10M vectors** (Postgres shops), **Chroma for prototypes only** (not production-grade).

## Evidence

- **Benchmark research:** Three benchmarks now define the measurement landscape — LoCoMo (1,540 questions, multi-session), LongMemEval (500 questions, six categories including temporal reasoning and knowledge update), and BEAM (1M–10M token scale, tests what memory systems do when context far exceeds typical benchmarks). Mem0 scores 92.5 on LoCoMo and 94.4 on LongMemEval. The hardest open problems identified across all three: cross-session identity, temporal abstraction at scale, and memory staleness detection.
  — *Mem0 State of AI Agent Memory 2026 report* — https://mem0.ai/blog/state-of-ai-agent-memory-2026
  — *Mem0 arXiv paper (Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory)* — https://arxiv.org/html/2504.19413v1

- **Three-layer memory architecture (HN):** An engineering team published their production design: working memory in the context window, episodic memory storing significant events with timestamps, and semantic memory for project-specific facts and conventions. They noted that Anthropic's agent-harness research confirmed agents declaring victory prematurely and verbose logging were both symptoms of missing episodic recall — the agent had no memory of what failed last time.
  — *Hacker News — "A three-layer memory architecture for long-running agents"* — https://news.ycombinator.com/item?id=46097759

- **Cross-session memory for coding agents:** agentmemory (4,800+ GitHub stars, v0.9.24 as of May 2026) provides a local memory server for Claude Code, Cursor, Codex, and other coding agents. It captures observations, indexes them with BM25 + vector + graph search, and uses Reciprocal Rank Fusion to merge ranked results. Benchmarks show R@5 = 95.2% recall rate, ~1,900 tokens/session average usage, and ~$10/year token cost. The architecture distinguishes itself from static instruction files (CLAUDE.md, .cursorrules) by recording session events and retrieving relevant prior context dynamically.
  — *4sAPI Blog — "How to Fix Claude Code & Cursor Memory Loss with agentmemory"* — https://blog.4sapi.com/blog/agentmemory-claude-code-cursor-memory
  — *Agentpedia — "Agentmemory Deep Dive"* — https://agentpedia.codes/blog/agentmemory-persistent-memory-ai-coding-agents
  — *GitHub: rohitg00/agentmemory* — https://github.com/rohitg00/agentmemory

- **Framework comparison (3 sources converge):** Mem0 leads on ecosystem size and AWS Agent SDK partnership. Zep/Graphiti is the strongest temporal engine with validity windows on facts — the right choice when fact evolution over time is a first-class concern. Letta exposes agent-managed tiered memory (core vs. archival) descended from MemGPT research — the right choice when you want the agent itself to decide what to remember and what to archive.
  — *AgenticWire — "Mem0 vs Zep vs Letta: Agent Memory Compared (2026)"* — https://www.agenticwire.news/article/mem0-zep-letta-agent-memory
  — *AI Workflow Lab — "Mem0 vs Letta vs Zep: Agent Memory for Production AI Agents (2026)"* — https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026
  — *CallSphere — "Mem0 vs Zep vs Letta: Honest Memory-Layer Comparison for 2026"* — https://callsphere.ai/blog/td30-fw-mem0-vs-zep-vs-letta-2026-honest-comparison-guide

## Gotchas

- **Naive conversation-chunk RAG degrades badly at scale.** Storing raw conversation history and retrieving it semantically produces high-recall but low-precision results. The agent gets back everything about "authentication" including three failed attempts, two tangents, and one unrelated discussion. Extract facts, not chunks.
- **Static instruction files (CLAUDE.md, .cursorrules) are not memory.** They are a ceiling, not a foundation — a 200-line cap, manual maintenance required, single-tool only. They don't record session events, don't support dynamic retrieval, and don't learn from corrections. Teams using them as a substitute for a real memory layer are patching the symptom.
- **Fact staleness is the silent accuracy killer.** Without validity windows or temporal reasoning, your agent will confidently assert that the user still lives in their old city, uses their old team structure, and follows their old coding style. The vector store has no mechanism to distinguish "current" from "historical" unless you build it.
- **Memory fragmentation across tools.** Most teams use multiple agents or coding assistants (Claude Code for terminal, Cursor for IDE). Without a shared memory store, each tool re-learns the same preferences independently. agentmemory and OpenMemory address this; if your stack is multi-tool, prioritize a shared memory backend over tool-specific memory.
