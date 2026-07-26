# S-1664 · The Tiered Memory Stack — When Your Agent Forgets Everything After Every Session

You wire up Mem0. You connect it to your vector store. Your agent now has a memory layer. Two weeks in, a user asks "remember that fix we discussed for the auth flow?" The agent says "I don't have that information." The memory layer exists. The data is stored. But the agent can't retrieve the right fact at the right time, in the right form, from the right tier. Memory is not a vector database. It is a tiered discipline of write, manage, and read — and most memory layers only solve the retrieval step.

## Forces

- **LLMs are stateless between calls.** Every session starts from zero unless you explicitly store and re-feed prior information. The context window is a per-call buffer, not persistent storage — confusing the two is the root cause of most memory failures (Redis, "Why a bigger context window won't fix your agent's memory," 2026; Mnemoverse, "AI Agent Memory Crisis," 2026).
- **Bigger context windows create a false sense of security.** Models suffer "lost in the middle" — attention degrades for information placed in the center of long contexts, sometimes scoring worse than providing no additional context at all (Liu et al., 2023, cited in Redis 2026). A 1M-token window raises the ceiling but quality degrades inside the window you already have before you hit any hard limit.
- **Agents fail in the 60–80% context utilization zone, not at the hard limit.** Production agents degrade silently — no errors, no exceptions, just gradual policy drift. One documented case: a loan-underwriting agent approving policy-violating applications at turn 37 of a session, after accumulated tool outputs and reasoning traces pushed the original policy document to position 94,000 of the context (Meritshot, "Agentic AI Pipelines Break Silently," Feb 2026).
- **Memory type determines write discipline.** Conversation logs, working scratchpads, extracted facts, and reference documents are four fundamentally different things — storing them the same way creates retrieval chaos. The decomposition that stuck in 2025–2026: Core Memory Blocks (always in context, mutable scratchpad) + External Memory (archival, retrieval-based, immutable writes) (Letta/MemGPT, arXiv:2310.08560).
- **Retrieval mechanism matters less than agent behavior.** Letta agents running GPT-4o-mini with zero specialized memory tooling — just conversation history stored in files — scored 74.0% on the LoCoMo long-term memory benchmark. Specialized tools (Mem0, LangMem, Zep) scored lower on the same benchmark. The conclusion: current benchmarks may not measure what matters, and memory is more about how agents manage context than the retrieval pipeline (Letta Blog, "Benchmarking AI Agent Memory," Aug 2025).

## The move

Build a three-tier memory architecture where each tier has distinct write and read disciplines. The tiers mirror human cognitive architecture — working, episodic, semantic — plus a fourth: procedural (learned agent behavior).

**Tier 1 — Working memory (in-context scratchpad):**
- A small, always-in-context core block that the agent can read and write during active sessions
- Mutable: the agent rewrites this during task execution (tracks current objective, intermediate steps, open questions)
- Cap at 2,000–4,000 tokens; this is the agent's active "scratchpad," not a history dump
- When this fills, the agent summarizes and promotes key items to Tier 2 before continuing

**Tier 2 — Episodic memory (conversation/event log):**
- Append-only log of what happened: tool calls, outcomes, decisions, errors
- Format: structured (JSONL or markdown) rather than raw message dumps — enables efficient retrieval by event type, time window, or outcome
- On session resume: retrieve relevant episodes via summary + semantic search, not full replay
- Key discipline: episodic writes are immutable once appended; edits corrupt the audit trail

**Tier 3 — Semantic memory (extracted facts and preferences):**
- LLM-extracted facts, user preferences, project conventions, architectural decisions
- Stored with provenance (which session, which tool call, which decision)
- Read path: query rewrite + vector retrieval + re-rank by recency and relevance
- Write discipline: update by version, never mutate in place — old facts stay in the log for audit
- This is where Mem0, Letta, and Zep add the most value; pick based on scope model (user vs. session vs. agent)

**Tier 4 — Procedural memory (learned agent behavior):**
- Prompts, system instructions, and skills the agent has learned from experience
- Stored as versioned documents, not extracted facts
- Read path: loaded on task initialization or skill invocation, not per-turn retrieval
- Write path: explicit skill acquisition step (agent decides it learned a pattern worth codifying), not automatic extraction

**Monitor context utilization as a first-class metric:**
- Track context fill percentage per agent-turn; alert at 60%, hard limit at 80%
- Track quality signals: retrieval hit rate, fact-conflict rate, policy-derailment rate
- Track cost: tokens-per-task as a proxy for memory efficiency; tiered memory typically achieves 4× cost reduction vs. full-history context stuffing (Jobs by Culture, "AI Agent Memory Systems," Jun 2026)

## Evidence

- **Letta Blog:** Letta agents using GPT-4o-mini with no specialized memory tools — just file-stored conversation history — achieved 74.0% on LoCoMo benchmark. Specialized memory tools (Mem0, LangMem, Zep) scored lower on the same test. Key insight: agent capabilities matter more than retrieval mechanism. — https://www.letta.com/blog/benchmarking-ai-agent-memory
- **Hmem HN (Show HN):** AI coding agents "forwrite" — making decisions that contradict ones made hours ago not because the session ended but because long conversations silently compress context and push earlier decisions out of the window. Hmem's solution: persistent hierarchical memory via MCP on local SQLite, enabling cross-session and cross-machine portability. — https://news.ycombinator.com/item?id=47103237
- **Meritshot Blog:** Fintech loan-underwriting agent degraded at turn 37 of a session — no errors thrown, just gradual policy drift as accumulated tool outputs and reasoning traces pushed the original policy document to position 94,000 of context. The failure mode: silent degradation in the 60–80% context fill zone. — https://www.meritshot.com/blog/agentic-ai-context-overflow

## Gotchas

- **Context window is RAM, not storage.** Stretching the window raises the ceiling but doesn't give you cross-session continuity, doesn't prevent attention degradation, and costs more per call. The hard limit isn't what breaks first — quality degrades inside the window before you hit the end.
- **Most memory failures are write-discipline failures, not retrieval failures.** Teams spend months tuning the retrieval pipeline and neglect the write side: what gets stored, in what format, with what provenance. A conversation log is not a fact store; a fact store is not an episodic record. Mixing them makes retrieval unreliable.
- **The "forwriting" problem is silent.** Unlike a crashed service or a bad API response, "forwriting" produces confident, plausible outputs that contradict prior context. It has no error signal. The only detection mechanism is tracking retrieval hit rate and running periodic fact-conflict checks against the knowledge base.
- **Naive vector search on conversation history returns temporally stale results.** A fact stored six months ago with a high cosine-similarity score may be obsolete — user preferences change, project architectures evolve, policies update. Retrieval must incorporate recency weighting, version tracking, or explicit staleness flags alongside semantic similarity.
