# S-2473 · The Multi-Agent Failure Stack — When 41–87% of Production Traces Break in Unexpected Ways

Your multi-agent pipeline looks correct in the diagram. Four agents, clear roles, defined message passing. You deploy it, run 100 tasks, and 40–87 of them silently fail — an agent loops for 35 minutes, two agents deadlock waiting for each other, a subagent takes an irreversible action before the supervisor can intervene. The failure mode is not in your code. It is in the gap between what the orchestrator assumes and what the agents actually do.

## Forces

- **Agents fail differently than microservices.** A microservice fails when its process crashes. An agent fails by silently looping, producing contradictory outputs, accumulating context until the model halts, or taking irreversible action before human intervention can land. The failure taxonomy is fundamentally different.
- **The routing problem and the persistence problem are different.** Agent orchestration frameworks all solve routing well. Few solve the persistence problem — managing state across 45-minute workflows without the agent silently losing track of what it was doing mid-task.
- **Inter-agent misalignment compounds with scale.** Two agents is manageable. Ten agents with shared resources, competing context windows, and implicit task dependencies is a system with emergent failure modes that no individual agent's logic can reason about.
- **Eval benchmarks mask the real failure rate.** Academic benchmarks test closed scenarios with known solutions. Production tasks have ambiguous goals, incomplete specifications, and agents that must decide when to stop — the exact conditions that trigger the failure modes that don't appear in benchmarks.

## The move

Design for failure taxonomy before designing for functionality. The pattern that works in production:

- **Supervisor tree over flat agent pool.** One orchestrator manages the workflow graph; subagents are leaf nodes with no cross-communication except through the supervisor. This limits the blast radius of any single agent's failure and makes the execution trace readable.

- **Token budgets per agent role.** Assign each agent class a hard token ceiling (e.g., Planner: 30% of context, Retriever: 20%, Validator: 20%). The Fleet system by sermakarevich uses per-task model overrides to stay within budget. Agents that exhaust their budget get handed back to the supervisor — they don't improvise with truncated context.

- **Durable task queue over in-memory state.** Replace shared global state with a durable queue (Redis Streams or RabbitMQ) that persists task ownership, status, and partial results across crashes. The orchestrator restarts from the queue, not from a dead agent's memory.

- **Circuit breakers on tool calls.** When an agent's tool-call failure rate exceeds a threshold (e.g., 3 consecutive failures), the circuit opens: the supervisor stops routing work to that tool and degrades gracefully — returns a best-effort answer or escalates to human review.

- **Idempotency guards on all side effects.** Every write operation should be idempotent so a retry from the durable queue doesn't create duplicate records. This is especially critical for agents that have long loops — the retry from step 12 should not re-execute steps 1–11.

- **Explicit termination conditions in the supervisor graph.** Don't rely on the agent to decide when it is done. Build explicit state transitions (pending → running → validated → complete) that the supervisor enforces, not the agent's own confidence.

## Evidence

- **Research paper:** UC Berkeley's "Why Do Multi-Agent LLM Systems Fail?" (arxiv:2503.13657, NeurIPS 2025) analyzed 1,642 annotated traces across 7 MAS frameworks and found failure rates of 41% to 86.7%. The taxonomy identifies 14 distinct failure modes in three categories: specification issues, inter-agent misalignment, and task verification failures. A parallel LLM-as-Judge annotation pipeline achieved κ=0.77–0.88 human agreement.
  — https://arxiv.org/abs/2503.13657

- **Open-source project:** Fleet (github.com/sermakarevich/fleet) is a Python supervisor for running Claude Code swarms at scale — the author ran it as a Show HN post. Architecture: centralized SQLite queue via beads, 10–15 concurrent agents, per-task model overrides, task dependencies defined in a graph, and an `ask_human` MCP tool for human-in-the-loop. The lesson: centralized orchestration with durable persistence survives agent failures that would lose an in-memory system entirely.
  — https://github.com/sermakarevich/fleet

- **Engineering blog:** Harsh Rastogi (AI Product Engineer, Modelia.ai / Asynq.ai) documented real production failures: a candidate evaluation agent hallucinated tool parameters and got stuck in loops; an image generation pipeline approved obviously flawed images by optimizing for workflow completion over quality. The fix: explicit token budgets per agent role, circuit breakers on tool calls, and a "stop condition" node in the execution graph enforced by the supervisor, not the agent.
  — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns

## Gotchas

- **Per-agent scoped memory, not shared context.** Passing a single global context object to all agents causes context pollution and makes failure traces unreadable. Scoped snapshots per agent — read-only, immutable — let you replay exactly what each agent saw without cross-contamination.
- **Long loops are the failure mode, not the success metric.** Agents that run longer often look more capable. In production, a 35-minute silent loop is worse than a fast failure. Instrument loop detection: count tool-call iterations per task and hard-kill at a threshold.
- **The framework matters less than the failure primitives.** Markaicode's benchmark of LangGraph vs CrewAI vs AutoGen found LangGraph edges out on tool-call success rate (97.4% vs 94.1%) and lower average latency (3,730 ms vs 3,910 ms per node), but the real differentiator was observability — LangGraph's graph inspection made failures readable in a way that CrewAI's autonomous agent model obscured.
- **Partial failure is not the same as no failure.** In a multi-agent pipeline, one agent completing successfully while another silently degraded is the worst outcome — you get false confidence. Design for explicit partial-success states that the supervisor must acknowledge before marking the overall task complete.
