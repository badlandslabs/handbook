# S-2277 · The Layered Memory Stack — When Your Agent Forgets Everything Between Sessions

_You built an agent that works in a demo. Three days later a user asks a follow-up and it greets them like a stranger. The agent has no memory of the prior session, no way to resume a crashed run, and no layer between "raw context window" and "starting from zero."_

## Forces

- **Context window is finite but compounding knowledge is infinite** — dumping everything into the prompt works until it doesn't, then it catastrophically degrades (the "Lost in the Middle" effect where models systematically underweight the center of long contexts).
- **Stateless feels safe but is a dead end** — every agent deployment starts stateless; the teams that win are the ones that figured out how to layer memory without blowing up token costs or creating consistency hazards.
- **Memory and storage are different concerns** — remembering _what happened_ (episodic) vs. remembering _what you know_ (semantic) vs. holding _what you're working on right now_ (working) are three distinct engineering problems with three distinct solutions.
- **Checkpointing and memory are often conflated** — checkpointing is about fault tolerance and resumability; memory is about learned knowledge and personalization. Most teams only solve one.

## The move

Design a layered memory architecture where each layer has a clear responsibility and distinct storage backend:

- **Working memory** — in-flight state during a single run. Use the agent framework's built-in state store (LangGraph's `checkpointer`, CrewAI's memory module). Back it with an in-process dict for speed during the session; nothing persists here across sessions.
- **Episodic memory** — a log of what happened and when. Store as structured records (JSON/dict per event) in a durable store (PostgreSQL, SQLite, or Redis). Include timestamps, agent identity, tool calls made, and outcomes. Query this on session resume to reconstruct context without re-running LLM calls.
- **Semantic memory** — what the agent "knows" about users, preferences, and domain facts. Store as embedded vectors in a vector database (Pinecone, Qdrant, pgvector, Chroma). Retrieve via RAG on each turn to inject relevant facts without bloating the system prompt. Mem0 has become the de facto OSS abstraction here, with 62.6k GitHub stars and ECAI 2025 publication.
- **Procedural memory** — how the agent should behave in recurring situations. Encode as system prompt fragments, tool definitions, or agentic RAG pipelines that retrieve "playbook" snippets based on the current goal type.

**Thread-based session routing**: Assign every user conversation a stable `thread_id` (user ID, UUID, or session token). Pass this to the checkpointer so each user's state lane is isolated and resumable. A LangGraph + Redis checkpointer pair handles this at production scale; a single SQLite file works for low-volume agents.

**Checkpoint on every step boundary**: Persist state after every tool call or LLM response, not just at the end of a run. This is what enables true resume-from-failure. LangGraph's `MemorySaver` for dev, `PostgresSaver` or `RedisSaver` for production — never ship with `MemorySaver` in production, because pod restarts wipe it.

**Staleness management**: Memory that never expires accumulates outdated facts. Add TTLs to episodic records (e.g., auto-expire after 30 days of inactivity) and re-embed semantic memory on a cadence for frequently-updated domains.

## Evidence

- **Mem0 benchmark (ECAI 2025):** State-of-the-art memory retrieval achieves 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query — versus ~26,000 tokens for full-context approaches. Biggest gains in temporal reasoning (+29.6 points) and multi-hop reasoning (+23.1 points). Mem0 integrates with 21 frameworks and 20 vector stores. — [mem0.ai](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **LangGraph production users:** LinkedIn uses LangGraph with checkpoint-based persistence for an AI recruiter agent that automates candidate sourcing, matching, and messaging. AppFolio saved 10+ hours/week with a property manager copilot. Both rely on thread-level state isolation to keep concurrent users' conversations independent. — [LangChain Blog](https://www.langchain.com/blog/is-langgraph-used-in-production)
- **Redis checkpointer v0.1.0 redesign (Aug 2025):** After months of real-world LangGraph usage, the Redis team shipped a performance-focused rewrite that eliminated redundant serialization and leveraged Redis' native data structures. The migration guides (`MIGRATION_0.1.0.md`, `MIGRATION_0.2.0.md` in the repo) document the breaking changes teams hit when moving from the PostgreSQL reference implementation — confirming this is a real production pain point, not a theoretical one. — [Redis Developer GitHub](https://github.com/redis-developer/langgraph-redis)
- **GoCodeo framework survey (Jul 2025):** Evaluated memory/state handling across leading agent frameworks, finding that working memory is universally handled but episodic and semantic memory support varies wildly. The four critical use cases driving memory investment: long-horizon tasks, multi-agent coordination, personalized interactions, and tool invocation history tracking. — [GoCodeo](https://www.gocodeo.com/post/evaluating-memory-and-state-handling-in-leading-ai-agent-frameworks)
- **Understanding Data / Agent Memory Patterns:** Documents checkpoint/resume as a distinct concern from memory — the core use case being human-in-the-loop workflows where approval latency means an agent cannot hold a connection open, and fault tolerance where a crash at 80% completion should resume, not restart. — [understandingdata.com](https://understandingdata.com/posts/agent-memory-patterns)

## Gotchas

- **"Lost in the Middle" is real and non-obvious:** Chroma's 2025 "Context Rot" research confirms LLM performance degrades non-uniformly across long contexts even within stated limits. Longer context does not mean better recall. RAG-based retrieval that injects only relevant facts outperforms brute-force context injection.
- **MemorySaver in production is a production outage waiting to happen:** Every LangGraph team discovers this the hard way. MemorySaver is for local dev only — it stores state in-process and loses everything on restart. Swap to a persistent checkpointer (Redis, Postgres) before the first deploy.
- **RAG is not memory:** Teams conflate retrieval-augmented generation (RAG) with agent memory. RAG finds documents relevant to a query. Memory remembers preferences, prior interactions, and accumulated context. You need both — and they need different storage strategies.
- **Cross-session identity is unsolved:** The Mem0 2026 benchmark report flags cross-session identity as one of the hardest open problems. If the same user appears on multiple devices or sessions, tying episodic records to a stable identity requires explicit user authentication — you can't infer it reliably from conversation content alone.
- **Memory staleness creates hallucination surface area:** If semantic memory is updated but episodic records are not, the agent has contradictory histories it will blend into confident-sounding but wrong claims. Version or flag episodic records when semantic facts are updated.
