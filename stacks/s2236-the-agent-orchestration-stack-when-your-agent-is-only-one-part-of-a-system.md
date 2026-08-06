# S-2236 · The Agent Orchestration Stack — When Your Agent Is Only One Part of a System

You have one agent working. Now you need two. Or ten. Or a pipeline where one agent's output triggers another's work, with branching logic, error recovery, and a human in the loop. Orchestration is the discipline that turns a collection of agents into a coherent system — and the gap between "it works as a single agent" and "it works as a system" is where most teams get hurt.

## Forces

- **Simplicity collapses under multi-step complexity.** A single agent with well-scoped tools beats a three-node graph that re-implements the same loop with extra latency. But when branching, parallelization, or crash-safe resume is needed, hand-rolled loops stop scaling.
- **Frameworks trade debuggability for convenience.** Anthropic's own engineers write: "These frameworks make it easy to get started… however, they often create extra layers of abstraction that can obscure the underlying prompts and responses, making them harder to debug." The advice: start with LLM APIs directly, reach for frameworks when the problem demands it.
- **Multi-agent coordination introduces failure modes single agents don't have.** Token duplication across agents wastes budget (MetaGPT: 72%, CAMEL: 86%, AgentVerse: 53% redundant context). Observability is the #1 reported barrier to production adoption of multi-agent systems. Deadlocks, silent failures, and runaway costs show up in production in ways that single-agent testing never surfaces.
- **The right pattern depends on the coordination topology, not the agents themselves.** Routing decisions, task delegation, and error escalation require different architectures for different scales and failure tolerances.

## The Move

Start with a single augmented LLM in a loop. Only introduce orchestration complexity when the problem demands it — and pick the pattern that matches the actual coordination need, not the most sophisticated one.

### The Five Core Patterns (Anthropic, December 2024)

1. **Prompt Chaining** — Linear sequence. Each LLM call's output feeds the next. Use for tasks that decompose cleanly into ordered steps (extract → transform → validate). Simple, predictable, easy to debug.

2. **Routing** — A single LLM decides which specialized path to follow based on input. Use when different inputs need different processing pipelines. Keeps the logic centralized; the router is the only decision point.

3. **Parallelization** — Multiple agents work simultaneously on subtasks, then outputs are merged. Use for tasks where subtasks are independent. Dramatically reduces latency but introduces merge complexity and potential conflicts.

4. **Orchestrator-Worker** — A central orchestrator dynamically assigns subtasks to specialized workers, may loop back for revisions. Use for complex, multi-step tasks where the decomposition isn't known upfront. More flexible than routing but harder to reason about.

5. **Evaluator-Optimizer** — A generator produces output, an evaluator judges it, and they loop until quality threshold is met. Use for tasks where quality is measurable and revision is cheap. Common in code generation and content refinement.

### Multi-Agent Coordination Topologies (Zylos Research, January 2026)

| Pattern | Best For | Key Risk |
|---|---|---|
| **Supervisor** | Complex workflows, governance requirements | Single point of failure |
| **Hierarchical** | Enterprise scale (20+ agents) | Coordination overhead |
| **Peer-to-Peer** | Fault tolerance, distributed tasks | Slower consensus |
| **Swarm** | Robotics, optimization (50+ agents) | Emergence complexity |

### Three Architectural Schools for Workflow Coordination (Zylos Research, April 2026)

| Model | Philosophy | Key Trait |
|---|---|---|
| **DAG-Based** | Explicit dependency graphs | Deterministic execution |
| **Event-Driven** | Async pub/sub, reactive consumers | Emergent workflows |
| **Actor Model** | Isolated state, message-passing | Fault isolation |

### Framework Decision (Pharos Production, March 2026; Idea to MVP, June 2026)

