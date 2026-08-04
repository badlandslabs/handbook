# S-2139 · The Memory Tiering Stack — When Your Agent Has RAM, Disk, and a Filing Cabinet, and Must Manage All Three

Your agent is three sessions into its relationship with the user. On session one, it extracted the user's name and timezone. On session two, it learned they prefer concise responses. On session three, it has no idea any of this happened — the vector store returned a stale embedding, the conversation history buffer dropped the first session, and the knowledge graph has no edges connecting the three sessions. The agent greets the user like a stranger. This is not a model problem. It is an architecture problem: you built a memory system from one technology and expected it to do the job of three.

## Forces

- **Vector search is not memory.** RAG-based retrieval solves semantic nearest-neighbor — it says nothing about recency, causality, identity, or skill. A vector store full of embeddings is a filing cabinet with no index, no expiration dates, and no concept of relevance vs. recency.
- **Every memory type wants a different backend.** Working memory needs sub-10ms latency in-context. Episodic memory needs time-indexed retrieval with embedding search. Semantic memory needs graph traversal and upsert semantics. Procedural memory needs executable, versioned artifacts. No single store handles all four.
- **The agent must manage its own memory hierarchy.** Unlike a database where a query engine decides what to return, agent memory systems often give the agent tools to read, write, compress, and page memory itself. This means the agent can fail at memory management the same way it can fail at tool use.
- **Stale reads are invisible failures.** A vector store returning yesterday's user preference looks identical to one returning fresh data. The agent reasoning chain that follows looks perfectly coherent. The failure is in the data, not the logic — and most monitoring misses it entirely.

## The move

Treat agent memory as an **OS-style tiered architecture**, not a single vector store. The 2025-2026 production consensus converged on a four-type taxonomy that maps to distinct storage and access patterns:

**1. Working memory — context window.** The token-limited scratchpad. You do not persist this; you engineer what enters it. Key pattern: **summary compression** (condense prior turns into a <500-token rolling summary) + **priority injection** (always-load facts go in the system prompt, not in retrieval). Mem0 reports 92.5% recall on LoCoMo at under 7,000 tokens per retrieval call versus 25,000+ for naive full-context re-injection — the summary-then-retrieve pattern is the dominant engineering solution.

**2. Episodic memory — event stream.** A record of what happened, in order, with timestamps. Backed by an event store (Postgres with a timestamp index) + dual indexing (time-based + embedding-based). This is where Zep's Graphiti temporal knowledge graph and Letta's recall memory live. The critical design: episodic records must be **immutable appends**, not mutable updates. A mutable memory write at step 47 can retroactively change what happened at step 3 — breaking the causal chain the agent's reasoning depends on.

**3. Semantic memory — decontextualized facts.** Consolidated knowledge extracted from episodic records: "user prefers concise responses," "geocoding API at api.example.com times out after 3s." Backed by a knowledge graph (Neo4j, FalkorDB) or structured key-value store with upsert semantics. The agent's write path to semantic memory should run asynchronously — Mem0's production users report async memory writes to avoid adding latency to the user-facing response path.

**4. Procedural memory — skills and plans.** Reusable, versioned artifacts: system prompts, tool definitions, agentic workflows. Backed by a versioned artifact store (S3 + metadata DB, or a dedicated registry). The key constraint: procedural memory must be **auditable** — you must be able to reconstruct exactly which version of which skill the agent was running at any past timestamp, because a failed skill at time T explains a failed decision at time T+1.

**The practical implementation stack** — from Perea's 2026 field manual and cross-referenced across Mem0's benchmark data, Zep's Graphiti docs, and Letta's architecture posts:
- **Hot path (episodic, <100ms):** Redis + Postgres with timestamp index
- **Embedding store (semantic retrieval):** Qdrant as default; Weaviate if running 50+ agents in parallel; pgvector only if corpus <10M vectors
- **Knowledge graph (semantic consolidation):** Neo4j, FalkorDB, or Amazon Neptune — for relational reasoning that vector similarity cannot support
- **Memory framework:** Mem0 (vector-first, 186M API calls Q3 2025, AWS exclusive), Zep/Graphiti (temporal graph-native), Letta (three-tier OS-inspired: core/archival/recall), or LangMem (LangGraph-native, lightweight)

## Evidence

- **Research field manual:** Perea (2026) documents the four-type taxonomy, four framework comparison, and vector-DB benchmark hierarchy across Qdrant/Weaviate/pgvector/Pinecone as production consensus from 45+ sources — [perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)
- **Framework benchmark:** Mem0 reported 92.5% on LoCoMo and 94.4% on LongMemEval at under 7,000 tokens per retrieval call; Zep/Graphiti scored 63.8% on LongMemEval versus 49% for baseline — [callsphere.ai blog](https://callsphere.ai/blog/td30-fw-mem0-vs-zep-vs-letta-2026-honest-comparison-guide); Mem0 raised $24M and serves as AWS's exclusive memory provider, processing 186M API calls in Q3 2025 — [agenticwire.news](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory)
- **Architecture pattern:** Letta's three-tier OS-inspired model (Core Memory = always-in-context registers, Archival Memory = paginated vector store, Recall Memory = full conversation event log) — [letta.com/blog/agent-memory](https://www.letta.com/blog/agent-memory); [adaptive-recall.com](https://www.adaptiverecall.com/memory-architecture/letta-memory-hierarchy.php)
- **Failure mode research:** Redis documented four context failure modes (stale reads, hallucinated context, context window exhaustion, memory poisoning) with specific examples of agents offering renewal discounts to churned customers — [redis.io/blog/the-4-failure-modes-of-agent-context](https://redis.io/en/blog/the-4-failure-modes-of-agent-context/)

## Gotchas

- **Vector search alone cannot answer "when did this happen?"** Temporal queries — "what did the user ask about in their first session?" or "has this preference changed over time?" — require time-indexed episodic storage, not just embedding similarity. A pure vector store returns the semantically closest match regardless of recency or causality.
- **Memory writes must be async or idempotent.** A synchronous memory write on the user-facing path adds latency and creates a new failure mode: a failed write means the agent learns nothing. Async writes must themselves be idempotent and have their own retry logic, or a failed async write silently creates a session with no memory.
- **Immutability is the default for episodic records.** If your episodic store allows mutable updates, a late-stage agent decision can retroactively rewrite history. The causal chain breaks. Use append-only event logs for episodic memory; upserts are only safe for semantic memory where consolidation is the intended behavior.
- **The agent's inner monologue about memory management is not auditable by default.** Letta and MemGPT give agents tools to manage their own memory paging. When the agent decides to evict a core memory block to make room, that eviction is a decision — and decisions need logs. If your memory system doesn't emit write/read/eviction events to your observability stack, you have no way to debug why the agent "forgot" something.
- **Context poisoning spreads through memory.** OWASP's ASI06 (Memory and Context Poisoning) notes that unlike prompt injection (session-scoped), a poisoned memory entry persists across sessions. A RAG retrieval returning an adversarial document can write that content into semantic memory — it then surfaces in every future session. The write path to memory needs sanitization even if the retrieval query itself looked innocent.
