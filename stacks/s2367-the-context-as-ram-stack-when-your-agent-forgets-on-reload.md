# S-2367 · The Context-as-RAM Stack

When your agent runs for hours then makes a decision it would never have made in the first hour — the problem is not the model. You are using the context window as a database.

## Forces

- The context window is volatile — it clears at session end, degrades under load, and costs more per token the fuller it gets
- "Lost in the middle" is real: models perform *worse* when relevant facts are buried mid-context than when they are absent entirely
- Teams that treat the context window as storage end up with agents that are stateless by default and forgetful by design
- Context drift — silent quality degradation before the window fills — kills agents before the limit ever hits
- The three standard mitigations (summarize, RAG, truncate) each have failure modes that only surface after extended runtime

## The move

**Treat the context window like RAM: fast, volatile, working storage — not a database.**

The consequence of this reframe changes every architectural decision:

- **Store persistently what must survive restarts.** User preferences, session history, extracted facts, learned policies. These go in a durable store (Postgres, SQLite, Redis, a vector DB). They are loaded *into* context at session start, not stored *in* context.

- **Treat summaries as a cache, not a source of truth.** Summarization is lossy. Mem0 claims 26% higher accuracy than OpenAI memory on LOCOMO benchmarks — but Letta disputes the methodology, and by hour 6-7 of continuous runtime, a summary that is factually accurate about *what happened* still produces an agent making wrong *decisions* because implicit state (intent, priority, partially-resolved reasoning) doesn't survive compression.

- **Load only what is relevant at decision time.** Semantic retrieval at session start is not enough — episodic memories (what happened in past sessions), active task state, and retrieved facts need to be present *at the right moment*. This requires tiered retrieval: working memory for in-flight state, episodic for session history, semantic for durable facts.

- **Compress before the LLM sees it.** Tools like Context Gateway (97 HN points) compress agent context *before* it hits the model. This is the pre-RAM compression layer — reducing what needs to be in-context rather than managing what is. The compression itself is a lossy operation and must be evaluated.

- **Distinguish checkpointing from memory.** LangGraph's checkpointer saves *state snapshots* (thread-level, for replay and resume) — not *knowledge*. A LangGraph practitioner in production reported 50 rows per graph execution in Postgres; the checkpointer is not a memory system. Forgetting this distinction means accumulating state without gaining intelligence.

## Evidence

- **Blog post (Mem0, 2026):** "The context window is RAM, not storage. Most production agent failures are not model failures but memory architecture failures." — documented three specific ways context window behaves like RAM: volatility (clears at session end), capacity effects (degrades before full), and access cost (full re-read every call). — https://mem0.ai/blog/context-window-is-ram-not-storage-why-most-agent-failures-happen-how-to-fix-them-in-2026

- **Research blog (Redis, 2025):** GPT-3.5-Turbo scored *worse than its closed-book baseline* in multi-document QA when the answer was buried mid-context. Confirmed that stretching context window size does not solve agent memory — it solves a different problem. — https://redis.io/blog/why-bigger-context-window-wont-fix-agent-memory/

- **Reddit r/AI_Agents (2mo ago):** Long-running agent practitioner reporting that by hour 6-7, summarization is factually accurate but implicit state (decision rationale, partially-resolved reasoning, priority signals) does not survive compression — agent starts making decisions it would not have made at hour 1. — https://www.reddit.com/r/AI_Agents/comments/1tqo0ua/what_actually_happens_to_your_context_window/

- **Show HN (Context Gateway, 2025):** 97 points. Tool that compresses agent context before it reaches the LLM, specifically targeting the token-cost and quality-degradation problems that grow with session length. — https://news.ycombinator.com/item?id=47367526

- **Research blog (Zylos Research, Feb 2026):** 65% of enterprise AI failures in 2025 attributed to context drift or memory issues — not model quality. Names three specific failure modes of the three standard mitigations (summarize, RAG, truncate) that only appear in extended runtime. — https://zylos.ai/research/2026-02-28-ai-agent-context-compression-strategies/

- **LangChain forum (Sep 2025):** Production practitioner reporting that LangGraph checkpointing creates ~50 rows per graph execution in Postgres — clarifying that checkpointing (state snapshots for replay) is not the same as agent memory (persistent knowledge across sessions). — https://forum.langchain.com/t/separate-long-term-memory-and-checkpointing/1668

## Gotchas

- **"Bigger context window" is not a memory solution.** Adding tokens buys time but does not solve volatility, degradation under load, or "lost in the middle." The Redis source has a specific benchmark showing GPT-3.5 performs worse with relevant context in the wrong position.

- **Summary accuracy ≠ decision correctness.** Summarization preserves facts but not intent, priority, or implicit reasoning state. Extended-runtime practitioners confirm this is the dominant failure mode past hour 6.

- **Checkpointing ≠ memory.** LangGraph's checkpointer saves state for replay/resume. It is not a durable knowledge store. Teams that conflate the two build agents that survive restarts but forget everything.

- **Compression is also lossy.** Pre-LLM compression tools (Context Gateway, ACON) reduce token cost and context size, but the compression itself discards information. Evaluate the output quality, not just the compression ratio.
