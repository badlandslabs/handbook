# S-2548 · The Orchestration Topology Stack — When Your Agent Team Has No Chains of Command

You assembled a capable multi-agent system: researcher, writer, reviewer, publisher. Each agent works alone. Together, they deadlock on priorities, duplicate work, or funnel everything through a single point of failure. The problem is not agent quality — it is the communication structure you gave them, or the absence of one.

## Forces

- **Topology shapes failure domains.** A star-shaped system where the orchestrator dies kills the entire workload. A mesh where every agent calls every other makes debugging a graph traversal problem, not a code trace.
- **Latency and parallelism are in tension with coordination cost.** Fully synchronous chains (each agent waits for the previous) are easy to reason about but slow. Fully parallel (everyone calls everyone) is fast but generates conflicting intermediate states.
- **Context ownership is ambiguous without explicit routing.** When agents share a prompt template or scratch-pad, writes race. When they share nothing, results don't compose.
- **Framework defaults encode assumptions you inherit silently.** CrewAI's `Process.sequential` and LangGraph's `StateGraph` make different trade-offs about who drives the loop — and neither is wrong for all cases.

## The Move

Choose your orchestration topology based on three variables: **task decomposition shape** (divergent → convergent, or parallelizable), **latency tolerance**, and **failure isolation requirement**.

### 1. Hub-and-Spoke (Orchestrator-Worker) — Use when one agent owns the goal

```
User → Orchestrator → [Worker A] → [Worker B] → Orchestrator → User
                  ↘ [Worker C] ↗
```

The orchestrator decomposes the goal, dispatches subtasks, collects results, and decides completion. Workers never call each other directly. All inter-agent state flows through the hub.

- Best for: Linear pipelines, tasks with a clear "owner"
- Failure mode: Orchestrator becomes a bottleneck and single point of failure
- Gotcha: The orchestrator LLM call count multiplies with team size — n workers means ~2n additional calls per round

### 2. Hierarchical (Supervisor Chain) — Use when subtask complexity varies by role

A mid-level supervisor owns a cluster of workers and reports to a higher orchestrator. Reduces the orchestrator's load by delegating intra-cluster coordination.

- Best for: Large teams (6+ agents), role-based groupings (e.g., "data team" supervised by a data lead)
- Failure mode: Supervisor failure cascades to its cluster but not the whole system
- Gotcha: Two-level plans are legible; three-level plans start to need explicit state management

### 3. Supervisor Pattern (LLM Router) — Use when routing logic is policy-heavy

A supervisor LLM evaluates each step's output and decides the next agent to call. No fixed sequence. The supervisor maintains a task state and routes dynamically.

```python
# Pseudo-code from production patterns
while not complete:
    state = supervisor.evaluate(current_output)
    next_agent = routing_policy.select(state)
    result = next_agent.execute(state.task)
    state.update(result)
```

- Best for: Open-ended tasks where the execution path is unknown at start
- Failure mode: Supervisor hallucinations cause unnecessary agent calls or misroutes
- Gotcha: Requires structured output from the supervisor (JSON schema, enum dispatch) — unstructured routing degrades fast

### 4. Message Bus (Pub/Sub or Queue-Based) — Use when agents should be decoupled and asynchronous

Agents publish results to a channel; other agents subscribe. The orchestrator is a message broker, not a decision engine. Workers operate independently and react to events.

- Best for: High-throughput workloads, event-driven pipelines, systems where agents must not block each other
- Failure mode: Message loss or duplication if delivery guarantees aren't explicit
- Gotcha: Debugging requires trace aggregation across channels — a distributed systems problem, not a prompt problem

### 5. Mesh (Peer-to-Peer) — Use when agents must negotiate shared resources

Every agent can call every other agent. No central coordinator. Results emerge from negotiation or voting.

- Best for: Consensus-building tasks, multi-perspective analysis, adversarial or competitive scenarios
- Failure mode: Circular dependencies, non-termination, undebuggable state
- Gotcha: Rarely the right choice for business workflows — most "mesh" implementations are actually hub-and-spoke with extra steps

## Evidence

- **Framework documentation / production pattern:** The Devstarsj blog post (June 2026) codifies exactly these four topologies (hub-and-spoke, hierarchical, supervisor, message bus) with runnable Python patterns for production deployments, noting that "decompose the problem, not just the prompt" is the core design principle distinguishing successful multi-agent systems from elaborate single-agent pipelines — https://devstarsj.github.io/2026/06/30/ai-agents-multi-agent-orchestration-production-2026/
- **Enterprise analysis:** NeuralCoreTech's orchestration guide (July 2026) frames the choice as an air-traffic-control problem: "every agent is competent on its own, but only the control tower keeps the whole system safe, efficient, and auditable" — https://neuralcoretech.com/agentic-ai-orchestration-2026/
- **Market data:** Y Combinator's Spring 2025 batch had 67 of 144 startups (46%) describing themselves as "AI agents," with multi-agent orchestration being the primary architectural differentiator cited in Demo Day pitches (PitchBook, Business Insider) — https://www.cbinsights.com/research/y-combinator-spring25-agentic-ai/
- **Industry framing:** Anthropic's engineering guide (Dec 2024, still canonical in 2025 HN discussion at 543 points) draws the key line: "workflows" (predefined code paths) vs "agents" (dynamic, LLM-directed), noting that the choice of orchestration pattern is the primary architectural decision, not a detail — https://www.anthropic.com/engineering/building-effective-agents

## Gotchas

- **Don't choose a topology before you know the task shape.** Parallelizable tasks (independent research across sources) benefit from bus or mesh. Convergent tasks (analyze + write + review) need a supervisor or hub. Starting with hub-and-spoke and evolving only when you hit a real bottleneck is the right default.
- **Adding agents without changing topology multiplies failures.** A hub-and-spoke system with 8 workers has one orchestrator doing routing for 8 concurrent calls — if the orchestrator's context window fills, the entire queue stalls. Profile the routing bottleneck before scaling the team.
- **Framework defaults will trap you.** CrewAI's `Process.sequential` enforces a chain. LangGraph's `StateGraph` enforces a state machine. Neither is wrong, but migrating from sequential to supervisor requires rewriting the execution loop, not just the prompts.
- **Observability must match topology.** A message bus with 5 agents needs distributed tracing (trace IDs propagated across channels). A hub-and-spoke needs only orchestrator-level logging. Choosing a complex topology without the observability to match it means you cannot see failures.
