# S-765 · The Agent Stack Stratifiers: Why One Framework Cannot Win

The monoculture era of agent tooling is over. In 2024, teams defaulted to a single orchestration layer and called it done. In 2025-2026, production teams are explicitly rejecting monolithic agent stacks — splitting execution environments, memory backends, tool registries, and orchestration logic into independently-swappable layers. The teams winning are treating the agent stack like the data stack: ingestion separate from warehousing separate from transformation separate from BI.

## Forces

- **Each layer has a different rate of change.** Model providers ship weekly. Sandboxing infrastructure changes quarterly. Orchestration frameworks change monthly. Locking them together means one layer's churn breaks everything else.
- **Specialists beat generalists at each layer.** No single team can win at LLM routing, sandboxing, memory, tool schema, and observability simultaneously — just as no vendor won the entire cloud stack.
- **Defensibility lives at layer boundaries.** The organizational world model (which tools, which data, which policies) is the durable moat — not the orchestration framework on top.
- **Migration cost grows with coupling.** Teams that chose "all-in-one" frameworks in 2024 are now rewriting agent routing logic to swap models, replacing entire sandbox layers, or retrofitting observability into architectures that weren't designed for it.
- **Enterprise buying patterns mirror the stratification.** Procurement departments evaluate E2B and Modal for sandboxing separately from CrewAI for orchestration separately from Pinecone for memory — because they negotiate separate contracts, renewals, and SLAs.

## The Move

Decompose the agent stack into six independently-versioned layers. Own the interfaces; swap the implementations.

1. **Model / Reasoning layer** — LLM API gateway (OpenAI, Anthropic, Azure OpenAI, or self-hosted). Swap models without touching orchestration. Key pattern: always route through a gateway abstraction, never hardcode model names.
2. **Sandbox / Execution environment** — E2B, Modal, Shuru, or Firecracker microVMs. Isolates untrusted code execution (code interpreters, shell tools) from the rest of the stack. This is increasingly its own procurement line item.
3. **Memory / State layer** — Vector store (Qdrant, Weaviate, Pinecone, pgvector) + semantic memory architecture. Session state, long-term recall, and episodic memory are three separate concerns — most teams conflate them.
4. **Tool / Tool-calling registry** — MCP (Model Context Protocol) servers or custom REST tool schemas. MCP is converging as the standard for tool description poisoning and tool versioning, but custom REST still dominates in orgs with existing API ecosystems.
5. **Orchestration / Workflow layer** — LangGraph (state machines), CrewAI (role-based crews), or custom state machines. LangGraph is winning at production complexity; CrewAI is winning at initial velocity. AutoGen is winning in Azure shops post-merger into Microsoft Agent Framework (GA Q1 2026).
6. **Observability / Evaluation layer** — LangSmith, Phoenix, or custom trace infrastructure with faithfulness scoring. Traces are table stakes; the gap is behavioral scoring, cost attribution per agent, and regression detection across runs.

## Evidence

- **Engineering blog + HN synthesis:** Philipp D. Dubach documented the six-layer stratification with defensibility analysis, confirmed by multiple HN commenters who mirror the same architectural split in their own production systems — noting that sandboxing is "clearly becoming its own thing" with dedicated players (E2B, Modal, Shuru, Firecracker wrappers). — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/) + [HN Thread](https://news.ycombinator.com/item?id=47114201)
- **Framework comparison:** LangGraph (90K+ stars, state machine approach, production-grade) vs CrewAI (20K+ stars, role-based, fast prototyping) vs Microsoft Agent Framework (30K+ stars, Azure-conversational, GA Q1 2026) — each winning in different segments with explicit migration from CrewAI → LangGraph observed as complexity grows. — [devops.gheware.com](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Stack survey (end-2025):** 37% of Fortune 500 enterprises using 5+ AI models in production (up from 29%), and 80% of Fortune 500 evaluating agentic AI — routing decisions alone justify the layer separation. — [a16z AI Enterprise 2025](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/), cross-referenced with [techspire production lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Swapping the orchestration layer does not require rewriting your tool registry** — if you kept them separate from the start. Teams that built tools inside CrewAI tasks are now trapped; tools built as MCP servers or REST endpoints are portable across frameworks.
- **Memory is not one problem.** Session memory (short-term context window), episodic memory (past interactions), and semantic memory (structured knowledge) require different storage backends. Conflating them into one vector store creates retrieval noise and misses the recall granularity you actually need.
- **Sandboxing is not optional if you execute code.** Code interpreter tools running in the same process as your agent are a remote code execution risk. Treat the sandbox as an external service boundary, not an in-process library.
