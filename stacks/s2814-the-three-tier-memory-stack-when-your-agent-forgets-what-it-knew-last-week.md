# S-2814 · The Three-Tier Memory Stack — When Your Agent Forgets What It Knew Last Week

Your agent aced the demo. Six weeks later it asked the same questions, forgot the user's preferences, and re-explained the same concepts. The model didn't change. The context window isn't the problem. The memory architecture is.

## Forces

- **Context windows are capacity, not memory.** A 1M-token context gives you room to stuff transcripts, but it has no principled retention, retrieval, or eviction — the agent sees everything with equal weight and equally incomplete recall.
- **The three cognitive layers have different access patterns.** What the agent did last session (episodic), what it knows about the world (semantic), and how it should behave (procedural) require fundamentally different storage and retrieval strategies — one store does not fit all.
- **Memory systems compete with their own context budgets.** Every token spent on memory retrieval is a token not spent on reasoning. Over-retrieval degrades model performance; under-retrieval creates the goldfish problem.
- **Consolidation is the hard part.** Raw conversation logs are noise. Extracting salient facts, resolving conflicts across sessions, and encoding learned behaviors into retrievable form requires explicit engineering that most teams skip.

## The move

Implement a three-tier memory architecture with distinct storage, retrieval, and update semantics for each layer.

**Episodic memory — what happened**
- Store raw time-stamped interaction events: tool calls, responses, user feedback, task outcomes
- Append-only log with lightweight salience scoring (relevance to current task, user valence)
- Retrieve by recency + similarity hybrid: most recent relevant episodes, not all episodes
- Compact old episodes into semantic memory during consolidation passes; do not let the episode store grow unbounded

**Semantic memory — what is known**
- Store extracted facts as short declarative statements: user preferences, domain knowledge, past conclusions
- Use a structured knowledge base or vector store (not raw transcript excerpts) for retrieval
- Run consolidation passes to merge redundant facts, update stale facts, and resolve conflicts across sessions
- Mem0 (YC S24) is the most widely deployed semantic layer as of mid-2026, with ~26% higher accuracy than OpenAI Memory on the LOCOMO benchmark and 91% lower p95 retrieval latency per the arXiv paper

**Procedural memory — how to behave**
- Store agent behaviors, policies, and learned strategies as explicit code or structured prompts — not embedded in the model's weights
- Version these alongside code; update retrieval signals when the agent's behavioral repertoire changes
- Examples: system prompts, tool selection heuristics, escalation policies, multi-agent handoff protocols

**Memory retrieval — feeding the context**
- Pull top-k relevant facts from semantic memory and recent episodes, then compress into a memory summary before injecting into context
- Do not dump the raw episode log into the context window — it degrades reasoning accuracy
- Set explicit retrieval triggers: at task start, after tool failures, after session gaps exceeding a threshold (e.g., 30 minutes)

## Evidence

- **arXiv paper:** Mem0 — Building Production-Ready AI Agents with Scalable Long-Term Memory (Chhikara et al., arXiv:2504.19413, April 2025) — introduces the episodic/semantic/procedural three-tier taxonomy and demonstrates 91% lower p95 latency and 90% token cost savings versus naive context stuffing — [https://arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413)
- **HN Discussion:** "Ask HN: What AI Agents are in production?" (HN id 42485738, December 2024) — practitioner reports their agent asked users for information "already in the database" because sessions were stateless; solution was to inject a structured user profile into context on every turn — [https://news.ycombinator.com/item?id=42485738](https://news.ycombinator.com/item?id=42485738)
- **Engineering blog:** "The Three Memory Systems Every Production AI Agent Needs" (tianpan.co, April 2026) — documents the "chatbot with amnesia" failure pattern and recommends append-only episodic stores with compaction passes to prevent unbounded growth — [https://tianpan.co/blog/long-term-memory-types-ai-agents](https://tianpan.co/blog/long-term-memory-types-ai-agents)

## Gotchas

- **Direct episode injection degrades performance.** Feeding raw conversation history into the context window without salience scoring or compression causes measurable accuracy drops — the model weights every line equally.
- **Stale memory is worse than no memory.** Without a consolidation pass, the agent acts on facts from sessions where the user's preferences or context changed. Set a maximum staleness threshold per fact type.
- **Privacy boundaries are harder on event logs.** Extracted facts are easier to audit and delete than raw transcripts (GDPR right to erasure). Consolidate into facts, not just store raw episodes.
- **Procedural memory drifts if not versioned.** When you update the agent's tool definitions or behavioral policies, the procedural memory layer can fall out of sync. Treat it like code, not like configuration.
