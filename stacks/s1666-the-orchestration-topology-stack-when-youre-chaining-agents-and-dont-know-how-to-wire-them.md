# S-1666 · The Orchestration Topology Stack — When You're Chaining Agents and Don't Know How to Wire Them

You built three agents. They each work in isolation. When you wire them together, the results degrade — context bleeds between steps, agents argue with each other, and the output is worse than a single agent working alone. The problem is not the agents. It is the topology: you picked a pipeline when you needed a fan-out, a monolith when you needed a supervisor tree. Choosing the wrong orchestration architecture is the most expensive mistake in multi-agent systems because it propagates into every downstream decision.

## Forces

- **"God agent" hits the ceiling.** A single overloaded agent managing 10+ tools and 5+ step types accumulates context, degrades on every dimension, and becomes impossible to debug (Pockit Tools, "LangGraph vs CrewAI vs AutoGen: Complete Guide," 2026; explainx.ai, "Multi-Agent Orchestration Patterns," June 2026).
- **Not every multi-agent setup needs orchestration.** The consensus from r/LangChain in 2026: most teams reach for orchestration too early. A single `create_agent` with 3–5 well-scoped tools beats a three-node graph with extra latency (ideatomvp.ai, "LangGraph Agent Orchestration Patterns," June 2026).
- **Orchestration cost is real and compounding.** CrewAI's own community data shows multi-agent token costs run 5× higher than single-agent equivalents due to multi-agent conversations multiplying LLM calls (aistackhub.ai, "AI Agent Orchestration Platforms," May 2026).
- **The graph shape determines the failure mode.** Sequential pipelines fail on the first bad output. Fan-out systems fail silently when one branch fails. Event-driven systems fail when no agent consumes the right event. Each topology has a characteristic failure pattern you must design for (Zylos Research, "Agent Workflow Orchestration Patterns," April 2026).

## The Move

Pick the topology by the dependency structure of your task — not by familiarity with a framework.

**1. Use a sequential pipeline when steps have hard data dependencies.** Step N requires the complete output of step N-1. Example: research → draft → edit → publish. Tools: LangGraph `StateGraph` in linear mode, or a plain Python loop over agent calls with a shared schema. This is the simplest valid architecture — use it until it breaks.

**2. Use fan-out / fan-in when independent subtasks exist.** Multiple agents process different slices of the same input in parallel, then results merge. Example: scrape three news sources simultaneously → synthesize. Tools: LangGraph `Send` API, CrewAI `Process.parallel`, or a `ThreadPoolExecutor` with structured result collection. Key: set a merge strategy before you build this — merging five contradictory summaries without a judge agent produces noise.

**3. Use an orchestrator / worker hierarchy when task decomposition is non-deterministic.** A central planner decides what sub-tasks exist, delegates them, and aggregates results. The planner must be able to revise its decomposition based on intermediate results. Tools: LangGraph with conditional edges for dynamic routing, or a custom supervisor class. This is the most common pattern for complex research, analysis, or planning tasks.

**4. Use a supervisor tree when agents need independent lifecycles and isolation.** Each worker runs as its own process or container, has its own state, and reports to a supervisor that handles retries, escalation, and termination. Tools: Temporal with durable executions, Microsoft Agent Framework with Magentic orchestrator, or Akka-style actor supervision. This is where enterprise deployments land — not where they start.

**5. Use event-driven (pub/sub) when agents should react to state changes, not wait for calls.** Agents publish results to a message bus; downstream agents subscribe to relevant event types. Tools: Kafka or Redis Streams as the bus, A2A protocol for agent-to-agent messaging, MCP for tool discovery. This topology decouples agents completely — a slow worker never blocks a fast one. Cost: debugging a silent failure when no subscriber consumes an event is harder than debugging a timed-out function call.

**6. Use a peer debate loop when no single agent has enough context.** Agents argue positions, synthesize agreement, or vote on outputs. Tools: AutoGen v0.4 / Microsoft Agent Framework `GroupChat`, CrewAI with adversarial roles, or LangGraph with a `while_loop` and voting condition. Most useful for reasoning tasks where a second opinion catches errors a single agent would defend.

**7. Add a routing layer before any topology.** Before wiring agents together, put a classifier that inspects the input and selects which path through the graph it takes. Even a simple regex or embedding-based router prevents the "one agent handles everything badly" pattern. This is a one-node addition that dramatically improves precision.

## Evidence

- **Research synthesis:** Three architectural schools have crystallized for coordinating AI agents in production: DAG-based (explicit dependency graphs, deterministic execution order via LangGraph, Temporal, Dagster), event-driven (asynchronous pub/sub, agents as reactive consumers via Kafka + A2A + MCP), and actor model (isolated state, message-passing, supervision hierarchies via Microsoft Agent Framework/Magentic, Akka) — Zylos Research, "Agent Workflow Orchestration Patterns: DAG, Event-Driven, and Actor Models," April 14, 2026 — https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns
- **HN practitioner survey:** On an "Ask HN: How are you orchestrating multi-agent AI workflows in production?" thread, respondents described building custom orchestrators on LangGraph, lightweight abstractions over Express + MongoDB, AGNO for its minimal design, and Node.js V8 isolates for isolation — with agreement that agent-to-agent data passing and observability are the hardest unsolved problems (Hacker News, Ask HN #47660705, 2026) — https://news.ycombinator.com/item?id=47660705
- **Framework decision matrix:** Databricks' State of AI Agents report found multi-agent workflows grew 327% between June and October 2025, with technology companies building multi-agent systems at 4× the rate of other industries. Enterprise teams reaching for orchestration should use CrewAI for role-based teams with minimal boilerplate, LangGraph for stateful workflows with branches/loops/human-in-the-loop, and Microsoft Agent Framework for conversational multi-agent reasoning — aistackhub.ai, "AI Agent Orchestration Platforms," May 9, 2026 — https://aistackhub.ai/ai-agent-orchestration-platforms

## Gotchas

- **Don't start with a supervisor tree.** Temporal and Akka-style supervision is enterprise-grade durability — it is also the most complex to debug. Start with a pipeline, fan-out, or orchestrator pattern and graduate upward only when the simpler form demonstrably breaks.
- **Fan-out without a merge strategy produces worse output than no fan-out.** Running five summarizers in parallel and concatenating their outputs is not synthesis. You need a judge, voter, or aggregator agent at the merge point — budget for it.
- **Context bleeds between agent calls in sequential pipelines.** If agent A sees agent B's intermediate output, agent B's reasoning errors contaminate agent A. Design explicit schema boundaries at each handoff, not raw text concatenation.
- **Multi-agent token costs compound invisibly.** A 5× token cost multiplier sounds manageable until you have a fan-out of 10 agents with 3 reasoning loops each. Build cost limits into the graph from day one, not after the first invoice.
- **The "god agent" anti-pattern creeps back in.** Once an orchestrator grows comfortable making all the routing decisions, it becomes a single overloaded agent with extra latency. Treat the routing layer as a separate agent that must remain narrow.
