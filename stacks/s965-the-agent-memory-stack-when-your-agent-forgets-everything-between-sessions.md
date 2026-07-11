# S-965 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent helped a user draft a contract on Monday. By Tuesday it has no idea who that user is, what project they're working on, or that the contract was already reviewed and approved. Every session starts from zero. The agent isn't broken — it's stateless by design. The fix is memory architecture: a discipline that transforms a stateless LLM into a system that remembers, learns, and adapts.

## Forces

- **Context windows are finite but memory needs aren't.** Frontier models ship with 200K–1M token context, but stuffing everything in the context window creates slow inference, high costs, and degraded retrieval — the "needle in a haystack" problem.
- **Retrieval is not memory.** Vector-store-backed RAG finds relevant documents, but it doesn't model how facts change over time, which memories are current, or which interactions preceded a given session.
- **One store can't serve all query patterns.** A vector DB answers "what did we discuss about Project X?" but not "what was true about this user in Q1?" Temporal reasoning, auditability, and conflict resolution require different storage models.
- **Memory writes are harder than reads.** Most teams build retrieval first, then discover that their agent floods the context with stale, contradictory, or irrelevant memories. The write path — what to store, when to consolidate, what to forget — is the actual engineering challenge.

## The Move

Structure memory as three or four distinct stores, each serving a different query pattern. Design a tiered pipeline that moves information from hot to cold storage. Treat the write path as a first-class concern, not an afterthought.

**The four memory types every production agent needs:**

- **Working memory** — the current context window. Small, fast, volatile. The agent's active scratchpad during a session. Managed by the orchestration framework, not a separate service.
- **Episodic memory** — specific past events and interactions. "User X submitted a compliance report on March 3rd." Stored in a vector database with structured temporal metadata. Enables the agent to reconstruct what happened before the current session.
- **Semantic memory** — extracted facts, preferences, and knowledge. "User X prefers brief summaries." Stored in a schema you can query and audit. Can be a relational DB, a knowledge graph, or a structured vector store — depending on your query requirements.
- **Procedural memory** — the agent's own instructions and learned behaviors. "How to escalate a flagged compliance issue." Versioned policy documents, system prompts, and learned tool chains the agent retrieves on demand.

**The production memory pipeline:**

- **Write path:** Every turn generates candidate memories. Rather than writing directly, route through a consolidation step — LLM-powered extraction that deduplicates, resolves conflicts, and assigns temporal validity windows. This runs asynchronously between sessions or on a schedule.
- **Read path:** On session start, retrieve episodic + semantic memories for the user/entity, then inject the top-K most relevant into working memory. Use a retrieval ranker (not just cosine similarity) that factors recency, relevance, and entity affinity.
- **Forgetting policy:** Memories have explicit expiry or "last-valid" timestamps. Zep's temporal knowledge graph models this natively — a fact like "Robbie only wears Adidas" gets invalidated when the user says "I'll be wearing Nike going forward" on a later date. Without temporal validity, agents retain contradictory facts indefinitely.
- **Tiered context:** Letta/MemGPT's OS-style pattern keeps a small "core memory" block always in context (identity, current task, critical facts), with larger archival and recall tiers paged in as needed. This is the pattern that achieved 93.4% deep memory retrieval accuracy in MemGPT benchmarks.

**The three platforms worth knowing:**

- **Mem0** (vector-first, Apache 2.0, ~48K GitHub stars, $24M Series A, exclusive memory provider for AWS Agentic SDEK): fastest path to cross-session personalization. Combines vector store + optional knowledge graph. Pro tier adds graph. Best for teams that want managed infrastructure with minimal ops overhead.
- **Zep / Graphiti** (temporal knowledge graph, Neo4j-backed, ~24K GitHub stars, 71.2% on LongMemEval benchmark): time is a first-class dimension. Validates "what was true at time T?" and handles fact invalidation cleanly. Best for agents that reason about how things change over time.
- **Letta** (OS-tiered runtime, MemGPT heritage, agents-as-a-service): the agent manages its own memory through function calls. Core/archival/recall tiers with paging. Self-editing memory blocks. Best for long-running agents where explicit memory management and introspection matter.

