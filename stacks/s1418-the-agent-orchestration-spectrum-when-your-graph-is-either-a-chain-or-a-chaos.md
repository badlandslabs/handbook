# S-1418 · The Agent Orchestration Spectrum: When Your Graph is Either a Chain or a Chaos

You have a LangChain chain. It works. Then requirements shift and you duct-tape an agent loop onto it. Then someone wants human approval mid-flow. Then parallel execution. Six months later your "simple pipeline" is a bespoke framework nobody can debug, and the graph has become the product's most feared subsystem. The orchestration layer is where most agent projects succeed or fail — not because agents are hard, but because wiring them together is an architectural decision dressed up as a library choice.

## Forces

- **Simple chains handle 80% of production use cases, but teams consistently reach for agents first.** LangChain's 2025 production survey found 73% of production systems use chains while only 12% use full agent loops — yet the instinct on day one is to build the latter.
- **Branching, parallelism, durability, and auditability each demand a different wiring model.** A linear chain can't branch. An agent loop can't be paused for human approval. A DAG can't handle cycles. Each real production requirement shifts you up the orchestration complexity ladder.
- **The framework you prototype in is not the framework you productionize in.** Practitioners widely report CrewAI for fast demos, LangGraph for production with branching or resume requirements — but treating these as interchangeable leads to painful migrations.
- **Multi-agent orchestration adds inter-agent communication as a new failure mode.** Agents that don't communicate well miss steps, block each other, or duplicate work — failure modes that don't exist in single-agent systems.

## The Move

Match the orchestration pattern to the actual bottleneck, not the architecture diagram you drew. Five patterns cover nearly all production use cases; production systems typically combine two or three.

**The hierarchy — use the simplest that fits:**

1. **Simple chain (LLM → LLM → LLM)** — Use for linear, fixed-sequence workflows where output of step N is input of step N+1. No branching, no loops. This is a pipeline, not an agent. Example: classify → extract → format. Handles ~80% of production use cases per LangChain's 2025 survey.

2. **Router pattern (LLM → routing decision → chain A | chain B | chain C)** — Use when a classifier must dispatch to different execution paths. The router is a lightweight LLM call; the branches can themselves be chains or agents. Supervisor pattern (single orchestrator delegates to specialists, assembles result) is the multi-agent variant. This cuts inference costs 40–60% at scale by directing simple queries to cheaper models.

3. **Parallel fan-out (LLM → N simultaneous agents → merge)** — Use when multiple independent subtasks can run concurrently and results merge before downstream steps. Common for research → validate → synthesize pipelines. Requires careful merge/Reducers logic for list-accumulating state.

4. **Agent loop / ReAct (LLM → tools → observation → LLM → ...)** — Use for open-ended tasks where the agent must decide how many steps to take and which tools to call. Constrain with iteration limits (Anthropic recommends starting conservative and increasing based on observed patterns). LangGraph's `interrupt_before` enables pausing for human approval mid-loop.

5. **State machine / LangGraph (explicit graph, cycles, persistence)** — Use when you need branching + parallelism + crash-safe resume + auditability. LangGraph treats state as a first-class object and persists to Postgres by default. Essential when a workflow must survive deploys or long human-approval delays. The key distinction: "Chains are DAGs; agents need cycles."

**Multi-agent crew patterns (CrewAI, Open Multi-Agent):**
- **Sequential process:** agents execute tasks in order, each consuming prior output. Use for pipelines with tight interdependencies.
- **Hierarchical process:** a manager agent plans, delegates, and synthesizes. The manager is not a router — it actively monitors and can redirect mid-execution. CrewAI reports 49,000+ GitHub stars and 100,000+ certified developers.

**The decision heuristic (from community consensus):**
- Draw the graph on paper first. If it has no cycles and no branches, ship a chain.
- If you need cycles or conditional branches, reach for LangGraph.
- If you need multiple agents with roles and delegation, reach for CrewAI or a supervisor pattern.
- If you need external events, pub/sub, or millions of concurrent tasks, consider event-driven or actor-model architectures (DAG-based orchestrators like Temporal or Airflow for the former; supervision hierarchies for the latter).

## Evidence

- **LangChain 2025 Production Survey (n=1,340 teams):** 73% of production systems use chains, 12% use full agents. 89% have observability but only 52% run evaluations. Survey covers Nov-Dec 2025 respondents across 63% tech sector. — [Source](https://www.langchain.com/state-of-agent-engineering)
- **Anthropic engineering guide (Dec 2024):** Recommends starting with predefined code-path workflows rather than autonomous agents, using simple composable patterns. Notes customer support and autonomous browsers as two highest-value agent applications. Iteration limits should start conservative and increase based on observed tool-call patterns. — [Source](https://www.anthropic.com/engineering/building-effective-agents)
- **Reddit/r/LangChain community synthesis (2026):** "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." Multi-agent orchestration reached too early is the most common over-engineering mistake. Single agent with 3–5 well-scoped tools beats a three-node graph. — [Source](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **Heym.run practitioner guide (May 2026):** Four patterns (sequential pipeline, parallel fan-out, supervisor router, agentic ReAct loop) cover the majority of production use cases. Supervisor router pattern reduces inference costs 40–60% at scale by directing simple queries to cheaper models. — [Source](https://heym.run/blog/llm-orchestration)
- **Agentika production retrospective (Feb 2026):** Harrison Chase (LangChain CEO) quote: "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." 80% of production use cases handled by simple chains. — [Source](https://agentika.uk/blog/llm-orchestration-patterns.html)

## Gotchas

- **Over-engineering at prototype time.** The fastest path to a demo is often the wrong foundation for production. Ship a chain baseline first, measure latency, cost, and failure modes, then add complexity only when a specific requirement demands it.
- **Confusing framework choice with architectural choice.** CrewAI vs. LangGraph is not the core decision — the core decision is which orchestration pattern your problem actually needs. Frameworks implement patterns; pick the pattern first.
- **State accumulation without Reducers.** In LangGraph, appending to list state across loop iterations causes duplicate items. Always define Reducers for accumulating state: `{"items": lambda old, new: old + [new]}`.
- **No iteration limit on agent loops.** Without an explicit cap, agents can loop indefinitely on tool-call failures or semantic drift. Anthropic's production guidance: start with 3–5 iterations and increase only after observing real patterns.
- **Multi-agent without shared state schema.** When multiple agents pass context, the schema of that context must be explicit and versioned. Implicit shared state across agents is the source of "they don't agree on what happened" failures.
