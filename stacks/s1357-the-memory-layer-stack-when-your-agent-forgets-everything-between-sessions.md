# S-1357 · The Memory Layer Stack

When you reach for it: Your agent works beautifully in a single session, then loses everything the moment the conversation ends. The next session starts at zero — no user preferences, no project context, no accumulated history. You're either re-explaining everything every time, or you're dumping full conversation history into the prompt and burning through your context window and budget.

## Forces

- **The stateless LLM problem.** LLMs are fundamentally stateless between calls. Every new session is a fresh brain. Long context windows didn't solve this — they made it cheaper to postpone solving it, which creates a different debt: expensive, slow, retrieval-dumb prompts.
- **"Just add a vector store" is half the answer.** Vector similarity search gives you retrieval, not memory. Memory is a lifecycle: selection → capture → storage → retrieval → decay. A vector store handles retrieval. The other four steps need design decisions your DB doesn't make for you.
- **Memory conflicts are silent poison.** If the agent remembers "user prefers Python" from session 3 and "user prefers Rust" from session 7, nearest-neighbor retrieval can surface the wrong one. Unlike a database, the system has no foreign key enforcing consistency — it just retrieves what semantically matches.
- **Cold start vs. long-running is a trade-off axis.** Some agents need instant deployment (cold start matters), others run for weeks (rich memory matters). The right memory architecture depends on which end of this spectrum you're on.

## The Move

Design a layered memory architecture that answers four questions every session:

1. **What do I keep?** (Selection) — Extract facts, not transcripts. Compress chat history into structured entity+preference memories. Raw conversation replay is a last resort.
2. **When do I write it?** (Capture trigger) — After each meaningful turn, or on session end. Don't write every token; write what would matter to the next session.
3. **Where does it live?** (Storage structure) — Choose the right abstraction for the retrieval pattern: vector store for semantic recall, knowledge graph for temporal relationships, plain text blocks for agent-editable summaries.
4. **How do I rank what's relevant?** (Retrieval) — Combine semantic similarity with recency, user identity, and task context. Pure nearest-neighbor is the baseline; adding metadata filters eliminates most false positives.

### Implementation options by priority:

- **Mem0** (Apache 2.0, self-hostable) — Lightweight facts-in-vector-store layer. Extracts entity facts from conversation, stores with user/session/agent metadata. Best for: personalization at scale, multi-user systems. Weakness: no native fact-evolution tracking; conflicts accumulate until manually resolved.
- **Letta / MemGPT** (Apache 2.0) — Three-tier memory blocks (core, archival, recall) the agent manages via tool calls. The agent decides what stays in context vs. moves to archival vs. gets recalled. Best for: long-running agents that need self-directed memory management. Weakness: cold start is slow; requires integrating Letta's runtime.
- **Zep / Graphiti** — Temporal knowledge graph. Stores facts as time-stamped relationships with validity windows. "User was in SF until March 2026, then NYC." Best for: CRMs, support agents, anything where when-mattered matters. Weakness: higher ops complexity than Mem0; graph traversal adds latency.
- **Flat context + semantic search** — For agents under ~500K tokens of history, a long-context model (Claude Opus 4.7, Gemini 2.5) with conversation chunks in a vector store can outperform purpose-built memory frameworks. 3-4x fewer tokens for comparable recall accuracy. Best for: small fleets, simple agents, teams that want to avoid framework lock-in.
- **Hybrid: Mem0 + Letta** — Use Mem0 for fast fact retrieval and user preferences, Letta for agent-authored summaries of long-running tasks. The two layers cover different time horizons.

## Evidence

- **Benchmarks:** Hindsight (multi-strategy retrieval: semantic + BM25 + graph traversal + temporal) scored **94.6% on LongMemEval** vs. Mem0's 49.0%. Mem0 uses semantic-only retrieval; the gap is retrieval strategy, not storage. — [AgentMarketCap benchmark roundup](https://agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026), April 2026
- **Long context vs. memory layer cost:** Flat context with vector-backed retrieval hits comparable accuracy at 3-4x fewer tokens than dumping full history. For a typical agent: ~$960/month with layered memory vs. ~$2,400/month with raw context stuffing. — [Iterathon benchmark case study](https://iterathon.tech/blog/ai-agent-memory-systems-implementation-guide-2026), January 2026
- **Three vendor defaults, three philosophies:** Anthropic mounts `/mnt/memory/` as a filesystem; Google scopes Memory Bank to identity (`user_id`-level); OpenAI backs `file_search` with a vector store. The API you build on determines your default memory model — switching later costs 2-6 weeks of engineering. — [DigitalApplied memory architecture breakdown](https://www.digitalapplied.com/blog/ai-agent-memory-vector-graph-episodic-2026), May 2026
- **Market signal:** Five open-source memory-layer repos accumulated **80,000+ combined GitHub stars in Q1 2026**. The memory layer is the defining infrastructure challenge of the agentic era — not because it's conceptually hard, but because production tradeoffs between recall accuracy, latency, token cost, and governance are brutal. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026), April 2026

## Gotchas

- **Memory staleness kills agents silently.** The agent retrieves a fact that was true six months ago and acts on it confidently. No error is thrown. Fix: add validity windows or explicit recency scoring to every retrieval. Zep and Graphiti handle this natively; Mem0 requires custom metadata.
- **Cold start is a deployment blocker for user-facing agents.** New users have no memory, so the first session is always degraded. Fix: seed with a profile questionnaire on first login, or use a "memory bootstrap" prompt that surfaces what you know about similar users without assuming.
- **"Stuff the full history" is a valid interim architecture, not a final one.** It's simple, works for <50K tokens, and avoids framework lock-in. The failure mode is cost and latency scaling non-linearly. Set a threshold (token count or session length) to migrate to a layered system before it becomes painful.
- **Memory correction is harder than memory retrieval.** Fixing a wrong fact means updating the vector store (or graph), verifying the fix propagates to future retrievals, and ensuring the agent stops using the old value. Most frameworks don't solve this — they just let you add a contradiction. The safest bet is a readable, inspectable store: if you can read the memory, you can debug it. — [memnode framework analysis](https://memnode.dev/articles/agent-memory-frameworks-2026-letta-mem0-graphiti-cognee), June 2026
- **Multi-agent memory requires scope isolation.** Multiple agents sharing a vector store leads to agents retrieving memories they shouldn't see. CtxVault's approach (independent knowledge vaults with separate retrieval paths) addresses this at the architecture level; metadata filtering on shared stores is the simpler but less robust alternative.
