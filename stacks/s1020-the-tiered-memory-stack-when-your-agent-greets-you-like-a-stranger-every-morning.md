# S-1020 · The Tiered Memory Stack: When Your Agent Greets You Like a Stranger Every Morning

An LLM is a stateless function: tokens in, tokens out. The moment you move beyond a one-shot chatbot into an agent that runs multi-step tasks, coordinates tools, and returns across sessions, you need it to behave as if it remembers. Without an explicit memory architecture, every session starts from zero. The agent that learned your codebase's conventions last week will ask you to explain them again today. This is the session amnesia problem — and "context window plus a vector store" is not a memory architecture. It's a pile.

## Forces

- **Context windows are attention, not memory.** Models begin deprioritizing critical information once context exceeds ~60% capacity, even when the answer sits visibly in the window. Long context does not solve the memory problem — it obscures it.
- **The write path is an afterthought.** Most teams build retrieval first and add memory writes as raw conversation logs. This produces noise, not knowledge. What gets stored, how it's indexed, and when it's consolidated matters more than the retrieval layer.
- **Every tier has a different access cost.** Working memory (context window) is zero-latency but expensive per token. Episodic storage (vector DB) has retrieval latency but scales. Semantic/procedural stores (knowledge graphs, prompt libraries) are persistent but require structured queries. A flat memory system where each tier "works in isolation" still fails if the system has no policy for which tier to read first, what to promote into the prompt, or what to demote when budget tightens.
- **Agents produce more than they consume.** The agent's own tool calls, intermediate results, and decisions are often the most valuable memory — but most systems only store the conversation transcript.

## The Move

Layer the memory system into four distinct tiers with explicit movement rules, not one shared store:

**Working memory (in-context):** The active context window — system prompt, recent turns, retrieved items. Keep it small (3–8K tokens) and expensive. Treat it as CPU cache, not a hard drive. On each turn, the retriever composes what gets promoted; the eviction policy decides what gets demoted.

**Episodic memory:** Stores what happened — conversation logs, tool call histories, task outcomes. Implemented as a vector store (Qdrant, pgvector, Chroma) indexed by time and semantic similarity. After each session, a consolidation step extracts facts, flags contradictions, and updates embeddings. This is where most teams start, and where most teams stop.

**Semantic memory:** Stores what is true — domain knowledge, user preferences, learned facts. Implemented as a knowledge graph (Neo4j, Dgraph) or hybrid graph+vector store. GraphRAG outperforms flat vector RAG on multi-hop queries by up to 43x fewer tokens for large summarization tasks. The graph models explicit relationships between entities, not just semantic similarity between chunks.

**Procedural memory:** Stores how to act — system prompts, skill definitions, workflow templates. Not stored as plain text; versioned, typed, and injected by the orchestration layer (LangGraph state, CrewAI tasks) based on the current goal. Mem0's multi-level approach handles user/session/agent state with adaptive personalization; Letta/MemGPT extend this with sleep-time consolidation that reorganizes memory between active turns.

**The consolidation pipeline is the architecture.** After each session or significant turn, a writer/reflector agent does not just dump logs — it summarizes contradictions, promotes high-frequency facts, demotes stale entries, and updates graph edges. This is what separates a system that accumulates noise from one that compounds in value. Agentic RAG systems (with active retrieval planning and memory) outperform static RAG by 26% in accuracy with 90% fewer tokens, because the agent decides what to retrieve rather than executing a fixed pipeline.

## Evidence

- **Survey:** The agent ecosystem converged on a four-tier memory taxonomy (working, episodic, semantic, procedural) by 2026. "No single storage paradigm dominates; hybrid vector-graph stores are the emerging standard backend. Frameworks treating memory as first-class (Mem0, Zep/Graphiti, Letta) are pulling ahead." — Zylos Research, "AI Agent Memory Architectures: From Context Windows to Persistent Knowledge," 2026-04-05 — https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge
- **OSS adoption:** Mem0 ("Universal Memory Layer for AI Agents") has 60.6k GitHub stars and ~2,500 commits as a YC S24 company, offering multi-level user/session/agent state with adaptive personalization. Memori ("Agent-Native Memory Infrastructure") has 15.5k stars and explicitly captures "memory from what agents do, not just what they say" — storing tool call histories and execution state, not just conversation text. — https://github.com/mem0ai/mem0 | https://github.com/GibsonAI/memori
- **Engineering blog:** HPE's Qdrant + MCP tutorial demonstrates the MCP protocol (Model Context Protocol) acting as a standardized "USB interface" between agents and vector stores, enabling semantic memory that persists across sessions without hardcoding vector DB complexity. — https://developer.hpe.com/blog/part-8-agentic-ai-and-qdrant-building-semantic-memory-with-mcp-protocol/

## Gotchas

- **Promoting everything into context window kills performance.** The 60% context capacity threshold means models start ignoring information before the window is full. Size working memory deliberately; use the retriever as a filter, not a passthrough.
- **Flat RAG is not memory.** Querying a static document corpus by semantic similarity does not produce an agent that learns. The write path — summarization, consolidation, graph update — is where memory actually forms.
- **Procedural memory drifts.** System prompts and skill definitions evolve. If procedural memory is versioned inconsistently, the agent's behavior changes silently between sessions. Treat it like code: review, diff, and rollback capability.
- **Security surfaces expand with memory.** A persistent memory store is an attack surface for prompt injection and memory poisoning. The Zylos survey flags this as the most pressing open problem for enterprise deployments — a poisoned memory corrupts every future session.
