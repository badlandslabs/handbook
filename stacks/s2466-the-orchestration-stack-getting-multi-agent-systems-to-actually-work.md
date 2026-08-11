# S-2466 · The Orchestration Stack

Multi-agent orchestration is the dominant topic in agentic AI discussions for 2025–2026 — and the dominant failure mode. The promise is compelling: specialized agents, parallel execution, fault isolation. The reality is that adding agents multiplies complexity, and complexity without structure collapses into expensive chaos. The question isn't whether to orchestrate — it's how to do it without burning through context windows, blowing your budget, and shipping behavior you can't predict.

## Forces

- **The complexity spiral hits fast**: Adding a second agent means managing inter-agent communication, shared state, failure propagation, and context partitioning. What looks like a straightforward decomposition becomes a distributed systems problem
- **Framework complexity vs. simplicity**: Both Anthropic and OpenAI independently found that their most successful enterprise customers shipped with "simple, composable patterns" — not complex framework abstractions — yet the ecosystem keeps pushing framework-first approaches
- **The human-in-the-loop tradeoff is non-obvious**: Teams oscillate between full autonomy and paranoid human oversight. The right answer depends on task reversibility, error cost, and whether you've actually measured your agent's reliability before widening its scope
- **Context is the real bottleneck**: A hub-and-spoke orchestrator can easily consume 100K+ tokens in tool definitions and inter-agent messages before the first productive action, making context management a first-class architectural concern

## The Move

Match your orchestration pattern to the problem shape. Six patterns cover the majority of production cases — most teams need only two or three combined in a single workflow.

- **Supervisor (Orchestrator-Worker)** for decomposable goals: A central agent parses the user's intent, breaks it into subtasks, assigns them to specialized workers, collects results, and synthesizes the final output. Best when the work has a clear root task with separable parts.
- **Sequential Pipeline** for multi-stage transformations: Each agent's output feeds the next as input. Chain-of-thought, document processing pipelines, and data enrichment flows. Best when order matters and each stage is single-purpose.
- **Parallel Fan-Out** for independent subtasks: One agent spawns N workers simultaneously, waits for all results, then merges. Best for bulk operations like batch document analysis, parallel research queries, or multi-source data fetching.
- **Router** for intent-driven dispatch: An LLM-based classifier routes incoming requests to specialized handlers. Best for customer-facing systems with distinct task types — compare to if/else but with semantic flexibility.
- **Hierarchical** for multi-team coordination: Mid-level managers coordinate groups of workers; senior orchestrators coordinate the managers. Scales to enterprise workflows. Best when different business domains require genuinely different expertise.
- **Evaluator-Optimizer Loop** for refinement cycles: One agent produces output, another evaluates it against criteria, and the first iterates. Best for code generation, document drafting, and any task where "good enough" is defined by evaluation rather than a single pass.

**Start assistive, automate later**: Begin with agents as recommenders with humans in the loop. Incrementally widen autonomy as you measure reliability in production. Rushing to full automation before establishing trust surfaces the most expensive failure modes first.

**Prefer direct tool calls over MCP for stability**: Anthropic's November 2025 advanced tool use documentation found that MCP introduces non-determinism through abstraction layers, ambiguous tool-selection behavior, and inconsistent parameter inference. For predictable production behavior, prefer direct function calls. Use MCP for discovery and prototyping, not production.

**Use Tool Search to combat context bloat**: Anthropic documented tool definition token costs spiraling to 134K+ tokens with full MCP server exposure. A GitHub MCP server alone ships ~26K tokens. Use on-demand tool discovery (loading only what the current subtask needs) rather than exposing all tools at once.

## Evidence

- **Engineering blog — Anthropic (Nov 2025):** Advanced tool use documentation documents real token costs of MCP servers (GitHub 35 tools = ~26K tokens; Slack 11 = ~21K) and introduces Tool Search as an on-demand discovery pattern to reduce upfront context cost. — [anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)

- **Primary source — arXiv paper (Dec 2025):** "A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows" finds that MCP "behavior remained unstable and exhibited flickering, non-reproducible failures" even after repeated instruction refinement, and recommends replacing MCP with direct function calls for production stability. — [arxiv.org/html/2512.08769v1](https://arxiv.org/html/2512.08769v1)

- **Engineering blog — WorkOS (July 2025):** Synthesizing Anthropic and OpenAI customer implementation data, finds that Morgan Stanley achieved 98% AI adoption through a RAG-based knowledge retrieval system for 16,000 financial advisors; BBVA deployed 2,900+ internal AI agents in 5 months; both companies report that "the most successful implementations weren't using complex frameworks — they were building with simple, composable patterns." — [workos.com/blog/enterprise-ai-agent-playbook](https://workos.com/blog/enterprise-ai-agent-playbook-what-anthropic-and-openai-reveal-about-building-production-ready-systems)

- **Community discussion — Hacker News "Ask HN" (2025):** Thread on multi-agent orchestration in production surfaces real implementation details: teams combining supervisor + fan-out patterns, using evaluator loops for code generation, and routing between specialized agents based on intent classification. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **Open-source — OpenAI Agents SDK:** Production-ready evolution of Swarm, built on three primitives (Agents, Handoffs, Guardrails) with built-in tracing and multi-agent coordination. The SDK's design philosophy explicitly favors "enough features to be worth using, but few enough primitives to make it quick to learn." — [openai.github.io/openai-agents-python](https://openai.github.io/openai-agents-python)

- **Enterprise case — Klarna (2025):** Deployed OpenAI-powered customer service agent handling 2.3M conversations/month (equivalent to 700 full-time agents), reporting 47% CSAT increase and $10M+ annual savings. Rollout also revealed that "customers began expressing frustration with AI-only support without clear escalation paths," illustrating the human-in-the-loop gap in autonomous deployments. — [delaware.pro](https://www.delaware.pro/en-lu/blogs/klarna-experiment-real-world-reflections-on-agentic-ai-deployment)

## Gotchas

- **Don't add agents when a tool will do**: Before introducing a second agent, check whether a better-scoped tool, context compression, or parallel tool calls within a single LLM turn could solve the problem. Multi-agent is right when tasks require independent reasoning, fault isolation, or different model sizes per subtask — not as a default for complexity.
- **Measure before automating**: Teams ship full autonomy before establishing reliability baselines. Run agents in assistive/co-pilot mode for long enough to measure task completion rate, error types, and human override frequency. Then widen autonomy proportionally. Rushing to automation is the most expensive mistake in agentic deployment.
- **Context management is not an afterthought**: The Production AI Institute and Anthropic both document context management as a core production concern — what to include in each turn, when to summarize, when to truncate conversation history, and how to partition context across agents. Treat it as an architectural decision, not a tuning parameter.
