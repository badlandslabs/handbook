# S-1481 · The Phase-Before-You-Stack Stack — When Predetermined Graphs Break in the Middle

You designed a beautiful orchestration graph. Five nodes, clear edges, predictable branching. It worked for every test case. On the forty-seventh production query, your agent found a bug in the dependency of the dependency of the test environment and spawned a task nobody anticipated. The graph has no edge for that. The agent stops or wanders. The teams that solved this didn't write bigger graphs — they changed what the graph represents.

## Forces

- **Predetermined branching is a prediction you will be wrong about.** You cannot enumerate every task an agent might need to spawn before the agent encounters it. Rigid graphs fail precisely at the moments that matter most — novel situations, edge cases, and discoveries that weren't in your spec.
- **Fully unconstrained agents duplicate work and lose coherence.** Letting agents spawn anything, anywhere, without phase structure leads to redundant tool calls, conflicting sub-agent outputs, and trajectories that drift from the original goal without anyone noticing until the user complains.
- **The single-coordinator bottleneck collapses under parallel load.** Routing every agent decision through one central LLM call serializes what should be parallel work, creates a single point of failure, and doesn't scale beyond 3-4 specialized agents.
- **Token duplication is a real cost.** Without coordination primitives, multi-agent systems redundantly include context that could be shared — Zylos Research measured 72-86% token duplication across MetaGPT, CAMEL, and AgentVerse, the frameworks teams reach for by default.

## The move

Define **phase types** instead of task lists. You don't know every task, but you know the kinds of work that happen: analysis, building, validation, review, deployment. A phase is a container with a goal, an outcome contract, and rules about what it can spawn. Agents create tasks within phases based on what they actually discover, not what you predicted upfront.

The structure lives in the phases, not the tasks. This is the architectural shift: **workflows build themselves as agents discover what needs to be done.**

The key components:

- **Phase types with spawning rules.** Each phase type declares what child phases it can spawn and under what conditions. An analysis phase can spawn a validation or investigation phase. A build phase can spawn fix or review phases. You define the grammar of your workflow; agents populate it.
- **Parallel execution within phase isolation.** Agents working in the same phase operate in isolated git worktrees (for code) or separate memory contexts. They don't overwrite each other's state. Parallelism is structural, not accidental.
- **Guardian agents for trajectory coherence.** A separate monitoring agent reviews entire conversation trajectories — not just "is this agent stuck?" but "is the accumulated work aligned with the phase goal?" LLM-powered coherence scoring catches drift before it compounds.
- **Durable execution with checkpoint-and-resume.** State persists through failures. An agent that crashes mid-task restarts from the last checkpoint, not from the beginning. For enterprise workflows that span hours or days, this is not optional — it is the difference between a pilot and production.
- **Structured handoff protocols.** When an agent finishes a phase and hands off to the next, the handoff follows a defined schema: output artifact, confidence score, open questions, and next-phase recommendation. This replaces ad-hoc context passing that degrades across 10+ agent hops.
- **Self-healing task management.** Tasks have lifecycle states, retry budgets, and escalation paths. A failed validation spawns a fix task. A stuck agent triggers a Guardian review. The workflow is aware of its own health.

## Evidence

- **GitHub README:** Hephaestus — "Semi-Structured Agentic Framework. Workflows build themselves as agents discover what needs to be done, not what you predicted upfront." — [GitHub](https://github.com/Ido-Levi/Hephaestus), ~1.1K stars (September 2025)
- **Engineering blog:** Microsoft ISE — documented the evolution from a modular monolith router pattern to a coordinator-based microservices architecture, enabling cross-team agent reuse for a production retail chatbot. Key failure mode of the monolith: "Agents were tightly coupled to the chatbot and couldn't be reused across teams." — [Microsoft ISE Developer Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems), June 2026
- **Enterprise case study:** LinkedIn's SQL Bot, built on LangGraph, serves hundreds of non-technical employees querying data warehouses in plain English — finds tables, writes SQL, detects and fixes errors, enforces access permissions — achieving 95% query accuracy satisfaction rate. LangGraph's durable execution enables restart from checkpoint rather than full replay. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows), April 2026

## Gotchas

- **Phase boundaries are harder to define than they look.** Teams underestimate how much disagreement exists about whether something is "validation" or "review" or "analysis." Invest in phase contracts — explicit output schemas — before investing in spawning logic.
- **Guardian coherence scoring adds latency and cost.** Running an LLM over every trajectory checkpoint is expensive at scale. Start with low-frequency coherence checks (every N steps or every phase boundary) and tune the threshold.
- **Git worktree isolation is a code-specific solution.** If your agents operate on documents, databases, or APIs rather than code, you need a different isolation mechanism. The principle (parallel agents can't clobber each other's state) applies everywhere; git worktrees do not.
- **Predictable graphs are still useful for predictable sub-problems.** Don't throw out structured orchestration for the whole workflow. The phase-based approach composes: use a rigid graph for the known 80%, and phase-based spawning for the discovery-driven 20% where rigidity breaks.
