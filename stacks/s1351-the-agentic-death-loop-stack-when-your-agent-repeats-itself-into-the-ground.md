# S-1351 · The Agentic Death Loop Stack

When your agent hits a failure, retries, hits the same failure, retries differently, makes a new error trying to fix the old one — and loops until it burns through tokens, time, and money without ever finishing. Every team that skips bounded execution discovers this the hard way in production.

## Forces

- **LLMs don't know when to stop** — unlike traditional code that throws an exception and crashes, an agent treats a repeated failure as a new problem to solve, not a signal to quit
- **Tool failures masquerade as retry opportunities** — a "no results found" search or a 503 API response looks like transient noise to a model, not a dead end
- **Production surfaces edge cases demos never showed** — agentic loops that look fine with 5 test cases explode when users hit the long tail
- **Cost spirals faster than you'd expect** — a single looping agent at $0.50/token can rack up hundreds of dollars in minutes with no user-facing value
- **Retries without idempotency are dangerous** — retrying a non-idempotent action (like sending an email or charging a card) multiplies the damage

## The Move

Design every agent loop with **bounded execution, layered recovery, and explicit escalation** from the start.

- **Hard step cap first.** Set `MAX_STEPS` (typically 10–15 for single agents, 20–30 for complex workflows) and stop unconditionally when reached. LangGraph: use `recursion_limit`. This is the single most effective guardrail — without it, you have no ceiling on cost or latency. (Source: Manvendra Rajpoot, "LLM Agent Error Recovery in 2026", blog.rajpoot.dev, May 2026)

- **Per-call retry contracts, not a blanket wrapper.** Every LLM call and every tool call gets its own retry contract: exception classes, max attempts, and backoff strategy defined at the call site. A 503 from a search API warrants 2 retries with exponential backoff; a malformed JSON response from an LLM warrants 1 retry; a timeout from a code execution tool warrants 0 retries and immediate fallback. Wrapping the entire agent in a single try/except is how teams miss what actually broke. (Source: bestaiweb.ai, "Agent Error Handling and Recovery", bestaiweb.ai, 2026)

- **Distinguish error types and route accordingly.** Tool failures fall into distinct categories: transient (retry), permanent (fallback or skip), and ambiguous (human escalation). Use structured error responses from tools so the agent can route correctly. Don't let the agent infer error severity from text — it will assume "try again" is always right. (Source: Harsh Rastogi, "Agentic AI in Production", harshrastogi.tech, March 2026)

- **Idempotency is a prerequisite for safe retries.** Before retrying any stateful action, generate or check an idempotency key. A retry is only as safe as its idempotency key. Actions like writes, emails, API posts, and DB inserts must be idempotent before retry is safe. (Source: bestaiweb.ai, "Agent Error Handling and Recovery")

- **Circuit breakers after 2–3 consecutive failures.** If the same tool fails 3 times in a row, stop calling it and route to a fallback — different tool, simpler response, or graceful degradation. This prevents the "agent keeps trying the same broken tool" death spiral. (Source: Open Empower, "AI Agent Production Failures", openempower.com, June 2026)

- **Cost circuit breakers.** Track cumulative spend per task. If cost exceeds a threshold (e.g., $2 for a single email reply task), halt and surface the overage. Agents burn money faster than engineers expect because multi-turn loops multiply token counts. (Source: Manvendra Rajpoot)

- **Checkpoint state for mid-flight recovery.** Save agent state (conversation history, tool results, intermediate outputs) at defined milestones. If the agent crashes mid-task, restart from the last checkpoint instead of re-running the entire workflow. (Source: Harsh Rastogi)

- **Escalation path, not just stop.** When MAX_STEPS is hit, don't just return an error. Provide the accumulated context, what the agent tried, and what it was trying to accomplish — so a human or supervisor agent can resume. Build a clean handoff, not a wall.

## Evidence

- **Production case study:** At Asynq.ai and Modelia.ai, a candidate evaluation agent worked flawlessly in development. In production it hallucinated tool parameters, got stuck in loops, occasionally produced evaluations that contradicted its own reasoning, and cost 3× the budget. Root causes: no input validation, no step cap, no cost tracking. Fix: per-call validation + MAX_STEPS + cost circuit breaker brought costs back to budget within a week. — Harsh Rastogi, AI Product Engineer, harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns, March 2026

- **Benchmark evidence:** Across GitHub issue-solving agent benchmarks, average trajectories ran 48.4K tokens over 40 steps, with tool messages alone accounting for 30.4K. Without step caps, a single difficult task can grow to consume the equivalent of an entire conversation's worth of tokens in one agent run. — Redis blog, "Agentic AI Architecture Patterns", redis.io/blog/agentic-ai-architecture-examples, 2025

- **Enterprise pattern catalog:** 2026 enterprise deployments consistently surfaced the same five failure modes: runaway loops, tool hallucination (right tool, wrong parameters), context window exhaustion, goal drift, and cost explosion. Teams that shipped with only retries and no step cap or circuit breaker were the most severely affected. — Luca Berton, CEO Open Empower, openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026, June 2026

## Gotchas

- **The "helpful" retry loop is your worst enemy.** Agents retry failed tool calls not because it's the right strategy, but because the model interprets "call failed" as "try again with different parameters" — a pattern that compounds into a death spiral.
- **Step cap without checkpointing loses all progress.** If you cap at step 12 but the agent did useful work on steps 1–11, you need a way to resume, not restart from zero.
- **Silent failures are worse than loud ones.** An agent returning a wrong answer via a wrong reasoning path is more dangerous than one that loudly fails. Build verification layers that check output quality, not just output presence.
- **Context compression is not free.** Summarizing old conversation turns to save tokens can lose critical details. The "compact history" approach trades off context preservation for cost — test the compression ratio on real tasks, not toy examples.
- **Human escalation without context is useless.** "Agent exceeded max steps" as a Slack message helps no one. The escalation payload needs the task goal, what was attempted, what succeeded, and what the blocker was.
