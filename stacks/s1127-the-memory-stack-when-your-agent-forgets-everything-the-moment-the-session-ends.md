# S-1127 · The Memory Stack — When Your Agent Forgets Everything the Moment the Session Ends

A user asks your agent to continue from a conversation three days ago. The agent has no idea what they're talking about. The model is state-of-the-art — the memory architecture is nonexistent. The fix isn't a larger context window. It's a layered persistence system that knows what to store, when to retrieve it, and when to forget.

## Forces

- **Context is expensive and finite.** Feeding full conversation history into every prompt scales linearly with cost and latency. At some point you must choose what stays and what goes — and naive truncation drops the oldest tokens, which may include the task definition itself.
- **Retrieval is not memory.** Storing embeddings in a vector DB and doing similarity search is a retrieval system, not a memory system. Memory requires fact extraction, deduplication, conflict resolution, and temporal reasoning — none of which a raw vector store provides.
- **The three-layer problem.** Agents need short-term (this session), episodic (past interactions), semantic (facts and preferences), and procedural (learned patterns) memory — each with different storage, retrieval, and consolidation strategies.
- **Multi-agent amnesia compounds.** When agents share no memory layer, they duplicate work, contradict each other, and cannot coordinate. The blackboard pattern requires an explicit shared store, not just message passing.
- **Memory grows unbounded.** Without consolidation, episodic memory accumulates forever. Without forgetting, retrieval degrades and costs explode.

## The move

Build a three-layer memory architecture with distinct storage and retrieval strategies for each tier.

**Short-term / checkpoint memory (session scope):**
- Persist graph state after every step using thread_id-scoped checkpointers (LangGraph pattern)
- Backends: SQLite for single-process/dev, Postgres for production, Redis for distributed
- Never let truncation drop the task definition — pin critical context as immovable
- Track token budget per retrieval chunk; evaluate context freshness before every tool call

**Episodic memory (interaction history):**
- Store full conversation turns in a searchable log (sliding window or summarization pipeline)
- Retrieve via hybrid search: semantic similarity + BM25 keyword matching + entity linking, fused and re-ranked
- Consolidate old episodes by compressing them into distilled semantic summaries (prevents unbounded growth)
- Tools: Mem0 (60K stars, Apr 2026 update: LoCoMo 71.4→92.5, LongMemEval 67.8→94.4), Zep/Graphiti, Letta's recall memory

**Semantic memory (facts and preferences):**
- Store structured facts in a relational store with JSONB support (Postgres) — not just embeddings
- Entity linking: extract entities, embed them, and link across memories for retrieval boosting
- Temporal reasoning: rank the right-dated instance for queries about current state vs. past events
- Conflict resolution: when new information contradicts old, the system must decide what wins
- Tools: Mem0's entity extraction + deduplication, Postgres JSONB, knowledge graphs (75-node graphs built from MEMORY.md files)

**Procedural memory (learned patterns):**
- Cache learned action sequences and decision patterns in fast-access storage (Redis Sorted Sets)
- Use for skill acquisition: patterns the agent has successfully executed before get stored for reuse
- Evict or decay low-confidence procedural memories over time

**Multi-agent shared memory:**
- Expose `save_memory` / `load_memory` as explicit tools in the agent's toolset
- The shared store acts as a blackboard: agents write findings, read context, and coordinate without message-passing overhead
- Works for multi-agent pipelines where agents operate in isolation otherwise

**The LLM-managed paging pattern (Letta):**
- Core memory (2–4KB, always in-context) = RAM
- Archival memory (external vector store, no size limit) = disk
- Recall memory (conversation log, pageable) = swap
- The LLM controls paging via `core_memory_replace`, `archival_memory_search`, `archival_memory_insert` — mirroring OS virtual memory

## Evidence

- **Mem0 GitHub README (60,763 stars):** April 2026 new algorithm ships single-pass ADD-only extraction (one LLM call, no UPDATE/DELETE), entity linking across memories, multi-signal retrieval (semantic + BM25 + entity matching), and temporal reasoning. Benchmarks: LoCoMo 71.4→92.5, LongMemEval 67.8→94.4, BEAM 10M 48.6 — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Mem0 Blog (May 2026):** "Most developers who claim their agent 'has memory' have actually built a retrieval system. Plugging Chroma or Pinecone into an agent pipeline gives the agent the ability to find similar text, but similarity search and memory are not the same thing." Memory adds: fact extraction, deduplication, conflict resolution, temporal awareness — [https://mem0.ai/blog/vector-databases-and-memory-for-ai-agents](https://mem0.ai/blog/vector-databases-and-memory-for-ai-agents)
- **LangGraph Checkpointing Reference:** Thread-scoped checkpointers save graph state after every superstep. Backends: InMemorySaver (dev only), SqliteSaver, PostgresSaver, RedisSaver. Pending writes preserve work when nodes fail. Thread_id + optional checkpoint_id provide fine-grained resume — [https://reference.langchain.com/python/langgraph/checkpoints](https://reference.langchain.com/python/langgraph/checkpoints)
- **CyberQuickly (Apr 2026):** Context truncation failure: when context fills, naive systems drop the oldest tokens — which may be the original task definition. The agent continues operating without knowing its goal. Mitigation: hierarchical summarization, token budget tracking, pinning critical context — [https://www.cyberquickly.com/2026/04/07/ai-agents-production-failure/](https://www.cyberquickly.com/2026/04/07/ai-agents-production-failure/)
- **HN Show HN — DeltaMemory (Jun 2026):** "Most AI agents forget everything when the session ends." Persistent cognitive memory for production agents — [https://news.ycombinator.com/item?id=47161647](https://news.ycombinator.com/item?id=47161647)
- **AI University docs (Mar 2026):** Multi-agent blackboard pattern: "An agent without memory is not an agent. It is a very expensive stateless function." save_memory/load_memory as first-class tools for agent coordination — [https://theaiuniversity.com/docs/building-agents/memory-and-context](https://theaiuniversity.com/docs/building-agents/memory-and-context)
- **Zylos Research (Apr 2026):** "The frameworks that have shipped this architecture at scale — Mem0, Zep/Graphiti, Letta — are pulling ahead of competitors that still treat memory as an afterthought." Hybrid vector-graph architectures with LLM-managed interfaces — [https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)

## Gotchas

- **Naive vector retrieval is not memory.** Similarity search and memory are architecturally different. You cannot add truth state computation, conflict resolution, or temporal reasoning to a vector store by adding metadata — you must rebuild around a belief model.
- **Truncation order kills agents.** When context fills, dropping oldest-first may remove the task definition while keeping tool results and retrieved chunks. Pin the goal and constraints as immovable.
- **ADD-only accumulation creates drift.** If memories are never overwritten, contradictory facts accumulate. The system needs explicit revision semantics — not just more embeddings.
- **Consolidation is not optional.** Without periodic compression of episodic into semantic memory, storage and retrieval costs grow linearly with conversation length. Without forgetting, recall quality degrades.
- **Short-term checkpointing ≠ long-term memory.** LangGraph's checkpointer persists a session's graph state — it does not give the agent cross-session recall of user facts, preferences, or past decisions.
- **Evaluation is immature.** LoCoMo and LongMemEval exist, but production memory quality is still largely measured by user satisfaction, not automated benchmarks.
