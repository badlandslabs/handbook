# S-1451 · The Layering Your Memory Stack — When Your Agent Has No Idea Who You Are Between Sessions

A user tells your agent on Monday: "I prefer Markdown formatting, no preamble." On Tuesday they open a new session and your agent greets them like a stranger. This is the session boundary problem. The field has converged on a layered memory architecture — but "layered" is doing a lot of work in that sentence. The real moves are about what lives in each layer, how retrieval is triggered, and how you prevent a useful memory system from becoming a hallucination amplifier.

## Forces

- **Memory grows until it becomes noise.** Without forgetting, the retrieval surface becomes too large to be useful. But the agent decides when to forget, and agents are unreliable judges of their own memory quality.
- **Retrieval quality determines downstream quality.** A perfectly accurate memory layer is worthless if the agent never retrieves it at the right moment. Semantic search returns plausible-but-wrong results more confidently than you'd expect.
- **Context windows are finite; memory is not.** At 200K tokens for a memory context, you need a strategy for what enters — and the naive answer (everything) degrades quality.
- **Stability vs. adaptability.** Users change preferences. An agent that never updates its stored facts is broken. An agent that updates too readily is also broken — it overfits to one-off actions.

## The move

The industry has converged on a two-tier architecture: **thread-scoped checkpointing** for conversation continuity and **semantic memory** for cross-session knowledge. The specific implementation layers look like this:

- **Working memory (in-context):** The current turn's context window. This is ephemeral — Redis describes it as "active thought" (https://redis.io/blog/ai-agent-memory-stateful-systems/). Design it so only the last N meaningful exchanges survive. Anything older goes to short-term or is dropped.

- **Short-term / episodic memory (per-session):** Retains the current conversation thread. LangGraph uses `PostgresSaver` and `RedisSaver` checkpointer patterns to snapshot agent state between turns (https://langgraphjs.guide/persistence). This is what lets a user resume a plan after the API call ended. Budget: Redis or in-process queue for sub-100ms retrieval.

- **Long-term / semantic memory (cross-session):** The layer that survives session boundaries. Three architectural schools compete:
  1. **Tiered self-editing (Letta/MemGPT):** The agent itself decides what to store and how to organize it. MemGPT pioneered this with its OS/actor metaphor — context overflow triggers paging to a simulated "storage tier." GitHub: ~21K stars (https://github.com/letta-ai/letta).
  2. **Passive extraction + semantic search (Mem0):** The system extracts facts from conversation passively, then retrieves via vector similarity. Library model — drop into any stack. GitHub: ~48K stars. Supports 21 vector stores (pgvector, ChromaDB, Pinecone, Qdrant, Weaviate, Milvus, Redis, Neo4j, FAISS, and more). Code: `client.add()` → `client.search()` (https://github.com/mem0ai/mem0).
  3. **Temporal knowledge graphs (Zep/Graphiti):** Facts are nodes in a graph with temporal edges. The graph tracks when facts became true and when superseded — prior versions remain queryable. arXiv:2501.13956. Reported 94.8% DMR (Deep Memory Retrieval) vs MemGPT's 93.4% (https://arxiv.org/html/2501.13956v1).

- **Procedural memory:** The agent's "knowing how" — stored as code, config, and system prompts. Not in the vector store. LangGraph `Compilation` is the programmatic version: agent workflows are compiled into checkpointer-compatible graphs (https://langgraphjs.guide/persistence).

- **Retrieve with confidence scoring, not just similarity.** Mem0 uses confidence-weighted retrieval: "User corrects agent 3x the same way → confidence 0.8 (likely real preference). User later does the opposite → confidence drops, old preference archived." (https://github.com/mem0ai/mem0/issues/6050). Zep's Graphiti follows temporal confidence decay — older fact versions are ranked lower. This is the anti-hallucination mechanism for the memory layer.

- **Neo4j Agent Memory for relational context:** When agent memory has relationships (user → project → task → subtask), a graph store outperforms a flat vector store. Three layers: conversations, entities, reasoning — in one graph (https://neo4j.com/labs/agent-memory).

## Evidence

- **arXiv:2310.08560 (MemGPT/Packer et al.):** The foundational paper introducing tiered memory with OS/actor metaphor for LLMs with finite context. https://sky.cs.berkeley.edu/project/memgpt/
- **arXiv:2501.13956 (Zep/Rasmussen et al.):** Temporal knowledge graphs for agent memory with benchmark data showing 94.8% DMR retrieval accuracy. https://arxiv.org/html/2501.13956v1
- **Letta engineering post:** "What your agent remembers is fundamentally determined by what exists in its context window at any given moment. Designing an agent memory is essentially context engineering." — https://www.letta.com/blog/agent-memory
- **Mem0 GitHub:** ~48K stars, passive extraction + semantic search library model, 21 vector store integrations. https://github.com/mem0ai/mem0
- **LangGraph Persistence Guide:** Checkpointer pattern (RedisSaver, PostgresSaver) for thread-scoped state across API boundaries. https://langgraphjs.guide/persistence
- **Redis AI Agent Memory blog:** Two-tier architecture framing — thread-scoped checkpointing + semantic memory. https://redis.io/blog/ai-agent-memory-stateful-systems/
- **Consumer AI benchmarks:** Anthropic Claude Memory (2026-03), OpenAI ChatGPT Memory (~40-80 stored entries per user per 30 days), Google Memory Bank (I/O 2026). All three converged on persistent cross-session fact storage within 6 months of each other.

## Gotchas

- **Vector similarity ≠ semantic truth.** A memory about the user's employer is accurate until they change jobs. Without temporal metadata or confidence decay, the vector store serves confident hallucinations.
- **The agent judges its own memory quality.** MemGPT's self-editing approach means the agent decides what to forget — but agents are unreliable judges of their own recall confidence. Build a separate validation layer.
- **Memory fragmentation in multi-agent systems.** When multiple agents share a memory store, stale reads and write races compound. Each agent needs a namespace or a read-version marker.
- **Context overflow paging breaks determinism.** If your agent's behavior changes because of what got paged to long-term storage, you've introduced non-determinism that's hard to test. Keep the paging trigger predictable.
- **Anonymous or multi-device users break the user_id assumption.** All major frameworks (Mem0, Letta, Zep) assume a stable `user_id`. If your auth flow mixes anonymous sessions with authenticated ones, you get duplicate memory profiles for the same person.
