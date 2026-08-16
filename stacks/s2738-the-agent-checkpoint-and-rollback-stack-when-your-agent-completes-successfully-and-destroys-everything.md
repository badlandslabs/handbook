# S-2738 · The Agent Checkpoint and Rollback Stack — When Your Agent Completes Successfully and Destroys Everything

Your agent ran `DROP TABLE` before confirming the backup existed. It misidentified the S3 partition prefix and deleted six months of production logs. It refactored 47 files autonomously, then lost context and produced broken code across all of them. In each case the agent completed the action successfully. The damage was real and immediate. Traditional software bugs live in code you can fix and redeploy. Agent mistakes live in external state mutations that already happened, and you can't version-control your production database.

## Forces

- **Agents mutate real state, not just memory.** Every tool call is a potential irreversible side effect. Unlike a code bug where you roll back and redeploy, a `DROP TABLE` that ran successfully is already done.
- **The agent's "success" signal is unreliable.** The LLM reports success; the action succeeded; but the action was the wrong action, or ran in the wrong order, or corrupted state that other agents depend on.
- **Partial progress is the dominant failure mode.** Agents complete steps 1–4 of 8 and then fail — leaving your system in an undefined intermediate state with no clean resume path. Checkpointing and idempotency are load-bearing infrastructure, not nice-to-haves.
- **Multi-agent cascades amplify irreversibility.** When one sub-agent fails mid-pipeline, the orchestrator doesn't know what to do with the others — and the system keeps running in a corrupted state until someone notices.

## The Move

Build an **undo infrastructure layer** around every agent tool call. The core move is to treat every state mutation as a candidate for checkpoint-before, rollback-capable, and to instrument failure recovery with the same rigor you apply to database transactions.

**Checkpoint before every write.** Before any mutation tool fires (DB write, file delete, API call with side effects), snapshot the current state. For databases: write-ahead log of pending changes. For S3: copy objects to a quarantine prefix before delete. For file operations: full directory snapshot or ref-copy to a staging area. The checkpoint is only useful if you can actually restore from it — test restore paths in staging, not just in theory.

**Hard step caps prevent runaway loops.** Set `MAX_STEPS` and stop execution unconditionally when reached. In LangGraph: `recursion_limit=12`. An agent that hasn't finished in 12 steps is lost — stop it, log the state, escalate. This is the single most important guardrail. Never let an agent loop indefinitely.

**Classify errors and route recovery by type.** Agent failures fall into four categories, each demanding a different response. Transient errors (HTTP 429, 503, timeouts) → retry with back-off. Semantic errors (malformed JSON, wrong tool called) → re-prompt with corrective context appended; retrying identical input never helps. Resource errors (token budget, context overflow, spending cap) → reduce payload (summarize history, drop older tool results, switch to cheaper model). Fatal errors (hard constraint, permanent quota exhausted) → abort, use fallback, notify.

**Circuit breakers for tool calls.** Track failure rates per tool or per agent. When a service is clearly down (consecutive failures exceed threshold), "open" the circuit — return fast failure for all subsequent calls without attempting the request. This prevents cascading failure where one agent's hung call blocks the entire reasoning loop. Three states: Closed (normal), Open (fail fast), Half-Open (probe recovery).

**Idempotency as a first-class constraint.** Every agent tool call must be safe to call twice. Use idempotency keys on API calls, conditional writes on databases (`UPDATE WHERE version = X`), and confirmation steps before destructive operations. A non-idempotent tool call is a production incident waiting to happen.

**Write-ahead state log for multi-agent pipelines.** Before any sub-agent receives a task, log the intended action and its preconditions to a durable queue. If the sub-agent times out, the orchestrator can read the WAL, see what completed, and resume — rather than re-running completed work or losing it entirely.

## Evidence

- **Engineering blog (AgentMarketCap, April 2026):** Documents real production incidents — `DROP TABLE` before backup, S3 misprefix deletion, 47-file refactor corruption — and proposes checkpoint/rollback as the architectural response. Recommends sandboxing as an alternative: "run destructive tools in a sandboxed environment first." — [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026)
- **Technical article (AI Codex, 2026):** Describes five multi-agent failure modes — timeout mid-pipeline, partial output, cascading failure, silent degradation (wrong answer passes validation), state inconsistency — and prescribes checkpoints-plus-idempotency as the foundational recovery pattern. Notes the write-ahead log approach for resuming interrupted pipelines. — [aicodex.to](https://www.aicodex.to/articles/multi-agent-failure-handling)
- **Show HN (agent-triage, February 2026):** Production trace diagnostic tool that extracts behavioral rules from system prompts, replays conversations step-by-step using an LLM-as-judge, and identifies which step, turn, and agent caused each failure — and how failures cascade through routing, handoffs, and retrieval. Runs locally; only LLM API calls leave the machine. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Engineering blog (Neel Mishra, 2026):** Presents four-category error taxonomy (transient, semantic, resource, fatal) with distinct recovery strategies per category. Key insight: semantic errors require re-prompting with corrective context, not blind retry. — [neelmishra.github.io](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Technical article (AgentixForce, May 2026):** Recommends connection timeout of 2–5 seconds, read timeout matching p99 latency of the operation, and explicit circuit breaker state machine (Closed/Open/Half-Open) adapted for LLM reasoning loops. — [agentixforce.ai](https://agentixforce.ai/blog/retry-timeout-circuit-breaker-patterns)
- **Workshop (deepsense.ai, 2025):** Field report showing structured orchestration and checkpoint-based memory can cut manual resolution time by 40–70% and reduce inference costs by up to 35% in production agent deployments. — [deepsense.ai](https://deepsense.ai/resource/ai-agents-lessons-learned-in-the-field/)

## Gotchas

- **Checkpointing is semantic-blind without instrumentation.** LangGraph checkpoints graph state, but a read and an email send get the same treatment. Annotate checkpoints with the semantic meaning of each step so rollback restores to a coherent logical state, not just a byte-level snapshot.
- **Retrying client errors is a bug, not a feature.** HTTP 400, 422, expired tokens — retrying these doesn't help, and it burns budget and latency. Classify errors before retrying; only transient errors merit automatic retry.
- **Hard step caps need monitoring, not just enforcement.** When `MAX_STEPS` is hit, the agent doesn't fail loudly — it just stops. You need an alert on `AgentExceededSteps` so someone reviews why the agent couldn't finish and whether it left partial state.
- **Rollback doesn't undo external systems.** If the agent sent an email, called a payment API, or triggered a webhook, rolling back your internal state doesn't reverse the external side effect. Gate destructive external actions behind human-in-the-loop confirmation, not just rollback infrastructure.
- **Partial outputs look like success.** The agent returned text; the HTTP call succeeded; but the JSON was truncated, the file was only half-written, the pipeline is missing step 5. Always validate output completeness before treating it as a successful result.
