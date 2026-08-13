# S-2602 · The Multi-Agent Orchestration Stack — When One Agent Is Not Enough

A single agent, no matter how capable the underlying model, hits a ceiling when faced with complex, multi-domain tasks. It must hold the entire context, decide the next action, execute it, evaluate the result, and repeat — all within a single reasoning loop. Multi-agent orchestration breaks this by assigning each step to a specialized agent. The challenge: choosing the right orchestration pattern, choosing the right protocol stack, and resisting the urge to add agents you don't need.

## Forces

- **Adding agents compounds failure surface.** Every agent in a loop is a potential failure point. The more agents you add, the more coordination overhead, the more places the system can diverge from the intended path.
- **Framework complexity grows faster than capability.** LangGraph, CrewAI, AutoGen, and now OpenAI Agents SDK and Google ADK all solve the same problem in different ways. Teams frequently pick a framework before understanding the pattern it implements, then spend weeks retrofitting.
- **Agent-to-agent communication lacks standards.** Until late 2025, there was no standard way for agents built by different teams, using different models, to talk to each other. That changed with MCP (Anthropic, November 2024) and A2A (Google, April 2025), but adoption is still early.
- **The Anthropic surprise: simple patterns beat frameworks.** After working with dozens of teams deploying agents in production, Anthropic's engineering team found that the most successful implementations used direct LLM API calls — not frameworks. "Many patterns can be implemented in a few lines of code." The implication: most orchestration problems don't need an orchestration framework.

## The Move

The orchestration stack has six production-viable patterns, ordered from simplest to most complex. Start at the top, move down only when you have a demonstrated need.

**1. Sequential chain (LCEL or direct API).** For linear, multi-step tasks where each step's input depends on the previous step's output. In LangChain: `chain = prompt | model | output_parser`. In raw Python: a loop that passes the prior output as the next input. Use when: the workflow is fixed, steps are known at build time.

**2. Router pattern.** A single LLM call classifies the incoming request and dispatches to one of N specialized handlers. Microsoft's ISE team describes migrating a retail chatbot from a modular monolith to a router pattern — each handler is an isolated agent, and adding a new intent requires only adding a handler, not rewriting the core. Use when: request types are fixed and few, but each requires different logic.

**3. ReAct loop (Reasoning + Acting).** The agent loop: reason about state → call a tool → observe result → repeat. This is the foundational agent pattern. Implement directly with your LLM provider's tool-calling API before reaching for a framework. Anthropic recommends starting here with direct API calls and building your own loop. Use when: the agent needs to browse, search, compute, or interact with external systems.

**4. Plan-and-execute (also called supervisor/executor).** A planner agent breaks a task into steps. An executor agent runs them. A supervisor evaluates results and decides whether to replan. This separates "what to do" from "do it" — useful when planning quality matters more than execution speed. Use when: tasks are complex and benefit from deliberate planning before action.

**5. Multi-agent with coordinator.** A coordinator (sometimes called an orchestrator, supervisor, or manager agent) routes sub-tasks to specialized agents, collects results, and synthesizes a final response. Workers run in parallel. This is the pattern Microsoft evolved their retail chatbot toward when the modular monolith hit scaling limits — individual agents become independently deployable and reusable across teams. Use when: you have distinct skill domains (e.g., a CFO agent and a CRO agent) that should run independently.

**6. Hierarchical colony (Queen + workers).** The Hive framework (aden-hive/hive, 107 HN points) implements a Queen agent that does the work first, then spawns worker clones for parallel execution. Each worker is a full agent with its own loop, tools, and model — a clone of the Queen. State is shared through a distributed tracker. Use when: you have embarrassingly parallel workloads where the same task needs to run against multiple inputs.

**Protocol layer.** Two protocols now define the agent interoperability foundation:
- **MCP (Model Context Protocol)** — Anthropic, November 2024. Standardizes how agents connect to tools and data sources. 200+ MCP servers available as of 2026. Replaces ad-hoc tool-integration code.
- **A2A (Agent-to-Agent)** — Google, April 2025, contributed to Linux Foundation June 2025, v1.0 in early 2026. Standardizes how agents discover, delegate to, and collaborate with each other. Backed by 50+ enterprise partners.

## Evidence

- **Engineering post:** Anthropic's "Building Effective AI Agents" (December 2024, updated 2025; 543 HN points, 88 comments) — after working with dozens of production agent teams, the finding is unambiguous: the most successful teams used simple patterns, not complex frameworks. "We suggest that developers start by using LLM APIs directly: many patterns can be implemented in a few lines of code." — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Enterprise case study:** Microsoft's ISE team documented a retail customer's evolution from a router-pattern modular monolith (multiple specialized agents, single query routed to one) to a microservices-style coordinator architecture — individual agents became independently deployable and reusable across teams. The key finding: the original architecture worked until cross-team reuse was required, at which point tight coupling became the blocker. — [https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Open-source framework:** Hive (aden-hive/hive) — "zero-setup, model-agnostic runtime for colonies of agents" with built-in state management, failure recovery, observability, and human oversight. The Queen-worker pattern was validated by a solo developer building a production SaaS (growity.ai) using Claude Code as an entire engineering team, eventually converging on a 3-role multi-agent setup with strict constraint on agent count. Show HN, 107 points. — [https://github.com/adenhq/hive](https://github.com/adenhq/hive)

- **Framework comparison:** LangGraph (stateful graphs, durable execution, Anthropic/Replit/LinkedIn/Uber in production), CrewAI (fastest path to role-based agents), and OpenAI Agents SDK (March 2025) vs. Google ADK (April 2025, 20k stars) represent the three tiers of multi-agent infrastructure: provider-native SDKs optimized for one model family, independent frameworks that work across providers, and lightweight wrappers that handle a single LLM call. — [https://www.ayautomate.com/blog/best-multi-agent-frameworks](https://www.ayautomate.com/blog/best-multi-agent-frameworks)

## Gotchas

- **The CEO agent anti-pattern.** When one agent is given broad authority to create organizational structure, it will — creating dozens of roles, inter-agent memos, and organizational complexity that consumes compute and produces nothing. Constrain agent count and role scope from the start. From the growity.ai developer: "Agents will happily create organizational complexity forever. You have to constrain them hard."
- **Framework over-engineering.** LangChain's 2025 production survey found that simple chains handle 80% of production use cases, yet teams consistently over-engineer their first implementations. Before adding CrewAI or LangGraph, implement the pattern directly with the LLM API and confirm the pattern is actually your bottleneck.
- **Protocol fragmentation is still real.** MCP has 200+ servers and strong adoption for tool integration. A2A is v1.0 but adoption is still early — most production multi-agent systems still use ad-hoc communication protocols. Don't assume interoperability until you've tested it across your specific stack combination.
