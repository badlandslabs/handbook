# S841 · The Agent Memory Stack — When the Context Window Is Not Memory

You have a customer-support agent running in production. A user returns three weeks later and the agent doesn't remember verifying their account the first time. The conversation log shows it happened — it just got dropped from the sliding window. You did everything right: full history in context, sliding window, compression. The memory was there. The agent still forgot.

## Forces

- **Context window is L1 cache, not memory.** It's a per-call input buffer the model reads fresh every time — not a persistent store. Growing the window to 1M tokens doesn't solve continuity across sessions; it just fits more of one conversation before you start dropping the oldest turns.
- **The sliding-window amputation.** Most teams stuff the last N messages into context, then advance the window forward as the conversation grows. The moment you slide past a critical fact, it's gone. Teams don't notice until a user brings it back and the agent denies it.
- **Storage ≠ retrieval.** Adding a vector database behind the agent doesn't solve memory. It creates a retrieval problem you still have to engineer: what to write, when to consolidate, what to recall, how to handle drift. Most teams do flat semantic search over conversation logs and call it done.
- **Pattern taxonomy is non-obvious.** "Memory" is actually three or four distinct concerns with different storage and retrieval requirements. Conflating them produces systems that are expensive to operate and still unreliable.

## The Move

Separate the memory architecture into distinct tiers, each with its own store and retrieval logic. Do not conflate the context window with long-term memory.

**Tier 1 — Working memory (context window).** The LLM's input buffer. Keep recent turns, session state, and active task context here. This is ephemeral per-call scratch space. Do not rely on it for cross-session continuity.

**Tier 2 — Episodic memory (what happened).** A durable event log of interactions: user messages, agent decisions, tool results, success/failure outcomes, and key turning points. Store with timestamps and session IDs. Retrieve by recency and semantic similarity. This is the flight recorder. One pattern from production: Memex-style local-first stores using SQLite + FTS5 to keep the full event log inspectable in plain SQL, with WAL mode for concurrency.

**Tier 3 — Semantic memory (facts and entities).** Extracted facts about users, products, policies, and ground truth. Queried on-demand. Retrieval should be hybrid (semantic vector + keyword) with entity-aware routing. Not every fact needs to be in every prompt — retrieve only what's relevant to the current turn.

**Tier 4 — Procedural memory (how to do things).** Learned workflows, agent skills, and operating policies. Key insight from Mengram: procedures must evolve when they fail — a workflow that broke on Friday should not be retried identically on Monday.

**Tier 5 — Consolidation pipeline.** Run a background process that: (a) extracts facts from episodic logs into semantic stores, (b) merges duplicate facts, (c) retracts superseded facts (Zep's bi-temporal graph approach), and (d) updates procedural memories when workflows fail. Without consolidation, all stores grow unbounded and retrieval quality degrades.

**Tool use over architecture.** Letta's benchmark finding: Letta agents on GPT-4o-mini achieved 74.0% on the LoCoMo memory benchmark using nothing but conversation histories in a filesystem — no specialized memory system, no vector store. The mechanism that worked was giving the agent tools (read files, list directory, grep) and letting it manage its own context. Agent capability with memory tools matters more than the retrieval backend. Build the memory interface as tools the agent can invoke, not a hidden infrastructure layer.

## Evidence

- **Blog post (AmtocSoft, Apr 2026):** "Context window expansion is not a memory strategy" — details a support team that lost a user's verified-account status when the oldest turns slid past the context window boundary after ~180K tokens, with cost math showing $6M/month if full history were stuffed into context at scale. Proposes episodic + semantic + procedural three-tier architecture based on 11 months of production telemetry (420K conversations/month, 2.7M memory reads/day). — [https://amtocsoft.blogspot.com/2026/04/ai-agent-memory-patterns-semantic.html](https://amtocsoft.blogspot.com/2026/04/ai-agent-memory-patterns-semantic.html)

- **Benchmark (Letta Blog, Aug 2025):** Letta agents on GPT-4o-mini scored 74.0% on the LoCoMo memory retrieval benchmark using a plain filesystem as the backing store — outperforming specialized memory tools (Mem0 reported 68.5% on the same benchmark with its graph variant). Conclusion: "memory is more about how agents manage context than the exact retrieval mechanism used." — [https://www.letta.com/blog/benchmarking-ai-agent-memory](https://www.letta.com/blog/benchmarking-ai-agent-memory)

- **Show HN (HN item #47217244, 2025):** AgentKeeper — cognitive persistence layer for AI agents, specifically addressing memory loss when agents switch providers, restart, or crash. Explicit design goal: memory that survives the agent lifecycle. — [https://news.ycombinator.com/item?id=47217244](https://news.ycombinator.com/item?id=47217244)

- **Show HN (HN item #46891715, 2025):** Ask HN — YC W23 engineering lab company evaluated Mem0, Letta/MemGPT, and other memory solutions. Finding: all solved "store facts from conversations" (key-value semantic search) but none solved "learn user patterns across repeated similar analyses" — what they actually needed. Points to a gap in the pattern-learning tier. — [https://news.ycombinator.com/item?id=46891715](https://news.ycombinator.com/item?id=46891715)

- **GitHub comparison lab:** agent-memory-lab compares 5 memory integration patterns for LangGraph-based agents — LangGraph store, langmem, Mem0, Zep, and Letta/MemGPT — documenting exact code differences, empirical trade-offs on what gets stored/recalled/lost, and a decision framework for choosing the right approach. — [https://github.com/gengzll/agent-memory-lab](https://github.com/gengzll/agent-memory-lab)

- **Technical blog (Redis.io, Jun 2026):** "Why a bigger context window won't fix your agent's memory" — directly articulates the distinction: context window is a per-call input buffer; memory is cross-session persistence. Growing the window does not solve continuity. — [https://redis.io/blog/why-bigger-context-window-wont-fix-agent-memory](https://redis.io/blog/why-bigger-context-window-wont-fix-agent-memory)

## Gotchas

- **Sliding windows silently amputate facts.** The most common production failure. Track which critical facts are currently in context vs. persisted — or better, write facts to external storage the moment they're established, not after.
- **Flat vector search over conversation logs is not a memory architecture.** It's retrieval of similar past context. It doesn't tell the agent who the user is, what they've done, or how they prefer to be handled. You still need episodic, semantic, and procedural layers.
- **Memory writes must be deliberate, not automatic.** Automatic writes without consolidation produce compounding errors — the agent stores redundant facts, drift goes undetected, and the semantic store becomes noise. Explicit write policies and consolidation are not optional.
- **Provider switching kills memory.** If your agent's memory lives in a managed platform's proprietary store, switching providers or restarting resets it. Design memory as provider-agnostic (files, SQLite, or an explicit schema) so the agent's identity survives infrastructure changes.
- **Cost at scale surprises teams fast.** A 1M-token context at Claude Sonnet pricing costs ~$3/input turn. At 400K conversations × 5 turns, that's $6M/month just for context stuffing. External memory stores plus targeted retrieval are order-of-magnitude cheaper.
