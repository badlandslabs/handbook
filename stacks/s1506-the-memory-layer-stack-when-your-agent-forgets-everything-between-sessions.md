# S-1506 · The Memory Layer Stack — When Your Agent Forgets Everything Between Sessions

Your agent aced the onboarding session: learned the user's name, their preferred stack, the team's review cadence. Then the session ended and it all vanished. Day two starts from zero. The user is frustrated. You reach for the obvious fix — stuff the conversation history into the next prompt — and promptly burn through the context window in a week. Memory is not chat history. It is a first-class infrastructure layer with its own taxonomy, failure modes, and stack choices.

## Forces

- **Context windows are finite and expensive.** GPT-4 (128K), Claude 3.7 (200K), Gemini (10M) all delay the problem; they don't solve it. At months of conversations, full-context is untenable — Mem0's April 2026 algorithm delivers 6.7K–7.0K tokens/retrieval versus 25,000+ for full-context approaches.
- **Chat history ≠ memory.** Raw conversation logs are noisy, contradictory, and require the model to re-parse context it already understood. The extraction step (converting noisy logs into structured facts) is where quality diverges.
- **Four memory types, not one.** Treating "memory" as a single bucket causes the wrong abstraction for the job: a coding agent needs procedural memory for tool-call patterns; a CRM agent needs episodic memory for client interactions; a research agent needs semantic memory for domain knowledge. Mixing them causes retrieval pollution.
- **Cross-context contamination is a silent production killer.** When agent A's facts bleed into agent B's session — same user, different task — users experience "the AI is creepy because it knows things it shouldn't." This is not a hallucination; it is a memory boundary failure.

## The Move

Layer your agent's memory across four distinct types, using a purpose-built memory framework rather than rolling your own retrieval:

- **Working memory:** The current context window — conversation turns, intermediate reasoning, tool call results. Managed by the orchestration framework (LangGraph state, etc.). No persistence needed here.
- **Episodic memory:** What happened when. Conversation summaries, key decisions, event sequences. Backed by Zep/Graphiti's temporal knowledge graph with validity windows (stores "X was true from date A to date B"). The right choice when "what did we agree on in Q1?" matters.
- **Semantic memory:** Extracted facts, preferences, domain knowledge. Backed by Mem0's vector-first extraction pipeline. The ADD-only pattern (Mem0's April 2026 algorithm) — one LLM call, no UPDATE/DELETE, facts accumulate — avoids the write-complexity of maintaining consistent state.
- **Procedural memory:** How to use tools, agent self-model, learned behaviors. Stored as structured system prompts or LangMem's persistent store layer. Often the most valuable but least implemented.

**Stack hierarchy for vector storage (per Perea.ai Research, April 2026 benchmarks):**
- **Hot path:** Qdrant — lowest latency for real-time retrieval
- **Tool registries:** Weaviate — better for structured metadata alongside vectors
- **<10M embeddings:** pgvector — simplest operational footprint
- **Managed simplicity:** Pinecone — reduces ops burden at cost premium

**For session checkpointing** (fault tolerance, not memory per se):
- PostgresSaver or Redis for LangGraph checkpointer — persist state after every step so crashes resume cleanly
- Thread-ID scoped: each conversation thread gets isolated state, preventing cross-talk

**Three MCP tools pattern** (Archetypal AI's production implementation):
- `remember_task`: captures completed work and outcomes
- `remember_context`: captures project conventions, user preferences
- `recall`: retrieves relevant memories at session start

## Evidence

- **Mem0 paper (ECAI 2025):** Documents the ADD-only extraction pattern. April 2026 algorithm: 92.5 LoCoMo, 94.4 LongMemEval, ~6.8K tokens/retrieval at 1.09s p50 latency. Established that context windows cannot scale with real-world conversation diversity. — [https://arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413)
- **Perea.ai Research — "Agent Memory in Production" (May 2026):** Consolidated four-type taxonomy, benchmarked Mem0 vs Zep (+18.5% improvement on LongMemEval), ranked vector DB hierarchy (Qdrant > Weaviate > pgvector > Pinecone). Identified critical failure modes: memory poisoning, drift, cross-context contamination. — [https://www.perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)
- **AI Workflow Lab — "LLM Memory for AI Agents" (June 2026):** Thread-scoped checkpointing pattern using PostgresSaver for LangGraph, with production code example. Documents the "lost in the middle" context degradation problem and maps it to the working/episodic/semantic/procedural taxonomy. — [https://aiworkflowlab.dev/article/llm-memory-state-management-production-ai-agents-architecture-patterns-frameworks-implementation](https://aiworkflowlab.dev/article/llm-memory-state-management-production-ai-agents-architecture-patterns-frameworks-implementation)
- **Archetypal AI (Reddit, 2025):** 14-agent civilization using Cloudflare Durable Objects + three MCP tools for cross-session memory. Demonstrates that the "re-teaching tax" — re-explaining context at every new session — is a quantifiable daily cost across the developer ecosystem. — [https://gist.github.com/bsharvey/7cb4d57600408ba4f1bd9745bd688816](https://gist.github.com/bsharvey/7cb4d57600408ba4f1bd9745bd688816)
- **AI Workflow Lab — "Mem0 vs Letta vs Zep" (May 2026):** Side-by-side architecture comparison: Mem0 = extraction + vector store, Zep = temporal knowledge graph with validity windows, Letta = OS-tiered memory blocks. Rule of thumb: Mem0 for personalization, Zep for temporal reasoning, Letta for agents that self-manage memory hierarchy. — [https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)

## Gotchas

- **Don't store raw chat logs as "memory."** Retrieval over noisy logs is semantically polluted. Always extract structured facts first — the LLM call overhead pays for itself in retrieval quality.
- **Cross-context contamination sneaks in when memory is user-global but tasks are not.** If agent A works on project X and agent B on project Y for the same user, their memories can bleed. Use thread/session IDs as a namespace boundary on all retrieval queries.
- **Procedural memory is the gap everyone skips.** Teams implement episodic + semantic and call it done. But learned tool-call patterns, retry strategies, and agent self-descriptions degrade with context. LangMem's persistent store layer addresses this specifically for LangGraph pipelines.
- **The validity window problem.** Zep/Graphiti's approach (facts have "true from/to" timestamps) is architecturally superior for long-running agents but requires your schema to support temporal queries. If your team is not ready to query "what was the user's role in January?" as a time-bounded fact, this complexity is premature.
- **Memory poisoning is real.** User feedback, corrections, and injected context all modify the memory store. Without a validation or voting layer, a single bad extraction can persist indefinitely. The ADD-only pattern (Mem0) sidesteps this by never overwriting, but accumulates noisy facts over time — budget for periodic summarization.
