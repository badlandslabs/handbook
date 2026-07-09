# S-867 · The Three-Tier Memory Stack — When Your Agent Forgets Everything But the Prompt

Your agent works within a session. Restart it, and it's a stranger. It re-asks questions it already answered, doesn't remember user preferences, and can't build on past work. The context window isn't memory — it's a whiteboard that gets erased on every restart. You need a persistent memory architecture that outlives sessions and doesn't require stuffing the entire conversation into every prompt.

## Forces

- **Context windows are RAM, not memory.** A 200K-token window is fast working space. It has no persistence, no structure, and costs more per token the more you stuff into it. Teams conflate "big context" with "memory" and end up with expensive, fragile systems. — [Zylos Research: Agent Memory Architectures, April 2026](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)
- **Memory types have different storage requirements.** Episodic memory (what happened), semantic memory (what is true), and procedural memory (how to do it) each need different backends — vector stores for retrieval, relational stores for querying, and file-based policies for versioning. A single vector DB can't serve all three. — [TECHSY: AI Agent Memory Types, April 2026](https://techsy.io/en/blog/ai-agent-memory-guide)
- **LLM-managed paging outperforms retrieval-only.** The agent deciding what to store and when beats a fixed RAG pipeline every time. Letting the LLM call `core_memory_replace` or `archival_memory_insert` gives it self-awareness about its own knowledge gaps. Fixed retrievers miss context and add noise. — [Adaptive Recall: Letta Memory Hierarchy](https://www.adaptiverecall.com/memory-architecture/letta-memory-hierarchy.php)
- **Memory sprawl is a real failure mode.** Unstructured accumulation without consolidation causes retrieval to degrade over time. "The more memory, the better" is false past a certain density threshold. The LoCoMo and LongMemEval benchmarks don't yet measure poisoning resistance or cross-session consistency. — [Zylos Research, 2026](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)

## The move

Build a three-tier memory architecture where each tier has a distinct storage backend, retrieval mechanism, and update policy. Let the LLM manage paging between tiers via explicit function calls — don't outsource memory decisions to infrastructure.

**Tier 1 — Core/Working Memory (in-context):**
- Small fixed block (2–4KB) always present in the prompt. Holds the agent's current self-model: who the user is, active task state, immediate goals.
- LLM writes and rewrites this directly via `core_memory_replace`. It's the agent's RAM.
- On session restart, reload from episodic store into core before first response.

**Tier 2 — Episodic/Recall Memory (searchable):**
- Conversation history, past events, completed tasks. Stored in a vector database with structured metadata (timestamp, user ID, topic, outcome).
- Retrieved via semantic search before each response — but retrieval query is the current task, not just the last message.
- Chunked and paginated; LLM pages relevant episodes in via `archival_memory_search`.

**Tier 3 — Semantic/Procedural Memory (persistent):**
- Declarative facts (user preferences, product knowledge), learned workflows (what worked last time), and policy documents (agent instructions).
- Stored in a relational or graph database you can audit and version — not just a vector index.
- Procedural memory lives in versioned files the agent retrieves on demand; updates go through a review/consolidation step.
- GDPR-right-to-erasure compliance requires structured deletion, not just soft-delete.

**LLM-managed paging, not fixed RAG:**
- Let the agent decide what to promote from episodic to semantic ("user prefers JSON output — write to semantic").
- Periodic consolidation job deduplicates, expires stale entries, and verifies against source-of-truth systems.
- Memory isolation per user or per conversation thread — critical for multi-tenant deployments.

**Storage backend choices:**
- Working memory: orchestrator state object (transient per request)
- Episodic: vector store (Pinecone, Qdrant, Weaviate) with metadata filters
- Semantic: relational (PostgreSQL) or graph database (Neo4j) for auditable, queryable facts
- Procedural: versioned files or a policy database with diff tracking

## Evidence

- **Research report:** Zylos Research's 2026 survey of production agent deployments found that hybrid vector-graph architectures outperform single-paradigm approaches, and that LLM-managed paging (à la Letta/MemGPT's OS-virtual-memory model) produces measurably better recall than fixed retrieval pipelines. — [Zylos Research: AI Agent Memory Architectures, April 2026](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)
- **Framework:** Letta (formerly MemGPT, 23.7k GitHub stars) implements the three-tier core/recall/archival model explicitly. The LLM calls `core_memory_replace`, `archival_memory_search`, and `archival_memory_insert` — making the agent responsible for its own memory management. Their architecture page draws the direct analogy: context window = RAM, external DB = disk, agent = OS page table. — [Letta GitHub](https://github.com/cpacker/MemGPT) · [Adaptive Recall: Letta Memory Hierarchy](https://www.adaptiverecall.com/memory-architecture/letta-memory-hierarchy.php)
- **Production guide:** TECHSY's 2026 memory architecture guide documents working/episodic/semantic/procedural as five distinct memory types, each with explicit backend recommendations. Notes that "context window plus vector store" is not a memory architecture — it's a prototype that degrades. — [TECHSY: AI Agent Memory Guide, April 2026](https://techsy.io/en/blog/ai-agent-memory-guide)
- **HN thread:** r/LocalLLaMA discussion on production multi-step tool chains surfaces the symptom: agents re-reason over every step because they can't reference what they already did. The top response recommends explicit state persistence between calls rather than relying on the model's context to carry state. — [Reddit r/LocalLLaMA: Multi-step tool chains in production, 6 months ago](https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/)

## Gotchas

- **Don't use a vector store as your only memory backend.** It handles episodic recall well but can't answer "what are all facts I know about this user?" or "which workflow has highest success rate?" without a structured layer.
- **Memory sprawl degrades retrieval.** Without a consolidation job, episodic memory grows unbounded and retrieval returns stale, contradictory, or irrelevant entries. The Zylos research report flags this as the primary production failure mode after the initial memory implementation.
- **Context window overflow ≠ memory full.** Teams add more context and call it memory. It isn't — it's expensive latency. The fix is paging, not stuffing.
- **Multi-tenant memory requires hard isolation.** User A's memory must never appear in User B's context. Relational or graph backends make this auditable; vector stores with tenant ID metadata are the minimum viable approach but require careful query filtering.
