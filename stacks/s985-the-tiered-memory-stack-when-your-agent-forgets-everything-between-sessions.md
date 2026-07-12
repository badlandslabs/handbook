# S-985 · The Tiered Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent aced the demo. Three turns into a real session, it has no idea who you are, what you discussed, or what it promised to do. You stare at the 200K-token context window and realize it's mostly noise.

Agents are stateless by default. A 200K-token context window is not memory — it's a very expensive whiteboard that gets erased on every session. True persistent memory requires explicit architecture, and teams that skip it ship agents that feel broken in production.

## Forces

- **Context is finite, experience is infinite** — the agent's entire history can't live in the prompt, yet every previous session contains information the agent needs
- **Naive RAG isn't enough** — fetching relevant docs before each call is read-only; the agent also needs to write, update, and forget
- **Memory tiering is non-obvious** — working context, conversation history, extracted facts, learned preferences, and procedural knowledge have different retrieval patterns and retention policies
- **The LLM shouldn't just passively receive memory** — the agent should actively decide what to store, when to page, and what to forget, mirroring OS virtual memory

## The move

Structure agent memory as four distinct tiers, each with its own storage, retrieval mechanism, and LLM interface:

**Tier 1 — Working Memory (Core Memory)**
- Small (2–8KB), always in-context — the agent's current understanding of the user and active task
- Analogous to RAM: fast, volatile, always live
- Letta calls this `core_memory`; it's the LLM's "desk" during a session
- LangMem's `MemoryStore` auto-updates this from conversation signals

**Tier 2 — Episodic Memory (Conversation History)**
- Full conversation logs, pageable in chunks
- Retrieved selectively — not all history is relevant to all queries
- Zep/Graphiti extracts temporal events and relationship changes from conversations
- Retrieval query is typically the user's last message or synthesized from context

**Tier 3 — Semantic Memory (Extracted Facts & Preferences)**
- Structured knowledge extracted from conversations: user preferences, agreed decisions, domain facts
- Backed by vector store (Pinecone, Qdrant) for semantic similarity search, or knowledge graph (Neo4j) for relational queries
- The agent writes here via explicit function calls (`memory_insert`, `preference_store`)
- Hybrid vector-graph stores are becoming the standard: semantic similarity + relationship traversal in one query

**Tier 4 — Procedural Memory (Agent's Own Instructions)**
- The agent's system prompt, tool definitions, and learned behaviors
- Includes dynamic updates: when the agent learns a new preference, the procedural layer gets updated
- LangMem handles this as a managed store that patches system prompts automatically

**The LLM controls paging** — not the application. The agent decides via function calls when to `archival_memory_search`, `core_memory_replace`, or `recall_memory_page`. This is Letta's core insight: LLMs managing their own virtual context is the right abstraction, not the OS deciding for them.

## Evidence

- **Anthropic engineering post:** Multi-agent research system uses a lead agent that synthesizes across parallel subagents, each with their own context windows. The paper notes that multi-agent systems burn ~15x the tokens of a single chat — but enable ~90.2% better answers on breadth-first research tasks. The architecture is fundamentally about distributing memory across agents. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Zylos Research (April 2026):** Surveys production memory architectures and finds hybrid vector-graph stores becoming the standard backend. "No single storage paradigm dominates. Vector databases excel at fuzzy semantic recall but are structurally blind to relationships. Knowledge graphs handle relational and temporal reasoning with deterministic precision but demand ontology maintenance." Recommends hybrid architectures for production agents. — [Zylos Research](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)

- **Letta architecture docs / MemGPT-style patterns:** Implements tiered memory where the agent uses `core_memory_replace`, `archival_memory_search`, and `archival_memory_insert` as function calls. "Just as an OS has specific mechanisms for page replacement (LRU, clock algorithm, working set model), Letta has specific mechanisms for context management. The agent has explicit tools for reading from and writing to its external storage." Inverts the traditional RAG pattern: retrieval is active (LLM-initiated) rather than passive (application-initiated). — [Letta Research](https://lin-guanguo.github.io/llm-memory-research/letta.research)

- **LangMem (LangChain):** Treats procedural memory as a managed store integrated into LangGraph. Agents using LangMem show measurable improvement on multi-session tasks because learned facts persist across sessions without manual prompt engineering. — [LangMem docs](https://docs.langchain.com/langgraph/concepts-memory/)

- **Zep / Graphiti:** Specializes in episodic memory with temporal awareness — understanding not just what happened, but when, and how it relates to subsequent events. "Best when temporal awareness and knowledge graph evolution are required." — [JobsByCulture Guide](https://jobsbyculture.com/blog/ai-agent-memory-systems-guide-2026)

## Gotchas

- **Don't mix memory tiers in one vector store** — working context (2KB, always live) and long-term knowledge (unbounded, pageable) have opposite retrieval and retention policies. Treat them as separate systems with explicit contracts.
- **Passive RAG ≠ agent memory** — standard RAG fetches docs before the LLM call. Letta-style memory lets the LLM decide dynamically what to store and retrieve. The behavioral difference is significant: passive RAG is read-only, agent memory is read-write.
- **Forgetting is a feature, not a cleanup task** — agents that store everything eventually hit token limits or retrieve irrelevant context. An explicit eviction policy (LRU, relevance threshold, time-based decay) is required. Letta's archival tier exists precisely so core memory can be kept small.
- **Memory writes must be idempotent** — if the agent calls `memory_insert` twice for the same fact (e.g., a retry after network error), the store should deduplicate or overwrite, not accumulate duplicates. This is the failure mode that breaks long-running sessions.
- **Cross-session identity is harder than it looks** — knowing the user is the same person across sessions requires authentication binding, not just session cookies. Without explicit identity linking, memory tier 3 fragments across anonymous sessions.
