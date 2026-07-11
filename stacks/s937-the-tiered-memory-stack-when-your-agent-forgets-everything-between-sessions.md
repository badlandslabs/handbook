# S-937 · The Tiered Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent works great in a demo. Then a user comes back the next day and it has no idea who they are, what they asked about last week, or why it approved a migration three days ago. LLMs are stateless by design — every API call starts from zero. Without an explicit memory architecture, your agent has no learning, no audit trail, and no personalization. It re-explains the same things on every first message. It repeats the same mistakes. It can't tell you why it did anything.

This is the agent memory problem: how do you give an agent durable, retrievable, and manageable context across sessions — without exploding your token budget or turning memory management into a second full-time job?

## Forces

- **Context windows are finite and expensive.** A 200K-token window sounds large until your agent needs 80K tokens of history just to be useful. Memory must be selective, not exhaustive.
- **Retrieval quality dominates storage quality.** Storing everything is easy. Storing the *right* things and retrieving them at the *right* moment is the hard part. A bad retrieval pollutes the context with noise.
- **Hot vs. cold trade-offs are non-obvious.** Putting everything in Redis is fast but expensive at scale. Putting everything in a vector store is cheap but slow and lossy. The right answer depends on read/write patterns, not technology preference.
- **LLM-managed paging beats manual management.** The agent deciding what to remember and when to forget (Letta/MemGPT's approach) consistently outperforms fixed retrieval pipelines — but adds complexity.
- **Memory has a lifecycle.** Memories go stale. Preferences change. GDPR requires deletion. Without lifecycle management, memory becomes liability.

## The move

Split memory into three tiers, each with a different storage technology, retrieval mechanism, and update frequency:

**Tier 1 — Hot memory (thread-level, pause/resume):**
- Store in Redis with TTL or PostgreSQL with thread_id key
- Holds the current conversation buffer + recent tool results
- Used for: pause-and-resume within a session, recovering from crashes
- Retrieval: direct key lookup, no semantic search
- Update: append-only during active session, flush on explicit end

**Tier 2 — Cold memory (cross-session, semantic):**
- Store in a vector database (Pinecone, Qdrant, Weaviate, or pgvector)
- Holds facts, preferences, learned patterns, project context
- Used for: personalization, continuity, learning from past sessions
- Retrieval: semantic similarity search on each turn, top-K results injected into context
- Update: after each session, summarize + embed new facts; run async

**Tier 3 — Document memory (persistent project knowledge):**
- Store as Markdown/JSON files, optionally with full-text index
- Holds human-authored context, system prompts, domain knowledge
- Used for: grounding, onboarding new sessions, explicit long-term facts
- Retrieval: keyword or semantic search on session start
- Update: explicit writes from the agent or human editors

**The LLM as the memory manager** (Letta/MemGPT pattern):
- Agent calls tool functions to read/write/erase memory tiers directly
- `core_memory_replace` → Tier 1, `archival_memory_search` → Tier 2, `archival_memory_insert` → Tier 2
- The model decides what to store and when to forget — analogous to OS virtual memory paging
- Prevents context overflow: when hot memory is full, the LLM autonomously consolidates to cold memory

**Retrieval triggers** — don't retrieve on every turn:
- Session start: load user profile + last conversation summary from Tier 2
- After tool calls: optionally store result in short-term buffer
- On explicit memory request: semantic search across Tier 2
- Cron/scheduled: nightly consolidation of Tier 1 → Tier 2 summarization

**Semantic caching layer** (optional but high-ROI):
- Before every LLM call, embed the query and check for similar cached responses
- Hit → return cached response; Miss → call LLM, cache result
- Teams report 70% cost reduction on repeated query patterns (StreamZero, 2026)

## Evidence

- **Reddit r/AI_Agents (primary source, 2mo ago):** Five production memory patterns documented — Daily Brief (cron + diff), Context Siphon (proactive injection from RAG), Preference Engine (structured user profiles), Learning Loop (feedback → memory update), and Session Resume (checkpointing). Author operated an AI memory layer for one year. — [URL](https://www.reddit.com/r/AI_Agents/comments/1t59qsk/5_patterns_i_keep_seeing_in_production_ai_agent)
- **Letta/MemGPT GitHub README (YC S24, active open-source):** OS-inspired memory hierarchy: core memory (context window, 2-4KB), recall memory (conversation log, pageable), archival memory (external vector store, unlimited). LLM controls all three tiers via function calls — model decides what to page in/out, not a fixed retrieval pipeline. 26.2K GitHub stars. — [URL](https://github.com/getzep/graphiti)
- **Mem0 GitHub README (YC S24):** Universal memory layer for AI agents. Claims +26% accuracy vs OpenAI Memory on LOCOMO benchmark, 91% faster responses, 90% fewer tokens. Supports Redis + vector DB backends. — [URL](https://github.com/mem0ai/mem0)
- **Zylos Research (2026-04):** "No single storage paradigm dominates. Production-grade agents increasingly rely on hybrid architectures that layer vector and graph storage, with an LLM-managed interface deciding what to store, retrieve, and forget." — [URL](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge/)
- **StreamZero blog (2026):** "Agents with proper memory achieve 3-5x higher task completion rates and 70% cost reduction via semantic caching." — [URL](https://streamzero.com/blog/posts/deep-dives-tools-technologies-architectures/memory-architecture-for-agents)
- **QubitTool Tech Blog (2026-05):** Three-layer production stack: Redis (hot/cache) + PostgreSQL (durable/conversational) + Vector DB (cold/semantic). WAL/CDC patterns for crash recovery. — [URL](https://qubittool.com/blog/ai-agent-memory-persistence-architecture)
- **Melvyn NQ Tan personal site (Sep–Dec 2025):** Deployed containerized ReAct agent with Redis + Mem0 on AWS. Multi-user isolation via separate agent containers with persistent user preferences. Redis cited as top choice for hot memory tier due to performance and vector search capability. — [URL](https://melvyn9.github.io/ai%20agents/llm%20systems/memory%20systems/redis/vector%20databases/docker/aws/2025/12/01/ai-agent)

## Gotchas

- **Don't store everything in Tier 1.** Raw conversation history grows unbounded. Without summarization, you'll pay for 100K tokens of history that compress to 500 useful facts.
- **Don't skip the validation layer on retrieval.** A semantic search that returns irrelevant memories is worse than no retrieval — it pollutes context with noise that looks authoritative. Run a relevance filter or reranker before injecting.
- **Memory becomes liability without lifecycle management.** Facts go stale, users revoke consent (GDPR), and outdated context causes the agent to act on superseded information. Implement TTLs, explicit invalidation, and periodic re-summarization.
- **Passive "store and remember" systems underperform active summarization.** Reddit commenter with extensive testing found that background LLM summarization of chat history (Claude.ai approach) significantly outperforms agents actively writing memories via tool calls — the agent's own tool-call discipline is weaker than a dedicated summarizer.
- **Hybrid Redis + vector DB adds operational complexity.** Two stores means two failure modes, two backup strategies, and consistency between them. If you can't operate two stores reliably, start with one (PostgreSQL with pgvector covers hot + cold for lower traffic).
