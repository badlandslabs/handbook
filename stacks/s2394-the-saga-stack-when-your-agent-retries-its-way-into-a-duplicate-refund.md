# S-2394 · The Saga Stack — When Your Agent Retries Its Way Into a Duplicate Refund

Your customer-support agent correctly identifies a valid refund. It calls `process_refund` — the API returns 200, the card is charged. Network timeout. The framework sees no result. The agent retries. The refund runs again. The customer gets two credits. Your eval scores are fine. This failure isn't a model problem. It's a distributed systems problem that the AI layer imported wholesale, without the patterns that distributed systems engineers spent decades developing to handle it.

## Forces

- **Agent retries are structurally different from API retries.** An API retry replays an identical request. An agent retry replays a decision that already caused side effects. The framework sees a timeout and reasons: "I didn't get confirmation, so I should try again." The payment already went through.
- **Multi-step pipelines fail in the middle, not atomically.** 14 tool calls in sequence — each with a 1% failure rate — means ~13% of runs end partially complete (0.99^14 ≈ 0.87). One in eight runs lands in a broken state. No COMMIT. No ROLLBACK.
- **"Fix the prompt" doesn't help here.** Adding "only call the payment tool once" to the system prompt doesn't prevent retries on network blips. The failure is below the semantic layer, at the transport and state layer.
- **Compensation is not the same as recovery.** Returning a second refund to offset the duplicate isn't recovery — it's cleanup. The agent's intent was one refund. The system's behavior was two. The gap lives in the infrastructure, not the model.

## The move

Build the **Saga pattern for agents**: idempotency keys on every side-effectful tool, checkpointing at every step, and compensation actions as first-class citizens, not afterthoughts.

- **Idempotency keys on every mutation.** Every tool that writes to an external system — payments, refunds, emails, CRM updates, database writes — must accept and honor an idempotency key. The tool deduplicates on key, not on semantic comparison. If the same key arrives twice, return the original result without re-executing.
- **Checkpoint after every step.** Serialize the agent's state (current step, completed steps, results so far) to durable storage after each successful tool call. On retry, resume from the last checkpoint, not from step 1.
- **Distinguish failure classes.** Lost ACKs (timeout but effect happened) → idempotency. Duplicate deliveries → deduplication on key. Reordering → compare intent, not just keys. Crash between effect and ledger write → atomic write-ahead record. Divergent retry payload → intent comparison.
- **Compensation actions as explicit tools.** Model "undo" as a first-class capability: `cancel_refund(id)`, `recall_email(message_id)`, `close_ticket(ticket_id)`. These are not cleanup scripts — they are part of the normal tool set the agent can call.
- **Circuit breakers at the orchestration layer.** If a sub-agent fails 3 times consecutively, stop routing to it and escalate. Don't let a broken agent consume your entire retry budget while cascading failures propagate upstream.
- **Test the failure modes explicitly.** Inject lost ACKs, duplicate deliveries, reordering, and crashes into your test harness. If your pipeline isn't designed to handle them, a production incident will teach you instead.

## Evidence

- **Engineering blog (Tian Pan, tianpan.co):** "The Idempotency Problem in Agentic Tool Calling" — documents the structural mismatch between agent retry loops and side-effectful operations, with CRM agents creating duplicate tickets, inventory agents double-deducting stock, and financial agents sending duplicate refunds — [tianpan.co/blog/2026-04-19-idempotency-agentic-tool-calling-saga-deduplication](https://tianpan.co/blog/2026-04-19-idempotency-agentic-tool-calling-saga-deduplication)
- **Engineering blog (Cognilium.ai):** "Multi-Agent Reliability: Idempotency, Checkpoints, and Retries" — quantified failure math: 14 tool calls at 1% individual failure rate → ~13% of runs land partial. With idempotency + checkpoints: duplicate emails fall from 3 to 1 per recovery, tokens to recover fall from ~34K to ~4K — [cognilium.ai/blogs/multi-agent-reliability](https://cognilium.ai/blogs/multi-agent-reliability)
- **Production reliability checklist (Metacto):** Real case — customer-support agent with good eval scores and clean traces shipped to production. A transient timeout triggered the retry loop. No idempotency key on `process_refund`. Result: customer received 5 duplicate refunds. Root cause: retry logic at the infrastructure layer violated the agent's actual intent — [metacto.com/blogs/ai-agent-tool-calling-production](https://www.metacto.com/blogs/ai-agent-tool-calling-production)

## Gotchas

- **Adding idempotency keys to your API doesn't mean your agent framework passes them.** The framework must generate the key, include it in the retry, and not regenerate it on retry. Most frameworks regenerate the call entirely, losing the key context.
- **A "successful" tool call is not the same as a confirmed tool call.** The API returned 200. Did the effect actually commit? Was the ACK lost on the way back? You can't know from the caller's perspective without an idempotency key and a ledger.
- **Checkpointing adds latency.** Serializing state after every step is expensive. The failure math says it's worth it. Profile the overhead before deciding to skip it.
- **Compensation tools can fail too.** Your `cancel_refund` endpoint can itself time out. Design compensation chains that are themselves idempotent. A cancellation that timed out needs a cancellation of the cancellation.
