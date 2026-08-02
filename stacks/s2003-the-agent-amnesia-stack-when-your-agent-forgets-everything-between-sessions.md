# S-2003 · The Agent Amnesia Stack — When Your Agent Forgets Everything Between Sessions

*When your agent works fine in a demo but falls apart after the tenth real conversation — re-asking the user's name, re-deriving plans it built yesterday, re-explaining preferences established last week. The fix isn't a bigger context window. It's a layered memory architecture that treats persistence as infrastructure.*

## Forces

- **Agents are stateless by default.** Every LLM API call starts from zero. A 1M-token context window does not solve this — it just moves the problem to "which zero do I start from."
- **Context stuffing is expensive and degrading.** Loading full conversation history into every prompt is costly at scale, and LLM accuracy measurably drops as context length increases. It's not memory — it's pagination.
- **Memory noise is as dangerous as no memory.** Storing everything without curation turns the knowledge base into a pile of contradictions. "User lives in Berlin" becomes toxic when it coexists with "User moved to Hamburg" and the retrieval returns both.
- **The forgetting problem is underappreciated.** Most frameworks optimize for storage and retrieval. Almost none optimize for what to forget — which means agents carry stale facts indefinitely, polluting every downstream reasoning step.
- **Cross-session identity is unsolved.** A memory system that can't distinguish "this user's preferences" from "that user's preferences" leaks data between users in multi-tenant deployments.

## The Move

The production-vetted approach in 2026 is a **layered two-tier architecture**: one system handles session continuity (checkpointing), another handles cross-session knowledge (semantic memory). Each layer has a distinct backend, TTL, and retrieval pattern.

### Layer 1: Checkpoint Store — Session Continuity

- Use **SQLite, Postgres, or Redis** for thread/session checkpointing. This is the "resume from where we left off" layer — conversation state, tool call history, mid-task positions.
- Native integrations exist: **LangGraph Checkpointer** uses Postgres/SQLite out of the box; **Letta** includes a built-in state store; **Redis** works for high-throughput resumability.
- Checkpoints should include: full message history, tool call log, working memory scratchpad, and session metadata (user_id, session_id, task_id).
- TTL policy is essential: checkpoints for completed tasks can expire in 24–72 hours; checkpoints for active multi-session tasks should persist until the task is explicitly closed.

### Layer 2: Semantic Memory — Cross-Session Knowledge

This is where agents become genuinely persistent. The 2026 field has converged on four frameworks, each filling a different niche:

| Framework | Approach | Best For |
|-----------|---------|----------|
| **Mem0** | Extracted facts with entity deduplication | Fastest time-to-value, widest integration surface (21 frameworks, 20 vector stores) |
| **Zep** | Temporal knowledge graph with timestamps | Audit trails, "what changed when," RBAC-heavy deployments |
| **Letta** | Agent-first runtime with self-editing memory blocks | Teams wanting memory + agent loop as one system |
| **LangMem** | Semantic + episodic + procedural, pluggable storage | Teams already in LangGraph ecosystem |

- **Entity extraction** converts raw conversation turns into structured facts ("User prefers dark mode," "Project deadline: June 15"). This is the key architectural decision — raw transcript storage (naive RAG) vs. extracted-fact storage (Mem0-style).
- Entity extraction requires an LLM call per turn, which adds latency (~0.5–2s) and cost. Budget for it.

### Layer 3: Procedural Memory — Tool Sequences

- Store learned tool sequences and behavioral heuristics separately from facts. This is what enables "the agent that deploys to staging without being told the steps again."
- **LangMem** has native procedural memory (learned behaviors/prompt rules). **Neo4j Agent Memory** stores reasoning traces and decision patterns.
- Procedural memory updates on explicit positive outcomes — don't store failed tool sequences as procedural knowledge.

### The Forgetting Discipline

The most underinvested part of agent memory. Practical approaches:

