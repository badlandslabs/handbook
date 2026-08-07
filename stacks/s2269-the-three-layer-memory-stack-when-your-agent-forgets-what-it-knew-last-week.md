# S-2269 · The Three-Layer Memory Stack — When Your Agent Forgets What It Knew Last Week

Your agent had a 45-minute conversation with a user three weeks ago. The user mentioned they are vegetarian, care about code readability over speed, and prefer SQLite to Postgres for their side project. Today the same user asks for dinner recommendations and the agent suggests chicken. The user asks to continue the research from last time and the agent replies, "Sure, let's start fresh." The context window was flushed. The session is gone. Everything the agent "learned" is gone. Your agent has no long-term memory — not because the model can't hold it, but because the architecture never gave it a place to store it.

## Forces

- **Context windows are recall, not memory.** A 200K-token context window gives you room to stuff information — it does not give you persistence. Stuff 500K tokens when you only need 2K of relevant context and you pay $1 per request at $2/1M tokens. At 1,000 conversations per day, that is $1,000/day in wasted context. And the moment the session ends, everything resets.
- **All memory is not the same.** Storing every conversation verbatim hits the ceiling fast. Retrieving everything as undifferentiated text drowns the agent in noise. You need structure — but too much structure and you lose flexibility. The trade-off between storage granularity, retrieval precision, and cost is not solvable with a single layer.
- **Retrieval is the failure point, not storage.** Even teams that add a vector database often treat it as a magic dump-and-retrieve. Without temporal reasoning, entity linking, and multi-signal fusion (semantic + keyword + entity), the agent retrieves the wrong memory, the stale memory, or noise that looks like memory. A false memory is worse than no memory — the agent confidently acts on something that isn't true.
- **False memory compounds.** Without retention regularization, agents develop semantic drift — accumulated errors and contradicted facts that compound over sessions. One interaction says "user prefers dark mode." Two weeks later, a different interaction stores "user mentioned light mode once." Retrieval picks one. The agent acts on it. The user corrects. That correction is not stored back. The cycle continues.

## The move

Decompose agent memory into three layers with distinct roles, retention policies, and retrieval signals. Treat them as separate systems with defined interfaces, not as one big store.

**Layer 1 — Working memory (short-term, session-scoped):**
- Sliding window of the current conversation (last N messages or tokens)
- Temporary variables and tool outputs from in-progress tasks
- Discarded at session end; never persisted unless explicitly promoted
- Retrieved automatically on every turn; no search needed, just prepend

**Layer 2 — Episodic memory (mid-term, cross-session):**
- Stored summaries of past conversations, tagged with user_id, timestamp, and topic
- Each episode is a structured summary, not a verbatim transcript — 90% token reduction over raw history
- Retrieved by temporal query: "what did we do last time?" or "what failed last Tuesday?"
- Mem0 v3 (April 2026) achieves 92.5 on LOCOMO with 7.0K tokens per episode — down from 46K+ tokens of raw context
- Entity linking connects facts across episodes so a preference mentioned in session 3 surfaces in session 47

**Layer 3 — Semantic memory (long-term, permanent-ish):**
- Extracted facts, preferences, and learned behaviors — not tied to a specific conversation
- "User is vegetarian." "Prefers readable code." "Database uses SQLite."
- Extracted via LLM calls during conversation — not stored verbatim, synthesized
- Retrieved via semantic + BM25 + entity fusion (not semantic search alone)
- Temporal reasoning ranks the most recent correct instance when a fact has changed over time

**Retrieval fusion at query time:**
- Parallel retrieval across all three layers using different signals
- Scores fused: semantic similarity + keyword match + entity overlap + recency
- Agent sees ranked memories with provenance ("from conversation 3 weeks ago" vs "from yesterday")
- Upward promotion: if a fact from episodic memory is referenced frequently, extract and promote to semantic

## Evidence

- **Research paper:** Multi-Layer Memory Framework evaluated on LOCOMO, LOCCO, and LoCoMo benchmarks demonstrates that decomposing dialogue history into working, episodic, and semantic layers with adaptive retrieval gating achieves 46.85 Success Rate, 0.618 overall F1, 56.90% six-period retention, and reduces false memory rate to 5.1% while cutting context usage to 58.40%. — [arXiv:2603.29194 (June 2025)](https://arxiv.org/html/2603.29194v1)

- **Open-source framework:** Mem0's three-layer decomposition (working/episodic/semantic) with multi-signal retrieval (semantic + BM25 + entity matching) and temporal reasoning is the canonical open-source implementation. On the LOCOMO benchmark, Mem0 v3 (April 2026) scores 92.5 with only 7.0K tokens per retrieval — 91% lower latency than full-context approaches. On BEAM (1M token setting): 64.1; BEAM (10M): 48.6. Agent-generated facts are stored with equal weight as user statements. — [Mem0 GitHub README, 2026](https://github.com/mem0ai/mem0)

- **Engineering guide:** Redis's production memory architecture document describes the same three-tier split (short-term context windows → mid-term session summaries → long-term persistent storage) achieving up to 90% token cost reduction while maintaining accuracy. — [Redis: AI Agent Memory — Building Stateful Systems, 2026](https://redis.io/blog/ai-agent-memory-stateful-systems/)

## Gotchas

- **Don't skip the working layer.** Many teams start with vector DB for long-term memory and ignore short-term — then the agent loses track of the current conversation mid-turn. Working memory is not optional; it is the foundation.
- **Verbatim storage hits walls fast.** Raw conversation history as episodic memory fails at scale: a 45-minute multi-turn conversation is 46K+ tokens. Summarize episodes into 200-500 token structured summaries. Mem0's single-pass ADD-only extraction does this in one LLM call.
- **Retrieval without temporal reasoning retrieves the wrong instance.** A query about "the database" returns the schema from six months ago unless time-aware ranking picks the current one. Multi-signal fusion (semantic + keyword + entity + recency) is not optional — single-signal retrieval fails silently.
- **Memory accumulation without forgetting creates drift.** An ADD-only memory store (no UPDATE/DELETE) is philosophically correct but practically dangerous. Without retention regularization, contradicted facts coexist and retrieval picks arbitrarily. Budget for periodic consolidation passes, not just accumulation.
