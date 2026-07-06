# S-686 · The Agent Stack Is Stratifying Into Specialized Layers

[The era of monolithic agent frameworks is ending. After two years of all-in-one stacks, production teams are discovering that the hard problems — sandboxing, durable execution, observability, typed handoffs — don't live inside any single framework. The stack is splitting into six specialized layers, and the teams that win are the ones who choose the right layer to own versus outsource.]

## Forces

- **One framework can't own every layer.** LangChain, CrewAI, and AutoGen all solve orchestration well, but they all punt on sandboxing, durable state recovery, and multi-tenant cost isolation. Teams that tried to stay monolithic hit walls on all three.
- **Context is the hardest layer to migrate.** Unlike models (swap API keys) or orchestration (rewrite graphs), your semantic context, memory schema, and embedding corpus carry enormous switching cost. It sits at the highest lock-in risk and is the hardest to rebuild from scratch.
- **Sandboxing got real fast.** Code-execution agents, file I/O agents, and web-search agents can't safely run in the same process. The moment agents touch infrastructure (SSH, database writes, git), you need a sandbox boundary. This need didn't exist in prototype-land.
- **The eval gap is killing teams.** 89% of organizations have observability for agents, but only 52% have automated evals. This means most teams can see that something broke — they just can't prove it until a human notices.
- **Multi-model is now the default.** 37% of enterprises use five or more AI models in production. Single-provider lock-in is now treated as single-cloud risk.

## The move

Treat the agent stack as six composable layers. Own only the ones where your product is differentiated; buy (or integrate) the rest.

**Layer 1 — Model selection and routing**
- Route by capability, cost, and latency. Claude 3.5/3.7 for reasoning, o3-mini for cost-sensitive tasks, open-source (Qwen, DeepSeek) for on-prem/data-sensitive work.
- Use model cascading: cheap model decides whether to escalate to expensive model. This is the #1 cost lever.

**Layer 2 — Orchestration framework**
- LangGraph for complex stateful workflows needing graph visualization and checkpointing.
- CrewAI for fastest prototyping with role-based agents (expect to outgrow it at 6-12 months of complexity).
- AutoGen for collaborative multi-agent conversations, especially in Azure-heavy environments.
- Roll your own (Pydantic AI, raw API) when you need zero-framework control and the team has the seniority to own it.

**Layer 3 — Tool and resource integration (MCP)**
- Model Context Protocol has become the standard: 97M+ monthly SDK downloads, 5,800+ servers, 300+ clients (Dec 2025).
- MCP donated to Linux Foundation's Agentic AI Foundation — governance risk reduced.
- Build MCP servers for your internal tools; consume pre-built servers for common integrations (Slack, Drive, GitHub, Apollo).
- Watch A2A (Agent2Agent, Google's complementary standard for agent-to-agent communication) — not yet production-critical but worth tracking.

**Layer 4 — Sandboxed execution runtime**
- The newest and most neglected layer. Agents doing file I/O, bash, web search, or infrastructure changes need isolation.
- Options: Polos (open-source, Docker-native, durable workflows), E2B, Modal, Firecracker microVMs.
- Key feature to evaluate: durable execution (resume from exact step on failure), prompt caching (60-80% cost savings on retries), and Slack/infrastructure integration.

**Layer 5 — Memory and retrieval**
- Vector DBs: Qdrant, Pinecone, Weaviate for semantic search; pgvector for teams already on Postgres.
- Agentic RAG: agents plan, self-correct, and dynamically adapt retrieval strategy — not a static lookup. Harvey AI achieved 0.2% hallucination rate with this approach.
- Hybrid search (keyword + semantic, combined with RRF) outperforms pure semantic for production queries with specific entity names.

**Layer 6 — Observability and evaluation**
- LangSmith for LangGraph-first teams (deep integration, end-to-end tracing).
- Arize Phoenix for OpenTelemetry-native observability with auto-instrumentation across frameworks.
- Langfuse for self-hosted, open-source alternative.
- Minimum viable: per-span latency, token counts, cost, retrieval similarity scores, automated quality evals (RAGAS/DeepEval for retrieval, custom LLMs-as-judge for generation).

## Evidence

- **Blog post (Philipp Dubach, Feb 2026):** The agent stack is stratifying into six layers with different winners at each. 37% of enterprises now use five or more AI models in production. Context is the highest lock-in and hardest-to-rebuild layer. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN Show HN (Polos, 2026):** "I kept stitching together Docker, a workflow engine, a notification layer, and custom retry logic. Every team I talked to was doing the same thing." Built Polos as an open-source execution runtime handling sandboxing and durable workflows separately from the agent logic. — [https://news.ycombinator.com/item?id=47153680](https://news.ycombinator.com/item?id=47153680)
- **Research (RaftLabs, Nov 2025):** 1,445% surge in multi-agent system inquiries (Gartner, Q1 2024 → Q2 2025). 57% of organizations already have agents in production. Inference costs compound to $5-8 per complex 4-agent task. 49% of organizations cite high inference costs as top blocker. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Research (Deepak Gupta, Dec 2025):** MCP has 97M+ monthly SDK downloads, 5,800+ servers, 10,000+ published servers, 300+ clients. Enterprise adoption projected at 90% by end of 2025. Donated to Linux Foundation. 43% of MCP servers have command injection flaws — security is still a concern. — [https://guptadeepak.com/research/mcp-enterprise-guide-2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Engineering blog (Amazon/AWS, 2025):** HITL (human-in-the-loop) is critical for multi-agent evaluation — automated metrics fail to catch coordination failures, inter-agent communication breakdowns, and emergent edge-case behaviors. Framework-agnostic evaluation remains unsolved. — [https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)
- **Guide (aliac.eu, Feb 2026):** Production agentic RAG metrics: Harvey AI achieved 0.2% hallucination rate, Deutsche Telekom achieved 89% acceptable answer rate across 2M+ conversations, European bank saved EUR 20M over 3 years. 72% of enterprise RAG deployments fail in their first year. — [https://aliac.eu/blog/agentic-rag-in-production](https://aliac.eu/blog/agentic-rag-in-production)

## Gotchas

- **MCP security is not solved.** 43% of MCP servers have command injection flaws. Exploit probability exceeds 92% when running 10 plugins together. Validate tool inputs at the broker layer, not just at the MCP server.
- **Typed schemas are non-negotiable in multi-agent systems.** Untyped handoffs (raw strings between agents) are the #1 cause of multi-agent failure. Every agent boundary needs Pydantic/JSON Schema contracts — not just prompts.
- **The eval gap will bite you in production.** "89% have observability" sounds good until you realize that seeing a failed trace is not the same as catching a regression in CI. Build evals into your pipeline, not just your dashboard.
- **Inference costs compound non-linearly.** A 4-agent workflow doesn't cost 4x a single-agent call — it costs $5-8 per task because each agent makes multiple LLM calls and each failure triggers retries. Model cascading and semantic caching are not optional at scale.
- **Gartner's 40% cancellation rate.** By end of 2027, Gartner predicts 40%+ of agentic AI projects will be canceled due to escalating costs, unclear ROI, and inadequate risk controls. The teams that survive will be the ones who treated agents as production software — with evals, cost controls, and clear success criteria — not science fair projects.
