# S-2419 · The Context Sink Stack — When Your Agent Asks the Same Question Twice

Your agent ran 47 customer sessions last week. In 41 of them, it asked the user to re-explain something it had already learned in a previous session. The model has a 200K-token context window. It also has zero memory. Every session starts from scratch. This is the context sink: information goes in, competence comes out, and nothing persists.

## Forces

- **Context windows are finite and expensive.** A 200K-token window sounds large until your agent needs 80K tokens of domain knowledge, 40K of conversation history, and 60K of retrieved documents. Attention is also O(n²) — long contexts are slow.
- **Retrieval adds latency but cuts cost.** Mem0 benchmarks show 91% latency reduction vs full-context (17.4s p95 → 1.4s) at only a 5% accuracy drop on LoCoMo. The trade-off is real but favorable.
- **Write quality determines retrieval quality.** The memory write is not a pass-through. Bad extraction → bad retrieval → bad context → bad output. The agent "forgets" because the write phase failed, not the read phase.
- **Simpler beats sophisticated for most teams.** Letta's own benchmarks: a plain filesystem scores **74% on memory tasks**, beating specialized vector-store libraries. Complexity is the enemy of correctness.
- **Memory types have different retrieval profiles.** Working memory needs sub-millisecond access. Episodic memory needs temporal-aware retrieval. Semantic memory needs similarity search. One storage backend rarely serves all three well.

## The Move

Implement a **three-tier memory architecture** that matches retrieval latency and cost to memory type.

**Tier 1 — Working memory (hot path):**
- Store the last N messages and current session state in a fast KV store (Redis, SQLite, or in-process dict)
- Load at session start; always in context
- Zero retrieval latency; zero retrieval cost
- Prune aggressively — if it wasn't used in the last 3 turns, drop it

**Tier 2 — Episodic + semantic memory (warm path):**
- Store conversation summaries, extracted facts, and user preferences
- Use a purpose-built memory layer (Mem0, Zep, or Letta) with a vector store backend
- Retrieval target: top 6–10 most relevant memories per query, re-ranked by recency × relevance
- Budget ~6,000–10,000 tokens for retrieved memory in the context window
- Run a **reflection loop** at session end: prompt the agent to summarize what changed, what it learned, what to remember. This is the write half of the memory loop and it is the most-skipped step in production.

**Tier 3 — Procedural memory (cold path):**
- Store agent behavior patterns, tool-use heuristics, and system instructions in static files or a dedicated block
- Update infrequently; loaded at session start
- Examples: CLAUDE.md for Claude Code, system prompt fragments for behavior policies

**Storage backend selection:**
- 1–10 agents, <10M vectors → **pgvector** (Postgres extension, zero infra overhead)
- 2–49 agents → **Qdrant** (hot path optimized, sub-10ms recall)
- 50+ agents or need managed infra → **Weaviate** or **Pinecone**
- Temporal relationship tracking (fact validity windows, evolving entities) → **Zep/Graphiti** knowledge graph layer

**The memory write loop (non-negotiable):**
```
Every session end → agent reflection → extract new/changed facts →
deduplicate against existing memory → write to episodic store →
update semantic index → done
```
Do not skip the reflection step. Extracting facts from raw conversation is noisy; a model's self-summary is cleaner.

## Evidence

- **Mem0 production benchmark:** 91.6% accuracy on LoCoMo at 6,800 tokens/query with p95 latency of 1.4s — 91% faster than full-context retrieval at only 5% accuracy cost. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)

- **Zep temporal knowledge graph:** Graphiti-powered retrieval achieves 94.8% on Deep Memory Retrieval (DMR) benchmark vs MemGPT's 93.4%, with 90% lower latency. Three-tier graph: Episode subgraph (raw messages), Semantic subgraph (extracted entities/facts), Identity subgraph (entity relationships). — [arXiv:2501.13956](https://arxiv.org/html/2501.13956v1)

- **Letta filesystem baseline:** Plain filesystem scoring 74% on agent memory tasks, outperforming specialized vector-store libraries on simple retrieval. Demonstrates that retrieval pipeline quality matters more than storage sophistication. — [Letta Agent Memory Blog](https://www.letta.com/blog/agent-memory), citing Letta benchmarks (2025)

- **LangChain Agent Builder memory system:** Built on COALA (Cognitive Architectures for Language Agents) framework. Key insight: task-specific agents (email assistant, doc helper) benefit more from memory than general-purpose agents because the same task repeats across sessions. — [LangChain Blog: How We Built Agent Builder's Memory System](https://www.langchain.com/blog/how-we-built-agent-builders-memory-system), February 2026

- **6-layer memory taxonomy for coding agents:** Layer 1 (auto-memory at session start), Layer 2 (system instructions), Layer 3 (reflection loop at session end), Layer 4 (agent-defined memory), Layer 5 (RAG over project context), Layer 6 (synthetic memory synthesis). Layers 1–4 are production-validated; Layer 6 is research-grade. — [futhgar/agent-memory-architecture](https://github.com/futhgar/agent-memory-architecture), MIT license, created April 2026

- **Context window overflow as primary failure mode:** Quadratic attention scaling and "lost in the middle" degradation make full-context approaches non-viable beyond ~50K tokens. Context engineering (treating the window as a scarce resource) is now the standard discipline. — [Weaviate: Context Engineering](https://weaviate.io/blog/context-engineering), December 2025

## Gotchas

- **Dumping raw conversation history into context is not memory.** It is slow, expensive, and the model ignores the middle. This is not a memory strategy.
- **Vector similarity is not enough for episodic recall.** "What did we do in session 23?" requires temporal-aware retrieval, not semantic similarity. Naive vector search returns semantically-similar-but-temporally-irrelevant memories. Use Zep/Graphiti or add a temporal filter to your retrieval query.
- **Memory write deduplication is non-optional.** Without it, the same fact gets stored 50 times across sessions and retrieval noise overwhelms signal. Run a similarity check before every write.
- **Memory becomes an attack surface at scale.** Persistent memory poisoning (injecting false facts that get retrieved as trusted context) is a real risk. Mem0 and Zep both have teams working on this; if you're rolling your own, add a fact-verification step before writes.
- **The reflection loop is the most-skipped step in production.** Teams implement the retrieval side (reads work great in demos) and skip the write side (harder to demo, requires session-end processing). Without it, the memory store fills with raw noise and retrieval quality degrades over time.
- **Context window attention degrades in the middle.** Models attend less to information in the middle of long contexts ("lost in the middle" problem). Put the most important retrieved memories at the start or end of the context window, not sandwiched in the middle.
