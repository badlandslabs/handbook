# S-1285 · The Silent Failure — When Your Agent Looks Healthy but Is Stuck

Your agent is running. It returned a response. No exceptions were thrown. But the task was never actually completed — it silently looped for 35 minutes, or it took an irreversible action before a human could intervene, or it spawned subprocesses that contend for shared resources until the context window fills and it halts. Traditional software crashes with a stack trace. Agents fail creatively, and the failure modes are qualitatively different. This is the silent failure pattern, and it is the core reliability challenge of production agentic systems.

## Forces

- **Agents don't crash — they drift.** A conventional service failure is obvious. An agent keeps running, keeps producing tokens, keeps seeming active — while drifting further from the intended outcome. The absence of an exception is not evidence of success.
- **Reliability compounds poorly across steps.** A 10-step pipeline with 85% reliability per step succeeds end-to-end only ~20% of the time. Each tool call and LLM invocation is a new failure surface. Naive reliability assumptions collapse at scale. (Zylos Research, May 2026 — https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Failure taxonomy differs from traditional software.** Specification failures account for 42% of multi-agent failures, coordination breakdowns for 37%, and verification gaps for 21%. Most engineering intuition about failure handling — circuit breakers, retries, timeouts — was built for deterministic software and requires redesign for probabilistic agents. (Galileo analysis, cited in Zylos Research, May 2026)
- **Hard budget constraints are non-negotiable.** A looping agent doesn't crash — it keeps spending. Budget circuit breakers that hard-stop execution at a token or step limit are infrastructure, not optional safety. (Previous cycle findings, S-1284)
- **Production failure rate is not negligible.** AI agent systems fail approximately 12–15% of the time due to transient issues: API rate limits, network timeouts, temporary service outages, and resource constraints. Without proper recovery mechanisms, these cascade into operational disasters. (Hendricks, April 2026 — https://hendricks.ai/insights/retry-logic-exponential-backoff-ai-agent-systems)

## The move

Build layered fault tolerance that assumes failure is the normal operating condition, not an edge case.

**Retry with exponential backoff and jitter:**
- Retry only transient errors — 429s, 5xx, timeouts. Do NOT retry 401s (credential errors won't self-correct) or 400s (bad arguments won't become valid by waiting).
- Exponential backoff prevents thundering-herd on shared resources. Add jitter (±20%) to decorrelate retry timing across parallel agents.
- Cap max retries (typically 3–5) to prevent indefinite retry loops that burn budget. (Mukunda Rao Katta, DEV Community, May 2025 — https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl)

**Circuit breakers for external dependencies:**
- Track failure rates per tool or API. When failure rate exceeds a threshold (e.g., 50% in last 10 calls), open the circuit — fail fast instead of hammering a degraded service.
- After a cooldown period, move to half-open state and allow a test request through. If it succeeds, close the circuit.
- Prevents cascading failures where one degraded service brings down the entire agent pipeline.

**Output validation guards:**
- LLM outputs are non-deterministic. Wrap every tool response and LLM output in a validation layer that checks schema, type, and semantic correctness before passing it downstream.
- If validation fails, retry the LLM call with a corrected prompt — don't propagate malformed output.
- This is distinct from traditional error handling because the same prompt can produce valid JSON one time and hallucinated schema the next. (Cowork.ink, April 2026 — https://cowork.ink/blog/ai-agent-error-handling)

**Dead letter queues (DLQ) for AI agents:**
- Failed tasks — particularly those that exhausted retries or triggered circuit breakers — go to a DLQ, not a trash can.
- DLQ entries should include: full conversation history, failure reason, tool outputs at time of failure, step count, and token spend.
- Human review of DLQ entries surfaces patterns that automated retry can't fix (persistent schema drift, tool API changes, prompt injection edge cases).
- Standard retry patterns break down for generative AI because the probabilistic nature of outputs means the same error may not reproduce on retry — but it will recur in production unless the root cause is diagnosed. (Hendricks, March 2026 — https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production)

**Graceful degradation chains:**
- Define a ranked list of fallback strategies. If the primary tool fails, try the fallback. If the fallback fails, try the next.
- Example chain: Claude Sonnet 4o → Claude Sonnet 4o-mini → GPT-4o-mini → "I'm unable to complete this task, here's what I attempted."
- The degradation chain keeps the agent useful even when individual components fail, rather than failing the entire session.

**Checkpointing and state recovery:**
- Save agent state (conversation history, tool outputs, current step) at defined checkpoints. If a failure occurs mid-task, resume from the last checkpoint rather than restarting.
- Particularly valuable for long-horizon tasks (10+ steps) where the cost of restart is high.

**Watchdog timers and hard limits:**
- Autonomous watchdog that tracks step count, elapsed time, and cumulative token spend against the current task.
- If any metric exceeds a defined threshold, interrupt the agent — force a checkpoint, log the state, and halt or escalate.
- This catches the silent loop failure mode that no retry or circuit breaker addresses.

## Evidence

- **Engineering post:** Anthropic's analysis of production agent deployments found that the most successful implementations used simple, composable error-handling patterns rather than complex frameworks. They recommend building your own guardrails around each tool rather than relying on framework-level abstractions. — https://www.anthropic.com/engineering/building-effective-agents
- **Research synthesis:** Zylos Research (May 2026) documented that Galileo's analysis of production incidents found 42% of multi-agent failures stem from specification errors (the agent was told to do the wrong thing), 37% from coordination breakdowns (agents interfered with each other), and 21% from verification gaps (the agent didn't check its own work). — https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/
- **DEV Community pattern catalog:** Three Error Recovery Patterns for LLM Agent Tool Failures (Mukunda Rao Katta, May 2025) provides code-level implementations of retry, fallback, and graceful degradation — with the core insight that "tool failures are not edge cases, they are the normal operating condition." — https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl

## Gotchas

- **Retrying a 401 is a waste.** Classify errors by type before deciding to retry. Transient (429, 5xx, timeout) → retry. Permanent (401, 403, 400) → fail immediately.
- **Same-prompt retry doesn't fix non-deterministic output failures.** If a malformed JSON output came from an LLM call, re-calling with the same prompt has a significant chance of reproducing the same failure. Fix the prompt or schema first, then retry.
- **Circuit breakers must be per-resource, not global.** Opening a single global circuit breaker when one tool fails takes down the entire agent. Track per-tool failure rates independently.
- **Watchdog limits must be tighter than budget limits.** The watchdog should halt before the budget is exhausted, leaving room to log state, write to DLQ, and report the failure gracefully rather than dying silently at the token cap.
- **Human escalation is not a last resort — it's a design primitive.** Define escalation triggers explicitly: irreversible actions, spending exceeding X, step count exceeding Y, DLQ depth exceeding Z. Build escalation into the architecture, not as an afterthought.
