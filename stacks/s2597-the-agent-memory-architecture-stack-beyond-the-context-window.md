# S-2597 · The Agent Memory Architecture Stack — Beyond the Context Window

Agents that start from scratch every conversation are not agents — they are expensive chatbots. Memory architecture is what separates a system that compounds value over time from one that forgets everything useful between turns.

## Forces

- **Context windows are not memory.** A 1M-token context is a buffer, not a memory system. LLMs suffer from "Lost in the Middle" degradation even within advertised limits, and cost scales non-linearly with context length. Retrieval from a memory store at 6–7K tokens outperforms full-context at 1M tokens on benchmarks. Source: [Mem0 research, arXiv:2504.19413](https://arxiv.org/html/2504.19413v1)
- **What to remember, what to forget, and when to retrieve are three separate decisions.** Most teams collapse these into one, usually by stuffing everything.
- **Storage tier and retrieval strategy must co-evolve.** A vector store bolted onto a stateless LLM without a retrieval routing layer creates more noise than signal.

## The Move

Build a four-tier memory architecture. Each tier has a distinct storage, retrieval rule, and lifecycle.

### The Four Tiers

| Tier | What it stores | Where it lives | How it's retrieved |
|------|---------------|----------------|-------------------|
| **Working** | Current session state — active task, recent tool calls, intermediate outputs | In-process / LangGraph state | Always in context; token budget managed by the orchestrator |
| **Episodic** | Past sessions — what was asked, answered, tried, and the outcome | Vector store + metadata index (Qdrant, Weaviate, pgvector) | Similarity search against current query; time-weighted |
| **Semantic** | Decontextualized facts extracted from episodes — user preferences, product facts, world knowledge | Knowledge graph or structured DB (Neo4j, PostgreSQL, TiDB) | Entity lookup + relevance scoring |
| **Procedural** | Learned routines, system prompts, agent policies, tool definitions | Versioned documents (git, DB, or static config) | Intent + role matching at session start |

### Retrieval Rules That Actually Work

- **Always route before retrieving.** Don't retrieve unless the current query has a memory-shaped signal. Spurious retrieval creates hallucinated recall.
- **Single-pass retrieval wins.** Mem0's updated algorithm (April 2026) achieves 92.5 on LoCoMo / 94.4 on LongMemEval with one retrieval call at 6–7K tokens — no agentic loop. Source: [Mem0 GitHub benchmarks](https://github.com/mem0ai/mem0)
- **Recency and salience decay.** Episodic entries should age out or get down-ranked. A conversation from 18 months ago is rarely relevant to today's task.
- **Semantic consolidation.** Extract facts from episodic records and store them as structured entities. "User prefers dark mode" should be a fact, not buried in a 40-message thread.

### Storage Backend by Tier

- **Hot path (working):** In-process dict or LangGraph state — no persistence needed within a session.
- **Episodic (vector):** Qdrant for sub-10M vectors with latency requirements; pgvector for under-10M vectors and teams already on Postgres; Pinecone for fully-managed at scale. Source: [Perea.ai, Agent Memory in Production, 2026](https://www.perea.ai/research/agent-memory-production)
- **Semantic (knowledge graph / relational):** Neo4j for complex relationship traversal; PostgreSQL for simpler entity-attribute-value; TiDB (distributed SQL + HTAP + vector) for unified approach. Source: [PingCAP, Best Database for AI Agents 2026](https://www.pingcap.com/compare/best-database-for-ai-agents/)
- **Procedural:** Git-tracked YAML/JSON files for tool definitions and agent policies; loaded at session init.

## Evidence

- **Academic:** The Mem0 paper (arXiv:2504.19413, April 2025) formalizes the three-tier episodic/semantic/procedural taxonomy and demonstrates that full-context reasoning at 1M tokens is 26% worse on LOCOMO benchmark than their retrieval approach using 7K tokens. Open-sourced at [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0).
- **Industry survey:** A systematic review of agentic AI frameworks (arXiv:2508.10146, August 2025) maps memory management across LangChain, LangGraph, AutoGen, CrewAI, Semantic Kernel, Agno, and Google ADK — noting that LangChain/LangGraph lead on memory integrations but CrewAI and Agno have simpler defaults. Source: [arXiv:2508.10146](https://arxiv.org/html/2508.10146v1)
- **Practitioner analysis:** Perea.ai's "Agent Memory in Production" (May 2026) documents the production stack hierarchy: Mem0 / Letta / Zep-Graphiti / LangMem as the four frameworks that have shipped at scale, with MCP as the tool-access layer and observability (LangSmith, AgentOps) as the third infrastructure pillar. Source: [perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)
- **Framework evidence:** Letta (formerly MemGPT, UC Berkeley research) has 11.9K GitHub stars and ships memory blocks as a first-class concept with a REST API — used by teams deploying agents as stateful microservices. Source: [github.com/letta-ai/letta](https://github.com/letta-ai/letta)
- **LangChain's position:** Harrison Chase (LangChain co-founder) notes that episodic memory in production is implemented as dynamic few-shot prompting — collecting past action sequences and injecting them as examples. Works when there's a "correct" way to do things; breaks down for novel situations. Source: [LangChain Blog, memory-for-agents](https://www.langchain.com/blog/memory-for-agents)

## Gotchas

- **Don't store everything.** Raw conversation history grows unboundedly and pollutes retrieval. Extract and consolidate facts into semantic memory before archiving episodes.
- **Context stuffing is not a memory strategy.** Teams with 200K-token context windows still hit degradation at 80K tokens for needle-in-haystack tasks. The Mem0 benchmarks show the ceiling: even at 10M context, accuracy on targeted retrieval drops to 48.6% (BEAM 10M benchmark) without explicit memory management. Source: [Mem0 GitHub](https://github.com/mem0ai/mem0)
- **Retrieval routing matters more than retrieval algorithms.** The most sophisticated vector store does nothing if you retrieve based on surface-level similarity rather than intent. Semantic memory with entity-aware routing outperforms pure embedding similarity for structured recall tasks.
- **Procedural memory drift.** When agent policies or tool definitions change, in-flight agents using stale procedural memory can behave inconsistently. Load procedural memory at session start and invalidate on deploy.
