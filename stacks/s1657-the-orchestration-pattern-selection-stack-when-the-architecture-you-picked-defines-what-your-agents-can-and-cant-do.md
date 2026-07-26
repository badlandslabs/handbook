# S-1657 · The Orchestration Pattern Selection Stack — When the Architecture You Picked Defines What Your Agents Can and Can't Do

You built a multi-agent system. It's slow, expensive, and breaks unpredictably. The agents are fine — each one does its job. The problem is the architecture connecting them. Choosing the wrong orchestration pattern is a one-time decision with permanent consequences: you can't bolt parallelism onto a pipeline, can't add a supervisor to a flat swarm without rebuilding half the system, and you can't retrofit typed handoffs into a mess of prose outputs without rewriting every agent boundary. Pattern selection is the load-bearing wall of agentic architecture.

## Forces

- **The orchestration pattern determines the failure mode.** Pipeline systems fail linearly (one bad output breaks everything downstream). Orchestrator-worker systems fail at the coordinator (one bad dispatch cascades). Fan-out systems fail at the aggregator (partial results, silent drops). There is no pattern without a corresponding failure taxonomy.
- **Most multi-agent failures are coordination failures, not agent failures.** 37% of multi-agent production failures trace to inter-agent coordination rather than individual agent limitations (Swarmsignal, 2026). Teams debug the wrong layer.
- **Typed schemas at agent boundaries are the #1 critical success factor.** Untyped handoffs — prose outputs passed between agents — cause state drift, retry collisions, and orphaned mutations within the first week of production traffic. RaftLabs found this in 100+ deployments.
- **Orchestration complexity grows exponentially, not linearly.** Adding agents to a pipeline is O(n); adding agents to a peer network is O(n²). Teams underestimate this until they're three agents deep and starting over.
- **57% of organizations have agents in production, but only 14% have organization-wide scaling** (LangChain State of Agent Engineering, 2026, n=1,300+). The gap is pattern and coordination debt, not agent capability.
- **Framework loyalty drives bad architecture.** The HN consensus in 2025: "There's absolute zero framework out there that's good enough for serious work" — teams increasingly build lightweight custom orchestrators rather than fitting workflows to framework primitives.

## The Move

Pick the pattern that matches the task topology, not the tool preference.

### Step 1 — Classify your task topology

| Task shape | Right pattern | Wrong pattern |
|---|---|---|
| Fixed sequence, each step depends on prior | Pipeline (sequential) | Fan-out (wastes parallelism) |
| One planner + multiple independent workers | Orchestrator-worker | Flat peer network (coordination chaos) |
| Embarrassingly parallel sub-tasks, one result | Fan-out/fan-in | Pipeline (blocks on slowest) |
| Complex hierarchy with approval gates | Hierarchical supervisor | Flat swarm (no accountability) |

### Step 2 — Make the coordinator stupid-stupid simple

Anthropic's production research system (June 2025) uses an orchestrator-worker pattern where the lead agent's sole job is **planning and dispatch** — it never does the work itself. Workers get fresh context windows, not the full conversation history. This alone delivered a **90.2% improvement** over a single Opus 4 agent on research benchmarks. The key constraint: workers receive scoped, typed task briefs, not a dump of everything the orchestrator has seen.

### Step 3 — Define typed schemas at every handoff boundary

Every inter-agent handoff must include:
- **Payload schema** — explicit, typed, versioned output format
- **Idempotency key** — so retries don't cause duplicate work
- **Trace ID** — so the full lineage is queryable
- **Explicit completion declaration** — what the upstream agent changed, what the downstream agent must still do

This is not optional. RaftLabs' analysis of 100+ production multi-agent deployments found that the teams with typed schemas at boundaries had dramatically lower debugging time. The teams without them discovered state drift and orphaned mutations within days of production traffic.

### Step 4 — Size agents to task complexity, not to impress

Anthropic's finding: **80% of performance variance is explained by token usage**, not model tier. Sonnet 4 workers + Opus 4 orchestrator outperformed single Opus 4. Upgrade workers, not the coordinator. Infer at the edge; reason at the hub.

### Step 5 — Budget before building

4-agent orchestrator-worker workflows cost **$5–8 per complex task** (RaftLabs, 2026). Sequential pipelines are cheaper per task but scale poorly. Fan-out is expensive but fast. Model the inference cost topology before committing to an architecture — the pattern determines the cost curve.

## Evidence

- **Anthropic Engineering Blog:** Multi-agent research system using orchestrator-worker pattern — Opus 4 lead + Sonnet 4 parallel workers. 90.2% improvement over single Opus 4 on internal benchmarks. 15x token usage vs. single-agent chat (vs. 4x for single agents). June 13, 2025. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **LangChain State of Agent Engineering 2026:** Survey of 1,300+ professionals. 57% have agents in production (up from 51%). Quality is the #1 production blocker at 32%, latency at 20%. Only 14% have achieved organization-wide scaling. November–December 2025. — [https://www.langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)
- **Ask HN: Multi-Agent AI Workflow Orchestration in Production:** Practitioner thread with real stacks — Node.js + V8 isolates per agent + MongoDB for shared state; LangGraph + custom orchestrator on top; AGNO for minimalistic decoupling. "There's absolute 0 framework out there that's good enough for serious work." — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **RaftLabs Multi-Agent Systems Guide:** Analysis of 100+ production deployments. Typed schemas at agent boundaries as #1 critical success factor. 89% of teams have observability, only 52% have evals. 1,445% surge in multi-agent inquiries (Gartner Q1 2024–Q2 2025). March 2026. — [https://www.raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Shopify Engineering:** Sidekick's agentic loop — Anthropic-style continuous cycle (input → LLM → action → feedback → loop). Learned that evaluation frameworks must evolve with the agent. August 2025. — [https://shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)

## Gotchas

- **Sequential pipelines bottleneck on the slowest step.** If your workflow has a 45-minute agent step and three 30-second steps, parallelism wins even if the architecture is messier.
- **Handoff protocols add overhead that doesn't pay off for single-stage pipelines.** Typed schemas only matter when work crosses agent boundaries. Don't add ceremony to a system where one agent can finish end-to-end.
- **Loose handoffs (prose outputs) work fine in demos and collapse in production.** The first week of real traffic will surface state drift and retry collisions. Fix it before you ship.
- **"Fan-out everything" is a trap.** Parallelism sounds free until you get 4 workers returning partial results, one returning an error, and your aggregator has to decide what "done" means. Fan-out needs explicit completion criteria and timeout handling.
- **Framework choices are reversible; pattern choices are not.** LangGraph, CrewAI, AutoGen, and custom-built orchestrators can all implement any of the four patterns. Pick the pattern first, then pick the framework that implements it with least friction.
