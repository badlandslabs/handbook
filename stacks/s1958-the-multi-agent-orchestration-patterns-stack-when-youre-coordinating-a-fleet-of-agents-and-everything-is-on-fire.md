# S-1958 · The Multi-Agent Orchestration Patterns Stack — When You're Coordinating a Fleet of Agents and Everything Is on Fire

You've got three agents: one browses the web, one runs SQL, one writes the report. The user asked one question. Now you have three loops, two deadlocks, one hallucinated query, and no idea which agent is in charge. This is the multi-agent coordination problem — and choosing the wrong pattern before you write the first line of code is the most expensive mistake you can make.

## Forces

- **Parallelism vs. synthesis tension.** You want agents working simultaneously for speed, but results need to be combined coherently. Naive parallel dispatch gives you speed but leaves you with a pile of outputs nobody owns.
- **Explicit control vs. emergent behavior trade-off.** Predefined code paths (workflows) are predictable and auditable. Dynamic agent loops are flexible but opaque. The moment you add an agent, you've traded deterministic behavior for adaptability.
- **Context window pressure.** Every agent gets its own context. Without a shared memory layer, agents make redundant calls or contradict each other. With one shared context, you hit token limits fast.
- **Supervisor bottleneck.** A single orchestrator routing every decision becomes the failure point and the throughput ceiling. But distributed coordination introduces race conditions and inconsistent state.
- **Framework lock-in cost.** LangGraph, CrewAI, and AutoGen each embody an orchestration philosophy. Migrating between them mid-production is painful. Anthropic's guidance explicitly recommends simple composable patterns over heavy frameworks.

## The Move

Choose your orchestration pattern *before* you pick a framework. The pattern determines what you build; the framework is an implementation detail.

**The six foundational patterns (cross-referenced across Anthropic, Microsoft Learn, AI University, and Zylos Research):**

1. **Single Agent** — One LLM with tools. Best for bounded, well-scoped tasks. Add more agents only when context windows crack, domain specialization is needed, or parallel work justifies the coordination overhead.

2. **Supervisor (Orchestrator/Subagent)** — A central coordinator decides which specialist to call next, routes results back to itself, and synthesizes the final output. The pattern from Anthropic's own Research feature (June 2025): a lead agent plans, subagents execute in parallel, supervisor collects and synthesizes. Microsoft calls this "Russian doll" or "magentic" patterns. Best for multi-domain tasks requiring synthesis. Bottleneck risk if the supervisor gets chatty.

3. **Router** — A classifier at the entry point dispatches to the correct agent without the router doing any task work itself. Lower latency than supervisor for high-volume, well-partitionable task types. Best when task categories are known at design time and you need throughput over synthesis.

4. **Pipeline (Sequential/Broadcast)** — Agents process in a defined order, each passing output to the next. Think CI/CD for LLM calls. Dead simple to reason about. Fails if any stage blocks. Best for deterministic multi-step processes where order matters and failure is recoverable.

5. **Handoff (Swarm)** — Agents pass control to each other peer-to-peer, like a game of hot potato. OpenAI's Agents SDK models this as a first-class concept with explicit "handoff" tool calls. Best for dynamic, conversational scenarios where the next best agent isn't known until the current one reports findings. Hardest to debug — control flow is distributed and implicit.

6. **Blackboard** — Multiple agents write to and read from a shared knowledge store without direct communication. Agents don't know about each other. Classic distributed AI pattern, now seeing revival for agent fleets that need to collaborate on shared state without tight coupling.

**Three architectural schools for execution (Zylos Research, April 2026):**

- **DAG-Based:** Explicit dependency graphs, deterministic execution. Frameworks: Dagster, Airflow, Prefect. Good for compliance-audit trails.
- **Event-Driven:** Async pub/sub — agents as reactive consumers. Protocols: A2A + MCP. Scales independent agents without a central coordinator.
- **Actor Model:** Isolated state, message-passing, supervision hierarchies. Frameworks: Microsoft Agent Framework, Akka. Best for resilient systems that need self-healing.

**LangGraph is the production default** when checkpointing, resume-on-failure, and human-in-the-loop breaks are needed. CrewAI is the fastest path to a working prototype with role-based logic. Microsoft Agent Framework is the enterprise Azure choice. Anthropic's own SDK favors minimal abstractions: Agents (LLM + tools), Handoffs, Guardrails, Sessions, and Tracing.

**Critical rule from Anthropic's engineering guidance:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." — https://www.anthropic.com/engineering/building-effective-agents

## Evidence

- **Anthropic engineering blog (June 2025):** Detailed writeup of Claude's own Research feature — uses a supervisor lead agent that plans research processes and spawns parallel subagents. Key lesson: dynamic, path-dependent problems suit multi-agent architectures because subagents provide separation of concerns and parallel operation with separate context windows prevents path dependency. — https://www.anthropic.com/engineering/multi-agent-research-system

- **MMC Ventures, State of Agentic AI: Founder's Edition (Nov 2025):** Interviewed 30+ European agentic AI startup founders and 40+ enterprise practitioners. Found that 65% of teams hit a wall within 12 months and have to rewrite their orchestration — most often because they chose the wrong abstraction level or didn't scope the pattern before choosing a framework. 80% of Fortune 500 exploring AI agents. — https://mmc.vc/research/state-of-agentic-ai-founders-edition/

- **AI University (updated March 2026):** Runs 15 agents in production. Documented all six foundational patterns with honest tradeoffs, real-world use cases, and code skeletons. Their core lesson: "Learn these patterns well enough to recognize which one you are building *before* you write the first line of code." — https://theaiuniversity.com/docs/building-agents/architecture-patterns

- **Zylos Research (April 2026):** Systematic breakdown of three execution models (DAG, Event-Driven, Actor) with production tradeoffs. Notes that by 2025, naive "chain LLM calls" approaches collapsed under deadlocks, state corruption, and runaway costs, teaching teams that agent coordination deserves distributed systems-level discipline. — https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns

- **Microsoft Learn — Orchestrator and Subagent Patterns:** Formal treatment of the hierarchical approach as "Russian doll" patterns. Recommends for open-ended processes with existing specialist agents, explicit quality needs per domain, and modular ownership. — https://learn.microsoft.com/en-us/agents/architecture/multi-agent-orchestrator-sub-agent

## Gotchas

- **Don't add agents for parallelism's sake.** The overhead of coordination — state passing, result synthesis, failure propagation — can easily exceed the speed gain from parallel execution. Measure before you parallelize.
- **Picking a framework before picking a pattern is backward.** Teams spend weeks evaluating LangGraph vs. CrewAI while the real question is whether they need supervisor routing or a pipeline. The pattern drives the framework choice, not the other way around.
- **Supervisor bottleneck is a real production failure mode.** If your orchestrator becomes the single point of both decision-making and synthesis, you've traded one LLM for one slightly smarter LLM. Design for supervisor statelessness — let subagents write to shared state, not just return values.
- **Handoffs are powerful but opaque.** Peer-to-peer agent passing gives flexibility but destroys the call stack. Invest in structured logging and tracing from day one — OpenAI's Agents SDK includes built-in tracing for exactly this reason.
- **Checkpointing is not optional in production.** Without LangGraph-style state checkpoints, a mid-run failure forces a full restart. For long-running agent tasks, this is the difference between a 5-minute recovery and a 5-hour one.
- **Workflow vs. agent distinction collapses in practice.** Anthropic explicitly warns: many applications that claim to need "agents" actually need optimized single LLM calls with retrieval. The failure mode is reaching for multi-agent complexity because it sounds impressive, not because the problem requires it.
