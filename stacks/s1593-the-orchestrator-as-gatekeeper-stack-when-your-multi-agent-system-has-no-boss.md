# S-1593 · The Orchestrator-as-Gatekeeper Stack — When Your Multi-Agent System Has No Boss

You have three agents. They each do one thing well. Then a user asks for something that requires all three — and the agents start calling each other in a loop, losing context in the handoff, and returning a result nobody can trace back to a decision. Every agent works fine in isolation. Together they are chaos. This is the orchestration vacuum problem, and it does not fix itself by adding more agents.

## Forces

- **Communication overhead scales quadratically** — if every agent can talk to every other agent, each new agent adds O(N) connections; at four agents that is already 12 edges to track
- **Shared state is the first casualty** — agents hand off partial results with no contract for what the next agent needs; context silently decays across hops
- **Supervision is not optional** — without a coordinating agent that owns the final output, there is no single entity responsible for the result's quality or completeness
- **Parallelism is seductive but fragile** — fan-out for speed is easy; fan-out with bounded cost, graceful degradation, and traceable synthesis is not

## The Move

Adopt the **supervisor-worker pattern**: one central agent owns the goal, decomposes the task, routes subtasks to specialists, monitors completion, and synthesizes the final output. Workers never return directly to the user — only to the supervisor.

**The canonical structure:**

- **Supervisor (lead agent):** Receives the user goal, plans the decomposition, assigns work to workers, handles retries and timeouts, synthesizes worker outputs into a coherent result.
- **Worker (specialist agents):** Each has a narrow, well-defined role with its own tools and prompts. Receives a task description from supervisor, executes, returns structured output. Knows nothing about other workers.
- **Shared message protocol:** Workers communicate only through the supervisor. Supervisor manages context windows by receiving summaries rather than raw transcripts.
- **Bounded parallelism:** Fan out to 3–5 workers maximum. Beyond that, coordination overhead exceeds the parallelism benefit.
- **Deterministic routing:** Supervisor decides routing, not workers. If a worker needs another worker's output, it returns to the supervisor, which dispatches a follow-up task.

**Implementation options:**

- LangGraph's built-in supervisor graph (most common in production)
- CrewAI's hierarchical mode
- Custom orchestrator with a router LLM making routing decisions
- Temporal/Camunda for durable workflow state + LLM for routing decisions

## Evidence

- **Anthropic Engineering Blog:** Their production Research system uses an orchestrator-worker pattern with a lead Claude (Opus 4) coordinating parallel subagents (Sonnet 4). Achieved **90.2% performance improvement** over single-agent systems on internal benchmarks. Token cost is ~15x a standard chat interaction, but the architecture delivered 90% reduction in research time on complex queries by running agents in parallel. Key lesson: "Architecture follows task structure. Multi-agent only wins when the task decomposes into independent parallel threads." — [How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) (June 2025)

- **TURION.AI production retrospective:** After deploying multi-agent systems across a dozen production contexts, their conclusion: "Supervisor + Specialists" is the pattern that ships. Specifically: "Most production 'multi-agent' systems are actually this pattern. Simple, debuggable, effective." They identify the alternative — peer-to-peer agent meshes — as the pattern that fails in production because it creates O(N²) communication overhead and undebuggable delegation loops. — [Multi-Agent Orchestration Infrastructure: Lessons from Production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production) (March 2026)

- **QA Wolf (YC W23):** Initially built a single agent for automated E2E test maintenance that attempted to handle the entire workflow — spotting issues, applying fixes, re-enabling tests. It became "a jack-of-all-trades and master of none," slower and more error-prone as tasks accumulated. Rewrote from scratch using a multi-agent approach with three specialized bots: one diagnoses failures, one applies fixes, one re-enables affected tests. Result: dramatic accuracy and efficiency improvement. Their lesson: "Think about a multi-agent system like a restaurant kitchen where each chef specializes in one dish." — [Three Principles for Building Multi-Agent AI Systems](https://www.qawolf.com/blog/read-three-principles-for-building-multi-agent-ai-systems) (November 2024)

- **Microsoft ISE Developer Blog:** Partnered with a retail customer migrating from a modular monolith router (single orchestrator dispatching to one agent per request) to a microservices coordinator pattern where domain agents become independent services. The key architectural shift: "Agents become independent deployables" with a thin coordinator handling orchestration. This enabled agent reuse across teams — the same domain agent could serve multiple coordinators for different business workflows. — [Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems) (June 2026)

- **arXiv production guide (2512.08769):** Surveying production deployments found that the dominant multi-agent pattern in practice is "supervisor/worker, with the supervisor responsible for task decomposition and synthesis." Cross-referenced with Azure's architecture guide listing the same pattern as the first-class recommended approach. — [A Practical Guide for Production-Grade Agentic AI Workflows](https://arxiv.org/html/2512.08769v1) (December 2025)

## Gotchas

- **Adding agents before the architecture is ready** — a shared-nothing multi-agent system with no supervisor is not multi-agent; it is multiple single agents that happen to share a process. The supervisor is not optional; it is the architecture.
- **Passing raw transcripts between workers** — context decays with each hop; supervisor should receive structured summaries, not full conversation logs.
- **Supervisor bottleneck** — if the supervisor is also the most expensive model and it does non-trivial synthesis, it becomes the latency ceiling. Mitigate by giving workers more autonomy (e.g., self-correct with bounded retry before returning to supervisor).
- **Worker homogeneity** — if all workers are prompted identically with the same tools, you have not achieved specialization. Workers must differ in role definition, tool access, or model tier to justify the coordination cost.
- **No timeout or retry boundary** — without explicit timeout and retry policies per worker, one stuck worker blocks the entire supervisor chain. Set per-task deadlines and graceful degradation paths.
