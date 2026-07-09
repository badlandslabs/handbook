# S-838 · The Agent Orchestration Stack — When the Loop Is Not Enough

You have a working single-agent loop — it reasons, calls tools, observes, repeats. Now you need it to coordinate multiple agents, route tasks to specialists, and recover from failures mid-workflow. The simple while-loop breaks down: who decides what runs next? How do agents pass state? What happens when one fails?

## Forces

- **Centralized control is debuggable but fragile.** A single orchestrator that routes every call is easy to trace — but it becomes a bottleneck, and a bug in the router takes down the entire workflow. (Anthropic, Building Effective AI Agents, 2026)
- **Full autonomy scales poorly.** Letting agents pick their own subtasks leads to emergent deadlocks and incoherent outputs. Practitioners report: "don't let agents pick their own subtasks. Define the task graph yourself; agents only handle the leaf nodes." (HN/swrly, Ask HN multi-agent workflows, 2025)
- **Context drift compounds in multi-agent systems.** Each agent sees a partial state. Without explicit read/write contracts, agents overwrite each other's context, producing contradictory outputs. (Markaicode, Multi-Agent Architecture, Jul 2026)
- **Orchestration flexibility trades off against determinism.** The more dynamic the routing, the harder it is to reproduce failures, set budgets, and enforce governance. (Camunda, Hype to Impact, Oct 2025)
- **Most frameworks do the same things poorly in different ways.** LangGraph, CrewAI, and AutoGen converged on similar primitives (ReAct loop, tool calling, state management). Practitioners report "there's absolute 0 framework out there that's good enough for serious work" and build custom on top. (HN/se gmondy, 2025)

## The Move

Four topologies exist on a spectrum from fully centralized to fully decentralized. Pick based on how predictable and decomposable your workflow is.

### Pattern 1: Supervisor (Centralized)

A single LLM-driven supervisor decides what each worker does and when. Workers are dumb executors — they receive a task, do it, return. The supervisor holds all state.

```
User → Supervisor (LLM) → [Worker A] → Supervisor decides → [Worker B] → Supervisor decides → Done
```

- Best for: ambiguous, cross-specialist, adaptive work where the next step depends on the previous output
- Trade-off: coordination overhead, latency, and cost accumulate with each supervisor round-trip
- Enterprise pattern: JPMorgan uses LangGraph's conditional edges with a supervisor node that evaluates each worker result before routing (Gheware, LangGraph Multi-Agent Orchestration, 2026)

### Pattern 2: Router (Upfront Dispatch)

A single classification step at the start sends the task to a fixed destination — a specialist team, a specific workflow, a known toolset. No ongoing coordination after dispatch.

```
User → Router (LLM) → [Destination workflow] → Done
```

- Best for: classification and routing where the workflow path is knowable at the start
- Trade-off: cannot handle tasks that need mid-flight re-routing; assumes task type is stable
- Implementation: LangGraph's conditional routing edges, CrewAI's routing rules, or a simple LLM classification call

### Pattern 3: Planner → Executor (Pipelined)

A planner decomposes the goal into an explicit step sequence upfront. Executors work through the steps. The planner may replan if a step produces unexpected output.

```
User → Planner (LLM) → [Step 1: Executor] → [Step 2: Executor] → [Step 3: Executor] → Done
```

- Best for: decomposable work with a legible roadmap — research pipelines, document processing, multi-stage analysis
- Trade-off: brittle when execution reveals evidence that invalidates the upfront plan
- Production use: SpecX task orchestration engine routes feature work into explicit requirement → implement → test → document steps (HN/dhaundy, Show HN, 2025)

### Pattern 4: Swarm (Fully Decentralized)

Agents announce capabilities and negotiate handoffs peer-to-peer. No central controller. Coordination emerges from the interaction graph.

```
[Agent A] ↔ [Agent B] ↔ [Agent C]
   ↑___________↘↙____________↓
```

