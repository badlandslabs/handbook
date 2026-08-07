# S-2266 · The Memory Layer Stack

[Your agent reasons beautifully inside a single session — then forgets everything the moment it ends. The next call starts from scratch. Memory layers turn that $0.01 stateless chatbot into a $0.10 stateful agent that compounds knowledge across weeks.]

## Forces

- Context windows handle intra-session continuity but cost proportionally more tokens with each retrieval pass — naively stuffing chat history is a latency and cost death spiral
- Naive vector search on past conversations returns semantically similar results but ignores temporal ordering and fact validity — "the meeting is at 3pm" from March is ranked the same as "the meeting is at 2pm" from yesterday
- Writing every interaction synchronously to storage adds latency directly to the response pipeline — the user feels it
- Cross-session identity and memory staleness (when does a stored fact become outdated?) remain genuinely hard unsolved problems
- Security risk: memory poisoning — adversarial content planted in memory can activate silently across future sessions

## The Move

The field converged in 2025-2026 on a layered memory architecture. Implement it in three tiers:

- **Working memory** — the context window. Keep it lean. Use compressed summaries rather than raw transcripts; aim for under 8K tokens of active context.
- **Episodic memory** — past conversations, completed tasks, prior decisions. Store as structured events with timestamps, not raw text chunks. Embed with a model that preserves temporal ordering.
- **Semantic memory** — extracted facts, learned preferences, institutional knowledge. Store as structured key-value facts (subject, predicate, object, valid_from, valid_to) not raw text. This is what lets the agent answer "what did we decide about X three weeks ago?"

On retrieval: hybrid search (dense embeddings + BM25 keyword overlap) outperforms either alone. agentmemory measured 2.2× better precision vs grep baselines with hybrid retrieval, achieving 95.2% recall@5 on LongMemEval.

On writes: always use async/non-blocking writes. The user's response should not wait for memory persistence. The most common production footgun is synchronous memory writes adding 200-400ms of felt latency.

On forgetting: implement time-to-live and staleness eviction. Facts have validity windows. "User prefers dark mode" from 2023 may no longer apply. Track `valid_from` / `valid_to` timestamps on facts, not just on when they were stored.

## Evidence

- **Benchmark comparison:** Mem0 scores 92.5 on LoCoMo (1,540 questions) and 94.4 on LongMemEval at ~6,900 tokens per query — versus 25,000+ for full-context approaches. The gains are sharpest on temporal reasoning (+29.6 points) and multi-hop (+23.1 points). — [Mem0 Benchmark Report, July 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Production volume:** Mem0 processed 186 million API calls in Q3 2025 and raised $24M (Series A, October 2025), became the exclusive memory provider for AWS Agent SDK. These are real deployment numbers, not projections. — [TechCrunch via AgenticWire](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory)
- **OSS adoption:** agentmemory reached 26.6k GitHub stars (July 2026) serving Claude Code, Cursor, Codex CLI, and 17+ other coding agents. The pattern of persistent cross-session memory for coding agents is now mainstream — [GitHub rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)

## Gotchas

- **Async writes by default** — synchronous memory writes block the response. Set `async_mode=True` in production.
- **Don't store raw transcripts** — extract facts, not conversations. Raw transcript retrieval precision degrades fast as history grows; extracted facts are 2-5× more token-efficient.
- **Memory poisoning is real** — adversarial content planted in memory can activate silently in future sessions. Sanitize untrusted memory sources before retrieval; add a validation layer between memory reads and the context window.
- **Three frameworks, three trade-offs** — Mem0 (fastest drop-in, vector-first), Zep/Graphiti (temporal knowledge graph for evolving facts), Letta (OS-tiered memory paging for full runtime state). Don't mix paradigms without understanding the conflicts.
- **Eval is harder than it looks** — an agent with 75% per-trial reliability has only 42% chance of passing three trials in a row. Measure reliability, not just capability. — [LangChain State of AI Agents 2026 via Mastra](https://mastra.ai/articles/ai-agent-evaluation)
