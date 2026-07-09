# S-850 · The Agent Failure Taxonomy Stack — When Silent Is Worse Than Crashing

Your agent ran all night. It returned a result. Nobody noticed it had dropped 140 records, spent $400 on retries against a rate-limited API, and arrived at an answer by hallucinating a tool that doesn't exist. Traditional try/catch shows green. The agent reports success. The data is wrong.

This is **Agent Failure Taxonomy** — agents fail in four distinct shapes that conventional error handling doesn't cover, and the silent failures cost more than the loud ones.

## Forces

- **Agents fail silently.** The output is valid JSON with no exception thrown — but the answer is wrong because a downstream tool returned garbage and the agent propagated it forward. No crash, no log, no alert.
- **Retry without idempotency is a side-effect duplicator.** Retrying a "create CRM record" step without an idempotency key creates two records on the second attempt.
- **A step cap without loop detection doesn't stop loops.** The agent keeps calling the same two tools in a circle — neither tool raises an error, the step counter never triggers, the bill climbs.
- **Self-correction is retry with a better error message.** You don't always need to re-run the same prompt. You need to tell the model exactly what went wrong.
- **Fallback paths must be defined before production, not improvised during incidents.** A two-tool fallback path is not complexity — it's the difference between graceful degradation and a cascading outage.

## The Move

**Layer the failure handling so each failure type gets its own recovery mechanism:**

- **Hard step cap + loop detection (always first).** Set `recursion_limit=12` in LangGraph. Add a loop-detection library (e.g., `agent-watchdog` or `agentcircuit`) that hashes tool-call sequences and halts if the same pattern repeats. This is your circuit breaker for the agent's own decision loop — independent of tool errors.

- **Classify errors as retryable or permanent before writing a single retry.** Only retry: timeout, rate-limit (429), 5xx server errors. Never retry: authentication failure (401), invalid input (400), malformed JSON from the model (fix the prompt instead), hallucinated tool calls (classify as permanent failure, log to audit).

- **Retries + idempotency keys are a package deal.** Every step that has side effects (write, send, update, create) must carry an idempotency key. A retry without one duplicates the side effect. The idempotency key is not a nice-to-have — it makes the retry safe.

- **Graceful degradation with a defined fallback chain.** A research agent that normally hits five tools should have a two-tool fallback that uses only a general web search and returns a partial result with a confidence flag. The fallback is not a degraded experience — it's a bounded one with explicit uncertainty.

- **Self-correction is a retry loop with validation in the middle.** After executing a tool, validate the output against an expected schema before continuing. If validation fails, pass the exact error (not a generic "something went wrong") back to the model with the original intent intact. The model re-plans from the error, not from scratch.

- **Dead-letter queue for unrecoverable steps.** Failed tasks go to a queue for human review, not into a void. The queue needs: task state, error category, retry count, timestamp. Review weekly — systematic failures reveal patterns that individual retries hide.

## Evidence

- **Deloitte 2026:** Only 11% of organizations have agents in production — and 80% of IT professionals report agents acting unexpectedly. APEX-Agents benchmark: top AI models complete fewer than 25% of real-world tasks on first attempt. — [CyberQuickly / Deloitte 2026, APEX-Agents benchmark](https://www.cyberquickly.com/2026/04/07/ai-agents-production-failure)

- **Proper error handling: 87% → 99.2% reliability.** OpenHelm documented that layered retry/backoff, circuit breakers, fallback chains, and timeout management reduced failure rate by 14× in production agent deployments. The key insight: error handling must be per-call-site, not a blanket try/except around the whole agent. — [OpenHelm Blog — Error Handling Patterns for Production AI Agents](https://www.openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)

- **Silent failure case study.** A lead-enrichment agent running in production was ghosting 30% of leads — no crash, no exception, no log. Root cause: Clearbit API rate limit (10 req/sec) exceeded by 3× production instances returning 429 silently. Fix: exponential backoff with jitter, circuit breaker that trips after 5 consecutive 429s, dead-letter queue for dropped records. — [Supergood Solutions — When Your Agent Fails Silently (April 2026)](https://supergood.solutions/blog/when-your-agent-fails-silently)

## Gotchas

- **Do not blanket-try/except the entire agent run.** A single `try: agent.run() except: fallback()` catches everything including semantic errors (wrong answer, no exception) and prevents granular recovery. Wrap each tool call and LLM call site individually.
- **A fallback that also calls the same failing tool will cascade.** Your fallback chain must be independently executable — if the failure is a rate limit, your fallback cannot share the same rate-limited resource.
- **Validation after execution is not optional.** The agent's output being structurally valid (valid JSON) does not mean it is semantically correct (the right answer). Output validation against an expected schema catches hallucinated tool results that pass as plausible-looking data.
- **Cost guards are part of failure handling.** A runaway loop is a budget failure before it's a logic failure. Set per-run token budgets and hard stops — the `agent-watchdog` library's `max_cost` guard, or equivalent, pays for itself the first time an agent finds a loop.