- **LangGraph** — Production-grade. First-class state machines, checkpointing, durable execution, human-in-the-loop approval points. Best for systems that need crash-safe resume, branching, or strict control flow. 90K+ GitHub stars. The default for enterprise deployment once CrewAI's simplicity stops sufficing.
- **CrewAI** — Role-based teams with sequential/parallel/hierarchical execution. Fast to prototype with. Medium production readiness. Teams migrate *to* LangGraph when they need approvals, branching, or crash-safe resume.
- **AutoGen (AG2)** — Conversation-driven multi-agent message passing. In early 2025 Microsoft released 0.4/AG2, a significant rewrite with event-driven architecture. Strong for code generation and research tasks. Still medium production readiness.
- **Skip the framework entirely** — Anthropic recommends: use LLM APIs directly for most patterns. A few lines of code with direct API calls beats a framework that obscures what's happening underneath.

### Critical: External Task State

A commonly-missed pattern: task state lives *inside* the agent (context window, session memory, compaction summaries). When the session resets, state disappears. The Beads pattern (Steve Yegge, 2025) externalizes task state to durable storage so agents can resume after context loss. The principle applies broadly: don't store critical task state in volatile agent memory.

## Evidence

- **Anthropic Engineering post:** "The most successful implementations use simple, composable patterns rather than complex frameworks." Documents all five core patterns with production examples. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Zylos Research (January 2026):** 72% of enterprise AI projects now involve multi-agent systems (up from 23% in 2024). Observability is the #1 production barrier. Token duplication: MetaGPT 72%, CAMEL 86%, AgentVerse 53%. Documents Supervisor, Hierarchical, Peer-to-Peer, and Swarm coordination topologies. — [https://zylos.ai/research/multi-agent-orchestration-2025](https://zylos.ai/research/multi-agent-orchestration-2025)
- **Zylos Research (April 2026):** Deep analysis of DAG-Based, Event-Driven, and Actor Model orchestration architectures. Notes: "By 2025 that approach had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs had taught teams that agent coordination deserves the same engineering discipline as distributed systems in general." — [https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)
- **Pharos Production (March 2026):** Framework comparison with GitHub stars and production readiness ratings. Notes AutoGen 0.4 rewrite "addressed many criticisms about the original version's production readiness." — [https://pharosproduction.com/insights/engineering/langchain-vs-crewai-vs-autogen](https://pharosproduction.com/insights/engineering/langchain-vs-crewai-vs-autogen)
- **Idea to MVP (June 2026):** Reports that r/LangChain community consensus is "most teams reach for multi-agent orchestration too early." LangGraph becomes necessary when branching, approvals, or crash-safe resume is needed. — [https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **Steve Yegge / Beads pattern (2025):** Task state lives inside the agent and disappears on session reset. Documents how context loss silently degrades quality across task sequences. — [https://jx0.ca/solving-agent-context-loss/](https://jx0.ca/solving-agent-context-loss/)
- **Augment Code (June 2026):** 84% of developers use or plan to use AI tools, yet only 29% trust AI outputs to be accurate. Documents handoff failure modes and their organizational costs. — [https://www.augmentcode.com/guides/agent-handoff-patterns-human-agent-interface](https://www.augmentcode.com/guides/agent-handoff-patterns-human-agent-interface)

## Gotchas

- **Reaching for orchestration too early.** A single agent with 3–5 well-scoped tools often beats a multi-node graph. Add complexity only when the problem actually demands it.
- **Token duplication burns budget silently.** Multi-agent systems with shared context windows repeat information across agents. Benchmark your specific framework before assuming it's efficient.
- **Observability is the #1 production blocker, not the agents.** Teams invest in agent logic but neglect tracing, logging, and cost tracking — then can't diagnose failures in production.
- **Framework abstraction hides the LLM calls that matter.** Anthropic explicitly warns about this. If you can't easily read the actual prompts and tool calls your orchestration is generating, your framework is working against you.
- **Human-in-the-loop is not optional at organizational scale.** The 29% trust gap means every agent output that touches a human reviewer needs a designed handoff — not just an output dump.
