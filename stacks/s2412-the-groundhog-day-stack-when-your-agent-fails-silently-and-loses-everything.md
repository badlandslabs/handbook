# S-2412 · The Groundhog Day Stack — When Your Agent Fails Silently and Loses Everything

Your agent ran for 20 minutes, consumed $200 in API tokens, and produced nothing useful — then crashed with no trace of what it was doing. Or it ran correctly until a network blip, and the entire workflow restarted from scratch. Or it took an irreversible action before the human-in-the-loop safeguard could fire. The problem isn't the model. It's that the system around it has no memory of its own past states, no recovery path when things go wrong, and no way to replay what happened. This stack is about building that memory: checkpointing, rollback, and failure recovery for production agents.

## Forces

- **State lives in two places and you control neither.** Agent frameworks track chat history; the OS tracks files and processes. The gap between them is where your agent's work disappears on crash. Chat-level recovery (LangGraph checkpoints, ConversationBufferMemory) misses OS-side effects like spawned processes, modified files, and installed packages. Full OS-level checkpointing (Docker snapshots, E2B sandboxes) is correct but 3.7× slower.
- **Checkpointing everything is worse than checkpointing nothing.** Per-turn full checkpointing slows execution up to 3.7× under co-location. But skipping checkpoints means every failure is a total restart. The right point to checkpoint is non-obvious: not every turn, only at decision points and after side-effectful operations.
- **Retry logic that retries everything destroys everything.** Retrying a non-idempotent tool call (a payment, a DB write, an email send) on timeout produces a double-charge, not a recovery. Distinguishing tool types is required before any retry policy makes sense.
- **Failures cascade faster than they recover.** In multi-agent systems, a single failure in one agent propagates downstream without corrective mechanisms. A simple tail-end retry is insufficient — the agent may have already deviated significantly from its intended path. 37% of multi-agent failures are coordination breakdowns, not model failures.
- **Silence is the worst failure mode.** A looping agent consuming tokens looks identical to a working agent from outside. By the time you notice, you've lost both time and money. The first sign of failure is often a billing alert, not a log.

## The Move

Layer three distinct recovery mechanisms, each handling a different failure surface:

**1. Idempotent tool classification before anything else.**
Sort every tool into three buckets before writing a single retry decorator:

- **PURE** — safe to retry indefinitely: search, read, compute, hash
- **SIDE_EFFECT** — retry only after checking prior state: write, send, update, delete
- **NON_DETERMINISTIC** — never retry: random, timestamp, external API with no idempotency key

Wrap side-effectful tools with a guard that checks whether the operation already succeeded (e.g., query the DB before re-inserting). Only then apply retry logic with exponential backoff.

**2. Semantic checkpointing at decision boundaries.**
Checkpoint at three moments, not every turn:

- Before any tool call with external side effects (write, send, execute)
- After receiving a tool result that changes the agent's belief state (new info arrived)
- On explicit human handoff boundaries

Over 75% of agent turns produce no recovery-relevant state — checkpointing those turns is pure overhead. The HKUST Crab system found that selective semantic checkpointing achieves 100% recovery correctness on code-repair workloads versus 8–13% for chat-only recovery.

**3. Structured rollback with state reducers.**
When a step fails after N successful steps, the agent's state must roll back to the last checkpoint, not restart from zero. Use LangGraph's checkpoint/checkpoint persistence with a configurable memory backend:

- **MemorySaver** (in-memory): dev only, fast iteration
- **SqliteSaver** (SQLite): single-instance production, low traffic
- **PostgresSaver** (PostgreSQL): multi-instance, high throughput

Attach a state reducer that undoes the last action's effect on the shared state dict. If step 4 of 7 fails, roll back to the step 3 snapshot, inject a retry flag, and re-enter the decision loop.

**4. Dead letter queue for unrecoverable failures.**
After N retries on the same step, route the task to a DLQ — not a crash. A DLQ entry captures: full checkpoint state, error type, retry count, and timestamp. A human or supervisor agent picks it up. One team using this pattern reduced human intervention from 8.7% to 1.2% of runs.

