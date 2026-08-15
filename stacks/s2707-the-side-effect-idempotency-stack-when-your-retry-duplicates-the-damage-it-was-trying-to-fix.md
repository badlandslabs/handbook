# S-2707 · The Side-Effect Idempotency Stack

When your agent crashes mid-job, you restart it, and it emails the customer twice — because "retry it" was the wrong answer all along.

## Forces

- **Retry ≠ Recovery** — a retried step without an idempotency key doesn't fix the failure; it duplicates the side effect you were trying to fix. Sending the same email twice is a worse outcome than the transient failure that preceded it.
- **Agents don't back off** — unlike deterministic code that hits a circuit breaker and stops, a model reasons around the failure, rephrases the query, and tries again. A real AWS production incident: 12 minutes, 40 tool calls, five-figure Bedrock bill — with no alert because nothing "crashed."
- **Crash erases progress** — if nothing outside the agent remembers state, a worker failure on step 7 of 12 means steps 1–6 replay from scratch, unless a checkpoint exists.
- **Tool output is unreliable** — agents hallucinate tool parameters (right tool, fabricated IDs) and tool outputs (RAG returns hallucinated facts as if confirmed). Validating only the HTTP status of a tool call misses both.
- **Failure has a taxonomy** — tool call errors, malformed model output, and mid-flight interruption each need a different recovery mechanism, not one blanket try/except.

## The Move

Four contracts, layered — each failure domain gets its own layer:

- **Retry contract per call site** — specify exception classes, max attempts, and backoff policy *per tool or LLM call*, not a global decorator. A 429 gets exponential backoff. A malformed JSON gets 0 retries and goes straight to the validator. A timeout after a write goes to the idempotency ledger, not a blind retry.

- **Output validator** — validate the *semantic correctness* of tool and LLM output before acting on it. Schema validation catches missing fields; a small validator model or structured output check catches hallucinated facts. A validator telling the model exactly what was wrong is self-correction — a retry with a better error message.

- **Idempotency ledger** — every side-effecting step gets an idempotency key stored before execution. On replay, check the ledger first. If the key exists and the step succeeded, skip execution and return the cached result. Applies to writes, API calls, emails, PR creations, and database mutations.

- **Checkpoint / durable runtime** — checkpoint agent state after each completed step (not after each LLM call). On crash, resume from the last checkpoint. LangGraph's built-in checkpointer, Temporal activities with heartbeat checkpointing, or Inngest each serve this role. The checkpoint must include which idempotency keys are already committed, so replay knows what to skip.

The layered defense in order of cost:

1. **Retries with backoff** — transient network errors, 429s
2. **Fallback to simpler tool** — primary search fails, use a cached result or static FAQ
3. **Circuit breaker for LLM calls** — track failure rate over a rolling window; when it exceeds threshold, fail fast for a cooldown period instead of burning budget
4. **Escalation to human** — after max retries + max fallbacks exhausted, log everything and page a human with full context

## Evidence

- **GitHub: vectara/awesome-agent-failures** — community-curated taxonomy of agent failure modes including tool hallucination, response hallucination, loop traps, and context truncation. Documents the four-layer specification stack (retry contract → output validator → checkpointer → durable workflow) as the recommended mitigation pattern — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)

- **Blog: Anirudh Negi — "Retry and Recovery Patterns for Long-Running AI Agent Jobs"** — documents a production log format showing how idempotency keys and checkpointing work in practice. Shows a real job log where a GitHub 502 triggered a requeue with a 120s delay and checkpoint resume on retry — [negiadventures.github.io/blog/agent-retry-recovery.html](https://negiadventures.github.io/blog/agent-retry-recovery.html)

- **AWS Builder Center — "Circuit Breakers for Agentic AI Workflows"** — describes how traditional circuit breakers fail for agents (agents reason around failures, don't back off), documents a real incident of 40 tool calls and a five-figure bill with no crash and no alert. Proposes agent-aware circuit breakers that track failure counts at the semantic level — [builder.aws.com/content/3HHhrpuoy7JUvqVtIEkXxKvXIFa](https://builder.aws.com/content/3HHhrpuoy7JUvqVtIEkXxKvXIFa)

## Gotchas

- **Idempotency without a ledger is wishful thinking** — you must *write* the idempotency key before executing the side effect. Writing it after means a crash between the write and the API call leaves you with no record of whether the call succeeded.
- **Structured output doesn't guarantee semantic correctness** — the model can return valid JSON that says "the database has been deleted" when it hasn't. You still need a validator on the content, not just the schema.
- **A global retry decorator is worse than no retry logic** — it applies the same policy to a read-only model call and a payment API call. The former is safe to retry blindly; the latter requires an idempotency key first.
- **Checkpoint granularity matters** — checkpointing after every LLM call is too fine; a crash mid-call loses the in-progress reasoning. Checkpoint after each completed *step* (tool executed, result absorbed) balances safety against replay cost.
- **Agents can loop without crashing** — watch for agents that hit a tool's rate limit, switch to a fallback, hit *that* rate limit, switch back, and loop indefinitely. Set a hard step-count ceiling with escalation, not just error-based termination.
