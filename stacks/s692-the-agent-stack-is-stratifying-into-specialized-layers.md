# S-692 · The Agent Stack Is Stratifying into Specialized Layers

[The agent stack is not a monolith. Every major compute era decomposes into specialized layers with different winners at each level — and the 2025–2026 AI agent stack is mid-stratification. Teams building "monolithic" agent systems are building technical debt; the infrastructure supporting each layer is diverging faster than most teams realize.]

## Forces

- **Models are commoditizing; context is compounding.** Every foundation model provider is racing to the bottom on price. The defensible asset — what competitors cannot replicate in 6 weeks — is the proprietary context and organizational world model you build on top. — [Philipp Dubach](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Sandboxing wasn't supposed to be its own category.** When agents started executing code, spawning sub-processes, and calling third-party APIs, the security/compute isolation layer suddenly needed its own product. E2B, Modal, Shuru, and Firecracker wrappers are all converging on the same gap. — [HN/phil777](https://news.ycombinator.com/item?id=47114201)
- **The 5+ model reality.** 37% of enterprises now run 5+ AI models in production (up from 29% in 2024), which means model routing and cost tiering are first-class infrastructure concerns, not afterthoughts. — [a16z AI Enterprise 2025 via Dubach](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Guardrails are not enough.** Input/output validation alone doesn't stop runaway agent loops. The real failure mode is agents calling each other in unbounded recursion — incidents have run $15 to $47,000 depending on duration. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

## The move

Build each layer with the right abstraction for its job, and treat the seams between layers as first-class interfaces:

- **Orchestration layer** — LangGraph for complex graph-based workflows where state machine semantics matter; CrewAI for rapid prototyping of role-based teams; avoid the temptation to use orchestration primitives as a general-purpose workflow engine.
- **Sandbox/execution layer** — Isolate every agent's tool execution in a subprocess with declared network whitelists and optional AST scanning before install. This is not optional once agents touch external APIs. — [HN/topherchris420](https://news.ycombinator.com/item?id=47279088)
- **Memory layer** — SQLite + FTS5 works at personal-agent scale with zero infra overhead. Graduate to Pinecone, Qdrant, or pgvector only when query volume or latency demands it. Context—not the vector DB—is the defensible part.
- **Tool/MCP layer** — Model Context Protocol is consolidating tool schemas across the ecosystem. Declare tools with strict output schemas and validate at the boundary; do not let agents pass unstructured JSON between tools.
- **Cost enforcement layer** — Budget circuit breakers are table stakes. The Zylos incident database shows the median runaway agent loop costs $X,000–$47,000 depending on how fast your alerting fires. Set per-session and per-task spend caps before going multi-agent.
- **Observability layer** — LangSmith, Phoenix, or a custom structured-logging stack. The harder requirement: evals, not just traces. 89% of teams have traces; only 52% have evaluation pipelines. — [Raft Labs](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Evidence

- **Engineering blog:** Philipp Dubach's 6-layer stack thesis (orchestration, sandboxing, memory, tools, routing, observability) with defensibility analysis — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN thread (777+ points):** Sandboxing emerging as its own product category, cross-referenced against E2B, Modal, Firecracker wrappers, with commentary on why monolithic agent architecture is the wrong call — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Research report:** Zylos production cost engineering data — $47K LangChain loop over 264 hours, $82K stolen-key incident, 60–85% of AI spend recoverable via caching/routing/circuit-breakers — [https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)
- **Industry analysis:** 37% enterprise 5+ model adoption (up from 29%), 40% of enterprise apps will have agents by 2026, >40% of agentic projects will be canceled by end of 2027 — [Gartner via Dubach](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Research synthesis:** 57% of organizations have agents in production; 4 orchestration patterns cover most use cases; inference costs compound to $5–8/complex task — [Raft Labs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Reddit/local-first build:** SQLite + FTS5 for personal-agent memory scale validated in production with cross-channel context persistence — [HN/topherchris420](https://news.ycombinator.com/item?id=47279088)

## Gotchas

- **Going monolithic at the orchestration layer** — stuffing everything into a single LangChain/LangGraph graph creates a state explosion that becomes undebuggable. Separate agents, separate state, shared memory schemas.
- **Skipping the sandbox layer** — agents with tool access that aren't process-isolated are security incidents waiting to happen. This is especially true when agents can call third-party APIs with credentials.
- **Treating the model as the moat** — model choice is a commodity decision. The layer that compounds defensibility is the proprietary context, evaluation data, and organizational world model you build over time.
