# S-1395 · The Agent Memory Architecture Stack — When Your Agent Wakes Up With No Memory

Your agent just spent 4 hours solving a complex bug. Tomorrow it starts from scratch — no memory of the fix, no record of the decisions made, no continuity with what came before. The session ended and the knowledge evaporated. This is not a prompt engineering problem. It is an architectural one: **agents are stateless by default, and context windows don't solve it**.

S-1393 (orchestration patterns) covers how agents chain steps. S-1394 (token budgets) covers cost control before execution. Neither addresses the core failure mode: after the session ends, nothing persists.

## Forces

- **Context windows have a ceiling that degrades performance.** Models start deprioritizing critical information once context exceeds 60% capacity, even when the answer is present in the window. A single 1M-token inference on Claude costs ~$15 — full history is expensive and slow.
- **Checkpointing and semantic memory serve different purposes.** Teams conflate conversation resumability (checkpointing) with knowledge retention (semantic memory), leading to either full-history dumps or total amnesia.
- **Every persistence layer is a new attack surface.** LangGraph's SQLite checkpointer had a documented SQL injection vulnerability (CVE chain to RCE, disclosed Dec 2025). Checkpoint databases store serialized agent state — if compromised, the attacker owns the memory.
- **The operational complexity curve is steep.** SQLite works for single agents. Postgres adds multi-node but requires TTL management and schema migrations. Redis adds hot-path speed but introduces a second system to monitor. Hybrid architectures compound failure modes.

## The Move

The field has converged on a **two-tier, four-layer memory architecture**:

### Two tiers (what to persist)

1. **Checkpoint store** — conversation continuity within and across sessions. Stores full graph state per turn so the agent can resume from where it left off. Write-heavy, low-latency required.
2. **Semantic memory** — cross-session knowledge. Facts extracted from conversations, user preferences, learned patterns. Query-heavy, tolerates higher latency.

### Four layers (how to think about the data)

- **Working memory** — the active scratchpad. Structured object tracking current task, step count, tool outputs. Lives in the graph state during execution. Gone when the session ends unless checkpointed.
- **Episodic memory** — what happened and when. Conversation logs, decision traces, failure events. Timeline-anchored, sparse, growing. This is the layer most teams skip.
- **Semantic memory** — facts the agent knows. Customer tier, API endpoints, domain rules. The agent equivalent of a knowledge base. Usually backed by a vector store.
- **Procedural memory** — how the agent acts. Prompts, tool definitions, system instructions. Relatively static; updated on deploy.

### Backend selection (SQLite → Postgres → Redis)

```
# Single agent, local dev: SQLite checkpointer
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
# ~2–8 KB per step. No setup. Crashes = restart from scratch.

# Production, multi-agent: Postgres checkpointer
from langgraph.checkpoint.postgres import PostgresSaver
conn = psycopg.connect("postgresql://user:pass@host:5432/agent_state")
saver = PostgresSaver(conn)
saver.setup()  # run migration once
# Scale: hundreds of concurrent threads. Add TTL cleanup.

# High-throughput: Redis hot path + Postgres cold path
# Write-through: every checkpoint → Redis (sub-ms read) + Postgres (async)
# On crash recovery: Redis first, backfill from Postgres if needed
# Cost at scale: ~500 MB Redis + ~2 GB Postgres disk vs 8–12 GB Redis-only
```

### Semantic memory (cross-session)

- **Mem0** (59K+ GitHub stars) — memory-as-a-service layer. 91% lower p95 latency than full context on LoCoMo benchmark. +26% accuracy vs OpenAI Memory. Multi-session, multi-user, self-hostable or cloud. Graph variant available for entity relationships.
- **Zep** — graph-centric with temporal validity dates per fact (`valid_at`/`invalid_at`). Precomputes entity summaries asynchronously. Better for knowledge graph richness; Mem0 wins on speed/cost.
- **Hmem** (Show HN, 2025) — hierarchical SQLite for coding agents via MCP. Project/lesson/error/decision/milestone/skill categories. Favorites always loaded at depth 2. Auto-backup on corruption. Local-first, MIT licensed.
- **agentmemory** — MCP server with RAG benchmarks (95.2% R@5 on LoCoMo). Code-graph indexing for coding agents.

## Evidence

- **ArXiv paper (Apr 2025):** Mem0 formally evaluated on LOCOMO benchmark — +26% accuracy over OpenAI Memory, 91% faster p95 latency, 90% fewer tokens. Baseline limitations: small sample (10 conversations), OpenAI baseline hand-ingested. — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)
- **SitePoint engineering analysis (2025):** Redis-only with full conversation histories consumed 8–12 GB RAM at 1,000 agents. Postgres-only used ~2 GB disk with compression. Hybrid (Redis hot + Postgres cold) used ~500 MB Redis + ~2 GB Postgres, with sub-5ms hot path and 92%+ precision@5. — [sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres](https://www.sitepoint.com/state-management-for-long-running-agents-redis-vs-postgres/)
- **Hacker News (Mar 2025):** Hmem Show HN thread — developers specifically cited context dilution within long sessions (early context compressed out before session ends, not just at session boundary) as the primary pain point, not cross-session amnesia. — [HN #47103237](https://news.ycombinator.com/item?id=47103237)
- **Check Point / CSA (Dec 2025 – Jun 2026):** LangGraph SQLite checkpointer had SQL injection via metadata filter key (GHSA-9rwj-6rc7-p77c, high severity). Chained to RCE in unpatched versions before langgraph 1.0.10 / langgraph-checkpoint-sqlite 3.0.1. — [GitHub Advisory](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-9rwj-6rc7-p77c)

## Gotchas

- **Episodic memory is not optional in production.** Most teams build checkpointing and semantic retrieval, then wonder why agents repeat past mistakes. Episodic memory (what happened, when, with what outcome) is what closes the loop between past sessions and current decisions. Without it, the agent has facts but no history.
- **The "hybrid" architecture sounds elegant but introduces consolidation lag.** The background worker that syncs Redis → Postgres can fail silently. Set up monitoring for lag metrics and alerts, not just for the happy path.
- **Checkpoint databases are code execution surfaces.** Treat them like any untrusted input. Validate thread IDs, sanitize metadata filter keys, monitor for abnormally large checkpoint blobs, and use auditd to watch the database file. The CVE history is a warning, not an anomaly.
- **Context window overflow happens inside a session, not just across sessions.** At 60% context capacity, models start burying critical information even within a single long conversation. Budget the context window like you budget memory: pre-allocate working memory slots and compress episodic history before the model starts losing signal.
