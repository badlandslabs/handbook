# S-2699 · The Two-Tier Memory Stack — When Your Agent Forgets Everything Between Sessions

You shipped a great demo. Users came back the next day and the agent greeted them like a stranger. Every session starts from zero. Every past interaction — gone. The fix isn't a bigger context window; it's a two-tier memory architecture that's now the production standard.

## Forces

- **Context windows reset per request** — no matter how large, every API call starts blank, so long conversations and cross-session continuity require external state
- **Performance vs. comprehensiveness** — dumping full history into every prompt is expensive and slow; agents need selective retrieval, not a fire hose
- **Write latency vs. response latency** — synchronous memory writes block the agent's reply; production systems need async condensation that doesn't stall the user
- **One store doesn't fit all** — short-term session state (TTL-based, fast) and long-term episodic/semantic memory (vector-indexed, queryable) have fundamentally different access patterns

## The Move

Split memory into two physically distinct stores with explicit read/write paths:

**Tier 1 — Ephemeral session buffer (Redis, TTL-based)**
- Stores raw conversation turns, tool call results, and intermediate state for the live session
- Agent reads from this buffer on every turn — it's the working memory
- Writes go here synchronously; the agent never waits for memory
- TTL eviction (e.g., 24–72h) auto-cleans stale sessions without manual cleanup

**Tier 2 — Long-term vector store (Pinecone, Weaviate, or Qdrant, namespaced per user)**
- Stores condensed summaries of past sessions, key facts, and semantic knowledge
- A background worker (Celery task, cron, or queue-driven) asynchronously condenses the session buffer into this store — never on the hot path
- Agent retrieves relevant history via semantic search on each turn, limited to top-K results to stay within context limits

**The read path on every turn:**
```
agent turn starts
  → read Redis session buffer (recent turns, tool results, working state)
  → read vector store (top-K semantically relevant past episodes, user facts)
  → merge into prompt context
  → agent responds
  → write turn to Redis buffer (sync)
```

**The write path (background):**
```
session ends or buffer threshold reached
  → queue condensation job
  → summarize buffer into episodic + semantic chunks
  → embed and upsert to vector store (per-user namespace)
  → optionally prune Redis buffer
```

## Evidence

- **Redis engineering blog:** Documents the two-store pattern explicitly — Redis as ephemeral buffer with TTL, paired with a vector store for semantic retrieval, citing that "three components = three failure domains" as the key tradeoff to manage. Recommends Redis Stack for hybrid vector + operational search in one system to reduce moving parts. — [Redis.io — AI Agent Memory: Building Stateful AI Systems](https://redis.io/blog/ai-agent-memory-stateful-systems/)

- **Markaicode production design guide (July 2026):** Gives the full two-tier blueprint for 100K+ conversations using LangChain + Redis + Pinecone. States the threshold: "under ~10K conversations, skip the vector store — a single Redis instance with TTL eviction covers most support agents." Details the async condensation pipeline and namespaced user isolation in Pinecone. — [markaicode.com — LangChain Agent Memory Architecture: Production Design](https://markaicode.com/architecture/ai-agent-memory-architecture)

- **Let's Data Science taxonomy (March 2026):** Defines the four memory types agents need — short-term (current conversation), working (active reasoning scratchpad), episodic (past events), and semantic (learned facts) — and maps each to a storage technology. Notes that even 200K-token context windows don't solve cross-session persistence because "context windows reset with each API request." — [letsdatascience.com — AI Agent Memory Architecture: From Zero to Production](https://letsdatascience.com/blog/ai-agent-memory-architecture)

## Gotchas

- **Don't write to the vector store synchronously** — summarization + embedding is too slow for the user's response latency budget; queue it and accept eventual consistency
- **Namespace isolation is not optional** — use per-user/perspective namespaces in the vector store; without it, semantic search bleeds context between users and is a privacy violation
- **Buffer summarization destroys detail** — if you need verbatim recall (audit logs, compliance), keep raw turns in an object store (S3) and summarize for the vector store separately; the summary is lossy
- **TTL misconfiguration is silent data loss** — set Redis TTL too short and users lose recent context; too long and you accumulate expensive, irrelevant memory; 24–72h is the common range, tune to your use case
