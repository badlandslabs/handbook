# S-953 · The Memory Layer Stack — When Your Agent Remembers Nothing Between Sessions

Your agent works perfectly for 20 minutes. It analyzes data, makes decisions, executes tasks. Then the session closes — or the process crashes, or the user switches devices. You restart it, and it starts from zero. No memory of what it just did, what it learned, or what decisions it made. Every API call starts fresh. Every context window is a clean slate.

This is the **memory layer problem**: agents are stateless by default, and most teams don't build persistence until it has already caused real damage — re-derive expensive research, lost user preferences, forgotten workflow state. By the time they notice, they're patching a gap in the architecture.

## Forces

- **Stateless by design vs. production by necessity** — LLMs are text-in, text-out systems. They don't naturally retain anything between calls. The context window is the only memory they have, and it evaporates when the session ends.
- **Bigger context ≠ memory** — 1M-token windows are real, but: (1) they're economically prohibitive at production scale; (2) models suffer "lost in the middle" attention degradation; (3) agents running for weeks accumulate far more relevant history than any context window can hold. Long contexts complement memory, they don't replace it.
- **Vector databases are retrieval, not memory** — Embedding a query and returning top-k similar results is not memory. Real memory requires fact extraction, deduplication, conflict resolution, and temporal tracking. Teams routinely confuse "I store text and retrieve it" with "my agent remembers."
- **Memory value compounds, but only with persistence** — An agent that remembers your project's conventions, your team's decisions, and your users' preferences across sessions gets better every week. A stateless agent starts from zero every time. The gap widens monotonically.

## The Move

Build a tiered memory architecture with four distinct layers. Don't reach for a single vector store and call it done.

**Tier 1 — Working memory (the context window):** Holds current conversation, immediate task state, and a small "always-on" core of high-value facts. This is what the agent reads on every turn. Keep it small and hot.

**Tier 2 — Episodic memory (conversation/event logs):** Store what happened in each session — raw or summarized. Not for retrieval on every turn; for re-loading when a user returns after days or weeks. Summarize aggressively to control token costs.

**Tier 3 — Semantic memory (extracted facts and preferences):** This is what separates retrieval from memory. Run an extraction step after each significant interaction to pull out facts ("user prefers detailed responses"), decisions ("we use PostgreSQL for this service"), and preferences ("the user lives in Berlin"). Store these as structured facts, not raw text. This layer is where Mem0, Zep, and Letta operate.

**Tier 4 — Procedural memory (the agent's own instructions):** How the agent should behave, what tools it has, what workflows it knows. This is the agent's operating manual — not user history, but the agent's own learned procedures. Updated when the agent learns a better approach.

**On forgetting:** Every memory system needs an expiration policy. Facts become stale ("the user lived in Berlin" is false when they moved). Episodic summaries compete for context space. Implement explicit retention rules: TTLs, recency weighting, contradiction detection.

**The stack in practice:** Mem0 (YC-backed, hybrid semantic+keyword+preference retrieval, ~61k GitHub stars, 92.5 LoCoMo benchmark score as of April 2026) for lightweight managed integration. Letta for OS-style explicit memory management with sleep-time compute (non-blocking async memory operations that don't slow down responses). Zep for temporal knowledge graphs when you need to track how facts change over time. MemoryKit (open-source, lightweight Python) for teams that want a file-based persistent layer without infrastructure.

## Evidence

- **GitHub / Benchmark data:** Mem0's April 2026 algorithm update achieved 92.5 on LoCoMo (up from 71.4) and 94.4 on LongMemEval (up from 67.8) using 7.0K tokens per retrieval — demonstrating that dedicated memory architecture meaningfully outperforms naive RAG. — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **Engineering blog:** Long context windows complement but don't replace memory systems — 1M tokens per turn is uneconomical at production scale, models suffer "lost in the middle" degradation, and agents running for weeks accumulate far more history than any context window can hold. — [AI Workflow Lab: Mem0 vs Letta vs Zep, June 2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Show HN / Primary source:** DeltaMemory launched on HN as persistent cognitive memory for production AI agents (July 2026). MemoryKit launched as a lightweight persistent memory layer for AI agents via Python library. MemoryGate launched as open-source persistent memory for AI agents via MCP. Each addressed the same root problem from a different angle. — [HN Show HN: MemoryKit, ~June 2026](https://news.ycombinator.com/item?id=47195240); [HN Show HN: MemoryGate, ~March 2026](https://news.ycombinator.com/item?id=46981840)
- **Mem0 fundraising data:** $24M Series A (October 2025), 14M+ downloads, 41k+ GitHub stars at time of raise. Y Combinator, Kindred Ventures, Basis Set Ventures, Peak XV, GitHub Fund backed. Shows the market validated the problem is real and large. — [PRNewswire, October 2025](https://www.tmcnet.com/usubmit/2025/10/28/10279381.htm)
- **Memory architecture pattern:** Six-layer memory architecture from futhgar/agent-memory-architecture — CLAUDE.md (global+project preferences, ~7,850 token baseline load) through Qdrant vector query — documents the concrete token costs of each layer. Baseline session load before user input: ~7,850 tokens across system prompt, auto-memory, and project rules. — [https://github.com/futhgar/agent-memory-architecture/blob/main/docs/architecture.md](https://github.com/futhgar/agent-memory-architecture/blob/main/docs/architecture.md)
- **Memory vs. vector DB distinction:** "Most developers who claim their agent 'has memory' have actually built a retrieval system. Plugging Chroma or Pinecone into an agent pipeline gives the agent the ability to find similar text, but similarity search and memory are not the same thing." Vector databases handle embedding storage and ANN search — they don't do fact extraction, deduplication, or contradiction detection. — [Mem0 Blog: Vector Databases and Memory for AI Agents, July 2026](https://mem0.ai/blog/vector-databases-and-memory-for-ai-agents)

## Gotchas

- **Session-level persistence is not the same as cross-session memory.** Storing conversation history in a database so the agent can resume a session is table stakes. Cross-session memory — the agent learning that "this user prefers X" and carrying that preference into an entirely new conversation weeks later — requires semantic extraction, not just retrieval.
- **Embedding-based retrieval returns both old and new facts with equal confidence.** If a user moved from Berlin to Munich, naive vector search will return "Berlin" facts just as readily as "Munich" facts. You need temporal metadata or explicit contradiction detection to handle stale facts.
- **Memory has a token cost that compounds.** Every retrieval adds tokens to every call. An unoptimized memory layer can make agents slower and more expensive than stateless agents. Profile your baseline token load (like the ~7,850 token baseline documented in agent-memory-architecture) before adding a memory system.
- **Framework lock-in is real.** Mem0's managed cloud, Letta's agent framework, and Zep's temporal graph each optimize for different trade-offs. Switching later is expensive. Evaluate based on your bottleneck — retrieval quality, latency, ops overhead, or temporal reasoning — not just feature checklists.
