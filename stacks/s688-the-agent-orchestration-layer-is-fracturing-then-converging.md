# S-688 · The Agent Orchestration Layer Is Fracturing, Then Converging

LangGraph, CrewAI, and AutoGen are not interchangeable. Teams that treat them as such spend 6–12 months rewriting. Production data from multiple independent sources now points to a clear decision tree — and a new protocol layer (MCP + A2A) is emerging as its own infrastructure tier.

## Forces

- **LangGraph has the steepest ramp but the lowest rewrite rate.** The graph/state-machine paradigm maps to real production debugging needs. Teams that start with CrewAI for speed often hit a wall when they need fine-grained control, conditional branching, or observability at the step level.
- **CrewAI's role-based model is genuinely faster to prototype.** For a team validating a concept in 2 weeks, CrewAI's agent/role/task abstraction is more intuitive than LangGraph's state graphs. But the same abstraction leaks at scale — when you need to share state across agents, handle partial failures, or instrument individual tool calls.
- **AutoGen is converging toward Microsoft's agent framework.** With Semantic Kernel merger and GA targeting Q1 2026, AutoGen's path is clearest for teams already deep in Azure. For everyone else, it's a narrowing choice.
- **The protocol layer is real and moving fast.** MCP (tool access) and A2A (agent collaboration) went from competing proposals to Linux Foundation standards in under 18 months. 50+ partners including AWS, Microsoft, Salesforce, SAP signed on. This is infrastructure, not hype.
- **Multi-agent overhead is a real cost, not a hypothetical one.** Each agent handoff adds 10–60 seconds of latency. A 5-agent pipeline that looked elegant in a diagram becomes a latency and cost problem in production — before you even get to the debugging nightmare.

## The Move

**Default to LangGraph. Reach for CrewAI only when the team is prototyping against a hard deadline and the scope is provably bounded. Treat A2A and MCP as first-class infrastructure, not add-ons.**

Specific guidance:

- **Use LangGraph's supervisor pattern** for multi-agent work — one orchestrator decomposes tasks and routes to specialists, rather than full peer-to-peer agent graphs. This pattern is debuggable, has predictable latency, and appears across LangGraph, CrewAI's hierarchical mode, and custom implementations.
- **Wire MCP in from day one**, not as a later addition. MCP (Model Context Protocol) standardizes tool calling across all major frameworks and models. The ecosystem of MCP servers is growing fast and switching cost after the fact is non-trivial.
- **Add A2A when you have multiple deployed agents that need to collaborate** — not for internal orchestration, but for cross-service agent-to-agent communication in production.
- **Default to supervisor/specialist topology over peer agent graphs.** Peer graphs (where any agent can call any agent) look flexible but produce undebuggable execution traces. Supervisor + specialists is the production pattern that keeps showing up.
- **If you start with CrewAI, have a migration plan.** Define the "LangGraph migration trigger" upfront — e.g., "when we need shared state across agents" or "when partial failure handling becomes critical." Don't discover the wall by hitting it.

## Evidence

- **Framework comparison (2026 data-driven):** LangGraph shows lowest rewrite rate in production due to graph-based state management matching real debugging needs. CrewAI fastest prototype-to-working-system but teams report hitting scalability limits within 6–12 months. AutoGen converging toward Microsoft Agent Framework for Azure-ecosystem teams, GA Q1 2026. 65% of teams report hitting a wall within 12 months and rewriting. — [Gheware DevOps AI Blog](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Protocol standardization:** Google's A2A (Apr 2025) and Anthropic's MCP (Nov 2024) both donated to Linux Foundation with 50+ enterprise partners. Industry consensus treats them as complementary layers — MCP for tool access, A2A for agent collaboration — analogously to how HTTP and WebSockets serve different networking needs. — [Zylos Research](https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols)
- **Multi-agent cost reality:** "95% of the time, you don't need multi-agent systems. The coordination overhead destroys your latency — each agent handoff adds 10 to 60 seconds." Building a 5-agent pipeline for a task that a well-prompted single agent handles just as well is the most common expensive mistake in agent engineering. — [Reddit r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1o5hvhm/multiagent_systems_are_mostly_theater/)
- **Supervisor pattern dominance:** LangGraph's supervisor pattern (one orchestrator → specialist agents) is the most common production architecture for multi-agent systems. Simple, debuggable, effective. — [TURION.AI](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **YC signal:** 67–70 of ~144 startups in YC Spring 2025 batch described as "AI agents." That ~47% concentration is the strongest market-signal data point for agentic adoption — and most are building narrow, well-scoped agents, not sprawling multi-agent systems. — [PitchBook](https://pitchbook.com/news/articles/y-combinator-is-going-all-in-on-ai-agents-making-up-nearly-50-of-latest-batch), [Evolution AI Hub](https://evolutionaihub.com/y-combinators-spring-2025-batch-70-startups-500k-each-on-agentic-ai/)

## Gotchas

- **Don't let GitHub star counts drive framework choice.** AutoGen has high visibility but its trajectory is toward Microsoft ecosystem lock-in, not open-source general-purpose use. Stars don't ship production code.
- **MCP is not A2A.** Teams sometimes conflate them. MCP connects a single agent to tools/APIs. A2A connects multiple agents to each other. Use the right protocol for the right abstraction layer.
- **The "more agents = better system" trap.** If a single well-structured agent with good tools and context can complete the task, adding agents adds latency, cost, and debugging surface area without adding capability. The supervisor/specialist split earns its cost only when specialists have genuinely different tool access, memory, or model requirements.
