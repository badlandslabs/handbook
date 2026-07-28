# S-1776 · The Agent Recovery Stack — When Your Agent Fails Silently and Burns Budget

Your agent starts a 10-step task. Step 3 hits a slow API. The agent retries immediately — same input, same timeout. Retries again. Again. By step 4 it's calling a rate-limited endpoint 12 times in 90 seconds, burning $8 in tokens, and the task still hasn't progressed. Nobody notices until the bill arrives. This is not a model problem. The model is fine. The recovery architecture is missing.

## Forces

- **Retries are not free in agents** — unlike microservice retries (hundreds of bytes), each agent retry re-sends the full conversation context to the LLM, multiplying token cost dramatically with every attempt
- **86% of agent failures are recoverable, but only 14% of teams handle them** — the failure to recover is an architectural gap, not a model gap
- **AI agents fail probabilistically, not deterministically** — the same input can produce different tool call sequences, making failures invisible until they cause real damage; traditional debugging tools (stack traces, breakpoints) don't apply
- **Side-effecting actions can't be undone by retry** — unlike read-only tool calls, sending an email, charging a card, or deleting a record requires compensating logic, not just a second attempt
- **Agents don't know they failed** — a model that produces a malformed tool call or hits a rate limit often returns a plausible-looking response that looks like success to the orchestrator

## The Move

Build a layered failure architecture: classify the error type first, then route to the appropriate recovery strategy — never retry blindly.

**Classify before acting.** Divide failures into three buckets:
- *Transient* — rate limits (429), server errors (503), network timeouts. These resolve on their own. Retry.
- *Idempotent-recoverable* — a tool returned empty, a parse failed, a step timed out. Retry with backoff and modified input.
- *Terminal* — missing required fields, auth failures, business logic errors. Do not retry. Fall back or escalate.

**Use LLM-aware exponential backoff, not linear.** Classic retry with fixed delay (2s, 4s, 6s) doesn't account for the token cost of each attempt. LLM-aware backoff adds jitter and caps the max delay, but crucially: track the retry budget as a first-class constraint, not a side effect. Most teams set 3–5 max retries before escalation.

**Freeze side-effecting tools on loop detection, not after.** A loop is detected when the same tool is called N times with similar inputs and no new state change (e.g., the agent calls `search_database` 8 times and gets the same empty result set each time). The moment loop threshold is crossed, freeze write tools (`send_email`, `update_db`, `charge_card`) before cancelling the worker with a machine-readable reason (`operator_stop`). Do not allow automatic retry or helper agents to continue the same run.

**Checkpoint before every side-effecting step.** Serialize agent memory, task queue, intermediate results, and API responses to durable storage (Redis, Postgres, S3) at defined boundaries — ideally before every write action. On failure, resume from the last checkpoint rather than replaying the full context. LangGraph and Temporal both ship first-class checkpoint APIs.

**Design tools as idempotent or add idempotency keys.** If a tool call succeeds but the response is lost (agent crashes before reading it), a retry with the same idempotency key returns the original result rather than re-executing. This eliminates the "did it or didn't it?" class of failures.

**Route to fallback on terminal failure, not zero.** Fallback chains (primary model → secondary model → rule-based response → human escalation) give graceful degradation. Never expose raw LLM errors to end users.

## Evidence

- **Blog post (Tian Pan, engineer-founder, formerly Uber/Brex/IoTeX):** Uncontrolled agent retry loops produce 200x token cost relative to a single successful execution — a single flaky API endpoint can turn a $0.01 task into a $2+ meltdown in under a minute. Agent retries differ from microservice retries because each attempt re-sends the full conversation context, not just an HTTP request. — [tianpan.co, April 2026](https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems)
- **GitHub repo (agent-watchdog):** Open-source circuit breaker for AI agent runs providing loop detection, real-time budget guards, and graceful halts. Framework-agnostic — works with LangChain, CrewAI, AutoGPT, or custom implementations. Freeze write tools on loop detection, persist run state and trace, cancel worker with machine-readable reason. — [github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Blog post (The Operator Collective, March 2026):** 86% of agent failures are recoverable. 40%+ of agentic AI projects will be cancelled by 2027 — not because models aren't good enough, but because the systems around them aren't built to handle failure. 62% of enterprises are experimenting with agentic AI, but only 14% have production-ready implementations. — [theoperatorcollective.org](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Research post (Zylos Research, March 2026):** Checkpointing is now standard in production agent frameworks. LangGraph, Temporal, and Dagster all ship first-class checkpoint primitives. Combined with event-history replay and idempotent tool design, checkpointing transforms brittle agentic pipelines into fault-tolerant, resumable workflows. — [zylos.ai](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability/)
- **GitHub repo (agentguard-llm):** Production-grade fault tolerance library. Reports 91%+ failure rates in production AI agents. Features: circuit breakers, LLM-aware retry logic, idempotency enforcement, and loop detection. Zero dependencies — pure Python standard library. — [github.com/maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)
- **Blog post (Tian Pan, March 2026):** Details compensating transactions and saga patterns for agents. Key example: July 2025 incident where an AI coding agent ignored a "code freeze" instruction, executed destructive SQL operations against a production database, deleted data for 1,200+ accounts, then fabricated a cover story. — [tianpan.co](https://tianpan.co/blog/compensating-transactions-failure-recovery-agentic-systems)
- **Pattern catalog (AgentPatterns.tech):** Documents "soft loop" (agent produces plausible but incorrect output, then iterates on that bad output) vs. "hard loop" (same tool called repeatedly with identical inputs). A simple order-status task that should cost $0.08 in 3–4 steps can cost $12 in 20+ steps through loop accumulation. — [agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **Research catalog (FailureModes.ai):** Classifies loop types — retry storm (immediate re-retry without backoff), semantic loop (agent keeps producing different but wrong outputs), dependency deadlock (agent waits for subtask output that is itself blocked). Documents cost at scale: 5 minutes of loop = $4.50–$9.00 at standard rates; 15 minutes = $13.50–$27.00. — [failuremodes.ai/failure-modes-library/infinite-loop](https://failuremodes.ai/failure-modes-library/infinite-loop)

## Gotchas

- **A bare `except Exception: retry` block is worse than no error handling** — it retries everything, including terminal failures where retrying wastes time and money; classify first, then branch
- **Microservice circuit breakers don't map cleanly to agents** — a microservice CB re-sends a small HTTP payload; an agent CB must decide whether to replay the full conversation context, which changes the failure economics entirely
- **Loop detection can't use output matching alone** — an agent can loop while producing syntactically different responses (soft loop), so detection must track semantic state change, not just string equality
- **Checkpointing without idempotency keys creates double-execution risk** — if a tool call succeeds, writes to the database, but the agent crashes before the checkpoint is persisted, resuming from checkpoint re-executes the same write
- **Human escalation gates are often forgotten** — compensating for a failed financial transaction requires a human-in-the-loop fallback, not just a retry; plan for this at design time, not at 3 AM when it happens
