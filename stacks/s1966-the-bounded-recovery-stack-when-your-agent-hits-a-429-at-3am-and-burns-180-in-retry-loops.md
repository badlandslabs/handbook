# S-1966 · The Bounded Recovery Stack — When Your Agent Hits a 429 at 3AM and Burns $180 in Retry Loops

Your agent worked perfectly in development. You shipped it to production on a Friday afternoon. By Saturday morning, you had a $1,200 API bill from a single failed workflow that retried 47 times with no backoff, a customer support ticket from a user who got the same email sent 6 times, and zero visibility into what went wrong. Your agent was "working" — it never errored out. It just kept failing silently and retrying badly. This is the bounded recovery problem: not how to prevent agents from failing, but how to make them fail *boundedly*.

## Forces

- **A 10-step workflow at 90% per-step reliability only succeeds cleanly 35% of the time** — at 95% per-step it jumps to ~60%, but still means 4 in 10 runs need recovery. Most teams only test the happy path.
- **Traditional error handling assumes retry is safe** — agents break this: blind retries on a tool that already fired (send email, charge card, create ticket) cause real side effects. A retry is not automatically idempotent.
- **200 OK doesn't guarantee correctness** — agents can return structurally valid responses that are semantically wrong, and no exception is thrown.
- **Production agents need layered recovery** — a single error handling strategy (all retries or all fail-fast) is wrong for different failure types. Rate limits need different treatment than schema violations.
- **Context carries state across failures** — if agent completes steps 1–4 then fails, a naive retry wastes tokens re-sending full history *and* may re-fire side effects from steps already executed.

## The move

A layered, type-aware recovery architecture. Five tiers that activate in order:

1. **Hard step cap** — the most important guardrail. Set `MAX_STEPS = 12` (LangGraph: `recursion_limit=12`). If the agent doesn't finish, stop, document the trace, escalate. A 12-step agent that loops forever costs less than a free-running one.
2. **Typed error routing** — route errors by category before deciding recovery:
   - **Transient** (429, 503, timeout): retry with exponential backoff + jitter
   - **Semantic** (malformed JSON, wrong tool params, schema violations): re-prompt with corrective context, don't just retry the same call
   - **Resource** (token budget exceeded, context overflow): compact context (summarize history, drop older results), not a retry
   - **Fatal** (auth failure, revoked key, content policy rejection): escalate immediately, do not retry
3. **Exponential backoff with jitter** — `1s → 2s → 4s → 8s → 16s` with random jitter. AWS research shows this reduces retry storms by 60–80% vs. fixed-delay. Use 3–5 retries for most operations, 5–7 for rate limits specifically.
4. **Circuit breaker** — after N consecutive failures (e.g., 5), stop calling the failing service for a cooldown window (e.g., 60s). Prevents cascading failures from a downstream outage. Track at the *tool* level, not the agent level.
5. **Idempotency guards + checkpoint/resume** — before firing a tool with side effects (email, payment, write), generate an idempotency key. Store checkpoints (agent state, step completed, intermediate results) in Redis or a database — not in-memory, since container orchestrators can kill/restart processes. On recovery, resume from last checkpoint without re-executing completed steps.
6. **Escalation queue** — when all automated recovery is exhausted, surface to a human. For compliance-critical operations (finance, healthcare, legal), escalate *before* max retries. Define explicitly which capabilities can gracefully degrade and which must work correctly or not at all.

## Evidence

- **LangGraph fault tolerance docs (June 2026):** First-class `RetryPolicy`, `TimeoutPolicy`, and `error_handler` primitives attach directly to nodes via `add_node`. `RetryPolicy` supports `initial_interval`, `backoff_factor=2.0`, `max_interval=128.0`, `jitter=True`, and `retry_on` as a tuple or callable. `error_handler` receives the exception and current state — lets you log, patch, or route to a recovery subgraph. — [LangChain Blog](https://www.langchain.com/blog/fault-tolerance-in-langgraph)
- **LangGraph ML+ guide (2026):** 10-step workflow at 90% per-step reliability succeeds only ~35% of the time. Empirically validates that bad output snowballs: if node A produces garbage, node B amplifies it. Three error handling patterns: retry decorators, fallback chains, and checkpoint/resume — all composable via a unified `ResilientAgent` class. Checkpoints stored externally (Redis) survive process restarts. — [machinelearningplus.com](https://machinelearningplus.com/gen-ai/langgraph-error-handling-retries-fallback-strategies/)
- **Real-world case — Asynq.ai candidate evaluation agent:** Worked flawlessly in development. In production it hallucinated tool parameters, got stuck in loops, contradicted its own reasoning mid-run, and cost 3× budget. Recovery required: sandboxing + dry-run before real tool calls, capability-based permissions, and confidence checks. — [Harsh Rastogi / Modelia.ai](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Real-world case — Modelia.ai image generation pipeline:** Agent approved obviously flawed images because it optimized for workflow completion over quality. Fix: validation gate after every generation step — model must pass its own output against a quality rubric before proceeding. — [Harsh Rastogi / Modelia.ai](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Production metric — OpenHelm benchmark (July 2024, still referenced in 2025–2026):** Proper layered error handling increased agent reliability from 87% to 99.2% — a 14× reduction in failure rate. Combined with circuit breakers: production agents with layered retry + circuit breakers + checkpointing achieved 97.8% autonomous recovery rate. — [OpenHelm Blog](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Google Cloud / Vertex AI case:** A document analysis agent processing 1,000+ page regulatory filings faced complete restart after Cloud Run timeouts at 58 minutes — no checkpoint system. Fix: systematic checkpointing of agent state (memory, conversation history, task queue, progress markers, intermediate results) to an external store. — [Brandon Lincoln Hendricks](https://brandonlincolnhendricks.com/research/implementing-agent-checkpointing-recovery-patterns-long-running-ai-tasks)

## Gotchas

- **Naive retry wastes tokens and re-fires side effects** — if step 3 already sent a Slack message, retrying step 3 sends it again. Checkpoint what succeeded before retrying.
- **Jitter is not optional** — without jitter, multiple concurrent agent instances retry at exactly the same time, creating a thundering herd that keeps hitting the rate limit. Always add random jitter.
- **Don't retry fatal errors** — auth failures, revoked keys, content policy rejections will fail the same way every time. Retrying burns money and compounds the problem. Detect these and escalate immediately.
- **Graceful degradation is not universal** — a degraded lower-quality response is acceptable for a customer support agent (still resolves ~70% of queries). It is not acceptable for a medical diagnosis, financial trading, or legal review agent. Define per-capability whether graceful degradation is a feature or a hazard.
- **Context compaction is not a retry** — if the error is "context window exceeded," retrying the same prompt will fail the same way. You must compact context first (summarize history, trim results), then retry with a smaller payload.
- **Step cap alone is insufficient** — without observability into *why* the agent hit the cap, a step limit just hides the failure. Log the full trajectory on every stop/escalation so you can diagnose whether it was a loop, a dead end, or a genuinely complex task.
