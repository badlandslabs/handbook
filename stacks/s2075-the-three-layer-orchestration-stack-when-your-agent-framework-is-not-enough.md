# S-2075 · The Three-Layer Orchestration Stack — When Your Agent Framework Is Not Enough

[You chose LangGraph. Your agent loops, calls tools, and routes decisions. But after three months in production you've had: an agent that ran 47 tool calls on a single user request and billed $34, a crashed executor that lost all mid-task state, a silent auth-token expiry that produced wrong outputs for six hours, and no way to replay what happened. Your framework is solving the right problem at the wrong layer. The failures are infrastructure problems, not model problems.]

## Forces

- **The framework/loop/infra confusion is endemic.** LangGraph, AutoGen, and the Claude SDK are agent frameworks — they handle application-level concerns (tool selection, context management, multi-agent dispatch). They do not handle infrastructure-level concerns (crash recovery, long-wait persistence, distributed coordination). Conflating the two leaves the gaps that kill production agents.
- **Agent flexibility and system predictability are in tension.** Anthropic's research — discussed on HN in June 2025 (543 points, 88 comments) — found that "agents increase the degrees of freedom in your system exponentially, making it harder to guarantee correct behavior." Teams that gave agents maximum autonomy without explicit boundaries consistently underperformed teams that started simple and added complexity only when the simpler pattern genuinely couldn't.
- **The checkpointer is load-bearing in production, invisible in prototyping.** A single-replica LangGraph app with in-memory state works fine until you deploy two replicas or a single replica crashes mid-task. At that point, the checkpointer is the difference between a self-healing system and a broken session with no recovery path.
- **Durability vs. latency is a tunable knob, not a binary.** Async checkpoint writes keep the agent responsive but risk losing the last step on crash. Sync writes are safe but add 10–30ms per step. Teams default to the safe choice, then measure before switching.
- **Production tool call failure rates (12–18%) dwarf benchmark rates (~0%).** SWE-bench Verified runs in a controlled container with zero rate limits, zero auth expiry, zero network jitter. Production has all of them. Infrastructure for failure handling — retries, circuit breakers, escalation paths — must be designed in, not patched on.

## The Move

Separate the agent into three distinct layers, each solving problems at the right abstraction level. Use the framework only for what it's actually for.

**Layer 1 — Agent Loop (your framework's job):**
- Tool selection and sequencing decisions
- Context window management and in-context example selection
- Multi-agent dispatch and handoff routing
- Guardrail triggering and stop conditions

**Layer 2 — Application Engineering (what the framework actually provides):**
- Error handling around individual tool calls
- Memory and checkpointing interfaces
- Tracing and observability hooks
- Prompt versioning and configuration management

**Layer 3 — Infrastructure Orchestration (Temporal/Lambda Durable Functions job):**
- Crash recovery and durable state persistence across process restarts
- Long-wait human-in-the-loop pauses (approval gates, review steps)
- Distributed coordination across executor replicas
- Retry policies scoped to infrastructure failures (not LLM errors)

**Practical implementation (LangGraph + Temporal example):**

```
Request → API Gateway → Stateless LangGraph Executor Pool
                              ↓ (async tool call)
                        Async Queue (Celery/SQS)
                              ↓ (result)
                        Temporal Workflow
                              ↓ (checkpoint + resume)
                        Postgres Checkpoint Store
```

- Use `AsyncPostgresSaver` with an `asyncpg` connection pool for checkpoint persistence. Use `durability="async"` for interactive agents (lower latency). Switch to `durability="sync"` only when the crash-window write loss is unacceptable.
- Add a Redis layer that caches the latest checkpoint pointer per thread_id for sub-millisecond recovery reads — the Postgres row is the authoritative store, Redis is the hot cache.
- Offload long-running tool calls (web searches, code execution, external API calls) to an async queue (Celery, SQS) so one slow call never blocks the executor pool. The executor resumes on result delivery.
- Implement circuit breakers at the tool-call layer: transient failures (rate limits, timeouts, network errors) get exponential backoff retries; semi-transient failures (auth rotation, schema drift) get escalation to human review or a fallback branch.

**On choosing orchestration patterns:**

| Pattern | Best for | Trade-off |
|---------|----------|-----------|
| DAG (LangGraph StateGraph) | Deterministic multi-step flows with conditional routing | Explicit, inspectable, but edges must be pre-defined |
| Event-driven (Kafka + A2A + MCP) | Loose coupling, many independent agents reacting to shared state | Harder to trace end-to-end, eventual consistency complexity |
| Actor model (AutoGen) | Complex multi-agent negotiation and delegation | Higher cognitive overhead, harder to debug |

The dominant production pattern in 2025–2026 is **hybrid**: DAG for the happy path, event-driven for cross-agent communication, and Temporal for durability guarantees the agent loop cannot provide itself.

## Evidence

- **HN Discussion (June 2025, 543 points):** Anthropic's "Building Effective Agents" post sparked the most-discussed agent thread of 2025. Commenter simonw called it "the most practical piece of writing I've seen on the subject of agents," but multiple practitioners pointed out that "agents increase degrees of freedom exponentially, making it harder to guarantee correct behavior." The consensus: start with predefined workflows, add agents only when dynamism is genuinely needed. — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)

- **AWS Builder Center (June 2026):** "From Agent Loop to Durable Execution" explicitly maps the three-layer stack — agent loop, agent framework, orchestration engine — and provides five production scenarios where Temporal's infrastructure layer solves problems LangGraph alone cannot. Key quote: "It manages sequencing, retry on failure, and the human-in-the-loop wait between steps." — [https://builder.aws.com/content/3FFJUX44Z2uzDxEYdmu7XEwTmS4/from-agent-loop-to-durable-execution-an-architecture-guide-for-production-agents](https://builder.aws.com/content/3FFJUX44Z2uzDxEYdmu7XEwTmS4/from-agent-loop-to-durable-execution-an-architecture-guide-for-production-agents)

- **Zylos Research (April 2026):** Analysis of 2025 production agent failures identifies three dominant failure categories: deadlocks (unmanaged parallel tool calls), state corruption (in-memory state lost on crash), and silent failures (auth expiry producing wrong outputs without raising errors). The three architectural schools — DAG, event-driven, actor model — each address different subsets of these failures. — [https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Conflating the framework with the infrastructure.** LangGraph persists state through a checkpointer interface, but the default in-memory checkpointer is a prototype artifact, not a production component. If your executor has more than one replica or must survive process restarts, you need a durable checkpointer from day one, not as a later upgrade.
- **Treating all failures as retryable.** Transient failures (rate limits, timeouts) warrant exponential backoff. Semi-transient failures (auth token rotation, schema drift, 4xx API errors) will retry forever with the same parameters. Distinguish failure types and route each to the appropriate handler.
- **Over-designing the agent layer before measuring.** LangGraph StateGraph, Temporal, Kafka, and a custom actor model can all coexist — but layering all three before you have production traces means you're optimizing for an architecture diagram, not user outcomes. Start with a single LLM call, add a defined workflow, add an agent only when dynamism is the actual requirement.
- **Missing observability at the execution-trace level.** LangSmith was processing traces from 400+ companies in production by late 2025. Without structured traces — every tool call, every decision, every branch — you cannot diagnose the 12–18% tool call failure rate or replay the 47-tool-call runaway that cost $34.
