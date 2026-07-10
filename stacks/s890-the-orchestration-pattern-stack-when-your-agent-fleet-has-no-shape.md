# S-890 · The Orchestration Pattern Stack — When Your Agent Fleet Has No Shape

You have multiple agents working on a complex task. They either trample each other, duplicate work, or produce incoherent output. The problem isn't the agents — it's the structure (or absence of it) between them.

## Forces

- **Specialization vs. coherence** — splitting work across agents improves depth but destroys consistency without a coordinating layer
- **Determinism vs. flexibility** — DAGs are predictable but can't handle agents that discover new sub-tasks at runtime
- **Latency vs. quality** — every orchestration hop adds an LLM call; naive pipelines introduce seconds of delay per request
- **Scaling the fleet** — adding new agents to a flat system creates conflicts; adding them to a well-structured system should be trivial
- **Single vs. composite** — one powerful agent often beats a team of weak ones; the question is knowing when the tradeoff flips

## The Move

Choose the orchestration pattern that matches the shape of your problem — then commit to it. Pattern mixing is fine, but mixing is a second-order concern; picking the wrong primary pattern is a one-way door.

### The Six Foundational Patterns

1. **Single Agent** — one agent, one job, one system prompt. Start here. Add complexity only when you hit concrete limits (context overflow, domain conflicts, latency requirements that exceed what one agent can deliver).

2. **Supervisor** — one central coordinator that plans, delegates to specialists, reviews outputs, and synthesizes. The supervisor never implements; it orchestrates. Best for multi-domain tasks where a single coherent response requires pulling from multiple knowledge areas. The coordinator pattern from Microsoft ISE (2026) is this: a retail organization replaced a flat router with a supervisor layer and achieved agent reuse across teams and use cases.

3. **Router** — a classifier routes each incoming query to exactly one specialized agent based on intent detection. Fast, simple, predictable. The trap: queries that span multiple domains get silently forced into one bucket. Microsoft ISE calls this the "modular monolith" — it works until it doesn't.

4. **Chain of Agents** — sequential pipeline where each agent reads the previous step's output and refines along a single quality axis. Draft → Security Review → Performance Audit → Final Polish. Mirrors how experienced human teams work. Each agent does one thing and does not disturb what prior agents got right. Best for tasks with strict sequential dependencies and multi-constraint outputs.

5. **Handoff** — agents transfer control to another agent mid-conversation based on a detected need. Like a phone transfer in a call center. Works well for long-running sessions where user intent shifts. The risk: if the handoff trigger is wrong, the user ends up with an agent that has no context.

6. **Blackboard** — multiple agents write to and read from a shared knowledge store, acting as independent experts contributing to a common problem. Good for research synthesis; dangerous for anything requiring strict ordering, because the final answer depends on which agent wrote last.

### Practical Decisions

- **DAG vs. event-driven vs. actor model:** DAGs (LangGraph, Prefect, Airflow) are deterministic and observable — good for batch pipelines where the workflow shape is known at design time. Event-driven (async pub/sub) is better when agents encounter unexpected failure modes or discover new sub-tasks dynamically — the workflow shape changes at runtime. Actor model suits stateful agents with complex lifecycles. Most teams start with DAG and hit the event-driven wall when their agents start behaving unpredictably. (Zylos Research, 2026)

- **Difficulty-aware routing:** Rather than sending all queries through the same pipeline depth, a classifier estimates difficulty and allocates compute proportionally. Simple queries get a single agent; complex queries get a multi-agent pipeline. This delivers significant cost reductions without accuracy loss. (Zylos Research, 2026)

- **Latency budget:** Multi-agent pipelines add ~500ms–2s per hop from LLM calls alone, before network latency. A three-hop pipeline is 1.5–6s of baseline latency. Budget for it. Teams targeting sub-2s latency often discover their multi-agent architecture is architecturally incompatible with their SLA.

## Evidence

- **Engineering blog:** Microsoft ISE documented a large retail organization migrating from a router-as-modular-monolith to a microservices architecture with reusable agents. The key insight: "No multi-agent orchestration or response synthesis" was the original failure mode. They adopted the coordinator pattern and achieved agent reuse across teams and use cases for the first time. — [Orchestration Patterns for Multi-Agent Systems (Microsoft ISE, June 2026)](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Engineering blog:** Microsoft ISE (Nov 2025) described an e-commerce voice assistant using agent selection with a central coordinator. Four core requirements: accurate agent selection, optimized LLM usage, efficient orchestration, and scalability to add new agents without degrading performance. — [Patterns for Building a Scalable Multi-Agent System (Microsoft ISE, Nov 2025)](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/)

- **Documentation:** The AI University runs 15 agents in production and catalogs six foundational patterns. Their blunt lesson: "Most people building with AI agents make the same mistake: they treat architecture as an afterthought. They wire up one agent, it works, they add another, and six weeks later they have a mess that nobody can reason about or debug." — [Multi-Agent Architecture Patterns (AI University, March 2026)](https://theaiuniversity.com/docs/building-agents/architecture-patterns)

- **Research:** Zylos Research (2026) analyzed DAG, event-driven, and actor model schools for agent coordination. Key finding: DAGs collapsed under "deadlocks, state corruption, silent failures, and runaway costs" when agents needed dynamic branching. Event-driven handles the uncertainty but adds operational complexity. — [Agent Workflow Orchestration Patterns (Zylos Research, April 2026)](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Starting too complex** — the single most common mistake is building a multi-agent system when one agent would suffice. The coordination overhead is real; only pay it when the problem genuinely requires it.

- **Flat agent collections** — adding agents without a coordinating layer doesn't scale. At three agents, everyone talks to everyone. At ten, it's a mesh with no clear ownership. At twenty, it's undebuggable. Build the coordinator pattern before you reach ten agents.

- **Latency ignored until production** — teams that don't budget for orchestration overhead discover their pipeline SLA is incompatible with their architecture. Measure latency per hop early.

- **Pattern drift** — systems that start as routers often evolve into supervisors organically, but without intentional migration the result is a hybrid that inherits the worst properties of both. Treat pattern changes as migrations, not patches.

- **Temperature=0.7 everywhere** — Microsoft's ISE team found that temperature=0 with top_p=0 was critical for coordination stability in multi-agent systems. High temperature in a supervisor agent introduces randomness into routing decisions. Set this intentionally per agent role.
