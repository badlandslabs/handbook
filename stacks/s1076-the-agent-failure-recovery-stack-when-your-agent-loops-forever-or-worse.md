# S-1076 · The Agent Failure Recovery Stack

When your agent gets stuck in a loop, produces confident nonsense, or takes an irreversible action before you can intervene — and you realize your error handling is just a bare try/except that logs and gives up.

## Forces

- **Non-determinism compounds.** A tool call that succeeds technically (HTTP 200) can fail semantically (returns the wrong data). Standard try-catch misses these entirely.
- **Errors are not exceptions.** In agentic systems, "errors" include hallucinations that return valid JSON, reasoning chains that produce confident wrong answers, and loops that look like productive activity.
- **Recovery is not one-size.** The right fix for a rate-limit timeout is not the right fix for a stuck reasoning loop is not the right fix for a spending spiral. You need a classified response ladder.
- **Activity is not progress.** API call counts, log volume, and file edit frequency rise during a stuck loop too — they cannot distinguish productive work from thrashing.
- **Failure modes cluster.** Across production incidents: ~42% are specification failures (agent does wrong thing), ~37% coordination breakdowns (multi-agent confusion), ~21% verification gaps (agent stops too early or accepts bad outputs).

## The Move

Build a **classified recovery ladder** — not a flat try/except, but a taxonomy of error classes each routed to the right handler. Layer three planes: guardrails that prevent runaway loops before they start, error classification that routes each failure to the right resolver, and escalation that hands off to humans when the agent cannot save itself.

### Guardrails — prevent before you recover

- **Hard step caps** are the single most important safeguard. Set `recursion_limit=12` in LangGraph or equivalent. If the agent has not finished in 12 steps, stop, document, and escalate. No agent should run for 35 minutes unsupervised.
- **Cost circuit breakers.** Track cumulative spend per task. At a threshold (e.g., 3x baseline cost), interrupt and surface to a human. The Asynq.ai candidate evaluation agent ran 3x over budget before anyone noticed.
- **Store errors in state, not just logs.** Rather than catching and swallowing exceptions, attach error metadata to the agent state so the LLM can see what failed and adjust. "Your last tool call returned a 404 — here is the endpoint schema — try a different resource path" beats silent failure.

### Error Classification — route to the right resolver

| Error Class | Who Fixes It | Signal | Response |
|---|---|---|---|
| **Transient** | System (automatic) | HTTP 429, 503, timeout, DNS blip | Retry with exponential backoff; same request succeeds if you wait |
| **Semantic** | The LLM | Malformed JSON, wrong tool chosen, schema violation | Append parse/reasoning error to state and loop back — LLM self-corrects |
| **Resource** | The system | Token budget hit, context overflow, spending cap | Summarize history, drop oldest results, route to cheaper model |
| **Fatal** | Human | Auth failure, permission denied, irreversible action attempted | `interrupt()` — pause and surface to human for approval |

(Classification schema from Austin Vance, Focused.io, April 2026)

### The Stuck-Loop Recovery Ladder

When a loop is detected via a genuine progress metric (not activity count), climb this ladder:

1. **Nudge** — inject a hint into state: "You've called the same tool 3x. Consider a different approach."
2. **Replan** — truncate reasoning history and ask the agent to re-plan from the current state snapshot
3. **Reset** — restore from the last checkpoint and try a different entry point
4. **Escalate** — surface the stuck state plus error log to a human with a summary
5. **Hand off** — if a sibling agent or workflow can take over, transfer state and let them continue

Never jump to escalation first. The cheap fix that breaks a repeater fails on a wanderer.

### Checkpointing for Long-Running Tasks

- Use LangGraph's `AsyncSqliteSaver` or Postgres-backed checkpointing to snapshot state at each tool-call boundary
- On failure, resume from the last checkpoint rather than re-running from scratch — avoids wasted LLM calls and prevents duplicate side effects
- For distributed systems, store checkpoints in Redis or Postgres with task IDs so workers can resume across restarts
- Tool-call boundaries are the right atomic unit for checkpointing — not every token and not only at workflow end

### Dead Letter Queues for AI-Specific Failures

Standard DLQ patterns break down for AI agents because failures include hallucinated parameters, token limit violations, and non-deterministic outputs that parse successfully but fail downstream. A production AI DLQ must:

- Classify each failure by type before queuing using the taxonomy above
- Preserve the full conversation state (not just the error) so a human or retry handler can reconstruct context
- Route specification failures (~42% of multi-agent failures) to a review queue, not a blind retry
- Set a maximum retry count per class: transient errors may retry 3x; semantic errors retry once with corrective context; fatal errors never retry automatically

## Evidence

- **Engineering blog:** A candidate evaluation agent at Asynq.ai hallucinated tool parameters, got stuck in loops, and cost 3x budget — fixed by cost circuit breakers and hard step caps — [Harsh Rastogi, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Primary research:** arXiv:2605.01604 documents 7 production failure modes unique to agentic systems; standard benchmarks fail to detect 4 of 7 entirely; proposes PAEF — a five-dimension continuous monitoring framework — [Mukund Pandey, May 2026](https://arxiv.org/html/2605.01604)
- **Case study synthesis:** Six documented agentic failures (Air Canada chatbot, NYC MyCity, Replit DB wipe, Cursor deletion, Klarna reversal, DPD chatbot) cluster into three structural modes: undisclosed binding actions, permission overreach, and unsupportable quality claims — [AgentMode.ai, April 2026](https://agentmodeai.com/agentic-ai-failure-case-studies/)
- **Architectural guide:** Dead letter queue patterns for AI agents require specialized handling for hallucinations, token violations, and non-deterministic outputs that standard DLQ systems miss — [Brandon Lincoln Hendricks, March 2026](https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production)
- **Framework patterns:** Error classification matrix (transient/LLM-recoverable/user-fixable) routed to different LangGraph primitives (`RetryPolicy`, error-in-state loops, `interrupt()`) — [Austin Vance, Focused.io, April 2026](https://focused.io/lab/langgraph-agent-error-handling-production)
- **Production review:** Agentic AI projects that shipped in 2025 succeeded where tight feedback loops existed (developer tooling, internal ops) and stalled where quality verification was expensive or slow (customer-facing without human review) — [Technspire, December 2025](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Activity does not equal progress.** API call counts and log volume spike during stuck loops too. Use a real progress metric: tests resolved, unique sources gathered, checklist items completed.
- **Retrying semantic errors blindly makes it worse.** If the LLM chose the wrong tool, retrying with exponential backoff just runs the same wrong tool faster. Append the error to state so the LLM can self-correct.
- **Checkpoint granularity matters.** Checkpointing on every token is expensive; checkpointing only at the end defeats recovery. Tool-call boundaries are the right atomic unit.
- **Cost spirals are silent.** The agent does not know it is spending too much. You need a circuit breaker watching cumulative spend outside the agent own state.
- **Context truncation as resource recovery loses history.** If you truncate conversation history to recover from a token limit, you lose checkpoint fidelity. Prefer structured summarization of intermediate steps over raw truncation.
