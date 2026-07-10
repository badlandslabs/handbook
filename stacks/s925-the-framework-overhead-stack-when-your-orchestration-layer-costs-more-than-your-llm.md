# S-925 · The Framework Overhead Stack — When Your Orchestration Layer Costs More Than Your LLM

You needed to call an LLM. You installed a framework, wrote 400 lines of YAML and Python glue, and now your p95 latency is 30% higher, your debugging requires reading framework source code, and a 4-agent workflow costs $4.80/run because the framework burned 3 extra steps on its own orchestration before your first tool even ran. The LLM cost is fine. The framework is what's expensive.

## Forces

- Frameworks (LangChain, CrewAI, AutoGen) promise fast prototyping but add abstraction layers that make debugging harder than calling the API directly — the most common production complaint.
- Direct API calls achieve 40% lower p50 latency and 8% lower token overhead per call compared to framework-wrapped equivalents — real benchmarks, not estimates.
- The cost formula is `model_choice × step_count`. Every framework-managed orchestration step is a step you didn't choose but still pay for.
- Framework choice shapes production constraints: CrewAI handles multi-agent but lacks state persistence for long runs; LangGraph gives stateful graphs but demands developer-heavy setup; AutoGen is in maintenance mode.
- Anthropic's own engineering team — after working with dozens of production agent teams — recommends direct API calls for most patterns, with frameworks only when multi-step complexity genuinely justifies the overhead.
- LLM API calls account for 60–80% of total agent operating cost. Framework overhead is on top of that.

## The move

Start with direct LLM API calls. Reach for a framework only when you can name the specific capability it provides that would take you more than a few days to build yourself.

**The direct-first playbook:**
- Call the model API directly with structured outputs or JSON mode. Most agent patterns (tool calling, chain-of-thought, simple loops) fit in under 100 lines of Python.
- If you need stateful graph workflows (branches, checkpoints, replay), use LangGraph — it's the only production-grade graph framework with typed state schemas, versioning, and checkpointing built in.
- If you need multi-agent role coordination (researcher → writer → reviewer), use CrewAI — it handles role assignment and handoffs out of the box, but accept that state persistence for long-running tasks is your problem.
- Never use AutoGen for new projects. Microsoft shifted it to maintenance mode; use Microsoft Agent Framework instead.

**The tool integration standard — use MCP:**
- Anthropic's Model Context Protocol has become the de facto standard for agent-tool integration, replacing the ad-hoc tool definitions that each framework implemented differently.
- MCP provides standardized authentication, permissions, and transport (stdio and Streamable HTTP). This matters for auditability in regulated environments.
- Direct MCP implementation is simpler than framework tool abstractions once you understand the protocol.

**When framework complexity pays off:**
- 5+ distinct tools with complex routing logic → LangGraph's typed state management reduces bugs
- Multi-agent crews with role handoffs → CrewAI's role system avoids rewriting coordination logic
- Teams that need to ship fast and iterate → framework abstractions reduce boilerplate enough to matter for time-to-first-working-prototype

## Evidence

- **Anthropic engineering post:** After working with dozens of teams building agents, Anthropic found "consistently, the most successful implementations use simple, composable patterns rather than complex frameworks" — recommending direct API calls with few-line implementations over framework wrappers. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Latency and cost benchmarks:** Direct API calls vs. LangChain-wrapped equivalents show p50 latency 280ms vs. 340ms (+21% overhead), p95 under load 710ms vs. 920ms (+30%), and cost per 1M input tokens $0.30 vs. $0.32 (+8% token overhead). Setup time: 5 min direct vs. 25 min LangChain. — [markaicode.com](https://markaicode.com/vs/anthropic-vs-langchain)

- **Production cost breakdown:** Across 4 real production deployments tracked over 6 months (October 2025–April 2026), LLM API calls account for 60–80% of total operating cost. A 3-agent CrewAI workflow (System C) cost $3.20/run in API calls alone, versus $0.31/run for a 2.4-step LangGraph single agent (System A). Model choice × step count is the operative formula. — [inventiple.com](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)

- **Framework landscape 2026:** AutoGen is in maintenance mode (Microsoft shifted to Microsoft Agent Framework). LangGraph powers production agents at Klarna, Uber, and LinkedIn. CrewAI has 60% Fortune 500 adoption and 44K+ GitHub stars. A fourth category — managed multi-agent platforms — has emerged for teams that need orchestration, observability, governance, and multi-tenancy without building it themselves. — [dev.to](https://dev.to/cristian_iridon_286794874/langgraph-vs-crewai-vs-autogen-in-2026-pick-the-right-ai-agent-framework-or-skip-frameworks-4m2c)

- **HN Show HN — Optio:** Kubernetes-based agent orchestration (88 points, 60 comments) built with Fastify + BullMQ + Drizzle ORM, running Claude Code and Codex in isolated K8s pods. The maintainer's explicit design choice: build on simple, well-understood primitives rather than an agent framework. — [news.ycombinator.com/item?id=47520220](https://news.ycombinator.com/item?id=47520220)

## Gotchas

- **CrewAI lacks built-in state persistence.** A 4-agent crew that fails on agent 3 restarts the entire crew — expensive for long-running tasks with significant token burn. Build your own checkpoint layer or use LangGraph.
- **LangChain adds abstraction without simplification.** The framework hides prompts and responses behind layers, making it harder to debug incorrect assumptions about what's happening. Know what's under the hood.
- **Framework overhead compounds in multi-agent systems.** Each additional agent typically adds 2–4 orchestration steps managed by the framework itself. In a 5-agent pipeline, you may be paying for 10–20 framework-managed steps per run.
- **MCP adoption is uneven.** It's the right direction for tool integration, but not all frameworks support it equally yet. Direct MCP implementation gives you more control than waiting for framework support.
