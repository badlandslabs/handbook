# S-1493 · The Recovery Ownership Stack — When an Agent Fails But Nobody Knows Who Retries

You have a multi-agent system. Agent C calls a tool, it fails. Does Agent C retry? Does Agent B (which delegated to C) retry? Does the system escalate to a human? Nobody wrote this down, so it depends on which exception propagates first. Your production agent silently fails at 3 AM and stays failed until someone notices.

This is the Recovery Ownership problem: in multi-agent systems, failure recovery is non-deterministic by default. Without an explicit convention about who owns retry, failures cascade unpredictably or die silently. The fix is a single architectural convention — parent-owns-child-retry — plus the error classification taxonomy to make it enforceable.

## Forces

- **Agents fail non-deterministically.** Unlike APIs, agent failures span both code errors (network timeouts, rate limits) and semantic errors (LLM outputs wrong format, hallucinates a tool that doesn't exist). A single try-catch doesn't cover both.
- **Delegation chains make ownership ambiguous.** If Agent C fails and was delegated by Agent B which was delegated by Agent A, the retry question becomes: who decides, who acts, and who pays the token budget?
- **Retrying without side-effect awareness causes duplicate execution.** An agent that retries a file-write or API call without checkpointing will execute it twice — or N times if retries compound.
- **The demo-to-production reliability gap.** Agents hit 90% success in demos. Business requirements demand 99.9%. The missing 9.1% is where ownership conventions live.
- **The "retry everything" instinct is wrong.** Not all errors are retryable. Retrying an auth failure or invalid input wastes budget and can mask the real problem.

## The move

Adopt the parent-owns-child-retry convention and an error classification taxonomy. Every agent failure maps to one of four types, and each type has a deterministic recovery path.

**1. Classify errors by type before choosing recovery.**

| Error Type | Examples | Recovery |
|---|---|---|
| `transient` | Network timeout, rate limit (429, 500) | Exponential backoff + retry (parent-owned) |
| `budget` | Token/cost ceiling hit mid-task | `budget-paused` terminal state — notify orchestrator, await top-up |
| `capability` | Agent requests an unavailable tool | Escalate to parent agent for capability routing |
| `semantic` | LLM output fails schema validation, wrong format | Retry in next turn with explicit correction prompt |

**2. Parent-owns-child-retry convention.** The immediate parent always owns retry of its direct children. Propagate `failed` upward only when the parent exhausts its own retry budget. This prevents both the "everyone retries" cascade and the "nobody retries" silence.

**3. Checkpoint before side effects.** Record a checkpoint before executing any action with side effects (file writes, API calls, database mutations). On retry, check `was this already done?` using an idempotency key before re-executing. This converts "retries cause duplicate operations" into "retries are safe."

**4. Three-tier retry budget.** Configure per-agent: max retries (typically 2–3), backoff strategy (exponential with jitter), and escalation trigger (e.g., after 2 retries of `semantic` error, escalate to human review).

**5. Dead letter queue for unresolvable failures.** Tasks that exhaust all retry budgets go to a DLQ with full trace context — conversation history, tool call log, error classification, and checkpoint state. Enables human review without starting from scratch.

**6. Signed audit receipts at agent boundaries.** Every handoff logs: task, context received, output produced. Tamper-evident boundaries make post-mortem analysis possible instead of reconstructing state from LLM-generated logs.

## Evidence

- **GitHub Discussion (Anthropic SDK):** Production practitioners sharing multi-agent error recovery patterns — documented the parent-owns-child-retry convention and `budget-paused` terminal state as a custom A2A protocol extension when standard states (`failed`, `canceled`, `completed`) proved insufficient — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **iBuidl.org (2026):** Catalogued 6 production failure patterns including missing rollback mechanisms and tool call infinite loops — found circuit breakers and idempotency keys as the concrete fix; recommends building agents "like distributed systems engineers build services" — [ibuidl.org/blog/ai-agent-production-failure-patterns-20260316](https://ibuidl.org/blog/ai-agent-production-failure-patterns-20260316)
- **OpenHelm Benchmark (2024):** Measured error handling improving agent reliability from 87% to 99.2% (14× fewer failures) through retry with exponential backoff, circuit breakers, and fallback mechanisms — [openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **GitHub (ombharatiya/ai-system-design-guide):** Open-source AI system design curriculum documenting the shift from try-catch to agentic self-correction and stateful rollbacks, with LangGraph and Microsoft Agent Framework providing native checkpoint/resume primitives — [github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Show HN (agent-triage):** Tool for diagnosing agent failures from production traces by extracting behavioral rules from system prompts, replaying conversation step-by-step with LLM-as-judge, and pinpointing exactly which turn broke — [news.ycombinator.com/item?id=47334775](https://news.ycombinator.com/item?id=47334775)

## Gotchas

- **Don't retry all errors.** Retrying auth failures, invalid input, or capability errors wastes budget and can mask the real problem. Classify first, retry only `transient` and (sometimes) `semantic` errors.
- **Don't skip checkpointing for read operations.** Even "safe" reads can fail mid-stream and leave the agent with partial context. Checkpoint state, not just outputs.
- **Don't let retry budgets be per-agent-instances.** If you spawn 10 instances of the same agent, each gets the same retry budget independently — which may be correct or may exhaust your API quota faster than expected. Track budgets at the orchestrator level.
- **Budget failures are silent by default.** Without a `budget-paused` state and alerting, agents that hit token ceilings mid-task report success with truncated output. The result looks fine; the task isn't.
