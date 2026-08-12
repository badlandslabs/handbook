# S-2536 · The Three-Tier Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent held a great conversation with Alice on Monday. On Tuesday it greets her like a stranger. On Wednesday it asks her name again. The model did not forget — the system did. Every session starts from a blank context window. The agent's history exists, but nothing in the architecture retrieves it, prioritizes it, or resolves conflicts across it. This is the memory architecture problem: agents that accumulate knowledge in theory but operate stateless in practice.

## Forces

- **Context vs. memory** — long context windows (1M tokens) do not solve memory; they just delay the problem. Models still suffer "lost in the middle" and premium pricing kicks in past 200K tokens
- **Latency vs. completeness** — hot-path memory updates add per-turn latency; background consolidation is async but risks stale retrievals
- **Storage vs. retrieval** — memory that cannot be retrieved efficiently might as well not exist. Raw conversation buffers are not a memory system
- **Generic vs. domain** — a general-purpose memory layer and a domain-specific knowledge graph serve fundamentally different retrieval needs
- **Multi-tenant vs. per-user** — shared memory stores leak cross-user context; per-user isolation adds infrastructure cost and compliance burden

## The move

The three-tier memory architecture mirrors cognitive science (Tulving 1972, now canonical in AI) and maps to production storage tiers with distinct latency, cost, and retrieval profiles:

- **Working memory (hot)** — the LLM context window itself. Stores active task state, recent conversation turns, and in-flight reasoning. Zero persistence cost but zero continuity. Retrieved by position (always available, always expensive to grow)
- **Episodic memory (warm)** — what happened and when. Stored in Redis, Weaviate, or pgvector. Timestamped event records with temporal ordering. Enables "remember what we discussed last week" queries. Retrieval: semantic similarity + time weighting
- **Semantic memory (cold)** — facts and relationships the agent has abstracted from events. Stored in graph databases (Neo4j, Graphiti) or structured KB stores. Entities and their relationships, independent of when they were learned. Enables "what are Alice's preferences" queries
- **Procedural memory (cold)** — how to do things. Stored as code, workflows, or skill definitions. Tool definitions, prompt templates, agent behaviors. Enables "what should I do when X happens"

**Memory consolidation**: background process runs during or after sessions, extracting facts from episodic records into semantic nodes, and surfacing procedural patterns. Mem0 calls this "dynamic extraction, consolidation, and retrieval." Letta calls it "sleep-time compute" — agents reason about context during idle time.

**Retrieval strategy**: on each agent turn, query all three memory tiers with the current context as the query vector. Rank and merge results. The Mem0 arXiv paper (2504.19413) shows graph-based memory (Mem0^g) outperforms dense natural-language memory by ~2% on overall scores; the 2026 Mem0 benchmarks report 92.5% on LoCoMo and 94.4% on LongMemEval.

**Hot vs. cold trade-off**: Letta benchmarks showed a plain filesystem scored 74% on memory tasks, beating some specialized vector-store libraries. Mem0 achieves <7,000 tokens per retrieval vs. 25,000+ for full-context, reducing latency by up to 90% versus passing all history.

## Evidence

- **arXiv paper:** Mem0 (Chhikara et al. 2025, arXiv:2504.19413) — introduces dense + graph memory architectures; reports 26% relative improvement over OpenAI on LLM-as-Judge metric; Mem0^g adds ~2% over base Mem0 — [https://arxiv.org/html/2504.19413v1](https://arxiv.org/html/2504.19413v1)

- **HN Show HN:** Hmem — persistent hierarchical memory for AI coding agents via MCP; solves context dilution (earlier decisions silently pushed out of context window in long sessions) and vendor/machine lock-in (switching from Claude Code to Cursor erases session memory). Beta, MIT license — [https://news.ycombinator.com/item?id=47103237](https://news.ycombinator.com/item?id=47103237)

- **Letta (formerly MemGPT):** 24,211 GitHub stars; agent memory benchmarked #1 model-agnostic agent on Terminal-Bench. Their "Context Repositories" concept (Feb 2026) rebuilds memory around git-based versioning and programmatic context management. "Sleep-time compute" (Apr 2025) lets agents reason during idle time. Memory-first RL is active research direction — [https://www.letta.com/blog](https://www.letta.com/blog)

- **Comparison analysis:** 2026 comparison (innobu.com) — Zep scores 63.8% vs Mem0's 49.0% on LongMemEval direct comparison; Mem0 leads on LoCoMo (92.5%). Key differentiator: Zep optimized for latency reduction (<7K tokens/retrieval), Mem0 for benchmark scores and integration breadth (21 frameworks, 20 vector stores) — [https://www.innobu.com/en/articles/agent-memory-2026-mem0-letta-zep-hermes-openclaude-comparison.html](https://www.innobu.com/en/articles/agent-memory-2026-mem0-letta-zep-hermes-openclaude-comparison.html)

## Gotchas

- **Storing is not remembering** — adding records to a vector DB is not a memory system. You need a retrieval strategy, a ranking function, and a consolidation process. Without them the store is a graveyard
- **In-the-hot-path vs. background consolidation** — hot-path updates (like ChatGPT's approach) introduce latency and couple memory logic to agent logic. Background consolidation (Letta, LangGraph async) is cheaper but risks stale memory until the next consolidation run. Choose based on latency tolerance
- **Cross-session identity** — the hardest open problem in agent memory (per Mem0's 2026 benchmark report). Knowing that two facts refer to the same person across sessions requires entity resolution the architecture must explicitly handle; it does not happen automatically from vector similarity
- **GDPR and user control** — per-tenant isolation, explicit user inspection/editing/deletion, and retention policies are not optional in production. Many "demos" of agent memory have no retention controls; evaluate accordingly
