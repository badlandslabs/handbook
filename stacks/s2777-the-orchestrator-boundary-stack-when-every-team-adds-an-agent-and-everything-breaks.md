# S-2777 · The Orchestrator Boundary Stack — When Every Team Adds an Agent and Everything Breaks

Your system worked fine with one agent. Then a second team added a second agent for a different domain, and you got a shared context object that both agents mutate simultaneously, a race condition that manifests once a month on Fridays, and no way to trace which agent produced which intermediate state. Someone suggests adding a third agent to manage the first two. This is the orchestrator boundary problem: agents are easy to add, but the coordination layer is where systems either scale or collapse.

## Forces

- **Agents are cheap; coordination is expensive.** Spinning up a new agent feels lightweight — it's just another LLM call with a different system prompt. But every new agent adds state dependencies, failure propagation paths, and observability gaps that don't appear in the prototype.
- **The wrong boundary is worse than no boundary.** Splitting agents along organizational lines (marketing agent, sales agent) creates brittle handoffs. Splitting along tool-and-context lines (file agent, web agent, code agent) tends to hold up, but requires up-front analysis that feels like over-engineering.
- **Naive multi-agent looks like microservices but isn't.** Agents share LLM state, not clean API contracts. A failing agent in a shared-context system can corrupt the conversation history for every other agent. A failing microservice just returns a 500.
- **Durable execution is non-negotiable for long-running agents.** A step that takes 20 minutes (a web scrape, a database query) cannot live in a process that can restart. Teams that skip this discover it at 2am.

## The move

Start at the lowest complexity that meets the requirement. Scale up only when you hit a concrete, observed bottleneck.

**1. Instrument the single-agent baseline first.** Before adding a second agent, add step-level tracing to the first one. Know how many tool calls it makes, which ones fail, and how long each step takes. The Azure Architecture Center calls this "single agent with tools" — one agent reasoning over a defined toolset, looping until completion. This handles far more than teams expect.

**2. Add a router, not a second agent, at the first fork.** When you need different behavior for different request types, add a classification step that dispatches to the same agent with different tool access — not a separate agent. The dispatch logic is a deterministic state machine, not an LLM decision.

**3. Move to multi-agent only for three specific signals:**
- Different tool access requirements that can't be conditionally gated in one agent
- Context overflow from a single conversation window
- Independent failure domains that need circuit breakers from each other

**4. Use a deterministic state machine as the orchestrator.** The orchestrator routes tasks, manages timeouts, and enforces ordering — it is not an LLM. Stateless agent workers receive tasks, execute, and return results. LangGraph is the dominant open-source pattern for this; Temporal handles durability. The production pattern from Innoflexion's 2026 enterprise analysis: "a single orchestrator with a deterministic state machine in front of a pool of stateless agent workers, connected through a durable task queue."

**5. Isolate memory with per-agent scoped snapshots.** Do not use one global context object. Each agent gets its own memory scope. Pass only the minimal necessary context at each handoff. The Anthropic production architecture guide confirms: "session memory in clustered store, not single-node Redis" and per-stage isolation so a slow tool call doesn't cascade.

**6. Make agent boundaries align with tool boundaries.** An agent that searches the web and writes files is two different failure domains. Splitting them means the web-search agent can time out without corrupting the file-write agent's state. This is the "single-responsibility agent" principle from the arXiv production-grade agentic AI paper (Bandara et al., December 2025).

**7. Add observability before the second agent ships.** You need to answer: which agent handled this request, what tools did it call, what did it return, and was the result correct? Without this you cannot debug a multi-agent failure — you can only restart and hope.

## Evidence

- **Official guide:** OpenAI's "A Practical Guide to Building Agents" presents a three-level complexity ladder (direct model call → single agent with tools → multi-agent) and explicitly states teams should "not add agents" when simpler approaches suffice — [https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents)

- **Research synthesis:** Zylos Research (April 2026) documents that "by 2025 ad-hoc agent chaining had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs had taught teams that agent coordination requires the same engineering discipline as distributed systems." The 2026 synthesis uses Temporal for durability, LangGraph for state graphs, and Kafka + A2A + MCP for event-driven — [https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)

- **Enterprise analysis:** Innoflexion's 2026 multi-agent orchestration guide synthesizes from 40+ client deployments: "a production multi-agent architecture puts a single orchestrator with a deterministic state machine in front of a pool of stateless agent workers, connects them through a durable task queue, and isolates shared memory with per-agent scoped snapshots" — [https://www.innoflexion.com/blog/multi-agent-orchestration-enterprise-genai-2026](https://www.innoflexion.com/blog/multi-agent-orchestration-enterprise-genai-2026)

- **Architecture guide:** Microsoft Azure's AI Agent Design Patterns guide provides a decision table for when to escalate from single-call → single-agent → multi-agent, emphasizing the cost/simplicity trade-offs at each level — [https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

- **Academic paper:** "A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows" (arXiv:2512.08769, December 2025) recommends: tool-first design over MCP, pure-function invocation, single-responsibility agents, clean separation between workflow logic and MCP servers, containerized deployment, and KISS principle — [https://arxiv.org/pdf/2512.08769](https://arxiv.org/pdf/2512.08769)

## Gotchas

- **Adding an agent to fix a broken agent compounds the problem.** A poorly scoped second agent that shares context with the first will corrupt both. Fix the boundary first, then add the agent.
- **LLM-as-orchestrator is expensive and non-deterministic.** Using a language model to decide what to do next, in addition to executing, doubles your inference cost and introduces non-determinism into your control flow. Keep orchestration deterministic; let the agent focus on execution.
- **Memory isolation is not the default.** Most agent frameworks start with a shared conversation history. You have to actively scope per-agent memory. Teams that skip this end up with agents that "hallucinate" from seeing each other's internal reasoning.
- **Durable execution is an after-thought until it isn't.** The first time an agent step takes 20 minutes and the pod restarts, you lose the entire run. Build this in from the start: task queue persistence, step checkpointing, and replay capability.
