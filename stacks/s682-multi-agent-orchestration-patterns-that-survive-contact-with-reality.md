# S-682 · Multi-Agent Orchestration Patterns That Survive Contact With Reality

[Single-agent systems with good tools handle more than you expect. Multi-agent systems earn their complexity only when agent boundaries align with genuine organizational or capability boundaries — not workflow steps. Getting this wrong multiplies cost, latency, and failure surface with each added agent.]

## Forces

- **Multi-agent complexity compounds non-linearly.** Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. The failure mode is not "it doesn't work" — it's "it works 80% of the time and you have no idea which 20%."
- **Cost surfaces in surprising places.** A support ticket resolution costing $1.10: $0.80 in LLM calls (visible), but $0.17 in MCP tool calls and $0.13 in external APIs (invisible in LLM dashboards). In tool-heavy workflows, non-LLM costs can exceed LLM costs. Teams with multi-agent systems routinely underestimate total cost by 30–50%.
- **The orchestration philosophy split is real.** LangGraph uses state machines, CrewAI uses roles, AutoGen uses conversations. These are not equivalent — they encode different assumptions about who is in control, and switching mid-project is painful.
- **Agent boundaries are the hardest decision.** "Start with one agent and add more only when a genuine boundary appears. Complexity is not free." — [FRENXT Labs](https://www.frenxt.com/research/multi-agent-architecture-guide)

## The move

**Three patterns actually work in production. Everything else is still in the "expensive pilot" bucket.**

### Supervisor + Specialists (most proven)
- One supervisor agent decomposes tasks and routes to specialist agents
- Specialists execute and return; supervisor integrates and validates
- **Why it works:** Simple, debuggable, natural failure isolation
- **Tools:** LangGraph's built-in supervisor, CrewAI hierarchical mode, or custom orchestrator
- **Best for:** E-commerce, customer support, multi-domain research tasks

### Parallel Execution with Fan-Out/Gather
- A router agent classifies input and dispatches to multiple specialists simultaneously
- Specialists work independently; results merge at a reunion point
- **Why it works:** Latency wins when sub-tasks are independent
- **Best for:** Multi-source research, parallel document processing, simultaneous API queries

### Pipeline Chaining
- Agents pass output as input to the next stage — no central supervisor
- **Why it works:** Minimal shared state, clear data flow, easy to trace
- **Best for:** Linear workflows where each stage has a clear output contract

**Unreliable in production:** Fully peer-to-peer agent networks, autonomous agent swarms without a central coordinator, and role-based agent teams without explicit state contracts.

## Evidence

- **Microsoft ISE field note:** Building a scalable multi-agent system for e-commerce voice/screen orchestration identified four non-negotiable requirements — accurate agent selection, optimized LLM usage (latency + token spend control), efficient orchestration with clear hand-offs, and horizontal scalability for adding agents without degrading performance. — [Microsoft ISE Developer Blog, Nov 2025](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)

- **Production cost anatomy:** One "resolve support ticket" task (5 LLM calls, 3 MCP tool calls, 4 external API calls) cost $1.10 total. $0.80 LLM, $0.17 MCP tools, $0.13 external APIs. In workflows with heavy tool usage, non-LLM costs regularly exceed LLM costs — invisible in standard LLM provider dashboards. — [Gris Labs / AgentMeter, March 2026](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)

- **Orchestration framework comparison:** LangGraph: 90,000+ GitHub stars, graph-based state machines, best for production complexity. CrewAI: fastest prototyping, role-based model, teams hit scalability limits within 6–12 months. AutoGen (Microsoft): conversational collaboration, Azure-native, GA planned Q1 2026. Bottom line: "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6–12 months in." — [Gheware DevOps AI Blog, 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

- **MCP adoption data:** Since November 2024 launch: OpenAI adopted MCP across ChatGPT Desktop and API (March 2025), Google DeepMind confirmed Gemini MCP support (April 2025), Microsoft/AWS/Cloudflare/Bloomberg as backers. 97+ million monthly SDK downloads. — [Udemy course citing ecosystem data, 2025](https://www.udemy.com/course/model-context-protocol-free)

## Gotchas

- **Start with one agent.** The most common premature optimization is adding a second agent before the first has defined tool contracts, error handling, and observability.
- **Non-LLM costs are your blind spot.** Instrument every tool call, every API call, every external service. Use a cost tracking layer that spans LLM + tools + APIs, not just token counts.
- **Supervisor loops kill latency.** A supervisor that calls a specialist, which calls the supervisor, which calls another specialist — this is the most common multi-agent anti-pattern. Define call depth limits and enforce them.
- **State management is the unsexy critical path.** Typed, scoped shared state with checkpointing is what separates a multi-agent system that recovers from failures gracefully from one that silently propagates corrupted context.
- **Orchestration framework debt is expensive.** Switching from CrewAI to LangGraph mid-project costs roughly 6–12 weeks. The rule of thumb: if you're building for production scale, start with LangGraph even if the learning curve is steeper.