**5. Heartbeat monitoring with token budget gates.**
Set a maximum token budget per task. Monitor cumulative token spend as a first-class signal, not an afterthought. If spend exceeds the budget gate before completion, pause and surface to monitoring — don't keep looping silently.

## Evidence

- **Company engineering post (Temporal):** The 2025 Production AI Stack Report documents seven core failure modes for production agents: interrupted API calls with no recovery path, silent loops consuming budget, state loss on service restart, error cascades in multi-agent pipelines, and more. OpenAI's Codex team uses Temporal's durable execution model to handle long-running agent workflows in production. Temporal raised $300M Series D (led by a16z) in 2025 specifically to fund durable execution infrastructure for agentic AI. — [https://temporal.io/pages/ai-production-stack-report](https://temporal.io/pages/ai-production-stack-report)
- **Engineering blog (GetATeam, Nov 2025):** After deploying hundreds of agents in production, documented that 90% fail. By implementing exponential backoff, dead letter queues, comprehensive monitoring with actionable alerts, and graceful degradation strategies, one team improved uptime from 94.2% to 99.7%, reduced MTTR from 23 minutes to 2 minutes, and dropped human intervention from 8.7% to 1.2% of runs. — [https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it)
- **Research paper (HKUST, arXiv 2026):** Crab — a semantics-aware checkpoint/restore runtime — demonstrates that chat-only recovery succeeds on only 8–13% of Terminal-Bench code-repair tasks. Their system achieves 100% recovery correctness on the same workload by bridging the agent–OS semantic gap, while reducing checkpoint traffic by 87% versus full per-turn approaches. 75%+ of agent turns produce no recovery-relevant state. — [https://arxiv.org/html/2604.28138v1](https://arxiv.org/html/2604.28138v1)
- **Engineering guide (markaicode, Mar 2026):** LangGraph production guide — Pydantic BaseModel for typed state management, per-step error recovery with try/catch around node execution, checkpoint persistence with configurable backends, and LangSmith tracing for debugging failures after the fact. The guide opens with: "Your LangGraph agent works perfectly in testing. In production it loops silently for 20 minutes, consuming $200 in API calls before you notice." — [https://markaicode.com/langgraph-production-agent](https://markaicode.com/langgraph-production-agent)
- **GitHub repo (agentckpt, 2026):** Open-source checkpoint-recovery middleware providing git-style content-addressable state snapshots with branching and rollback, idempotent tool wrappers by type (PURE/SIDE_EFFECT/NON_DETERMINISTIC), and branch-and-merge execution for best-of-N recovery strategies. Framework-agnostic, works with any async agent pipeline. — [https://github.com/isaacuselman/agentckpt](https://github.com/isaacuselman/agentckpt)

## Gotchas

- **Chat-level recovery misses OS state.** LangGraph checkpoints save the state dict and message history. If your agent ran `pip install` or modified a file, those effects are gone on restore. If you're in a sandboxed environment, use Crab-style semantics-aware C/R that tracks OS-level side effects alongside tool calls.
- **Idempotent retry without classification is a data corruption risk.** A payment tool that charges on call will double-charge on retry. Classify tools first; the retry policy follows from the classification, not the other way around.
- **DLQs that nobody reads are not failure handling.** A dead letter queue that gets written to but never picked up is just a more expensive crash. Treat DLQ depth as a first-class SLA metric — alert when it grows.
- **Circuit breakers without fallback paths cascade anyway.** Opening a circuit breaker (stop calling the degraded service) only helps if the calling agent has a defined fallback: use cached data, degrade gracefully, or escalate to human. Without a fallback, the circuit breaker just changes the error type.
- **Checkpoint granularity is a throughput vs. correctness tradeoff.** SQLite checkpointing is simpler and correct but doesn't scale to thousands of concurrent threads. PostgreSQL checkpointing handles scale but adds latency per checkpoint. Model this before production, not after.
