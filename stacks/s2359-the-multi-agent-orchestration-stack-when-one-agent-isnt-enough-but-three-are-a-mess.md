# S-2359 · The Multi-Agent Orchestration Stack — When One Agent Isn't Enough But Three Are a Mess

Single-agent loops solve single tasks. Most production work involves sub-tasks with different skill profiles, different tools, and different reliability requirements. Teams reach for multi-agent systems when the task has natural seams — parallel research arms, sequential quality gates, or specialist domains — and the seams are sharp enough to isolate. The problem is that multi-agent orchestration multiplies failure modes: an agent that goes off-task, a tool call that blocks indefinitely, a shared memory state that gets corrupted, a cost that scales super-linearly with team size. Getting it right means picking the right topology for the task shape, not the trendiest pattern.

## Forces

- **Parallelism promises speed; coordination costs kill it.** Research tasks, batch analysis, and multi-source synthesis are naturally parallelizable, and multi-agent systems exploit that — but the overhead of result reconciliation, shared state management, and inter-agent communication can negate the gains for tasks that aren't wide enough.
- **More agents means more observability debt.** A single-agent loop is one trace. Three agents with fan-out is three traces with cross-references, a shared memory store, and a reconciliation step that isn't itself a trace. Most teams discover this at 2am when a production incident can't be debugged.
- **The 15x token problem.** Multi-agent systems with Claude Opus as lead and Sonnet as workers outperform single Opus by 90.2% on research tasks — but consume roughly 15x more tokens than a comparable single-agent chat. Cost is an architectural constraint, not an afterthought.
- **40% of pilots fail within six months of production deployment.** Gartner data shows that multi-agent adoption is surging (1,445% inquiry growth Q1 2024–Q2 2025) but the majority of pilots don't survive contact with production. The failure pattern is consistent: wrong pattern selection, no observability layer, no budget for coordination overhead.

## The move

**Pick the topology that matches the task's natural shape.** Three patterns appear consistently across Anthropic's research system, Mastra, AgentMesh, and production reports — each optimized for a different task structure.

**1. Orchestrator-Worker (fan-out/fan-in):** A lead agent decomposes a task, dispatches subagents in parallel, waits for all results, then reconciles. Use when: the task has independent research arms or parallelizable sub-tasks (e.g., multi-source research, parallel API calls to different services). Lead uses capable model; workers use cheaper, task-specific models. Anthropic's Claude Research uses this — lead writes plan to shared memory, Sonnet subagents explore independently, lead condenses results. **Key risk:** lead reconciliation becomes a single point of failure; worker failures need explicit retry/timeout handling.

**2. Supervisor (sequential pipeline):** A supervisor agent gates each stage of a pipeline, deciding whether to proceed, retry, or escalate. Use when: tasks have strict ordering and quality gates (e.g., code review → test → deploy, or document → review → approve). Supervisors are typically the most capable model. **Key risk:** supervisor becomes a bottleneck; if the gatekeeping logic is complex, the supervisor itself may need orchestration.

**3. Hierarchical (nested agents):** A top-level agent manages teams of agents, each managing sub-teams. Use when: organizational structure maps naturally to the task (e.g., department heads → team leads → specialists). AgentMesh implements this via Pregel/BSP for state management. **Key risk:** deep hierarchies amplify latency and token cost; state synchronization across layers is non-trivial.

**4. State-machine (fixed control flow):** Agents move through defined states with explicit transitions. Use when: the task is well-understood, deterministic enough to pre-define, and needs auditability. **Key risk:** brittleness when the task has unpredictable branches.

**Shared memory is the load-bearing component, not an afterthought.** All topologies need a shared artifact store — a file, object store, or vector DB where agents write findings and successors read context. Without it, agents operate in isolation and reconciliation fails. Anthropic uses a shared memory store where the lead writes the plan and subagents write condensed findings. Fountain City Tech's production validation confirmed: "Subagents return condensed findings via shared memory store (artifact pattern). Lead agent reconciles findings into final answer with citations."

**Set per-agent budgets: step limits, token caps, and timeouts.** An agent in a fan-out that never returns blocks the entire orchestration. Budget every subagent independently. Mastra's approach includes explicit step budgets per agent type.

**Observability requires cross-agent traces, not per-agent traces.** A single Jaeger or OpenTelemetry trace ID that follows a task through all agents is the minimum viable observability layer. Without it, you cannot answer "which subagent produced the bad output" in production.

## Evidence

- **Engineering blog / primary source:** Anthropic's multi-agent research system uses a lead agent that plans research and spawns subagents with separate context windows for parallel exploration. Subagents write to a shared artifact store; the lead reconciles. The system is used in production for Claude Research. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Production validation:** Fountain City Tech deployed Anthropic's multi-agent blueprint in production. Found 90.2% performance improvement over single Opus 4 on research tasks, but confirmed the ~15x token cost increase and added a "multi-turn coherence gap" when subagent findings conflict. — [Fountain City Tech](https://fountaincity.tech/resources/blog/anthropic-multi-agent-blueprint-production/)
- **Framework / market data:** Beam.ai's 2026 orchestration patterns analysis covers six patterns with real failure modes. Reports 40% of multi-agent pilots fail within six months of production deployment, citing wrong pattern selection and lack of observability. — [Beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **GitHub (open source):** AgentMesh (Go, Apache 2.0) implements multi-agent orchestration via Pregel BSP for state management, supporting parallel execution and cross-agent observability. — [GitHub](https://github.com/hupe1980/agentmesh)
- **HN / community:** Show HN discussion on "Evolving Agents" (139 points, March 2025) surfaced the post-fork reconciliation problem — agents branch with `fork` but nothing brings sessions back together. The EvolvingAgentsLabs plugin versions agent evolution and gates merges on eval results. — [Hacker News](https://news.ycombinator.com/item?id=43310963)

## Gotchas

- **Starting with multi-agent when single-agent suffices.** If the task fits in a loop, the coordination overhead of multiple agents is pure cost. Anthropic's guidance is explicit: start with the simplest workflow that works, add agents only when the task has genuine seams.
- **No shared artifact store.** Without it, subagents in a fan-out produce findings that the lead can't reliably access. This is the most common architectural mistake — teams build the agent logic and treat the shared state as an implementation detail.
- **Subagent failures are silent by default.** A subagent that times out or returns empty-handed doesn't propagate an error unless you've explicitly wired one. Every subagent invocation needs a retry policy and a fallback.
- **Token cost surprises.** The 15x multiplier isn't theoretical — it hits on the first billing cycle. Model selection (expensive lead + cheap workers) and result condensation at the subagent level are non-negotiable production practices, not optimizations.
- **Deep hierarchies amplify latency.** Each layer adds a round-trip. A three-layer hierarchy with 500ms per LLM call means 1.5s minimum latency before the top level can respond. Measure before committing.
