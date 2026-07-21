# S-1456 · The Orchestration Pattern Stack — When One Agent Isn't Enough But Five Is Chaos

Spin up one capable agent and it impresses you. Spin up five, point them at the same goal, and you quickly learn that intelligence does not automatically coordinate. The field has converged on four orchestration patterns that cover most real-world cases — but the choice of which one to use is the first non-trivial decision in any multi-agent system, and most teams get it wrong by defaulting to what sounds sophisticated rather than what fits their task shape.

## Forces

- **Coordination overhead grows faster than capability.** Adding agents adds failure modes: wrong handoffs, race conditions on shared resources, cascading errors that are harder to trace than any single-agent failure.
- **Inference cost compounds per agent.** Teams report $5–8 per complex task in multi-agent setups. Orchestration that fires every agent in sequence on a simple query is an expensive way to solve a cheap problem.
- **Observability gaps compound at agent boundaries.** A single-agent trace is linear. A five-agent workflow with branching and merging produces a graph that most debugging tools aren't built to render.
- **The pattern you prototype with is rarely the one that survives production.** Sequential pipelines are easy to reason about and hard to extend. Hierarchical systems handle scale but introduce single points of failure. Most teams start with one pattern and retrofit another when they hit the wall.

## The Move

The move is to match the orchestration topology to the task shape — not to pick the most flexible one and force-fit it. Four patterns, four task shapes:

**1. Sequential pipeline (A → B → C)** — for tasks with strict ordering dependencies. The output of each agent feeds the next. Best for: structured workflows where B cannot start until A finishes (e.g., research → draft → review → publish). Simple to trace, easy to debug, hard to parallelize.

**2. Hierarchical / supervisor (Overseer → Workers)** — a central orchestrator classifies intent and delegates to specialized workers, then synthesizes results. Best for: enterprise-grade systems where a single decision-maker routing to domain experts reduces cross-cutting concerns. Microsoft ships this as a first-class pattern in their multi-agent reference architecture (2025). Handles complexity at scale but the overseer becomes a bottleneck and single point of failure.

**3. Parallel fan-out / fan-in (A → [B, C, D] →聚合)** — a splitter dispatches sub-tasks to multiple agents simultaneously, results are aggregated. Best for: tasks that can be decomposed into independent sub-tasks (e.g., research three competitors in parallel → synthesize report). The aggregation step is the hard part — weak synthesis kills otherwise sound parallel execution.

**4. Peer-to-peer / swarm (agents handoff to peers dynamically)** — agents negotiate task ownership at runtime based on capability signals. Best for: open-ended, conversational scenarios where task boundaries aren't known upfront. OpenAI's Swarm and similar frameworks prototype this pattern. The hardest to reason about and the hardest to debug — a natural fit for chat, a poor fit for anything with an SLA.

**The routing primitive that ties them together:** Microsoft recommends a semantic router as a lightweight NLU/SLM classifier for initial intent routing, falling back to an LLM only on low-confidence cases. This reduces cost while maintaining accuracy — the practical version of "route to the right agent" that most architectures describe but few implement cost-effectively.

## Evidence

- **Research survey (306 respondents, 86 deployed systems, 26 domains, arXiv:2512.04123):** 73% of practitioners build agents for productivity gains. 68% limit agents to ≤10 steps before human intervention. 85% build custom rather than using third-party frameworks — the ecosystem is fragmented and teams have strong opinions.
- **Analyst report (RaftLabs, March 2026):** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. 57% of organizations are already running agents in production. Teams with successful multi-agent systems report 3x faster task completion and 60% better accuracy — but only when the pattern fits the task.
- **Framework comparison (hjLabs/hjlabs.in, 2025):** AutoGen entered maintenance mode October 2025. CrewAI crossed 52k GitHub stars with ~2B agent executions/year (May 2026). The practical split: LangGraph for fine-grained control → CrewAI for quick multi-agent prototypes → OpenAI Agents SDK for conversational/swarm scenarios.
- **Reference architecture (Microsoft/multi-agent-reference-architecture, GitHub, 2025):** Ships 10 patterns including semantic routing, hierarchical supervisor, parallel fan-out, and state aggregation. The documentation explicitly warns that "untyped handoffs kill multi-agent workflows faster than any other issue" — type-safe message passing between agents is the underrated engineering problem.

## Gotchas

- **Fan-out without a strong aggregator is just distributed latency.** Teams add parallelism because it sounds efficient, then discover the synthesis step is where 80% of the quality problems live. Invest in the aggregator before the parallelization.
- **Step limits create phantom success.** The 68% of teams capping at ≤10 steps aren't solving for capability — they're constraining blast radius. An agent that gives up at step 10 looks identical to one that finished cleanly in your monitoring. You need explicit signals for "completed" vs "gave up at boundary."
- **Cross-agent observability is an afterthought in every framework.** Single-agent tracing (LangSmith, Phoenix, etc.) works. Multi-agent traces produce graphs that require custom tooling to render meaningfully. Budget time to build this — it will save you more time than it costs.
- **The overseer in a hierarchical system is your reliability floor.** If the supervisor agent goes off-model, the entire system degrades. Treat the orchestrator as the highest-stakes component in your stack — more thoroughly tested, more conservatively prompted, more guarded against drift.
- **CrewAI's simplicity is a trap at scale.** Great for proving the concept, painful when you need state management, custom routing, or fine-grained error handling. The prototype-to-production gap is wider than the GitHub stars suggest.
