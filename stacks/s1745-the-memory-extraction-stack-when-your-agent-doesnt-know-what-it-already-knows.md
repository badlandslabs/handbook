# S-1745 · The Memory Extraction Stack

When your agent starts every session asking questions it already answered last week — the problem is not storage. It is that nobody decided *what to extract* from prior sessions, *when to extract it*, and *how to retrieve it later*. Most agent memory systems fail at the first step.

## Forces

- **Extraction timing** — eager (every message) wastes tokens on noise; lazy (end of session) loses critical details in summarization
- **Structured extraction vs. raw storage** — storing full transcripts is cheap but unusable; storing only LLM-extracted facts is powerful but lossy and slow
- **Provider lock-in** — agents lose all memory when switching models or restarting if memory is tied to session context
- **Poisoning surface** — persistent memory introduces a new attack vector: an attacker who can write to agent memory can persistently alter its behavior
- **Belief vs. observation** — the agent's memory is a model of what it believes, not a record of what happened; these diverge over time

## The move

Design the **Extractor-Storage-Retrieval pipeline** as three independent concerns, not one system.

**Extractor — what to keep and when:**
- Run extraction as a *separate LLM call* after each session (not every message) with a typed output schema (e.g., JSON: `{entity, attribute, value, confidence, source_session}`)
- Add a **recency weight**: facts mentioned in the last N sessions get boosted retrieval priority
- Use **surprise detection** to flag when new information contradicts existing beliefs — only extract deltas, not redundancies

**Storage — where and how:**
- **Checkpoint store** (single-session continuity): SQLite or Postgres via LangGraph checkpointers — handles conversation resumability, time-travel debugging
- **Semantic memory** (cross-session knowledge): vector DB (Qdrant, pgvector) for similarity search, OR SQLite-backed knowledge graph for relational traversal
- **Avoid provider coupling**: store extracted facts as plain JSON/markdown, not inside any LLM vendor's session store
- **Scope hierarchy**: same entity can have different attributes per project/user/context — partition storage accordingly (e.g., agent-recall's scope: `user:alice:project:api-migration`)

**Retrieval — how to get it back:**
- **Context Selector** runs per-request: embed the user's current query, retrieve top-K relevant facts, inject into system prompt
- Use **hybrid search**: semantic vector similarity + keyword BM25 for factual precision
- Set a **TTL on facts** or an entropy-based forgetting schedule — agentmemory and Nous both implement decay toward uniform belief distribution

**Defend against poisoning:**
- Treat memory as untrusted input at retrieval time — validate fact provenance before acting on it
- Append-only storage prevents retroactive edits without audit trail
- The MemGhost attack (arXiv 2026) plants instructions in long-term memory that agents act on later — input validation at the retrieval layer is the defense

## Evidence

- **GitHub/Show HN:** Agent Recall — SQLite-backed knowledge graph with MCP server, production-proven at 30+ concurrent agents at a digital agency. Every feature extracted from a production failure. Provides 9 MCP tools with proactive-saving instructions. — [github.com/mnardit/agent-recall](https://github.com/mnardit/agent-recall)
- **arXiv paper (Zep AI):** Zep uses a three-tier temporal knowledge graph (Episode subgraph → Semantic subgraph → Fact subgraph) that maintains historical relationships. Outperforms MemGPT on Deep Memory Retrieval (94.8% vs 93.4%) with 90% lower latency. — [arxiv.org/html/2501.13956](https://arxiv.org/html/2501.13956v1)
- **Blog post (NiteAgent, Jun 2026):** The two-tier model is now standard in production: checkpoint stores (SQLite/Postgres) for session continuity, semantic memory (Mem0/Zep/custom) for cross-session knowledge. Summarization loop compresses old turns when context exceeds threshold (~20 messages). — [niteagent.com/blog/agent-memory-production-guide](https://niteagent.com/blog/agent-memory-production-guide/)
- **Blog post (brgsk, May 2026):** "Agent Memory: An Anatomy" — critical analysis of how most libraries label episodic/semantic/procedural without actually implementing separate systems. Key insight: the extraction timing decision (eager vs lazy) determines token cost vs. information loss trade-off. — [brgsk.xyz/agent-memory-anatomy](https://brgsk.xyz/agent-memory-anatomy/)
- **arXiv paper (Pranav Singh, Jul 2026):** "When Does Belief-Based Memory Help?" — Nous system uses Bayesian belief tracking with information-theoretic surprise detection. Critical finding: simple memory updates can be *worse* than no memory when the world changes — belief must be reliability-weighted. — [arxiv.org/html/2606.22030](https://arxiv.org/html/2606.22030v2)

## Gotchas

- Storing full conversation transcripts is not memory — it is a liability. Retrieval will淹没 the model in noise and burn tokens.
- Switching LLM providers without exporting facts first means starting from scratch. Decouple storage from provider.
- A fact extracted with low confidence last month, still in memory, will be treated as equal to a high-confidence fact today. Track confidence.
- Summarization for compression is lossy — the agent loses access to the *evidence trail* that led to a conclusion, not just the conclusion.
- Memory poisoning (MemGhost) is a real attack class in 2026. If your agent reads from a shared memory store, validate writes.
