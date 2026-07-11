# S-944 · The Idempotency Gate Stack — When Your Agent Retries a Write and Something Happens Twice

Your agent charges a customer $847. The Stripe API times out. Your retry logic fires. The second charge goes through too. Two charges, one order, one furious customer, and a $1,694 bill the finance team will spend a week untangling. The demo worked fine. The prompt was good. The model was fine. The failure was entirely in the retry logic — or rather, the absence of it. Agents don't just return wrong answers. They double-send emails, double-create tickets, and double-execute writes in ways that traditional error handling completely misses.

## Forces

- **LLMs are nondeterministic, but the side effects they trigger need to be deterministic.** The model's output varies across calls. The Stripe charge, the Slack message, the database write — these must not vary. This is the core tension of agent reliability.
- **Standard retry logic is dangerous for agents.** A traditional API retry on `500` is safe. An agent retry during a 6-step workflow where steps 1-3 already completed is not — retrying from step 3 sends emails that step 3 already sent.
- **Agents fail silently, including during retries.** A tool call can return `200 OK` while semantically failing — wrong data shape, wrong recipient, wrong amount. The retry fires, the second attempt also "succeeds," and nobody finds out until the customer emails.
- **86% of agent failures are recoverable (Operator Collective, March 2026) but retries without idempotency turn recoverable failures into data integrity incidents.**
- **The three retry layers — transport, tool, model — have completely different safety requirements.** Treating them the same way is how teams get the idempotency bug in the first place.

## The Move

The fix is not "add more retries." It is a layered idempotency architecture that makes every action in the agent's workflow safe to repeat.

**1. Key everything before execution, not after.**
Generate idempotency keys *before* the LLM decides what to do, not after. Keys must derive from inputs that don't change on retry: user ID, intent hash, workflow run ID, step index. If you key after execution, you can't use the key to check whether the first call already succeeded.

```
idempotency_key = hash(user_id + intent + run_id + step_index)
```

Stripe's idempotency pattern sets the bar — pass the key on the first request, pass it again on every retry. The API returns the cached response for duplicates.

**2. Instrument semantic validation, not just HTTP status.**
HTTP 200 from a tool call means the network call succeeded. It says nothing about whether the output is correct. Validate the *shape and meaning* of tool responses before acting on them:

```
if tool_result["status"] == "success":
    if not is_valid_amount(tool_result["amount"], expected_range):
        raise SemanticValidationError(f"Amount {tool_result['amount']} outside expected range")
    if not is_known_customer(tool_result["customer_id"]):
        raise SemanticValidationError(f"Unknown customer ID returned")
```

This catches the failure mode where the API returns valid JSON that is the wrong answer.

**3. Decouple the retry from the workflow state.**
Store workflow state in durable storage (database, Redis) *before* each step executes. On retry, the agent fetches the last known state and resumes from the last committed step — not by re-executing from the beginning. This is the difference between "retry the workflow" and "resume the workflow."

**4. Route failures to a dead letter queue, not a loop.**
When a step fails after max retries, don't retry infinitely and don't crash silently. Write the failed task to a DLQ with full context: what was attempted, what failed, the full tool response, and the retry history. A human reviews and resolves. The agent continues processing other tasks.

```
FailedTool(task_id=..., step=3, attempt=3,
           error="rate_limit_exceeded",
           context={"user_id": ..., "intent": ...},
           retry_history=[...]) → DLQ
```

**5. Use circuit breakers to stop retrying downstream failures.**
When a tool or API is clearly down (not transient), a retry loop burns tokens and worsens the downstream situation. Circuit breakers track failure rates and open after a threshold — subsequent calls fail fast instead of queuing up. Three states: CLOSED (normal), OPEN (fail fast), HALF-OPEN (test recovery).

```
circuit_breaker.call(lambda: stripe.charge(...))
# After 5 failures in 10s → OPEN
# After 30s in OPEN → HALF-OPEN (test one call)
# If test succeeds → CLOSED
```

**6. Set per-step and per-workflow retry budgets.**
Don't let retries compound. A 6-step workflow where each step retries 3 times with exponential backoff can turn a 30-second operation into a 20-minute zombie. Cap total workflow retry attempts and per-step budgets. When the budget is exhausted, route to DLQ.

## Evidence

- **Technical blog (Gravity Fast):** "AI Agent Fallback and Retry: A 2026 Playbook" documents the three-layer retry architecture (transport, tool, model) with safe defaults: 100ms base delay, 30s cap, ±25% jitter, 3 max retries, 10% QPS retry budget. Notes these match AWS client SDK defaults and Stripe's idempotency pattern. — https://gravity.fast/blog/ai-agent-fallback-and-retry
- **Technical blog (I Am Stackwell):** "How to Make AI Agents Idempotent" describes the core failure: agents retry mid-workflow without checking whether prior steps already completed, leading to double charges and duplicate emails. Emphasizes pre-execution key generation and durable state storage as the two required patterns. — https://iamstackwell.com/posts/how-to-make-ai-agents-idempotent
- **Technical blog (BuildMVPFast):** "Idempotent AI Agents: Retry-Safe Patterns for Production Workflows" documents the "LLMs are nondeterministic but their side effects need to be deterministic" problem, with concrete patterns for idempotency key generation from run IDs and intent hashes, and checkpoint-based workflow state. — https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026

## Gotchas

- **Don't retry write operations without idempotency keys.** This is the cardinal rule. A GET retry is safe; a POST charge without a key is a double charge. If the external API doesn't support idempotency keys, wrap it with your own deduplication layer that checks whether the operation already succeeded before executing.
- **Exponential backoff without jitter causes thundering herd.** If 50 agents all retry at the same interval, they all hit the API simultaneously after the backoff. Always add jitter — ±25% full jitter is the recommended default.
- **Semantic validation catches what HTTP status codes miss.** An API returning `200 OK` with `"amount": -5000` is a failure that retry logic won't catch. Define expected value ranges and data shapes *before* the workflow runs.
- **Don't retry on "bad input" failures.** A 400 response or content policy violation won't resolve with backoff. Route these to a DLQ or return an error to the user — retrying only burns tokens.
- **State must be durable, not in-memory.** If you checkpoint workflow state in a Python dict and the process restarts, you're back to square one. Use a database, Redis, or a WAL — something that survives process death.