- **TTL-based decay**: checkpoint data expires after N days; semantic facts get demoted after M retrievals without reinforcement.
- **Biological forgetting curves**: systems like **YourMemory** (GitHub, 261 stars, +16pp over Mem0 on LoCoMo benchmark) and **Hippo** (683 stars, npm, 926 tests) implement Ebbinghaus-style decay — recall strengthens a memory's half-life, disuse decays it. Hippo's lifecycle: Buffer → Episodic → Semantic → Archived → Pruned.
- **Explicit overwrite**: when a user contradicts a stored fact ("I actually moved to Hamburg"), the system must update in-place, not append. Vector search returns both old and new without this.
- **Pollution guardrails**: configure extractors with tight system prompts, or use `infer=False` (Mem0) to only persist explicit agent-side memory writes, not every user turn.

### Multi-Tenant Isolation

- Every `add()` and `search()` call must pass `user_id` or `session_id`. This is the most common production bug in agent memory systems — frameworks default to global namespaces in starter examples.
- Zep provides RBAC-aware memory by design. For other frameworks, implement namespace partitioning at the storage layer.

## Evidence

- **Show HN (98 points, 53 comments):** "YourMemory — AI memory with biological decay (+16pp better recall than Mem0 on LoCoMo)" — GitHub repo sachitrafa/YourMemory — https://news.ycombinator.com/item?id=47914367
- **Perea.ai Research (2026-05-07):** "Agent Memory in Production — Memory is the third infrastructure layer for agents, after MCP for tool access and observability for runtime visibility. The 2025-2026 landscape converged on a four-type taxonomy (working / episodic / semantic / procedural), four serious frameworks (Mem0, Zep/Graphiti, Letta, LangMem), and a benchmarked vector-DB hierarchy." — https://www.perea.ai/research/agent-memory-production
- **Mem0 State of AI Agent Memory 2026 (2026-08-01):** "LoCoMo, LongMemEval, and BEAM benchmarks are now the standard for comparing memory architectures. 92.5 on LoCoMo, 94.4 on LongMemEval. Biggest gains: +29.6 points on temporal reasoning and +23.1 on multi-hop reasoning." — https://mem0.ai/blog/state-of-ai-agent-memory-2026
- **Show HN (Show):** "SQLite Memory — Markdown-based AI agent memory with offline-first sync" — sqlite-memory implements markdown files as source of truth, embeddings for semantic understanding, hybrid full-text + vector search — https://news.ycombinator.com/item?id=47676123
- **AI Workflow Lab:** "Mem0 vs Letta vs Zep: Agent Memory 2026" — benchmark on real support bot; practical production pitfalls including multi-tenant namespace isolation failures and memory pollution from off-topic turns — https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026
- **Hippo Memory (683 stars, 926 tests):** "Most AI memory systems save everything and search later — that's storage, not memory. hippo implements forget by default, earn persistence through use, provenance on every memory. Buffer → Episodic → Semantic → Archived → Pruned." — https://hippo-memory.com/
- **Neo4j Labs Agent Memory (390 stars):** Graph-native memory using POLE+O model (Person, Object, Location, Event, Other) with entity resolution, relationship extraction, and MCP server with 16 tools — https://github.com/neo4j-labs/agent-memory
- **Show HN Ask:** "How are you solving long-term memory for production AI agents in 2026?" — practitioner thread specifically about teams past demos into real production — https://news.ycombinator.com/item?id=48683139

## Gotchas

- **Don't use a vector store as your only memory backend.** Vector similarity retrieval returns noisy results on raw transcripts. Extracted-fact + graph approaches consistently outperform pure chunk retrieval in production benchmarks.
- **Contradiction handling is not automatic.** When a user updates a preference, you need in-place overwrite semantics, not append-only storage. Most starter examples omit this and produce silent data corruption in production.
- **Embedding drift on model upgrades.** If you upgrade your embedding model, all previously stored vectors become incompatible with new queries. Either re-embed everything or version your embedding model in the storage schema.
- **Entity extraction cost compounds.** Every conversation turn that triggers entity extraction costs an LLM call. At 10K daily sessions, that's 10K additional LLM calls per day just for memory maintenance.
- **Multi-tenant namespace is easy to miss.** All four major frameworks default to global namespaces in their getting-started examples. This is a data-leak risk — add user/session scoping from day one.
