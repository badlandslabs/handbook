# S-778 · The Agent Stack Is Stratifying Into Six Specialized Layers

When you're assembling an agentic system, the instinct is to pick one framework and build the whole stack inside it. That works for a prototype. The moment you hit production, you discover that the layers have fundamentally different characteristics — different change rates, different defensibility profiles, different failure modes. Teams that treat the stack as monolithic pay for it in maintainability debt, lock-in, and failed rewrites.

## Forces

- **Layers have different half-lives.** The model layer changes every 6–12 months. The tool-calling interface changes slower. The orchestration logic changes slowest of all. Monolithic frameworks force you to upgrade everything together, or upgrade nothing.
- **Lock-in is non-obvious.** A framework that owns your orchestration also owns your state model, your retry logic, and your tool interface. Escaping it means rebuilding all of those in parallel.
- **Sandboxing has become its own discipline.** Execution isolation (what happens when the agent runs a tool?) is architecturally separate from orchestration. Treating it as an afterthought creates security and reliability gaps.
- **The defensible asset is not the model.** As models commoditize, the value accumulates in the organizational world model — the specific, curated knowledge and tooling that makes your agent useful in your domain.

## The move

The production-grade agent stack decomposes into **six specialized layers**, each with independent release cycles and different selection criteria:

1. **Security / Access Control** — RBAC/ABAC for agent actions, compliance guardrails, audit logs. Not optional for regulated domains. Plumbed before orchestration.
2. **Tool / MCP Layer** — Model Context Protocol (MCP) has emerged as the standard interface for tool exposure. Clean client-host-server architecture with JSON-RPC transport. Isolates tool definitions from orchestration.
3. **Execution / Sandboxing** — The runtime where agent actions actually execute. Shuru, E2B, Modal, Firecracker microVMs. This layer is stratifying independently because the isolation requirements are fundamentally different from orchestration.
4. **Orchestration** — LangGraph (state machines, retries, durable execution), CrewAI (role-based teams, fastest to MVP), or AutoGen (conversational dynamics). LangGraph is the production default unless you have an explicit reason otherwise. CrewAI for role-mapping problems and internal pipelines. AutoGen entering maintenance.
5. **Memory / Retrieval** — Hybrid search (dense + sparse, fused with Reciprocal Rank Fusion) + re-rankers. Naive vector search fails on exact-match queries (ISSUE-1234) and on "lost in the middle" for long contexts. Production RAG is a system design problem, not a model problem.
6. **Evaluation / Observability** — LangSmith, Arize Phoenix, or custom structured logging. Without evals at the agent level, you cannot distinguish "the agent got worse" from "the retrieval got worse."

## Evidence

- **Engineering blog (primary source):** The six-layer stack decomposition and layer-specific defensibility analysis from Philipp Dubach (2026) — 37% of enterprises now use 5+ AI models in production, with >40% of agentic AI projects predicted canceled by end of 2027 due to architectural debt — [philippdubach.com/posts/dont-go-monolithic](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN comment (primary source):** Developer describing the agent stack splitting with sandboxing becoming its own specialized layer — E2B, Modal, Firecracker wrappers converging on execution isolation — [news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Engineering blog (primary source):** Production RAG architecture breakdown — hybrid search with RRF, chunking strategy trade-offs, re-ranker evaluation, and the 3s latency budget for retrieval in production — [axiscoretech.com/blog/llm-agents/rag-architectures](https://axiscoretech.com/blog/llm-agents/rag-architectures)
- **Documentation (primary source):** MCP (Model Context Protocol) client-host-server architecture — JSON-RPC stateful sessions with clear security boundaries between layers — [modelcontextprotocol.io/specification](https://modelcontextprotocol.io/specification/2025-06-18/architecture)
- **Comparison analysis (primary source):** LangGraph vs CrewAI vs AutoGen decision framework — LangGraph for production planner-executor, CrewAI for role-based teams, AutoGen in maintenance — [internative.net/insights/blog/langgraph-vs-crewai-vs-autogen-2026-comparison](https://internative.net/insights/blog/langgraph-vs-crewai-vs-autogen-2026-comparison)

## Gotchas

- **Don't start with the framework — start with the flow.** Framework choice (LangGraph vs CrewAI) follows from the interaction pattern, not the other way around. CrewAI's "Flow-first" documentation now recommends wrapping crews in flows for production.
- **Naive RAG is a 40% failure rate at retrieval.** Without hybrid search, you lose exact-match queries. Without proper chunking, you dilute signal. Without re-rankers evaluated against your actual queries, you can't tell if retrieval quality degraded.
- **The MCP ecosystem is young but moving fast.** MCP SDK downloads are growing rapidly, but the tool catalog is fragmented. Verify that your tool's MCP server is actively maintained before committing to it.
- **Multi-agent coordination overhead is non-linear.** Three agents coordinating via a manager is tractable. Six agents with peer-to-peer coordination produces emergent failure modes that don't exist in the single-agent case. Test coordination under failure, not just under success.
