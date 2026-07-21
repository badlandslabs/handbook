# S-1460 · The Memory-Tiering Stack — When Your Agent Has No Memory of Yesterday

Your agent works great in demos. In a single session, it answers follow-up questions, remembers your name, and follows through on previous requests. Then the session ends. Tomorrow you start over and the agent has no idea who you are, what you discussed, or what it promised to do. The model is stateless. Memory isn't built in — it has to be architected.

## Forces

- **Context windows are expensive at scale.** A 1M-token context on Claude costs ~$15/call. At 1,000 conversations/day, full-context retrieval runs $15,000/day. Production agents hit context overflow within 15–20 turns regardless of window size.
- **Storage and retrieval are different problems.** Putting everything in a vector store doesn't solve the problem — you also need to decide what to store, when to retrieve it, and how to handle contradictions and staleness.
- **LLMs hallucinate from stale memory.** Unlike missing information (the agent doesn't know it), stale information is worse — the agent confidently applies outdated facts. A user's employer changes but the agent keeps referencing the old one.
- **Frameworks solve different sub-problems.** Mem0, Zep, Letta, and Cognee are not interchangeable — each targets a distinct memory failure mode. Picking the wrong one means buying complexity without solving your actual problem.

## The move

Design a four-tier memory architecture from the start. Don't bolt memory onto a stateless agent — make it structural.

**Tier 1 — Working Memory (the context window):**
- System prompt, current conversation, active task state
- Small, fast, LLM-native — everything the model touches directly
- Cost is linear with size; prune aggressively after each turn
- This is your RAM, not your hard drive

**Tier 2 — Episodic Memory (conversation history as events):**
- Store each interaction as a structured event: timestamp, user query, agent response, outcome
- Use a temporal knowledge graph (Zep/Graphiti) over flat vector search when order and recency matter
- Zep's Graphiti scores **63.8%** on LongMemEval vs Mem0's **49.0%** — a 15-point gap specifically on temporal retrieval tasks
- Event-level records survive context overflow and enable "what happened last time" queries

**Tier 3 — Semantic Memory (extracted facts and preferences):**
- LLM-extracted facts, user preferences, learned behaviors — synthesized from episodic data
- Stored as structured key-value facts, not raw conversation chunks
- This is what the agent needs at the start of every session: "user prefers concise responses," "project uses pytest"
- Update via explicit extraction pipeline, not raw retrieval

**Tier 4 — Procedural Memory (agent's own instructions and learned behaviors):**
- The agent's system prompt, learned tools, refined instructions — what the agent *knows how to do*
- Letta's MemGPT-style approach: agent manages this tier via `core_memory_replace` function calls
- Self-editing by the agent itself is the key innovation — the model decides what to keep in its always-available context

**The retrieval pattern:**
- Before each inference turn, run a targeted query against episodic + semantic memory
- Retrieve top-K relevant facts, inject into working memory
- Keep the retrieval pipeline simple at first (semantic search + re-rank) before adding complexity
- Letta benchmarks show a plain filesystem scores **74%** on memory tasks — sophisticated retrieval beats simple retrieval only when the problem genuinely demands it

**The forgetting policy:**
- Time-based expiration throws away useful information indiscriminately
- Confidence decay helps but doesn't eliminate stale facts
- Contradiction detection (secondary process that flags new info conflicting with stored facts) catches explicit corrections but misses gradual drift
- No perfect solution exists — choose a policy and instrument it

## Evidence

- **Letta case study (Bilt):** Bilt built a million-agent recommendation system on Letta, transitioning from basic scoring algorithms to memory-augmented agents serving personalized recommendations at scale. Their journey demonstrates how tiered memory enables personalization that stateless systems cannot. — [letta.com/case-studies](https://www.letta.com/case-studies)
- **Letta case study (Kognitos):** Kognitos used Letta to prototype an enterprise analytics tool for a major logistics client in days. The project generated a half-million-dollar success story by enabling the agent to maintain context across complex, multi-step data queries. — [letta.com/case-studies/kognitos](https://www.letta.com/case-studies/kognitos)
- **Letta case study (11x):** 11x built a Deep Research agent on Letta in 72 hours, transforming their sales automation platform. The rapid iteration was possible because Letta's memory architecture handled session persistence, freeing the team from building that infrastructure from scratch. — [letta.com/case-studies](https://www.letta.com/case-studies)
- **Framework comparison (Particula Tech, June 2026):** Direct benchmarks across Mem0, Zep, Letta, and Cognee — with quantified accuracy scores on LongMemEval, cost-per-query ranges ($0.002–0.01/query at low volume), and explicit tradeoffs for each framework's approach. — [particula.tech/blog](https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026)
- **Production guide (Tian Pan, October 2025):** Detailed four-type taxonomy (working, episodic, semantic, procedural) with production failure modes — specifically the stale memory problem and current mitigation approaches. — [tianpan.co](https://tianpan.co/blog/2025-10-21-memory-architectures-for-production-ai-agents)
- **Redis engineering guide (June 2026):** Cost analysis showing 1M-token inference at ~$15/call and context overflow at 15–20 turns in production customer support scenarios. — [redis.io/blog](https://redis.io/blog/ai-agent-memory-stateful-systems)
- **HN Show: Hmem (MCP memory):** Real tool solving cross-tool memory lock-in — an agent's memory survives tool-switching (Claude Code → Cursor) and machine-switching (laptop → desktop). SQLite-backed, local, MIT licensed. — [news.ycombinator.com/item?id=47103237](https://news.ycombinator.com/item?id=47103237)

## Gotchas

- **Vector search alone isn't memory.** Storing conversation chunks in a vector DB and retrieving them doesn't solve staleness, contradiction, or cost. Semantic memory requires extraction and synthesis — not just storage.
- **Context constitution drift.** Over many sessions, the agent's core memory can drift from reality as it edits its own instructions. Version-control your core memory and treat it like code.
- **Cross-tool memory is a separate problem.** Most frameworks assume a single agent platform. If your agents run across Claude Code, Cursor, and a custom API, memory doesn't automatically follow. MCP-based solutions (Hmem) address this but require explicit setup.
- **The 15-turn collapse.** Regardless of how large your context window is, production cost pressure means you can't afford to flood context with history past ~20 turns. Design for this from day one, not as an optimization.
