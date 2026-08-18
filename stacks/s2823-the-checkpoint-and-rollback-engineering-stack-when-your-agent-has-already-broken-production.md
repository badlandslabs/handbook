# S-2823 · The Checkpoint and Rollback Engineering Stack — When Your Agent Has Already Broken Production

Your agent ran a DROP TABLE before confirming the backup existed. Your agent deleted six months of S3 logs by misidentifying a partition prefix. Your agent refactored 47 files, then lost context and produced broken code across all of them. In each case the agent completed the action successfully. The damage was real and immediate. The problem isn't a caught exception. The problem is that the side effect already happened. The fix is checkpoint-before-action and explicit rollback branches.

## Forces

- **Agent mistakes live in external state, not code.** Traditional software bugs live in code you fix and redeploy. Agent mistakes live in database rows, S3 objects, file systems, and API calls that already executed. There is no automatic transaction boundary.
- **Ambiguous failures are the norm, not the exception.** A tool call returns 200 but the side effect didn't commit. A model loses context mid-workflow. The agent loops on a wrong branch. None of these produce an exception — they produce plausible wrongness.
- **Restarting from scratch wastes all prior progress.** If your agent does 10 things correctly and fails on step 11, a full restart makes you re-pay for all 10. Checkpointing lets you resume from the last known good state instead.
- **Humans need to audit, replay, and approve mid-run.** Production agents need to survive restarts, support human approvals at gates, and let engineers replay past executions for debugging. All three require state snapshots.

## The Move

Build a checkpoint-and-rollback layer around every consequential tool call. The core practice: snapshot durable state *before* any action that modifies external systems, then design explicit recovery branches for every failure mode.

### Checkpoint mechanics

- **Snapshot before action.** Write a durable checkpoint (full agent state: messages, tool history, working memory, intermediate results) to persistent storage *before* executing any state-mutating tool call. Label it with step index and action intent.
- **Idempotent tool design.** Design tool calls so replaying them is safe. Use `WHERE id NOT IN (SELECT already_processed)` guards, conditional PUTs instead of unconditional POSTs, and optimistic locking with version checks.
- **Saga pattern for multi-step rollback.** For workflows with multiple consequential steps, model each step as a saga: record the compensating action alongside the forward action. If step N fails, execute compensating actions for steps N-1 → 1 in reverse order.
- **Distinguish verify from call.** A 200 HTTP response is not proof of a committed side effect. Call the read endpoint after write endpoints to confirm the state actually changed.
- **Constrain the unit of work.** Keep the scope of each step small enough that a failed step doesn't force rolling back the entire workflow. Large refactors, batch deletes, and schema migrations should be chunked.

### Rollback recovery branches

- **Quarantine bad state.** When a tool output is detected as invalid or unsafe, isolate the current state snapshot, mark it as suspect, and fork recovery from the last clean checkpoint rather than propagating corrupted state.
- **Explicit retry with state replay.** On retryable failures (rate limits, timeouts), replay from the checkpoint before the failed call — not from scratch and not from a mid-call position. The replay must include the original tool result so the LLM can reason about what happened without re-executing.
- **Human escalation gate.** For high-stakes actions (Destructive DDL, DELETE without WHERE, PATCH to financial records), checkpoint before the call, pause, surface the intent to a human, and resume only on explicit approval. Log the approval.
- **Dead-letter queue for ambiguous failures.** When the outcome of a call is genuinely unknowable (timeout with no response), park the request in a dead-letter queue, alert the operator, and require explicit resolution before the workflow continues.

### Observability for rollback

- **Log every checkpoint.** Store checkpoint metadata (step, timestamp, tool, actor, pre-state hash) in a queryable log separate from the agent's working memory.
- **Trail of compensating actions.** Every rollback should itself be logged as a first-class event, not silently swallowed. The audit trail is the proof that the system recovered correctly.
- **Cost and token accounting at checkpoints.** Store the cumulative cost and token count at each checkpoint. This lets you detect runaway loops by cost growth rate, not just call count.

## Evidence

- **Engineering blog:** AgentMarketCap — "Agent Checkpoint and Rollback Engineering 2026" documents concrete failure cases (agent DROPs a table before confirming backup, agent deletes 6 months of S3 logs via misidentified partition prefix, agent produces broken code across 47 files after mid-workflow context loss) and notes Gartner projects 40% of enterprise apps will include task-specific agents in 2026 — all needing answers to "how do you undo it?" — [AgentMarketCap, April 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026)
- **Engineering blog:** Subodh Jena — "Persistence and Checkpointing: Time Travel and Recovery for LLM Agents" details the four capabilities checkpoints enable (survive restarts, support mid-run human approval, enable replay debugging, continue from last successful step) and applies the database transaction principle "write durable state before consequential calls so a restart can resume from known truth instead of guessing" to agent workflows — [subodhjena.com, April 2026](https://www.subodhjena.com/blog/persistence-and-checkpointing)
- **Company engineering post:** Toucan Toco CTO David Nowinsky — "5 Lessons from Running a Multi-Agent System in Production" documents a 4-phase lifecycle (Classification → Planning → Execution → Response) and the principle that LLM-agent systems fail differently from traditional web apps: "the system may not crash; it just gives wrong answers or loops quietly" — [toucantoco.com, February 2026](https://www.toucantoco.com/en/blog/error-handling-observability-multi-agents-system)
- **GitHub:** NassimRahimi/agent-failure-recovery — demonstrates a workflow that detects unsafe output, attributes failure to the tool call that produced it, quarantines bad state, rolls back to a known-good snapshot, and validates restored state is safe — [github.com/NassimRahimi/agent-failure-recovery](https://github.com/NassimRahimi/agent-failure-recovery)

## Gotchas

- **"Successful" tool calls are not the same as correct side effects.** A DELETE returns 200 but the ORM had the wrong partition. A file write succeeds but the disk was full and it went to a temp directory. Always verify state, not just response codes.
- **Checkpointing every step is expensive.** Writing full state snapshots at every super-step adds latency and storage cost. Scope checkpoints to state-mutating actions only; informational steps don't need them.
- **Rollback to checkpoint doesn't undo third-party side effects.** If your agent called a Stripe refund API, rolling back your local state doesn't reverse the refund. Design compensating actions for external API calls and accept that some side effects are irreversible.
- **LLM context loss mid-workflow requires restart from checkpoint, not resume.** A model that loses context mid-execution cannot be resumed — it needs a fresh context populated from the last checkpoint. This is architecturally different from a simple retry.
- **Idempotency keys prevent duplicate side effects on retry, but don't help with partial execution.** If a tool call partially succeeded before timing out, replaying it with an idempotency key may produce a duplicate or a conflict, not a clean retry. You need application-level conflict detection.
