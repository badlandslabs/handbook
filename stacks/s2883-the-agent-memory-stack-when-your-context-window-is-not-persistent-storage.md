# S-2883 · The Agent Memory Stack — When Your Context Window Is Not Persistent Storage

Your agent works beautifully within a session. It reasons, retrieves facts, makes nuanced decisions. Then the session ends, the context clears, and the next session starts from zero — as if the last hour never happened. The user repeats themselves. The agent makes the same mistake. Nothing compounds. This is not a model problem. It is an infrastructure problem that no amount of model capacity will solve.

## Forces

- **Context is RAM, not a database.** A large context window gives the agent working memory — fast, zero-latency, fully accessible. But it evaporates at session end, costs more per token as it fills, and degrades under load ("lost in the middle" effects where information in the middle of long contexts gets ignored).
- **Retrieval is the hard part, not storage.** The community has converged on storage backends: SQLite for local/small-scale, PostgreSQL + pgvector for mid-scale (under 10M entries), Qdrant for production hot paths, Weaviate when managing 50+ agents, Pinecone for zero-ops managed. Storage is solved. The unsolved problem is what to retrieve, when, and how to avoid garbage-in-garbage-out.
- **Write quality determines retrieval quality.** The most common failure is treating memory as a dump — stuffing every conversation turn into a vector store and hoping retrieval works. It doesn't. Without write gates (what to store, what to merge, what to discard), memory becomes noise that degrades downstream reasoning.
- **Active forgetting matters as much as remembering.** Biological memory doesn't just store — it consolidates, prunes, and strengthens. Systems like MemForge and Formative Memory model this with decay, sleep cycles, and use-frequency weighting. Teams that only add memory without pruning end up with agents that know too much irrelevant detail.

## The Move

Build a purpose-built persistent memory layer between the LLM and the rest of the stack. Treat it as the third production infrastructure layer — after tool access (MCP) and observability.

**Core architecture (four memory types):**
- **Working memory** — the context window. Fast, ephemeral, zero persistence. Use it for in-session reasoning, not long-term storage.
- **Episodic memory** — what happened: past conversations, completed tasks, prior decisions. Enables the agent to "pick up where it left off." Format as structured events with timestamps, not raw transcript dumps.
- **Semantic memory** — extracted facts, preferences, and knowledge. Persists across sessions in a retrievable form. Requires a write gate: extract, not just store. Requires a retrieval layer: semantic search (embeddings) + optionally a knowledge graph for relationships.
- **Procedural memory** — how to do things: reusable task patterns, skills, agent-generated procedures. Auto-generated from repeated successful task patterns. This is what turns "has done this before" into "knows how to do this efficiently."

**Storage backend selection:**
- Local / single-user: SQLite (OpenMemory) — zero setup, works offline, portable
- Small-to-mid scale (< 10M entries), existing Postgres: pgvector — no new infra
- Production hot path: Qdrant — default choice in the Mem0/Letta/Zep ecosystem
- 50+ concurrent agents: Weaviate — better multi-tenant isolation
- Zero-ops / managed: Pinecone — pays with vendor lock-in for operational simplicity

**Retrieval pattern (vs. full context re-load):**
- Semantic search (vector) for topic-relevant memories
- Optionally: knowledge graph traversal for related entities
- Hybrid: recency weighting + importance scoring + relevance
- Target: under 10K tokens per retrieval round — full context reload wastes tokens and latency

**Memory maintenance:**
- Write gate: extract structured facts from raw conversation, don't just dump transcripts
- Consolidation/sleep cycles: periodically merge redundant memories, prune stale entries, strengthen frequently-used ones
- Point-in-time queries: "what was true on date X?" — essential for debugging agent behavior over time

## Evidence

- **Mem0 GitHub README:** Universal memory layer for AI agents, 63,589 stars. New memory algorithm (April 2026) achieves 92.5% on LoCoMo and 94.4% on LongMemEval with 6,700–6,900 tokens per retrieval — versus 25,000+ for full-context reload. Supports SQLite, Qdrant, Weaviate, Pinecone, pgvector, Chroma as backends. — [GitHub: mem0ai/mem0](https://github.com/mem0ai/mem0)
- **OpenMemory GitHub (CaviraOSS):** Local-first memory store for LLM agents, 4,445 stars, Apache-2.0. Differentiates from vector DB/RAG by understanding memory *types* (fact, event, preference, feeling), tracking recency and importance, and supporting point-in-time queries. SQLite backend with Python + Node SDKs. HN thread (48 points): community reaction split between fans (privacy, offline, modular) and skeptics ("just use Redis"). — [GitHub: CaviraOSS/OpenMemory](https://github.com/CaviraOSS/OpenMemory)
- **Perea.ai Research "Agent Memory in Production" (May 2026):** Converged landscape: 4 memory types (working/episodic/semantic/procedural), 4 frameworks (Mem0, Zep/Graphiti, Letta, LangMem), benchmarked vector DB hierarchy (Qdrant > Weaviate > pgvector > Pinecone). Key insight: "Adopting a framework is buying its opinions — storage substrate vs. framework, each picks an episode shape, write gate, retrieval blend, tier policy, and tenant model." — [perea.ai Research](https://www.perea.ai/research/agent-memory-production)
- **Formative Memory (GitHub, OpenClaw plugin):** Memories strengthen through use, fade when unused, consolidate overnight. Implements biological analogy: recall → evaluate → capture → consolidate cycle. Retrieval uses hybrid search (embedding + BM25). — [GitHub: jarimustonen/formative-memory](https://github.com/jarimustonen/formative-memory)

## Gotchas

- **Don't store transcripts, store extracted facts.** Raw conversation dumps create retrieval noise. The write pipeline should extract structured facts, preferences, and events — then discard the transcript.
- **Don't skip the write gate.** Without filtering, memory grows unbounded and retrieval relevance drops. Every framework that works in production has an opinionated write pipeline.
- **Don't confuse context window with memory.** Even a 200K context window doesn't solve cross-session persistence. The moment the session ends, it's gone — regardless of size.
- **Benchmark scores are on managed platforms.** Mem0's 94.4% LongMemEval is on their managed platform with proprietary optimizations. Open-source results may differ significantly.
- **Framework lock-in is real.** Each memory framework imposes its own episode schema, retrieval contract, and storage format. Switching later is expensive — choose based on your compliance and portability requirements, not just benchmark scores.
