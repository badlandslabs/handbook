# S-1912 · The Failure-Is-Already-Happening Stack — When Your Agent Is Stuck and Nobody Knows

Your agent has been looping on the same task for 47 minutes. It's not crashing — it's running. CPU is normal. No exceptions in the logs. But it's not making progress either. It keeps calling the same tool with the same arguments, getting the same error, and trying again with a slightly different prompt that produces the same result. Meanwhile, downstream systems are waiting for a response that will never come. The fix is not a smarter agent — it is a **structured failure architecture** that detects degradation, recovers proportionally, and escalates when recovery fails.

## Forces

- Agents fail differently than traditional software: no stack trace, no crash, no obvious signal — just silent degradation (looping, drifting, or producing confident wrong answers)
- Activity-based monitoring (CPU, log volume, API call count) rises during stuck loops, so it can't distinguish stuck from working
- A 98% per-agent success rate across a 5-step chain produces only ~90% end-to-end reliability — cascades are the default, not the exception
- 86% of agent failures are recoverable, but recovery only happens if the system is designed for it
- The heaviest recovery action (human handoff) is the wrong first move for cheap failures; the cheapest action (nudge) fails for hard failures — a single strategy doesn't cover both

## The Move

Build a **bounded recovery ladder** around every agent loop, with explicit escalation gates and a dead-letter queue for what falls off the bottom. The pattern has five layers:

**Layer 1 — Checkpoint before the fall.** Before any tool call that has side effects or costs money, write the agent's current state (step count, tool history, context window snapshot) to durable storage. If the process crashes, it resumes from the checkpoint, not the top. Frameworks like LangGraph pair well with Temporal as the durability layer; CrewAI and AutoGen need external persistence bolted on.

**Layer 2 — Bounded retry with exponential backoff.** Transient failures (rate limits, timeouts, 503s) self-resolve. Retry with jitter, capped at 3–5 attempts. Do not retry semantic errors (wrong schema, hallucinated tool names) — re-prompt instead.

**Layer 3 — The recovery ladder.** When loop detection fires, climb a bounded escalation ladder:
1. **Nudge** — inject a "consider a different approach" prompt to break repeaters
2. **Replan** — ask the agent to re-state the goal and propose a new strategy
3. **Reset context** — strip recent history, restore to last checkpoint, re-inject the goal
4. **Escalate** — route to a more capable model (e.g., switch from Haiku to Sonnet for this task)
5. **Human handoff** — log the full trace, emit to DLQ, alert a human

**Layer 4 — Dead letter queue with reason codes.** Every failure that exits the recovery ladder goes to the DLQ with: (a) a reason code (transient / poison / governance / side-effect-uncertain), (b) evidence fields (last tool call, error message, context snapshot), and (c) an idempotency key so replay doesn't duplicate side effects. Replay always runs through policy evaluation again before dispatch — never replay a raw payload.

**Layer 5 — Timeout budget across the full chain.** Set an overall budget (e.g., 5 minutes) and a per-step budget. If the chain hits the overall budget, route to DLQ immediately. Cordum caps scheduling retries at ~50 (roughly 25 minutes), then emits DLQ metadata with reason codes rather than retrying indefinitely.

## Evidence

- **Research synthesis:** The recovery ladder pattern is documented at agentpatterns.ai as "stuck-loop recovery" with maturity level "adopted" (reviewed June 2026) — [Stuck-Loop Recovery | AgentPatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)
- **Engineering post:** Supergood Solutions documents the cascade math: 98% × 98% × 98% × 98% × 98% = ~90.4% for a 5-agent chain — the conclusion is that fault tolerance is not optional; it is the only way to achieve acceptable end-to-end reliability — [When Agents Fail | Supergood Solutions](https://supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026)
- **DLQ pattern:** Cordum documents the four-class failure triage (transient, poison, governance, side-effect-uncertain) with reason codes driving deterministic replay decisions, noting that replay without fresh policy checks can duplicate side effects — [AI Agent DLQ and Replay Patterns | Cordum](https://cordum.io/blog/ai-agent-dlq-replay-patterns)
- **Failure taxonomy:** Neel Mishra categorizes agent errors into transient (retry), semantic (re-prompt), unrecoverable (DLQ), and cascading (circuit breaker) — each requiring a distinct recovery strategy — [Agent Error Handling: Retries and Fallbacks | Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Engineering survey:** Cleanlab's 2025 survey of 95 engineering leaders with agents in production found < 1 in 3 teams are satisfied with observability and guardrail solutions, and 63% plan to improve evaluation and observability — confirming that failure detection and recovery infrastructure is the gap — [AI Agents in Production 2025 | Cleanlab](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Activity ≠ progress.** API call counts, log volume, and CPU rise during stuck loops too. Use a progress metric that can only increase when real work is done: failing tests resolved, unique test cases passed, tokens in a completed artifact. Activity proxies cannot distinguish stuck from converging.
- **Naive retry amplifies cost spirals.** If a loop is caused by a hallucinated tool parameter, retrying with the same prompt just burns more tokens. Re-prompt or escalate before retrying semantic errors.
- **DLQ replay without re-evaluation duplicates side effects.** If the agent already sent an email or wrote a record, replaying the full chain from a checkpoint can repeat the side effect. Always re-run policy checks before dispatching from the DLQ, and use idempotency keys to prevent duplicates.
- **No single recovery strategy works across failure types.** A nudge breaks a repeater but not a wanderer. A human handoff catches everything but is too slow and expensive for the 86% of failures that are recoverable by machine. Build the ladder, don't pick one level.
