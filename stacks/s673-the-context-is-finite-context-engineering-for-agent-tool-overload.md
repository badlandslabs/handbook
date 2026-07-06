# S-673 · The Context Is Finite: Context Engineering for Agent Tool Overload

[You gave your agent 50 tools. It works in the demo. At 5,000 users, it starts picking the wrong tool, hallucinating function names, and costing 4x more per request. The problem isn't the LLM — it's that you treated the context window as infinite. The fix is context engineering: selective tool loading, retrieval over static lists, and explicit memory compaction.]

## Forces

- **Tool selection degrades with scale, not just count.** The model doesn't just get slower with more tools — it gets less accurate. Selection accuracy falls because the model is choosing from N options per step, and the space of valid actions grows super-linearly.
- **MCP's success created the problem MCP solves.** Anthropic's MCP crossed 97M monthly SDK downloads (Linux Foundation, 2025), making tool connectivity trivial. The result: agents that previously had 5 tools now have 50+ from a dozen MCP servers — and hit hard limits at the client layer (Cursor: 40 tools max, GitHub Copilot: 128 tools max).
- **Naive RAG ≠ memory.** Teams drop Pinecone behind an agent and call it "memory." It works for an hour, then degrades — the agent retrieves semantically similar but temporally irrelevant context, losing session continuity. Vector similarity does not equal "remembering what matters."
- **Context rot is real before the hard limit.** Needle-in-a-haystack studies show model recall degrades progressively, not suddenly. At 70% context fill, accuracy is measurably lower even when the target information is present. Most teams only instrument for hard failures.

## The move

**1. Select, don't load.** Tools should be retrieved dynamically, not loaded statically. LangChain reports retrieval-based tool selection improves accuracy 3x over static list loading. The agent sees only the 5-8 tools relevant to the current step, not the full catalog.

**2. Externalize large tool outputs.** Store verbose tool results (file scans, database dumps, search results) on disk or in object storage. Pass the agent a file path and summary preview — not the full payload. This mirrors how Claude Code handles large outputs. Reduces context burn without losing access.

**3. Compaction over truncation.** When context fills, distill it — don't drop the oldest messages. Claude's compaction strategy summarizes previous reasoning and decisions into high-fidelity notes, preserving the signal while recovering the tokens. Simple truncation loses the model's own reasoning trail, which is often the most contextually important material.

**4. Typed memory tiers, not a single vector store.** Separate what you need fast (session state, preferences) from what you need semantically (knowledge retrieval). Episodic memory (what happened last session) and semantic memory (user preferences, entity facts) are architecturally different — shoving both into a vector index is a category error.

**5. Instrument for selection failure, not just execution failure.** The most expensive failure mode is the agent picking the wrong tool and then spending 3-5 steps recovering. Log each tool selection, the context at selection time, and the outcome. Build an eval set from real failure traces.

## Evidence

- **HN post (philippdubach):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Shopify Engineering (ICML 2025):** Sidekick hit the tool complexity wall as capabilities expanded. Solution: tool routing that dynamically routes to the right subset based on task type, not a monolithic tool list. Tool routing became a first-class architectural concern. — [Shopify Engineering](https://shopify.engineering/building-production-ready-agentic-systems)
- **Claude Cookbook (Anthropic, March 2026):** "Context is finite with diminishing marginal returns. The goal is finding the smallest set of high-signal tokens that maximize desired outcomes." Documents compaction, externalization, and selective retrieval as three first-party API strategies. — [Claude Context Engineering](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)
- **Agent Patterns (agentpatterns.tech):** "Tool selection is part of LLM inference. When the number of tools grows, the number of possible paths also grows, and selection becomes less stable." Documents LangChain's 3x tool selection accuracy improvement from retrieval-based loading. — [Agent Patterns: Too Many Tools](https://www.agentpatterns.tech/en/anti-patterns/too-many-tools)
- **Reddit r/AI_Agents:** "Vector DBs are NOT Memory. I've been banging my head against the wall... the agent kept failing. By Day 3 it was a complete mess." The agent used Pinecone + chunking + RAG. It worked for an hour, then degraded as semantically-similar-but-irrelevant context displaced session-critical information. — [Reddit r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1qefmh0/vector_dbs_are_not_memory_learned_this_the_hard/)
- **Technspire End-of-2025 Review:** Four categories shipped to production (developer tooling, internal ops, research/analysis, customer support augmentation). Key insight: "Agents only worked in narrow, well-scoped domains." Scope discipline — including tool discipline — was the distinguishing factor between production success and expensive pilot. — [Technspire](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **The hard limit is not the failure point.** Cursor caps at 40 tools, Copilot at 128. But accuracy degrades long before those limits. Plan for selection quality, not just tool availability.
- **RAG retrieval and memory are different problems.** Vector similarity answers "what is semantically similar?" Memory needs to answer "what should the agent actually recall right now?" These require different architectures.
- **Context compaction is not summarization.** Simply summarizing old messages loses the causal chain — why the agent made each decision. Preserve decision rationale separately from event records.
- **Tool descriptions matter as much as tool count.** A small set of poorly described tools causes more selection errors than a large set with precise, distinct descriptions. Invest in tool metadata before adding more tools.
