# S-2757 · The Control-Flow Model Stack — When Your Agents Go Circular and Nobody Tracked Where

When your agent gets stuck in a loop and no one knows why. When a retry goes wrong and the workflow silently continues with bad state. When adding a second agent makes everything nondeterministic and undebuggable.

## Forces

- **Acyclicity vs. the real world.** DAGs are clean and parallelizable, but agents naturally need retries, loops, and recovery paths — the features that DAGs explicitly forbid. You either model those as separate nodes (state explosion) or you need something with cycles.
- **Explicit control vs. emergent behavior.** The `while True: observe → think → act` loop is dead simple but impossible to replay deterministically. Every recovery attempt adds state you can't reconstruct.
- **Orchestration failures dwarf agent failures.** 37% of multi-agent system failures trace to inter-agent coordination, not the individual agents themselves — making the control-flow model a higher-leverage bet than model selection.
- **Framework shapes your options.** LangGraph defaults to cyclic state graphs; CrewAI has sequential and hierarchical processes; Temporal enforces explicit workflow definitions; AutoGen uses group chat. Each makes certain patterns cheap and others expensive.
- **Agent count multiplies coordination overhead.** Multi-agent systems are harder to operate than single agents by roughly the order of their agent count — every control-flow model decision compounds.

## The Move

Choose your control-flow model based on how much retry, branching, and state persistence your workflow actually needs. In practice, most teams move through three phases.

**Phase 1 — Start with a plain chain (sequential pipeline).** One agent, one step at a time, output of step N is input to step N+1. Deterministic, replayable, debuggable. Most real production workflows are still this. LangGraph `StateGraph` with a linear chain, CrewAI sequential process, or a simple `for` loop over agent calls. The moment you need a second agent that runs in parallel, you've left Phase 1.

**Phase 2 — Add explicit state machines for each agent node.** Each agent gets its own state machine with fixed states: `IDLE`, `OBSERVING`, `REASONING`, `ACTING`, `WAITING`, `ERROR`, `DONE`. Transitions are event-triggered (observation ready, LLM response received, timeout). The overall orchestration is a DAG where nodes are state machines and edges are data dependencies or control-flow signals. This is what LangGraph's `StateGraph` with checkpoints actually implements — each node is a state transition function. The agent-swarm.dev team replaced their DAG engine with this after hitting coordination failures at scale: "We drew a DAG, hit production, drew a state machine. The arrows are happier now."

**Phase 3 — Move to event-driven for complex, scalable coordination.** Agents publish events (e.g., `task.completed`, `approval.needed`) and other agents subscribe. The orchestrator becomes an event router rather than a call graph. This scales best for systems with many agents, multiple failure recovery paths, and human-in-the-loop checkpoints. The zylos.ai research maps this to the Actor model: isolated agent state, message-passing between agents, supervision hierarchies for failure.

The decision matrix:

| Model | Use when | Avoid when |
|---|---|---|
| Sequential chain | Linear workflows, clear input-output, low retry needs | Anything requiring branching or parallel work |
| DAG | Data pipelines, batch processing, clear topological sort | Tasks needing feedback loops, retries, or dynamic re-routing |
| State machine per node | Production multi-agent, non-deterministic agents, complex recovery | Simple single-agent workflows (overkill) |
| Event-driven / Actor | Large-scale agent swarms, human-in-the-loop gates, real-time coordination | Small, predictable workflows (too much infrastructure) |

## Evidence

- **Primary source — engineering post:** "Why We Ditched DAGs for State Machines in Agent Orchestration" — agent-swarm.dev team documents abandoning their DAG workflow engine after hitting coordination failures at scale in June 2024, switching to per-agent state machines with event-triggered transitions. Their fix: explicit `IDLE/OBSERVING/REASONING/ACTING/WAITING/ERROR/DONE` states per node. — [https://www.agent-swarm.dev/blog/deep-dive-state-machine-orchestration](https://www.agent-swarm.dev/blog/deep-dive-state-machine-orchestration)
- **Primary source — engineering post:** "Why We Replaced Generic Agent Loops with DAGs: A State Machine Autopsy" — documents the failure modes of `while True` agent loops (impossible to replay deterministically, shared-memory threading overhead, deadlock risk) and the DAG state machine pattern as the replacement. Each agent is a state machine; the overall orchestration is a DAG of those machines. — [https://blog.rinet.one/replacing-agent-loops-with-dags](https://blog.rinet.one/replacing-agent-loops-with-dags)
- **Primary source — research synthesis:** "AI Agent Orchestration: Patterns for Production" — synthesizes six production patterns (Sequential Pipeline, Supervisor + Specialists, Parallel with Merge, Event-Driven, Hierarchical, Blackbird) and documents the 37% coordination failure stat. Notes that "in 2024 the answer was often 'just chain together some LLM calls.' By 2025 that approach had collapsed under its own complexity." — [https://swarmsignal.net/ai-agent-orchestration-patterns/](https://swarmsignal.net/ai-agent-orchestration-patterns/)
- **Primary source — field note:** "Multi-Agent Orchestration Infrastructure: Lessons from Production" — describes the three production patterns that survive: Supervisor + Specialists (most common, one orchestrator decomposes and routes), Pipeline (sequential with branching), and Hierarchical (multi-level delegation). Notes that adding agents increases operational complexity roughly linearly with agent count. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/)
- **Primary source — field note:** "Multi-Agent Systems in Production: Lessons from the Field" — documents the most common mistake: over-engineering from day one with multi-agent architecture before understanding the problem domain. Also covers failure modes: coordination overhead, emergent failure modes, cost unpredictability, observability gaps. — [https://data-gate.ch/multi-agent-systems-production-lessons](https://data-gate.ch/multi-agent-systems-production-lessons)

## Gotchas

- **State explosion.** A full finite state machine per agent with explicit transitions sounds clean until you have 8 agents with 7 states each and 50 possible transitions. Map only the states that matter for your failure modes — don't model everything.
- **LangGraph's `recursion_limit` is a hidden circuit breaker.** LangGraph defaults to 25 steps per node before raising an error. In production, real agent tasks routinely hit this on complex reasoning. Set it explicitly and monitor where it fires.
- **DAGs can't represent retry paths without state explosion.** If you need "on failure, retry this agent up to 3 times then route to error handler," a DAG forces you to model three explicit retry nodes per agent. A state machine just has a `RETRY` transition. This is the core reason teams migrate from DAGs to state machines as workflows mature.
- **Human-in-the-loop breaks every model.** Approval gates, pause-for-review checkpoints, and manual corrections don't fit naturally into any control-flow model. Plan for them as explicit `WAITING` states in your state machines, not as afterthoughts in your DAG.
- **Non-determinism makes replay hard regardless of model.** Even with perfect state machine design, an agent that produces different outputs on the same input each run makes recovery from mid-workflow failures painful. Checkpointing (LangGraph's `MemorySaver`, Temporal's workflow history) is not optional in production — it's the only way to resume after crashes.