- Best for: exploratory domains where no single planner can anticipate the full task space
- Trade-off: hardest to debug, reproduce, and govern; best suited for research prototypes, not regulated production workflows
- Observation: IBM research notes 94% of enterprises report "agent sprawl" creating security and operational headaches precisely because decentralized agents operate without design-time handoff contracts (DevStarsJ, LangChain AI Agents Production Guide, Feb 2026)

### Implementation Layer: Shared State

Regardless of topology, multi-agent systems require an explicit state contract:

- **Per-agent scoped state** prevents context drift. Each agent reads and writes only its slice. A shared state store (Redis, PostgreSQL, or MongoDB) holds the authoritative record. (Markaicode, 2026)
- **Checkpointing** at each agent handoff enables recovery without re-executing completed steps. LangGraph's built-in checkpointing, or a custom Redis snapshot per agent turn. (Gheware, 2026)
- **Structured output schemas** for agent-to-agent messages prevent hallucinated field names. Pydantic models or JSON Schema enforced at each handoff boundary. (HN/pablovarela: "MongoDB JSON docs with pipeline IDs — each agent writes to its own doc").

## Evidence

- **Anthropic whitepaper: Centralized vs. decentralized architectures.** "Centralized systems employ hierarchical patterns where a central supervisor intelligently delegates tasks to specialized agents, creating clear chains of responsibility." Contrasts with decentralized systems where agents self-coordinate. — [Building Effective AI Agents: Architecture Patterns (PDF)](https://resources.anthropic.com/hubfs/Building%20Effective%20AI%20Agents-%20Architecture%20Patterns%20and%20Implementation%20Frameworks.pdf)
- **HN Ask: Multi-agent orchestration in production (11 practitioners).** Key findings: custom beats frameworks for serious work; fan-out/fan-in over parallel agents; SQLite-structured JSON or Redis-backed scratchpad for inter-agent data flow; define the task graph yourself, agents only handle leaves. — [HN thread #47660705](https://news.ycombinator.com/item?id=47660705)
- **Groovy Web: 4 topologies from 50+ production agent systems.** Patterns ranked by predictability of workflow: Router (most predictable) → Planner-Executor → Supervisor → Swarm (most adaptive). Includes failure mode analysis per pattern. — [Multi-Agent Orchestration: 4 Patterns for 2026](https://www.groovyweb.co/blog/multi-agent-orchestration-patterns-supervisor-router-pipeline-swarm-2026)
- **Agent Engineering: Supervisor vs. Router vs. Planner-Executor taxonomy.** Framework-agnostic comparison of when decisions happen, who owns the task, and the main failure mode for each. — [Supervisor, Router, and Planner-Executor Patterns](https://agentengineering.org/articles/supervisor-router-and-planner-executor-patterns/)

## Gotchas

- **Don't give agents full autonomy over task decomposition.** The "let agents pick their own subtasks" pattern consistently produces deadlocks and incoherent outputs in production. Define the DAG; let agents execute within it.
- **The supervisor pattern's per-step LLM call is expensive.** A 10-step workflow with a supervisor routing each step doubles your token cost. Budget for it or use conditional edges with deterministic routing for known paths.
- **Context drift is the primary multi-agent failure mode, not orchestration logic.** Teams spend weeks optimizing routing topology only to discover agents were overwriting each other's state. Fix the state contract before the routing topology.
- **Framework choice is mostly cosmetic.** LangGraph, CrewAI, AutoGen, and AGNO all implement the same patterns. The real differentiators are: checkpointing quality, observability integrations, and whether you can read the source code when it breaks. Most teams building "serious" systems end up customizing or wrapping anyway.
- **Human-in-the-loop is not optional for high-stakes flows.** LangGraph's interrupt mechanism, CrewAI's human-in-the-loop tasks, and Camunda's process orchestration all enforce approval gates on actions exceeding thresholds (financial transactions, data deletion, external API writes). Without this, a routing error cascades into irreversible actions.
