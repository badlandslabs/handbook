# S-2160 · The Memory Stack — When Your Agent Asks the Same Question It Answered Yesterday

Your agent ran for two hours yesterday. It researched the user's codebase, made architectural recommendations, wrote and tested three API endpoints, and summarized findings in a report. Today the user opens a new session and the agent greets them like a stranger. It doesn't remember the project, the decisions made, or the constraints agreed on. This is not a model quality problem. Every LLM is stateless by design. The fix is an explicit memory architecture — and "stuffing the context window with conversation history" is not one.

## Forces

- **Context windows are workspace, not warehouse.** A 1M-token context sounds generous until one hour of agent work consumes it. Even if it didn't, stuffing raw conversation degrades reasoning — the signal-to-noise ratio drops as history grows.
- **Naive vector search returns temporally stale results.** A fact from three weeks ago about a cancelled feature ranks the same as yesterday's decision. Without temporal awareness, retrieval is a coin flip.
- **Four memory types compete for the same budget.** Working memory (current context), episodic memory (what happened), semantic memory (what it means), and procedural memory (how the agent should behave) each need different storage and retrieval strategies — and most teams conflate them.
- **Multi-agent systems amplify forgetfulness.** An agent that forgets between sessions is a solvable problem. A researcher agent and a writer agent that both forget the same shared context creates silent incoherence nobody errors out on.

## The Move

Separate memory into tiers with distinct storage, retrieval, and eviction policies. Don't dump raw history into a vector store and hope retrieval works.

- **Distill, don't dump.** The dominant production pattern is a layered pipeline: raw conversation → atomic facts → scenario knowledge → core persona/preferences. This is the L0→L3 distillation used by TencentDB Agent Memory and the Mem0 extraction pipeline. It reduces token costs by up to 90% compared to stuffing full history.
- **Use the right store for each tier.** Working memory → context window (zero persistence). Episodic → append-only log with timestamps, queried by recency. Semantic → vector store with reranking (BM25 + dense + cross-encoder). Procedural → system prompt or fine-tuned weights.
- **Implement supersession, not just retrieval.** When a user changes their name, the old name should be hidden, not buried in the recall results. TencentDB Agent Memory calls this "supersession." Elasticsearch Labs built it into their agent memory layer with 0.89 R@10 recall.
- **Thread/session IDs unlock checkpointing.** LangGraph checkpointers (MemorySaver for dev, Postgres for prod) serialize full agent state per thread_id. Pass the same thread_id on resume and the agent picks up mid-graph. No re-explanation.
- **Context window is still your workspace.** Keep a small, always-present "core memory" in the context — the top N most-accessed facts, the current goal, the user's name. This is what MemGPT and Letta call "working memory." Everything else is retrieved on demand.

## Evidence

- **GitHub repo (TencentDB Agent-Memory, 13,953 stars):** Layered distillation pipeline (L0→L3) with four memory assets (Chat Memory, Skill, LLM-Wiki, Code-Graph) governed per-tenant. Built at Tencent scale. — [https://github.com/TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
- **Engineering blog (Elasticsearch Labs, 116 HN points):** Built agent memory on Elasticsearch with R@10 of 0.89 using hybrid retrieval (BM25 + dense vectors with RRF) + cross-encoder reranking + per-user DLS isolation. Categories: episodic (raw conversation), semantic (structured facts), procedural (agent instructions). — [https://www.elastic.co/search-labs/blog/agent-memory-elasticsearch](https://www.elastic.co/search-labs/blog/agent-memory-elasticsearch)
- **arXiv paper (Memori, 2026):** Treats agent memory as a data structuring problem, not a context scaling problem. Separate memory from the LLM provider to avoid vendor lock-in. Three architectural layers: advanced augmentation pipeline, structured memory storage, dynamic retrieval. — [https://arxiv.org/abs/2603.19935](https://arxiv.org/abs/2603.19935)
- **GitHub repo (agent-recall, MIT):** SQLite-backed knowledge graph for coding agents, extracted from a live system running 30+ concurrent agents at a digital agency. Scope hierarchy (same person has different roles in different projects) vs flat memory. — [https://github.com/mnardit/agent-recall](https://github.com/mnardit/agent-recall)
- **GitHub repo (agentmemory, 26,543 stars):** Persistent memory for Claude Code, Cursor, Gemini CLI, and any MCP client. Seeds sessions with context from previous work. — [https://github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **GitHub repo (Mem0, 55.7k+ stars):** Multi-level memory (User, Session, Agent) with 92.5 on LoCoMo benchmark, 94.4 on LongMemEval, 64.1 on BEAM at 1M tokens. Y Combinator S24. Extraction pipeline distinguishes signal from noise. — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)

## Gotchas

- **Don't use a vector store as your only memory.** Pure semantic search on raw conversation ignores temporal ordering, entity relationships, and contradictions. Hybrid retrieval (vector + keyword + reranker) significantly outperforms vector-only.
- **Temporal decay is non-negotiable in production.** Without it, the agent retrieves a cancelled feature spec alongside the active one. Add recency scoring to your retrieval pipeline.
- **Session IDs are not optional.** Without stable thread/session identifiers, checkpointing and cross-session memory have no key to store under. Design this in from day one.
- **Procedural memory needs a different mechanism.** You can't store "how to behave" in a vector store. System prompts, fine-tuned models, or explicit tool definitions carry procedural memory — don't try to retrofit it into episodic storage.
