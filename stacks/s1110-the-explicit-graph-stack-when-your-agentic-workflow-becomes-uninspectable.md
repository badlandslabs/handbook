# S-1110 · The Explicit Graph Stack

*When your agentic workflow becomes uninspectable*

You built a working agent. Then it grew. Now you have 12 tool calls, 4 specialist agents, conditional branches, retry logic, and a human-in-the-loop gate. The system works — but you can't trace why it failed last Tuesday, you can't replay it, and adding a new agent path requires touching four files. The architecture broke at the seams. You need an explicit graph.

## Forces

- **Flexibility vs. governance** — agents are non-deterministic by nature, but production demands traceable, auditable execution paths
- **Simplicity vs. capability** — a single giant prompt with many tools works for demos; it collapses on complex, long-horizon tasks
- **Abstraction vs. control** — frameworks add useful primitives but also hide execution semantics you need to debug
- **Iteration vs. stability** — the graph changes every sprint, but each change needs to be reviewable and rollback-able

## The move

Treat your agentic workflow as an **explicit directed graph** — not a chat transcript, not a linear pipeline, but a state machine where every node is typed, every edge is conditional, and every execution is checkpointed and replayable.

**The six core patterns that map to graph topology:**

- **Sequential chain** — linear graph, each node's output feeds the next; best for pipelines with a clear single-owner at each step
- **Router** — a classifier node dispatches to specialist subgraphs; scales by task type without wiring every possible path
- **Parallel fan-out/fan-in** — one node spawns N parallel branches, a join node aggregates results; use for independent subtasks
- **Evaluator-optimizer loop** — a cycle with a termination condition; keep the graph tight — context resets between rounds, hard iteration limits are non-negotiable
- **Supervisor + specialists** — one orchestrator node manages multiple leaf agents via typed messages; the orchestrator holds the global state
- **Subgraph composition** — a compiled graph becomes a single node in a parent graph; enables modular, testable unit graphs that compose into enterprise workflows

**Graph engineering decisions that separate prod from demos:**

- **Typed state, not dicts** — define the state schema explicitly; when state shape is implicit, schema drift causes silent failures
- **Checkpoint every node** — serializable state snapshots enable replay, resume, and rollback; LangGraph's `checkpointer` does this for you, roll-your-own needs Postgres + snapshots
- **Hard round/loop limits** — always; infinite loops in generative systems are not theoretical
- **`interrupt()` for human gates** — suspend execution at a typed boundary (e.g., `interrupt_before=['execute_payment']`), wait for human signal, resume with `Command(resume={...})` and the same `thread_id`; this is what separates finance/ops deployments from demos
- **Observability first** — trace every node entry, state delta, tool call, and LLM decision; LangSmith, Phoenix, or custom spans; if you can't replay a failed run, you can't debug it

**Framework landscape (2026):**

| Framework | Model | Best for |
|-----------|-------|----------|
| **LangGraph** | State machine / DAG | Complex, stateful, production workflows needing checkpointing and interrupts |
| **CrewAI** | Role-based | Fastest path to working prototypes; teams hit limits at scale (6–12 months) |
| **Microsoft Agent Framework** (AutoGen + Semantic Kernel) | Conversational + kernel | Azure/enterprise shops already in the Microsoft stack; GA April 2026 |
| **Mastra** | Graph-based | TypeScript-first teams; 22k stars, 300k weekly npm downloads |
| **Roll your own** | State machine | When no framework's constraints match your requirements;HN practitioners say "no framework is good enough for serious work" |

## Evidence

- **HN Ask thread (11 practitioners):** Practitioners split between LangGraph + custom, CrewAI for prototypes, and rolling their own with Express + MongoDB + typed message passing. Key data-passing approaches: shared Postgres schema (typed rows), Redis pub/sub for event-driven, and direct function calls for synchronous subgraphs. Observability universally cited as the #1 pain point. — [Hacker News, ID 47660705](https://news.ycombinator.com/item?id=47660705)

- **Practitioner guide (Thinking.inc, March 2026):** "Across the deployments we have observed, a large share of failures originate in orchestration design rather than individual agent capability — agents are individually capable but poorly coordinated. The agents worked; the wiring did not." Found six patterns cover 90% of enterprise use cases; production systems combine 2–3 patterns within a single workflow. — [Thinking.inc — Agent Orchestration Patterns](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)

- **Framework comparison (Gheware, 2026):** Core architectural difference: AutoGen uses conversations, CrewAI uses roles, LangGraph uses state machines. LangGraph earns its keep when you need branching, parallelism, resumability, or subgraph composition — not before. "Most teams reach for multi-agent orchestration too early." — [LangGraph vs CrewAI vs AutoGen Comparison](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

- **arXiv production guide (2025):** Multi-agent workflow design for production: workflow decomposition, agent specialization, tool integration, safety mechanisms, and orchestration strategies. Case study: `nurolense` — multimodal news-analysis + media-generation workflow scraping web, filtering topics, generating podcast scripts, producing audio/video artifacts. Demonstrates heterogeneous agents composing into a unified pipeline deployed reliably. — [arXiv:2512.08769](https://arxiv.org/html/2512.08769v1)

## Gotchas

- **Don't start with a complex graph.** A single `create_agent` with 3–5 well-scoped tools beats a three-node graph with extra latency. Add graph structure when branching, parallelism, or resumability is genuinely required.
- **Context resets between loop rounds.** In evaluator-optimizer cycles, don't append previous attempts to context — summarize them as structured input. Each round starts fresh; token accumulation is the silent accuracy killer.
- **Token duplication in multi-agent systems is real.** MetaGPT: 72%, CAMEL: 86%, AgentVerse: 53% — shared context and agent-to-agent messaging can multiply token costs and latency without careful scoping.
- **The interrupt/resume pattern has a footgun.** If `thread_id` isn't stable across pauses, the graph state can't be restored. Bind it to a durable entity ID (order ID, session ID, user ID) — not a random UUID.
- **Framework churn is real.** LangGraph 1.0 hit GA with zero breaking changes in October 2025 — but the ecosystem moves fast. Pin versions, test upgrades against replayed traces, and treat the graph definition as a first-class artifact in version control.
