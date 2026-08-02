# S-1995 · The Agent Memory Architecture Stack — When Your Agent Forgets Everything the Moment the Session Ends

*When your AI agent works perfectly in a demo — completes tasks, follows context, nails the nuances — and then the next day the user types "continue where we left off" and the agent has no idea who they are, what they were working on, or what it already tried. Every session starts from zero. Nothing compounds. You need a memory architecture.*

## Forces

- **Context windows are not memory.** A 1M-token context costs ~$3/call. At 100 users × 5 sessions/day, raw context replay hits $1,500/day in input tokens — before you factor in 80–120K token bloat within 2–3 weeks of production use.
- **Session boundaries destroy continuity.** Deployments crash in-memory context. Nightly restarts wipe state. Switching LLM providers loses everything. The agent "dies" at every boundary.
- **Retrieval degrades before the window fills.** "Needle in a haystack" tests show that embedding-based retrieval quality drops significantly before the context window is exhausted — naive vector search against a conversation log is not enough.
- **Three memory types compete for the same budget.** Episodic (what happened), semantic (what's true), and procedural (how to behave) each demand different storage, retrieval, and update strategies. Most teams pick one and wonder why the agent still forgets.

## The Move

Build a **four-tier memory architecture** inspired by cognitive science, with explicit retrieval rules per tier. This is not one database — it is a curation pipeline that decides what to store, where, and how to retrieve it at the right moment.

### The four tiers

- **Working memory** — Current task state held in the context window at runtime. Stored in-process (LangGraph state, etc.). Always in context. Zero retrieval latency. Evicted on session end. Budget: keep it under 8K tokens of actual task-relevant state, not conversation history.
- **Episodic memory** — Summarized past sessions. Stored in a vector database with rich metadata (timestamps, user IDs, outcome status). Retrieved by semantic similarity to the current query, then filtered by recency and relevance. Prune aggressively: keep summaries, not transcripts. A 6-month transcript is useless; a summary of "user rejected tender #4421 last week due to budget cap" is gold.
- **Semantic memory** — Extracted persistent facts about users, preferences, and world state. Stored in a relational schema or knowledge graph (not a vector store). Updated on explicit facts, not inferred. Retrieved by direct lookup. This is the "truth layer" — the agent queries it like a database, not a similarity search.
- **Procedural memory** — Learned behaviors, workflows, and behavioral rules. Stored as executable prompts, skill definitions (Anthropic `SKILL.md`), or policy files. Not retrieved dynamically — loaded at startup or on skill activation. This is how you encode "when debugging Python, always check import errors first."

### Retrieval discipline

Retrieve episodic memory by semantic similarity, then filter by recency (last 7 days > last 30 days > older). Retrieve semantic memory by structured lookup, not vector search. Procedural memory is not retrieved — it is loaded. Mixing retrieval strategies is the most common architectural mistake.

### Consolidation and forgetting

Run a nightly consolidation job that reads raw conversation logs, identifies worth-keeping facts and decisions, and promotes them to semantic memory. Apply forgetting curves: memories that haven't been accessed in 30 days get downgraded from episodic to archival. A December 2025 Tsinghua survey found that biologically-inspired consolidation (simulating sleep) produced Cohen's d = 2.31 improvement in agent task performance — 51.6% vs 49.1% task success on their benchmark.

### Cross-agent memory

For multi-agent systems, maintain a shared semantic memory store that all agents read from. Episodic memory stays per-agent (each agent has its own session history). Procedural memory is shared as skill libraries. This mirrors how Zep/Graphiti models agent-to-agent knowledge sharing.

## Evidence

- **Blog post (Abhishek Chauhan, engineer):** Documents the real cost problem — 100 users × 5 sessions/day × raw context replay = $1,500/day input token spend. Also describes the RevAgent case where sales reps were re-explaining pipeline context every session. Concludes external memory is the only production-viable path. — [abhishekchauhan.it/blog/agent-memory-mem0-zep-langmem-production](https://www.abhishekchauhan.it/blog/agent-memory-mem0-zep-langmem-production)
- **Engineering blog (Synthara Technologies, May 2026):** The four-tier taxonomy (working/episodic/semantic/procedural) with explicit storage and retrieval rules per tier. Key quote: *"A reasoner that starts from zero every turn is a chatbot. A reasoner with structured memory across the four tiers is something that compounds value with use."* — [syntharatechnologies.com/blog/agent-memory-architectures](https://www.syntharatechnologies.com/blog/agent-memory-architectures)
- **GitHub research repo (marc-shade/memory-consolidation, Nov 2025):** Sleep-inspired memory consolidation for AI agents. Benchmarks show 2.36 percentage-point improvement in task success (51.6% vs 49.1%) with large effect size (Cohen's d = 2.31, p = 0.007). Ablation studies show episodic consolidation is the primary driver. — [github.com/marc-shade/memory-consolidation](https://github.com/marc-shade/memory-consolidation)

## Gotchas

- **Vector search is not enough for semantic facts.** Storing "user prefers Python" as an embedding and retrieving it by similarity search will return it alongside semantically-similar-but-irrelevant facts. Semantic memory needs structured storage with direct lookup — a knowledge graph, relational schema, or at minimum a key-value store with typed fields.
- **Transcripts bloat, summaries compress.** Storing raw conversation logs in episodic memory is a storage and retrieval trap. Run extraction at session end: "what did we decide, what did we try that failed, what does the user care about next?" Store the summaries, not the logs.
- **Mem0's graph is Pro-tier only.** The 55K-star Mem0 open-source version uses semantic search only. Graph traversal (critical for cross-fact relationships like "user's company → project → rejection reason → budget constraint") is locked behind $249/month. Zep/Graphiti has graph as a core free feature with 63.8% on LongMemEval vs Mem0's 49.0%. Choose based on whether you need relationship traversal, not star count.
- **Context boundaries are not just sessions.** A model swap, a provider outage with a fallback model, a deployment that restarts the service — all wipe working memory. Design your memory architecture to survive process restarts, not just session ends. Persist working memory state to disk or a KV store at each tool call boundary.
