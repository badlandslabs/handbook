# S-1247 · The Durable Execution Stack: When LangGraph Meets Temporal and Your Agent Stops Dying Halfway Through

Your agent works in the demo. It crashes at step 7 of a 10-step workflow, losing all state. You add retry logic. It now retries the wrong step and corrupts the output. You add more logic to track which step it's on. You've now built a workflow engine badly. The right answer is to use a workflow engine — specifically, durable execution — from the start.

## Forces

- **Per-step accuracy compounds against you.** With 95% per-step accuracy, a 10-step workflow completes only 60% of the time; a 50-step workflow drops below 8%. Retry logic alone can't fix this because retries without durable state just re-execute from scratch.
- **LLM calls are expensive and non-deterministic.** A failed GPT-4o call mid-workflow wastes real money. Replaying the same call on retry may produce a different result, making naive retries unreliable.
- **Production agents need to survive infrastructure failures.** Network timeouts, container restarts, host preemptions, and API rate limits are not edge cases — they are the baseline in cloud environments.
- **Durable execution and agent reasoning are separate concerns.** Trying to handle both in the same layer creates tight coupling and makes each harder to reason about.

## The move

**Layer LangGraph (agent reasoning) over Temporal (durable orchestration).** They address different problems and compose cleanly.

**LangGraph** models the agent as a state machine with checkpointed state, keyed by thread ID. It handles: routing decisions (which tool to call next), conditional branching (if X, do Y else Z), and the agent's internal reasoning loop. Think of it as "what the agent decides."

**Temporal** provides durable execution runtime with event-sourced history. It backs multi-step workflows with: deterministic replay on failure, activity-level retries with backoff, built-in timeouts and dead-letter queues, and long-running workflow support (hours to days). Think of it as "what the agent gets to finish."

**The composite pattern:**
- LangGraph manages agent state and tool routing within each step
- Temporal manages step sequencing, failure recovery, and cross-step durability
- The agent's LLM call is wrapped as a Temporal activity with retries
- Long-horizon state (thread ID, conversation history, intermediate results) persists in Temporal's event history, not in memory

**When to add Temporal to LangGraph:**
| Condition | Action |
|-----------|--------|
| Workflow finishes in <30s with 1-2 tool calls | LangGraph alone |
| 3+ external/tool calls across steps | Add Temporal |
| Workflow pauses for hours or days | Add Temporal |
| Actions where duplicate retry would be harmful (writes, sends) | Add Temporal with idempotency keys |
| Task duration exceeds 4 hours | Add Temporal |

**Event-driven alternatives for stateless or fan-out scenarios:**
- **DAG-based (LangGraph native):** Explicit dependency graphs, deterministic execution, testable. Best when workflow structure is known upfront.
- **Event-driven pub/sub:** Async message passing with reactive consumers. Best for decoupled systems with many producers and consumers. Dank-AI and similar frameworks use this for multi-agent fan-in/fan-out where agents run as containerized microservices.
- **Actor model:** Isolated state with message-passing and supervision trees. Best for fault isolation at scale — each agent is an actor that can fail and be restarted independently without affecting others.

## Evidence

- **Engineering post — Anthropic (2025):** MCP adoption reached "thousands of MCP servers" with SDKs across all major languages. Anthropic's own engineering team recommends code-based tool calling patterns to reduce per-call token overhead at scale — agents write code to call tools instead of calling tools directly, cutting token costs significantly. — [Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Research — AgentMarketCap (2026):** Real-world deployment data shows 73% of enterprise agents experience reliability failures in year one. With 85% per-step accuracy, a 10-step task has ~20% survival rate; at 20 steps, statistically improbable. The recommendation: use Temporal for workflows exceeding 3 external calls or 4-hour duration. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/durable-agent-execution-production-temporal-modal-event-sourced)
- **HN "Show HN" — Dank-AI (Nov 2025):** Practitioners noting that event-driven stateless runtimes are "becoming a trend for multi/sub-agent workflows" using queuing systems, with teams discovering "fan-in conflict locks" and coordination problems that swarms of agents introduce. — [Hacker News](https://news.ycombinator.com/item?id=46021135)
- **Research — Zylos AI (2026):** By 2025, ad-hoc agent chaining "collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs." Three orchestration schools crystallized: DAG-based (predictable, testable), event-driven (scalable, decoupled), and actor model (fault-isolated). Durable execution is now "a core requirement for modern AI systems." — [Zylos Research](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Don't retry LLM calls without idempotency.** A failed GPT-4o call that gets retried may produce a different output — the same prompt is not deterministic. Wrap LLM calls in activities with idempotency keys tied to the conversation state, not just the prompt.
- **LangGraph checkpointing alone isn't durable execution.** LangGraph checkpoints survive a container restart, but not a full deployment teardown or a Temporal-scale outage. If your agent needs to survive hours-long pauses or multi-region failover, you need Temporal's event-sourced history, not just LangGraph's in-process state.
- **Actor model and durable execution solve different problems.** The actor model gives you fault isolation and location transparency; Temporal gives you deterministic replay and saga compensation. Many teams implement both — actors for per-agent resilience, Temporal for cross-agent workflow durability.
- **Event-driven fan-out introduces race conditions.** When multiple agents consume the same event queue, the order of processing is non-deterministic. Add explicit sequencing or acknowledgment semantics if your workflow requires ordered state transitions.
