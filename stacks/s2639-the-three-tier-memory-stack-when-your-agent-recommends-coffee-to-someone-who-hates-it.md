# S-2639 · The Three-Tier Memory Stack — When Your Agent Recommends Coffee to Someone Who Hates It

You can tell an agent "I don't like coffee" in one session and get an espresso recommendation in the next. The LLM isn't broken — it reasoned correctly from the context it was given. The problem is that context window resets on every API request, and most teams never built anything to fill it. That's the memory architecture gap: stateless inference meets stateful use cases.

## Forces

- **Stateless inference is by design.** LLM APIs have no persistent state — every call starts fresh. A bigger context window makes forgetting slower, not impossible.
- **Teams conflate three things.** Chat history (chronological transcript), session replay (re-execution data), and durable memory (user facts) are treated as interchangeable, so they end up storing too much noise and too little signal.
- **The retrieval penalty compounds.** Naive RAG on conversation history produces noisy, structureless recall. Vector similarity finds semantically adjacent text, not facts that should govern decisions.
- **Memory hygiene is an afterthought.** Without explicit promotion and expiration rules, memory grows unbounded — eventually drowning signal in trivia.

## The move

Implement a **three-tier memory architecture** that separates working state, durable facts, and governance:

**Tier 1 — Session State (working memory):**
- What the agent is actively reasoning about right now
- Full message history, tool outputs, intermediate reasoning
- Stored in process memory or Redis during the session
- TTL-based expiration — discard when the conversation ends
- For LangGraph: attach a checkpointer (SQLite for dev, Postgres for prod) and thread each conversation by `thread_id`

**Tier 2 — Durable Memory (persistent facts):**
- User preferences, project context, standing rules, extracted facts
- Stored in a structured backend chosen for your retrieval pattern:
  - **Mem0** (hybrid KV + graph + vector, 63K+ GitHub stars): automatic fact extraction and semantic retrieval, new April 2026 algorithm scored 92.5 on LoCoMo benchmark
  - **SQL/relational** (Gibson AI's Memori): structured tables, queryable with WHERE clauses, avoids noisy vector similarity at scale
  - **Postgres + pgvector**: one database, full-text + semantic search, ACID guarantees
  - **SQLite + sqlite-vec** (SmartChannels): zero-dependency local-first, viable for single-server deployments
- Facts are promoted from Tier 1 after confirmation or explicit extraction by the LLM itself

**Tier 3 — Memory Hygiene (governance layer):**
- What gets promoted, what expires, what gets corrected
- Explicit rules: "never store PII", "preferences override facts", "expire project facts after 30 days of inactivity"
- LLM-assisted: the agent periodically reviews its own memory and removes stale entries
- Redis Agent Memory implements automatic summarization of older events and background extraction of durable facts

**The retrieval pattern:**
- On every new message, fetch durable facts by user ID and thread ID
- Merge into the system prompt or tool context, weighted by recency and confidence
- Do not prepend raw conversation history — retrieve specific facts

## Evidence

- **GitHub README / arXiv paper:** Mem0's hybrid datastore (KV for facts, graph for entity relationships, vector for semantic similarity) with benchmark data showing LoCoMo score improved from 71.4 to 92.5 with the April 2026 algorithm update at 7.0K tokens and 0.88s p50 latency — [Mem0 GitHub](https://github.com/mem0ai/mem0), [arXiv:2504.19413](https://arxiv.org/html/2504.19413v1)
- **HN discussion (201+ points, Sept 2024):** Multiple teams describe switching from pure vector RAG to hybrid or SQL approaches for agent memory. Gibson AI's Memori HN post argues SQL tables outperform graphs at scale for fact retrieval — [HN Show HN: Mem0](https://news.ycombinator.com/item?id=41447317), [HN: SQL for AI Memory](https://news.ycombinator.com/item?id=45329322)
- **Engineering blog / GitHub:** LangGraph's three-tier checkpointer system (InMemorySaver for tests, SqliteSaver for dev, PostgresSaver for production) with `thread_id`-based state threading. SmartChannels uses sqlite-vec + FTS5 for zero-dependency cross-channel memory — [LangGraph persistence guide](https://langgraphjs.guide/persistence), [SmartChannels README](https://github.com/smartchannels/smartchannels)
- **Engineering blog:** Redis Agent Memory provides session-scoped working memory with automatic summarization of older events and background extraction of durable facts. Red Hat's emerging tech team formalizes the "model + harness + memory + environment + evolution" capability equation — [Redis Agent Memory](https://redis.io/agent-memory), [Red Hat: Architecting Memory for AI Agents](https://next.redhat.com/2026/06/01/from-context-to-dreams-architecting-memory-for-ai-agents/)

## Gotchas

- **Never prepend raw chat history to the context.** It wastes tokens and buries facts. Extract facts into Tier 2, then retrieve selectively into context.
- **thread_id is the resume key, not a magic string.** LangGraph checkpointers use `thread_id` to scope state — but if you lose the thread_id, you lose the conversation. Persist it alongside the session.
- **SQLite checkpointers don't survive pod restarts.** Fine for local dev; use Postgres for anything that redeploys. Redis trades durability for speed — if it restarts mid-session, your agent's soul is gone.
- **Memory without hygiene becomes a liability.** Unbounded memory growth degrades retrieval quality. Explicit promotion rules and periodic cleanup are required, not optional.
