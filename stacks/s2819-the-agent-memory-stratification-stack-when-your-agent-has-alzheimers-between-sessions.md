# S-2819 · The Agent Memory Stratification Stack — When Your Agent Has Alzheimer's Between Sessions

Your agent crushes it in testing — 50-turn reasoning chains, tool chains, perfect outputs. Then the user closes the browser, reopens it tomorrow, and the agent is a stranger. It re-asks questions it already answered, ignores preferences it set, and starts research it already completed. The fix isn't a bigger context window. It's a memory system that separates what the agent needs *right now* from what it learned *last month*.

## Forces

- **Context windows are a floor, not a solution.** Even 200k–2M token windows overflow on complex tasks, cost too much to fill with history, and models still struggle with contradiction resolution when earlier facts conflict with later updates (per the BEAM benchmark).
- **Checkpointing and memory are different problems.** Checkpointing saves *execution state* so a crashed agent resumes mid-step. Memory saves *learned facts and preferences* so the agent doesn't relearn who the user is. Teams conflate these and build neither well.
- **The naive approach (log everything to vector DB) is actually harmful.** Naive vector search returns temporally stale results — it may surface a fact about a cancelled subscription before the update. The field has converged on a two-tier architecture for this reason.
- **Every framework has a different philosophy.** Mem0 extracts facts passively into a vector store. Letta exposes editable memory blocks as an agent runtime. Zep uses temporal knowledge graphs that track when facts were true. LangMem is LangGraph-native. Picking the wrong one for your use case adds latency, cost, and brittleness.

## The Move

Split agent memory into three tiers, stored in separate systems matched to their access patterns:

- **Working memory (ephemeral):** The live conversation context — last N messages in a sliding window. Stored in Redis with TTL eviction. Written synchronously on every turn. No persistence across sessions; rebuilt from the long-term store on session resume.
- **Episodic memory (checkpointed):** The agent's execution state at each step — thread_id, current node, tool call history, mid-task variables. Stored via LangGraph's PostgresSaver or Redis checkpointer. Survives crashes; enables resume-from-breakpoint, not user-preference recall.
- **Semantic memory (persistent):** Facts, preferences, entity relationships extracted from conversations. Stored in a vector DB (Pinecone, Qdrant) or knowledge graph (Zep/Graphiti), namespaced per user. Written asynchronously by a background worker — the agent never blocks on a memory write. Retrieved on every turn and prepended to the system prompt.

**The critical write path:** On every user message, the agent reads both working memory (Redis) and semantic memory (vector store) and merges them into context. The write path fires in the background: a summarizer model or extraction pipeline condenses recent conversation turns into facts, deduplicates against existing memories, and upserts. This decouples memory writes from response latency — the agent replies while memory settles.

**The retrieval path:** On session resume, the agent retrieves the last checkpoint (for mid-task resumption) and the top-K semantically relevant memories (for preference/context continuity), then reconstructs working memory from the checkpoint's message history.

## Evidence

- **Benchmark: LongMemEval (Wu et al., 2025) — 500 personal-chat questions across 6 categories including multi-session reasoning and knowledge update.** Letta scored 83.2% (S-Tier, 50 sessions); Zep scored 63.8% via its temporal knowledge graph approach. A-Mem (Xu et al., 2025) scored in the same range. This is the primary published benchmark for agent long-term memory quality.
- **Production metric: Mem0 processing 1 billion tokens/day across its customer base** as of early 2026, with +26% accuracy improvement over OpenAI's built-in memory on the LOCOMO benchmark. Async memory writes are now the default (`async_mode=True`) after synchronous writes were identified as blocking the response pipeline in production.
- **HN Show HN: "An experiment in giving coding agents long-term memory"** — a developer implemented persistent memory for a coding agent using a vector store, showing concrete evidence that agents benefit from memory of past tasks and preferences, not just session context.
- **LangGraph production pattern (markaicode.com, 2026):** TypedDict for development; Pydantic BaseModel for production state. PostgresSaver for checkpoint persistence across server restarts. The pattern: `config = {"configurable": {"thread_id": "user-session-9527"}}` — thread_id as the primary key, composable with `{user_id}:{session_id}` for multi-device resume. LangGraph's Redis integration provides both thread-level persistence and cross-thread memory in a single store.

## Gotchas

- **Don't use a vector store as your only memory layer.** Vector similarity search doesn't handle temporal contradiction — it will return facts about the old state of something that has since changed. Use Zep-style temporal invalidation or track timestamps on every memory record.
- **Async summarization is eventually consistent.** If the summarizer queue crashes, you lose the last N minutes of episodic detail. For high-stakes tasks, write a synchronous "memory marker" at key decision points that survives queue failures.
- **Context window size is irrelevant above ~50K tokens for memory quality.** The BEAM benchmark found that models' memory quality plateaus well before context windows fill — what matters is what you extract and store, not how much you can theoretically fit.
- **Checkpointing alone doesn't give you user memory.** LangGraph checkpoints save execution state (what node you're in, what variables are set). They don't save "this user prefers concise responses" or "we already tried option X." Those need semantic memory extraction, which is a separate pipeline.
- **Mem0's passive extraction is token-efficient but opaque.** The extraction model decides what matters; the agent can't guide it. If your use case requires the agent to explicitly flag "remember this," you need Letta's editable memory blocks, not Mem0's passive extraction.
