# S-2144 · The Agent Failure Recovery Stack — When Your Agent Loops for 35 Minutes and Tells You Nothing

Your agent starts a multi-step task. Step 3 fails — a tool returns an unexpected schema. The agent pauses, retries, fails again, then silently re-plans around the error and continues. Forty minutes later it completes — having done the wrong thing, accumulated 40,000 tokens of context bloat, and left no trace that anything ever went wrong. This is not an edge case. It is the default behavior of agents without deliberate failure handling. The failure was recoverable; the system just chose not to surface it.

## Forces

- **Agents fail without raising exceptions.** A tool returning a malformed response, a model hallucinating a tool name that doesn't exist, an agent drifting from its goal — none of these throw errors in the traditional sense. The agent continues executing, just on bad premises.
- **The cost of a loop is invisible until the invoice arrives.** Infinite or near-infinite loops burn tokens without any runtime exception. A 35-minute looping agent silently costs more than 500 normal invocations.
- **Self-correction is not free and not reliable.** Research from Kamoi et al. (2024) found that reliable self-correction depends primarily on external feedback — models correcting themselves from internal reasoning alone is inconsistent. Most production teams treat self-correction as a magic wand instead of a designed subsystem.
- **Rollback must survive process restarts.** An agent that checkpoints state to in-memory structures loses everything when the container orchestrator restarts it. External state stores (Redis, Postgres) are required for real recoverability.
- **Privileged actions compound failure severity.** An agent making destructive API calls (database deletes, infrastructure teardowns) can cause irreversible harm before a human can intervene. The failure mode is not degraded service — it is data loss.

## The Move

Design failure handling as a layered hierarchy, not a try-catch wrapper. Each layer handles a different failure category:

**Layer 1 — Instrument everything that can fail.** Every LLM call, tool invocation, and external API request must be wrapped with observable error handling. Log not just whether something failed, but what the failure was, how many times it was retried, and what the agent did afterward.

**Layer 2 — Count-based loop detection.** Track the (tool, arguments) tuple at each step. When the same tuple appears 3+ times in one session, inject a mandatory pivot instruction: *"You have tried this path N times. It is not converging. Try a different tool or admit you cannot complete this task."* This is the cheapest possible loop breaker and the most commonly skipped.

**Layer 3 — Exponential backoff with jitter for transient failures.** Base delay 1s → 2s → 4s → 8s, max 60s, ~30% jitter randomization. Max 3 retries. This prevents thundering-herd when a service recovers. Every dependency needs its own breaker — a shared breaker across unrelated services causes unnecessary degradation.

**Layer 4 — State checkpointing after every successful tool call.** Using LangGraph's `MemorySaver` or `SqliteSaver`, persist state after each node. On failure, resume from the last safe checkpoint using the same `thread_id`. Postgres is preferred over Redis for complex state; Redis for simple conversational state. A 2026 LangGraph issue (#8234) flagged that `durability="sync"` can restore inconsistent state post-crash — use `durability="async"` with a WAL strategy for production.

**Layer 5 — Circuit breakers with tiered recovery.** Trigger on 5 consecutive failures or >30% error rate in a 10-minute window. Three states: Closed (normal) → Open (fast-fail, 30s) → Half-Open (probe). On open: alert the coordination agent and switch to degraded/manual mode. Each external dependency needs its own breaker — a shared breaker across unrelated services causes unnecessary degradation.

**Layer 6 — Fallback chains for model and strategy failures.** Chain: primary model → secondary model (e.g., Claude Opus → Claude Haiku for cost/speed) → simplified agent with fewer tools → human escalation. Make each fallback tier observable — if the agent degrades to a smaller model, the monitoring system should know and alert.

**Layer 7 — Human-in-the-loop escalation gates.** For destructive operations (DELETE, DROP, teardown), require explicit confirmation or use an approval queue. The Cursor/Railway incident — where an agent used a found API token to delete production volumes and backups in seconds — was not a model failure; it was a privilege management failure. Principle: the system must assume the model may be confused or overconfident. Damage must still be constrained.

**Layer 8 — The recovery ladder for stuck agents.** When loop detection fires, climb a bounded ladder: (1) Nudge — inject pivot instruction. (2) Replan — give the agent a simplified goal and last checkpoint context. (3) Escalate — alert human with session transcript. (4) Reset — restore to last safe checkpoint and try a different strategy. (5) Hand off — route to a human operator with full context attached.

## Evidence

- **GitHub Discussion:** Anthropic SDK contributors sharing production patterns — "30-second timeout per tool call," "3 AM Rule" for production-grade agents achieving 97.8% autonomous recovery. Circuit breaker triggered at 5 consecutive failures or >30% error rate in 10-minute window. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **AI System Design Guide:** Counter-based loop intervention — if the same (Tool, Args) tuple appears 3 times, inject mandatory pivot instruction. State checkpointing in LangGraph/LangChain saves a "State Snapshot" to a database after every successful tool call; rollback restores to the last safe step. — [github.com/ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

- **Zylos Research / Galileo 2025:** Production incident analysis — specification failures account for ~42% of multi-agent failures, coordination breakdowns for ~37%, verification gaps for ~21%. Deadlock, resource contention, goal drift, and cascading errors in multi-agent systems are distinct from conventional software failure modes and require dedicated patterns. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)

- **AI Agents Blog:** Five production error recovery patterns — exponential backoff, circuit breakers, checkpoint-and-resume, fallback strategies, and escalation queues. Specifically notes that a single bad tool call at step 3 of a 12-step workflow, if unhandled, leaves the entire pipeline in an undefined state with no checkpoint, no retry, no fallback — just silence. — [aiagentsblog.com](https://aiagentsblog.com/blog/agent-error-recovery-patterns/)

- **Penligent AI post-mortem:** Cursor agent with Claude Opus 4.6 deleted a Railway production database and backups in seconds. Root cause: the system allowed agent text to become production action without privilege constraints. The agent "confessed" it guessed instead of verifying — assumed staging volume deletion was scoped to staging. — [penligent.ai](https://www.penligent.ai/hackinglabs/ai-agent-deleted-a-production-database-the-real-failure-was-access-control/)

## Gotchas

- **Self-correction requires external feedback.** Don't assume the model will catch its own mistakes from internal reasoning alone. Design the environment to provide verifiable feedback (tool outputs, API responses, LLM-as-judge validation) rather than relying on model introspection.

- **In-memory checkpoints die with the process.** If you're checkpointing to Python objects or in-process state, a container restart wipes everything. Use Redis, Postgres, or Sqlite with persistence for any agent that runs longer than a single request.

- **Circuit breakers must be per-dependency, not global.** A global breaker means one flaky dependency opens the circuit for all other dependencies. Each LLM provider, each external API, each tool class gets its own breaker with its own thresholds.

- **The recovery ladder must have bounded steps.** Without explicit bounds, "escalate to human" can silently queue forever. Define timeouts at each tier: nudge after 2 loop detections, replan after 5, escalate after 10, reset after 15. Track these as first-class metrics.

- **Quiet failures are worse than loud ones.** An agent that completes a task but produces wrong output, or an agent that silently degrades to a smaller model without alerting, is more dangerous than one that fails loudly and obviously. Design your failure handling to surface problems, not suppress them.