**Platform-native alternatives:** Anthropic's "Dreaming" (May 6, 2026) runs an async hippocampal-consolidation process between sessions — Harvey reported a **6x task completion lift** after enabling it. Google ships Memory Bank at identity scope. OpenAI uses vector-store-backed `file_search`. Claude Opus 4.7's 1M-token flat-priced context has made long-context a legitimate memory architecture for small fleets, undercutting Mem0 + Pinecone at under 500K tokens accumulated history.

## Evidence

- **HN Ask thread (May 9, 2025):** Practitioners building LLM agents and copilots discussing whether knowledge graphs are worth the operational overhead for memory — consensus leaned toward "yes if you need temporal reasoning, no if simple retrieval suffices." — [news.ycombinator.com/item?id=43940654](https://news.ycombinator.com/item?id=43940654)
- **Letta (MemGPT) benchmarks:** MemGPT achieved 93.4% deep memory retrieval accuracy on GPT-4 by using tiered OS-style memory management — the result that demonstrated memory architecture as a tractable engineering problem rather than a modeling limitation. — [lin-guanguo.github.io/llm-memory-research/letta.research](https://lin-guanguo.github.io/llm-memory-research/letta.research)
- **Zep open-source launch:** Zep open-sourced their graph memory engine (Graphiti) with the explicit claim that agent-powered retrieval and complex multi-level architectures are "slow, non-deterministic, and difficult to reason with" — Zep precomputes the graph and related facts asynchronously for low-latency retrieval. — [reddit.com/r/LLMDevs/comments/1fq302p](https://reddit.com/r/LLMDevs/comments/1fq302p/zep_opensource_graph_memory_for_ai_apps)
- **Anthropic Dreaming (May 2026):** Async hippocampal-replay process that reorganizes agent memory between sessions. Harvey reportedly saw 6x task completion lift. The model does not change — it's a memory operations layer with a smart consolidation policy. — [digitalapplied.com/blog/ai-agent-memory-vector-graph-episodic-2026](https://www.digitalapplied.com/blog/ai-agent-memory-vector-graph-episodic-2026)
- **Redis production guide:** Confirms three-tier pattern as the dominant production approach: working memory in the orchestrator state object, episodic in vector store with structured metadata, semantic in relational schema for auditability, procedural in versioned policy documents. — [redis.io/blog/ai-agent-memory-stateful-systems](https://redis.io/blog/ai-agent-memory-stateful-systems)
- **Mem0 ecosystem stats:** 48K GitHub stars, $24M Series A (Basis Set Ventures, Oct 2025), exclusive memory provider for AWS Agentic SDEK. — [agenticwire.news/article/mem0-zep-letta-agent-memory](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory)
- **Production cost metric:** Agents with proper memory architecture achieve 3–5x higher task completion rates and 70% cost reduction via semantic caching. — [streamzero.com/blog/posts/deep-dives-tools-techniques-architectures/memory-architecture-for-agents](https://streamzero.com/blog/posts/deep-dives-tools-technologies-architectures/memory-architecture-for-agents)

## Gotchas

- **LangChain memory is deprecated.** Migrate to LangGraph's checkpointer-based pattern — LangChain abandoned the memory module and the migration path is to stateful graph-based architectures.
- **Vector similarity alone is a poor memory retriever.** Without temporal metadata, you can't distinguish "what was true last month" from "what was true last year." The agent retrieves the most similar match, not the most current one. Pair vectors with temporal validity windows or a graph layer.
- **Consolidation is load-bearing.** Teams build the retrieval path first, then discover the agent is dumping noisy, contradictory memories into the context window on every session start. The consolidation pipeline — deduplication, conflict resolution, summarization — is what separates production memory from a noisy scratch pad.
- **The forget policy is not optional.** GDPR's right-to-be-forgotten applies to agent memory. Graph-backed systems (Zep/Graphiti) handle this cleanly by invalidating subgraphs. Pure vector stores require explicit deletion by document ID, which most teams don't implement until a compliance audit.
