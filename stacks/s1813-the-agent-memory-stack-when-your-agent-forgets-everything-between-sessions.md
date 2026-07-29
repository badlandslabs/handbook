# S-1813 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

You build a capable agent. It reasons, it plans, it calls tools. Then the session ends and it resets — no memory of what it tried, what worked, what the user prefers, or what it learned about the environment. The next session starts from scratch. That reset tax compounds: users repeat themselves, agents repeat mistakes, and the agent never gets better at a particular user or task. The memory layer is what separates a production agent from an expensive chatbot.

## Forces

- **Context is finite but experience is infinite.** A 200K-token context window cannot hold a weeks-long history of interactions, learned facts, and user preferences. You need a memory system that decides what to store, what to retrieve, and what to forget — without burning your token budget on every query.
- **Simple vector search is insufficient for temporal reasoning.** Cosine similarity on embeddings tells you "this is related" but not "this fact was true but is now superseded." Agents need to reason about what is still valid, what has changed, and what they have already tried. None of that is reducible to a similarity score.
- **Memory scoping is non-obvious.** User-level memory (preferences that persist across sessions), session-level memory (current task context), and agent-level memory (learned facts about the environment) require different storage strategies, retrieval frequencies, and eviction policies. Conflating them is a common source of brittleness.
- **The abstraction temptation.** It is easy to reach for a single-memory-backend-to-rule-them-all, but the teams shipping reliable agents tend to compose multiple storage types rather than pick one.

## The move

Use a **hybrid memory architecture** that separates concerns across retrieval speed and temporal reasoning needs.

**The three-tier model** (confirmed across AgentMarketCap's April 2026 production survey, Letta's architecture docs, and multiple HN discussions):

- **Working memory:** In-context content — the current context window. Zero-latency, limited capacity, resets every session.
- **Episodic memory:** Structured records of past interactions and events. "What did this user ask last time?" "What tool calls did the agent make in session 47?"
- **Semantic memory:** Learned facts, preferences, and knowledge. "This user prefers concise responses." "API endpoint X is flaky." Persists across sessions.

**The storage stack** (from real production systems — Mem0 at 59.5k GitHub stars, Graphiti, AgentMemory, Letta):

- **Vector store (FAISS, Qdrant, Pinecone, pgvector):** Semantic search for similarity retrieval. Fast, scalable, battle-tested for RAG. Use for episodic recall — "find interactions similar to this query."
- **Knowledge graph (Neo4j + Graphiti):** Entity-relationship tracking with bi-temporal timestamps. The critical addition over pure vectors: each fact carries `t_valid` (when it became true in the world) and `t_recorded` (when the agent learned it). This lets the graph naturally handle fact decay, contradiction, and temporal reasoning without batch recomputation.
- **Key-value store (Redis, SQLite):** Fast lookups for user preferences, session state, and structured metadata. Use for the things you query by exact key rather than semantic similarity.

**The retrieval cycle** (from Letta's architecture, confirmed by the Mem0 paper):

1. **Search:** Query all three stores in parallel (vector similarity + graph traversal + KV lookup).
2. **Include:** Inject retrieved memories into the context window alongside the current prompt.
3. **Reflect:** After task completion, the agent generates new memories from the interaction — facts, preferences, corrections.
4. **Store:** Write new memories to the appropriate store, with appropriate TTL and metadata.

**Scope memories correctly** (from Mem0's multi-level architecture):

- **User-level:** Preferences, profile facts, long-term relationship context. High persistence, low eviction.
- **Session-level:** Current task, recent tool calls, mid-task decisions. Medium persistence, cleared on session end or TTL.
- **Agent-level:** Learned environment facts — "this API rate-limits at 100 req/min," "this codebase uses Python 3.12." Shared across users for the same agent.

**Let the agent decide what to forget.** Hippo (Show HN, 128 points) models this biologically: unused memory traces decay naturally via synaptic weight weakening, not via hard TTLs. Practically, this means your memory system should surface recency and usage frequency as retrieval signals alongside semantic similarity.

## Evidence

- **Engineering blog (Anthropic):** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Recommends starting with LLM APIs directly and understanding the underlying code before adding framework layers. — [Anthropic Engineering: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Company engineering (Letta):** Every agent maintains a single perpetual thread. Core memory consists of in-context memory blocks; a search-include-reflect cycle manages the boundary between working memory and persistent memory. — [Letta Blog: Agent Memory](https://www.letta.com/blog/agent-memory)
- **Research paper + open-source (Mem0):** A scalable memory-centric architecture with vector, graph, and key-value layers. Three scoping levels: user, session, and agent. April 2026 algorithm achieved 90% token cost reduction and 91% latency reduction. Y Combinator S24, $24M funding, 59.5k GitHub stars. — [Mem0 GitHub / arXiv:2504.19413](https://github.com/mem0ai/mem0)
- **Developer blog (Neo4j / Zep AI):** Graphiti models everything as a directed graph with bi-temporal facts — `t_valid` and `t_recorded` per edge. Handles fact supersession and temporal reasoning without batch recomputation. — [Graphiti: Knowledge Graph Memory for an Agentic World](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- **Show HN (128 points):** Hippo — biologically inspired memory using spiking neural networks and R-STDP for synaptic decay. "The secret to good memory isn't remembering more. It's knowing what to forget." — [Hippo on GitHub](https://github.com/kitfunso/hippo-memory)
- **Production benchmark (AgentMarketCap, April 2026):** Survey of Letta, Mem0, Zep, and Hindsight in production. Confirms three-tier memory model. Notes that agents without purpose-built memory "reset every session" and describes memory as "the defining feature separating pilots from production deployments." — [AgentMemory in Production 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-production-2026)

## Gotchas

- **Do not store everything.** Naive full-transcript memory quickly exceeds context window limits and inflates token costs. Instead, extract structured facts, preferences, and decision records — not raw conversation logs.
- **Conflating retrieval and reasoning.** Vector similarity is good for "find relevant memories" but poor for "is this fact still true?" If your agent needs to reason about temporal context (has this API changed since last week? has the user corrected this preference?), you need a graph layer with temporal metadata, not a vector store alone.
- **Forgetting to scope.** A user preference (user-level) and an environment fact (agent-level) have different eviction policies. Treating all memory as one bucket leads to stale preferences persisting or useful environment facts getting garbage-collected.
- **Silent memory corruption.** Unlike code crashes, memory corruption is silent — the agent acts on wrong facts and you never know. Systems like AgentMemory (26k stars, 1,435 tests) flag this with auto-capture hooks and integrity checks; without that, you need explicit memory validation steps in your agent loop.
