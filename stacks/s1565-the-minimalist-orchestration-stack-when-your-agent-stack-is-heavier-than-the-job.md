# S-1565 · The Minimalist Orchestration Stack — When Your Agent Stack Is Heavier Than the Job

You spent two weeks integrating LangChain. Your agent now handles six tool calls and one conditional branch. You are still debugging the integration. Meanwhile, the team that shipped the same capability last Tuesday wrote 80 lines of Python and a Postgres table. The gap between agent framework complexity and agent capability needs is wider than the framework vendors admit.

## Forces

- **Frameworks solve problems you do not have.** LangChain, CrewAI, AutoGen, and their kin were built for the hardest multi-agent scenarios. Most real deployments are simpler — and the framework tax is pure overhead.
- **The "roll your own" contingent is growing, not shrinking.** Practitioners with production experience increasingly default to minimal Python orchestration, not framework-first. The signal is consistent across multiple independent threads.
- **Production agents are less agentic than demos.** Anthropic's own guidance (their most-viewed engineering post, 543 HN points) says: prefer simple workflows until you genuinely need the agent's flexibility. Most teams do not need it.
- **Cost and latency compound through orchestration layers.** Every abstraction between you and the LLM adds inference latency, debugging opacity, and failure surface. A LangChain loop that runs 200 steps costs real money and produces no useful signal when it breaks.

## The Move

Start with the simplest possible architecture. Add complexity only when evidence forces it.

- **Parallelize aggressively.** Most multi-step tasks have independent sub-tasks. Run them concurrently, not sequentially. This is the single highest-leverage change teams overlook.
- **Route at the task level, not the model level.** A lightweight router (regex, keyword match, or small classifier) that dispatches to the right agent costs 5ms and saves 400ms of wasted inference. Do not route with a frontier model.
- **Use a shared message bus for inter-agent communication.** Redis Streams or Postgres pub/sub works fine. Do not build a custom message protocol. Keep the schema flat: `{agent_id, task_id, payload, timestamp}`.
- **Instrument before you optimize.** Log every agent decision, tool call, and LLM call with cost and latency. Without this, you cannot tell a good agent from a bad prompt.
- **Implement step-counting for loop detection.** Hard cap at N steps (typically 20-50 depending on task complexity). Track cost in real time. Alert on threshold breach.
- **Prefer stateless unless state is required.** If an agent can finish a task in one session, do not add memory. Add memory only when the evidence (not the hypothesis) shows a need for it.

## Evidence

- **HN Ask: Multi-agent orchestration in production:** A practitioner thread (11 comments) asked "How are you orchestrating multi-agent AI workflows in production?" Responses: one team uses Node.js + V8 isolates with Express endpoints; one says "There's absolute 0 framework out there that's good enough for serious work"; a third built on top of LangGraph but wrote their own orchestrator; another uses the Agno framework for minimal overhead. The consistent pattern is custom or near-custom on top of a thin library. — [Hacker News, ~3 months ago](https://news.ycombinator.com/item?id=47660705)
- **HN Ask: Does anyone use CrewAI or LangChain anymore?** A thread asking directly about these frameworks' continued usage attracted responses noting teams are migrating to simpler patterns: custom Python, LangGraph (without LangChain abstractions), or n8n for visual workflows. The frame is abandonment, not adoption. — [Hacker News, 4 months ago](https://news.ycombinator.com/item?id=47132187)
- **Anthropic "Building Effective AI Agents" (Dec 2024):** Anthropic's engineering team explicitly recommends: workflows (predefined code paths) for predictable, consistent tasks; agents (model-driven tool use) only when flexibility is genuinely needed. The post has 543 points on HN and is the canonical reference for this distinction. Key quote: "Find the simplest solution possible, and only increase complexity when needed." — [Anthropic Engineering, December 2024](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Do not use a framework because it is popular.** Popularity correlates with documentation coverage, not with production fit. LangChain's 136K stars reflects 2023 enthusiasm; practitioners shipping in 2025-2026 are more skeptical.
- **A framework does not replace an observability layer.** LangChain and CrewAI have built-in tracing, but it is not production-grade observability. You still need structured logging, cost tracking, and step-level traces. Budget for this separately.
- **The "one more framework" temptation is a trap.** Adding LangChain/CrewAI/AutoGen because you might need multi-agent coordination later is buying insurance against a problem you do not have. Build the complexity when the use case exists.
- **Parallelism in agent frameworks is often simulated.** Many frameworks claim parallel agent execution but serialize under the hood due to shared state. Verify with a load test, not a demo.
