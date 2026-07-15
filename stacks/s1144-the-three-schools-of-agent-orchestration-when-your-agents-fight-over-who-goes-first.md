# S-1144 · The Three Schools of Agent Orchestration

When your single-agent setup hits a wall — parallel exploration, context limits, tool sprawl — and you reach for multi-agent coordination, the first decision is which architecture to bet on. The answer is not obvious, and teams routinely pick a pattern that fights their problem.

## Forces
- **Linear chains vs. dynamic autonomy** — some tasks need a fixed recipe; others need the agent to decide the next step at runtime
- **Explicit control vs. emergent collaboration** — you either want to know exactly what happens, or you want agents to figure it out together
- **Cost vs. capability** — agent loops cost 3–5× more tokens than equivalent chains (Anthropic), and teams routinely over-engineer their first multi-agent system
- **Debuggability vs. expressiveness** — the more dynamic the orchestration, the harder it is to trace what went wrong
- **80% of production use cases are simple chains** (LangChain 2025 Production Survey), yet teams jump to agent loops before exhausting them

## The move

Three architectural schools have proven themselves in production. Pick based on your problem shape, not framework hype.

**1. DAG-Based (Explicit Graphs — LangGraph, Temporal, Dagster)**
- Define the execution order as an explicit directed graph with typed nodes and edges
- State is a shared dictionary passed from node to node; the graph controls all transitions
- Natural fit: batch pipelines, ML training, workflows with known step dependencies
- Each node is a pure function (LLM call or tool) — no agent decides where to go next
- Failure: retry at the node, check a dead-letter queue, or halt — the graph determines what happens

**2. Hierarchical Supervisor (Router + Workers — CrewAI, custom Python)**
- A router/classifier agent sits at the top and delegates sub-tasks to specialized worker agents
- Workers run in parallel; their outputs feed back to the supervisor for synthesis
- Natural fit: tasks that decompose into independent research directions, parallel document analysis
- The router decides *who* does the work; workers decide *how* to do their piece
- Critical: give the router a clear taxonomy of tasks so it routes accurately — vague routing = wrong worker

**3. Conversational / Actor Model (AutoGen, Microsoft Agent Framework 1.0)**
- Agents exchange messages freely; the system is driven by conversation, not a pre-defined graph
- Each agent has isolated state; message-passing is the only coordination mechanism
- Supervision hierarchies let a parent restart, retry, or escalate a crashed child agent
- Natural fit: open-ended research, multi-perspective analysis, scenarios where you don't know the steps upfront
- Risk: emergent deadlocks (A→B→A circular delegation), semantic failures (logically wrong but syntactically valid output), and runaway costs from unbounded retry loops

**The routing heuristic (Agentika):**
- Simple linear steps → DAG / Sequential Chain
- Classification + routing → Router Pattern
- Open-ended, multi-perspective → Hierarchical Supervisor or Conversational

**Difficulty-aware dynamic routing (Zylos 2026):**
- A lightweight classifier estimates query difficulty at runtime
- Simple queries get a shallow chain; complex queries route to deep multi-agent pipelines
- Teams report 40–60% cost reduction with no accuracy loss (Agentika, Weights & Biases 2025)

## Evidence

- **Survey:** LangChain 2025 Production Survey found 80% of production systems use simple chains, and that 73% of surveyed systems use chain-based orchestration as their primary pattern — [LangChain 2025 Production Survey](https://langchain.com/surveys) (referenced by Agentika)
- **Engineering post:** Anthropic's multi-agent research architecture uses an orchestrator-worker pattern — a lead agent decomposes tasks and dispatches to parallel workers, with 15× token usage vs. single-agent chat but 90.2% improvement on internal benchmarks — [Colourful Codes / Anthropic Architecture Analysis](https://cuizhanming.com/anthropic-multi-agent-research-architecture)
- **HN community validation:** "Evolving Agents Framework" (139 points, March 2025) — real HN discussion of dynamic agent evolution, semantic tool routing, and YAML-defined workflows validated by 37 comment threads — [HN Show HN: Evolving Agents Framework](https://news.ycombinator.com/item?id=43310963)
- **Framework comparison (2026):** LangGraph (graph/state-machine, production-stable), CrewAI (role-based teams, fast prototypes), Microsoft Agent Framework 1.0 GA (conversational, Azure-native) — [TURION.AI LangGraph vs CrewAI vs AutoGen 2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Architecture taxonomy:** Three-school breakdown (DAG, Event-Driven, Actor) with dead letter queues, failure mode taxonomy, and supervision hierarchies — [Zylos Research: Agent Workflow Orchestration Patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas
- **Over-engineering is the default failure mode.** LangChain's 2025 survey found teams consistently reach for agent loops before exhausting simple chains. Start simple; escalate only when you have evidence the chain won't suffice.
- **Silent state corruption is worse than crashes.** Cascading context corruption (incorrect state propagated downstream) and silent state loss (no checkpoint to recover from) are harder to debug than explicit failures. Build checkpoints at every major phase boundary.
- **Tool descriptions are as important as tools.** Anthropic's research team explicitly recommends investing in prompt quality for tool descriptions — agents that misunderstand a tool's output format cause cascading failures downstream.
- **Semantic failures slip past syntax checks.** An LLM output that is syntactically valid but logically wrong will pass most validators. You need outcome-based evaluation, not output-format validation.
- **Set hard budget guards on agent loops.** Token usage can run 3–15× higher than equivalent chains. Set per-task token budgets and iteration caps (typically 10–20 steps) before deploying any conversational or actor-model system.
