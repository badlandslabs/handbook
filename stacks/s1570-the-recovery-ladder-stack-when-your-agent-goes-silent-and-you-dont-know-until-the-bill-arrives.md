# S-1570 · The Recovery Ladder Stack — When Your Agent Goes Silent and You Don't Know Until the Bill Arrives

When an agent loops on a broken tool, produces confidently wrong output, or silently cascades bad state through 8 downstream steps — and none of them raise an exception.

## Forces

- **Agents fail sideways, not loudly.** Traditional software crashes or returns an error. Agents return HTTP 200 with valid JSON in the wrong shape, and keep going.
- **The cheap fix breaks the expensive case.** A single retry works for a transient blip; the same retry loop wastes $200 on a hard failure that should escalate in the first call.
- **You can't inspect what you can't see.** Loop detection by call count alone misses wanderers that take different wrong paths each time.
- **State across steps compounds the blast radius.** A malformed field at step 2 surfaces at step 9 as a cascade nobody can trace.

## The move

Classify every failure by **who should fix it**, then route each class through a bounded escalation ladder.

**Step 1 — Classify the failure type before choosing a recovery:**

| Failure class | Who fixes it | Example | First response |
|---|---|---|---|
| Transient | System (automatic) | 429 rate limit, DNS blip, 503 | Retry with exponential backoff + jitter |
| Tool-return malformed | The LLM (loop it back) | Bad JSON, wrong tool chosen, partial output | Inject error into state, re-call with context |
| User-fixable | The human | Missing required field, ambiguous input | `interrupt()` — surface to user, don't retry |
| Unexpected | Developer | `TypeError`, schema mismatch, logic bug | Let it bubble — swallowing it hides real bugs |
| Persistent/dead | Escalation | Quota exhausted, API key invalid, hard auth failure | Fallback path or graceful halt |

**Step 2 — Implement the escalation ladder (bounded):**

1. **Nudge** — inject a correction hint into the next LLM call (step counter, error message, "you've tried X times, try a different approach"). Stay in the same tool/approach.
2. **Replan** — call the LLM with the full error state and ask it to produce a revised plan before continuing.
3. **Reset** — roll back to the last checkpoint, swap the model or prompt, restart from that point.
4. **Hand off** — surface to a human with the full error trace. Do not loop endlessly waiting for human input — mark the task as blocked and log context.

**Step 3 — Guard the perimeter with hard limits:**

- **Step cap** — hard maximum on agent steps (e.g., 50). Agents that exhaust the cap escalate, not retry.
- **Cost circuit breaker** — track spend per run. Open the circuit when spend exceeds a threshold. Tools like `agent-watchdog` (MIT, framework-agnostic) provide this out of the box: `max_budget_usd=5.00`, `max_steps=30`.
- **Loop detection** — track recent state/action pairs, not just call counts. A wanderer that takes 10 different wrong actions still loops; a repeater that calls the same broken tool 10 times also loops — both need to be caught.
- **Output sentinel** — validate LLM output against a Pydantic schema before passing it downstream. `AgentCircuit` (Python decorator) wraps any agent function with this: if the LLM returns something that doesn't match `sentinel_schema`, the decorator rejects it rather than passing garbage downstream.

**Step 4 — Checkpoint before irreversible steps:**

Any step that creates a side effect (writes a file, sends an email, calls an external API, mutates state) should have a checkpoint immediately before it. If recovery rolls back, it rolls back past the irreversible boundary, not into it.

## Evidence

- **HN Show HN:** AgentCircuit creator describes losing "$200+ on one run" from a looping agent node calling the same broken function repeatedly, and LLM output not matching what downstream code expected — both caught post-hoc by a bill. Built as a Python decorator with `sentinel_schema` validation to fail fast on malformed output. — [HN Show HN: AgentCircuit](https://news.ycombinator.com/item?id=46899775)
- **DEV Community / engineering post:** LangGraph's error classification matrix with four buckets (transient/LLM-recoverable/user-fixable/unexpected) and the principle that retrying a user-fixable error wastes 3 attempts before failing anyway. Covers `RetryPolicy`, `Command`, and `interrupt()` primitives with real code. — [LangGraph Error Handling Patterns for Production AI Agents](https://dev.to/focused_dot_io/langgraph-error-handling-patterns-for-production-ai-agents-33p7)
- **GitHub:** `agent-watchdog` (MIT, 27 commits) — framework-agnostic loop detection + budget guards + graceful halts. Solves three specific problems: agents calling broken tools forever without triggering framework loop detection, runs costing 10x budget with no visibility, and processes crashing at step 9 of 12 then retrying from step 1 re-triggering side effects. — [github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)

## Gotchas

- **Retrying everything is worse than retrying nothing.** A blanket `except Exception: retry()` will hammer rate-limited APIs and exhaust budgets on hard failures. Classify first, retry second.
- **Activity is not progress.** Call counts, file edits, and log lines all increase during stuck loops. Track a **real progress metric** — unique tasks completed, failing tests resolved, checklist items checked — that only moves when genuine work is done.
- **Checkpointing is only useful if rollback actually restores state.** If your checkpoint serializes to disk but your agent process is stateless across restarts, the rollback needs to reload from that checkpoint. Many teams add checkpoints but skip the reload.
- **Silent failures look like success.** HTTP 200, valid JSON, correct schema — and the output is confidently wrong. This is the most expensive class. Output validation against a schema (sentinel) is the only structural defense; logging and monitoring alone won't catch it.
- **The recovery ladder must be bounded.** Without hard step caps and cost limits, "escalate to human" can mean "loop until the budget runs out and then error." A human handoff that never happens is not escalation — it's silence.
