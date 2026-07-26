# S-1670 · The Memory Stratification Stack — When Your Agent Wakes Up Every Morning With No Memory

Your agent works perfectly in a single session. Put it down, come back tomorrow, and it has no idea who you are, what you were working on, or what it promised to do. Every session starts from zero. This is not a bug — it is the default state of LLMs — but it is also the single highest-impact problem to solve if you want an agent that actually compounds value over time.

## Forces

- **Context windows are finite but memory needs are unbounded.** Even 128K-token contexts eventually flush. Real conversations wander across unrelated topics for hours before returning to something important.
- **Retrieval quality is harder than storage.** Saving messages is trivial. Knowing *what* to save, *when* to consolidate it, and *how* to retrieve the right thing at the right moment is an unsolved engineering problem.
- **Two mental models compete.** Memory as a *database to query* versus memory as a *state the agent carries*. The retrieval camp leads to RAG stacks; the state camp leads to curated context injection. Both work; most teams end up needing both.
- **User trust is the hardest problem.** Users do not trust agents that silently accumulate knowledge they cannot see or correct. The product question is not just "how do we store memory" but "how do we make memory visible, inspectable, and editable."

## The move

Design a **layered memory architecture** that handles three distinct time horizons, each with its own storage mechanism and retrieval strategy:

- **Working memory (session scope):** The rolling conversation buffer. Managed by the orchestration framework (e.g., LangGraph TypedDict state with reducers, or a summary-then-truncate pipeline). This is the agent's immediate scratchpad — it is always present and always accurate, but it dies with the session. Key insight from production deployments: use a `max_turns` cap with LLM-based summarization before truncation, not naive first-in-first-out, because the most recent message is not always the most important.

- **Semantic memory (cross-session scope):** What the agent learns about the user, their preferences, and recurring patterns. This is where Mem0 (61K GitHub stars, the most widely deployed semantic memory layer as of mid-2026) and its derivatives live. Mem0 uses a hybrid retrieval approach combining vector similarity search with keyword matching and a graph-based extension (Mem0^g) that models entities and their relationships as directed labeled graphs. PingCAP's mem9 reached 10,000 users within two weeks of its March 2026 launch, confirming real demand. The key architectural choice: do you store dense natural-language memory entries, structured facts, or both? The answer is both — but they need different retrieval paths.

- **Procedural / episodic memory (long-term scope):** What the agent learned to *do* — tool chains, successful strategies, agentic workflows. This lives in a wiki or knowledge base (Obsidian-style or structured KV store) that the agent can reference but that does not auto-inject into every context. This layer is high-signal but low-frequency: it is consulted when relevant, not carried always.

- **Curated core memory (always-active):** A small, bounded file that is injected into *every* prompt without retrieval. Hermes Agent uses a two-file core (`MEMORY.md` + `USER.md`, totaling ~1,300 tokens) that is always present in the system prompt. The key insight: curated, always-active memory outperforms retrieval-based approaches for persistent agents because it eliminates the retrieval step entirely for the highest-value facts. The constraint (bounded size) forces curation, which prevents memory bloat.

- **Storage stack:** Most production systems land on a three-tier storage model: Redis for low-latency cache (recent interactions), PostgreSQL/TiDB for durable structured storage with ACID guarantees, and a vector database (Qdrant, Pinecone) for semantic retrieval. Self-hosted alternatives (SQLite for local-first, CouchDB for sync) work for privacy-sensitive deployments but require more operational overhead.

## Evidence

- **arXiv paper (Mem0):** Mem0's architecture uses extraction and consolidation phases — on new input, it extracts entities and facts; on a consolidation tick, it resolves conflicts and updates the graph. Their April 2026 new algorithm improved LoCoMo benchmark from 71.4 to 92.5 with only 7.0K tokens retrieved. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)

- **Company engineering post (PingCAP/mem9):** "mem9 started as a customer request in March 2026, not a roadmap. We shipped a prototype before we wrote a plan." Key lessons: agent memory is not a storage problem — it is an engineering problem at the intersection of ingestion, ranking, evaluation, and product judgment. "A memory API alone is not a product. Users want to see, inspect, trust, and correct what an agent remembers." — [PingCAP Blog](https://www.pingcap.com/blog/how-we-built-mem9-agent-memory-product)

- **HN Show post (Hmem):** Hmem provides persistent hierarchical memory for coding agents via MCP, backed by SQLite. Their analysis: the two unsolved memory problems are *context dilution* (conversations get compressed and agents forget decisions made hours ago) and *vendor/machine lock-in* (memory tied to one tool on one machine). Solution: portable hierarchical memory that survives tool and machine switches. — [Hacker News](https://news.ycombinator.com/item?id=47103237)

## Gotchas

- **Retrieval at the wrong time.** Adding a retrieval step to the prompt loop adds latency and can retrieve stale or irrelevant context that derails the agent. Only retrieve when the agent explicitly signals it needs historical context — not on every turn.
- **Memory bloat without curation.** Agents will accumulate memory indefinitely if left unchecked. Without a bounding mechanism (hard token limit, LLM-based importance scoring, or explicit consolidation policy), memory grows to fill the context window and retrieval quality degrades. The Hermes core-memory approach of hard-bounded files forces this discipline.
- **Cross-user memory leaks.** If your memory store is shared across sessions without user segmentation, one user's data bleeds into another's. Partition memory by user ID at the storage layer, not just at the retrieval layer.
- **Crash recovery is not the same as memory.** Saving conversation logs to a database is not memory — it is an audit trail. True memory requires extraction, consolidation, and retrieval as first-class operations. A crash-recovered session that re-reads every message is not the same as an agent that knows what *mattered* from that session.
