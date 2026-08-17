# S-2795 · The Multi-Agent Orchestration Stack — When 37% of Your Failures Are Not Agent Problems

You've built a team of capable agents. Each one passes its unit tests. Together, they're unreliable. An agent produces output another agent can't parse. Two agents fight over a resource. A pipeline hangs because one agent silently failed. The problem isn't the agents — it's the choreography between them. According to production data, **37% of multi-agent failures trace to inter-agent coordination, not individual agent limitations**. This stack is about the choreography layer: how agents communicate, delegate, and recover together.

## Forces

- **Coordination overhead grows super-linearly.** As you add agents, the number of communication channels grows as O(n²). A 3-agent system has 3 channels; a 10-agent system has 45. Most teams design agents before designing the protocol, and pay for it in production.
- **The "capable in isolation, broken in concert" trap.** An agent that passes every test in isolation will deadlock, race, or cascade-fail when composed with others. Serialization of shared state, timing assumptions, and implicit trust between agents are invisible until the system runs for real.
- **Pattern choice determines failure mode shape.** Sequential pipelines fail predictably (one point of failure) but can't exploit parallelism. Parallel systems are fast but produce non-deterministic failure modes. Supervisor systems are robust but create a single point of contention. No pattern wins — each makes different trade-offs.
- **Framework defaults are not production defaults.** LangGraph's checkpointing, CrewAI's role hierarchy, and AutoGen's async loops all work in demos. Production use exposes the gaps: missing timeout propagation, checkpoint storage gaps, and conversation state that survives provider restarts.
- **Token budgets and latency budgets fight each other.** Passing rich context between agents (for coordination) consumes context window and adds latency. Passing minimal context (for efficiency) causes agents to act on stale or incomplete information.

## The Move

Choose an orchestration pattern based on task dependency structure, not framework popularity. Implement it with explicit protocols for three coordination primitives: what agents produce for each other, how failures propagate, and when to escalate to human review.

**Sequential pipeline — when task order is fixed and irreversible:**
- Chain agents where each step's input strictly depends on the previous step's output
- Use deterministic edges (LangGraph StateGraph with fixed transitions, CrewAI "sequential process")
- Insert validation gates between stages — don't let a downstream agent operate on unchecked upstream output
- Example: research → extract → write → review. Each stage transforms; later stages can't recover from earlier corruption.

**Parallel fan-out/fan-in — when independent subproblems dominate:**
- Spawn parallel subagents for independent work, then synthesize their outputs
- Anthropic's production research system uses this: planner agent decomposes a query, spawns parallel research agents, then synthesizes — achieving **90.2% improvement over single-agent Opus 4** on internal benchmarks
- Use a "collapse" step: a synthesis agent that consumes all subagent outputs and produces a coherent whole
- Set a global timeout on the fan-out phase; longest-running subagent determines latency
- Implement early termination: if one subagent finds a definitive answer, cancel the others

**Supervisor/hierarchical — when a conductor needs visibility and override authority:**
- A supervisor agent routes tasks to specialist agents, collects results, and decides next steps
- LangGraph's supervisor pattern maps cleanly: supervisor is the root node; specialists are called tools
- Key advantage: the supervisor can see partial results and re-route dynamically (retry specialist, escalate to human)
- Single point of failure in the supervisor — make it the most robust component

**Swarms/looped collaboration — when no agent has sufficient context alone:**
- Agents communicate in rounds, passing partial results and refining iteratively
- Use a shared message bus or blackboard architecture — not direct agent-to-agent calls
- Each round should produce a progress marker; after N rounds with no progress, terminate and escalate
- Best for creative or exploratory tasks where no agent can produce a complete answer independently

**Universal coordination guardrails (apply regardless of pattern):**
- **Explicit output schemas** — every agent-to-agent handoff uses a defined JSON schema. If downstream can't parse upstream's output, fail immediately with a schema mismatch error — don't guess or patch.
- **Timeout propagation** — every inter-agent call has an explicit timeout. If agent B doesn't respond within 30s, agent A should retry once then escalate — not wait indefinitely.
- **Checkpoint state** — after every major stage, write intermediate state to durable storage. On crash, resume from last checkpoint rather than replaying from scratch.
- **Circuit breaker on agent calls** — if an agent is failing repeatedly (e.g., 5 failures in 60 seconds), stop routing work to it, alert, and serve degraded output.

## Evidence

- **Azure Architecture Center:** Documents the four core patterns (Sequential, Parallel, Supervisor, Swarms) with framework implementations and trade-off matrices. Distinguishes orchestration from workflow automation: orchestration means agents make routing decisions dynamically, not just executing a fixed sequence. — [URL](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

- **Anthropic Engineering Blog:** Anthropic's production research system uses a planner agent to decompose queries, parallel subagents for simultaneous research, and a synthesis agent to produce the final output. Key finding: multi-agent Opus 4 + Sonnet 4 subagents achieved **90.2% relative improvement** over single-agent Opus 4 on internal research evaluations. The parallel compression model is key: subagents distill findings, reducing token volume before synthesis. — [URL](https://www.anthropic.com/engineering/built-multi-agent-research-system)

- **Swarmsignal production analysis:** Documents that **37% of multi-agent failures are coordination failures**, not individual agent failures. Analyzes the six production orchestration patterns with framework implementation details: sequential (CrewAI sequential process, LangGraph linear StateGraph), parallel fan-out (Anthropic approach, CrewAI hierarchical process), supervisor (LangGraph supervisor pattern), and swarm patterns. — [URL](https://swarmsignal.net/ai-agent-orchestration-patterns)

## Gotchas

- **Don't add agents for parallelism's sake.** Adding a second agent to a task that has no independent sub-problems just doubles your coordination surface. Measure before adding: is the task actually decomposable?
- **Silent failure is the default failure mode.** An agent that times out often produces no output and no error — the next agent in the pipeline waits indefinitely. Build heartbeat/pong checks for every long-running inter-agent call.
- **Context passing destroys context windows.** Passing full conversation history between agents burns tokens fast. Design a "handoff document" pattern: each agent produces a structured summary of what the next agent needs, not a transcript.
- **Checkpointing looks solved until you need it across provider restarts.** LangGraph checkpointing works within a session. If your agent host restarts mid-pipeline, you need durable external state (Redis, S3, or a DB) — not just in-process checkpointing.
- **Supervisor bottlenecks are invisible under light load.** A supervisor routing to 5 agents handles load gracefully. Under 50 concurrent requests, that single supervisor becomes a serializing bottleneck. Load-test at 10× expected concurrency before shipping.
- **Framework release cadence creates protocol drift.** CrewAI, LangGraph, and AutoGen release breaking changes frequently. Pin framework versions in production; test upgrades against your coordination protocol specifically, not just agent behavior.
