# S-1935 · The Agent Recovery Stack — When Your Agent Fails Silently and Costs You 250K API Calls

When your AI agent has gone off the rails — looping, returning confident wrong answers, burning budget with unbounded retries — and you need a recovery architecture that actually holds under production load.

## Forces

- **Agents fail like nothing else** — they don't crash and log stack traces. They keep going. They return "success" with corrupted data. They loop silently for 35 minutes. The failure modes are qualitatively different from traditional software, which means traditional retry logic isn't enough.
- **The recovery mechanism is also the runaway mechanism** — the exact patterns that keep agents running (retries, fallbacks, self-correction) are the ones that cause runaway behavior when they're unbounded. A missing retry cap once let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent was executing exactly its recovery logic — it just had no ceiling.
- **State is the hard problem** — checkpointing is easy to describe but hard to get right. If step 7 of a 10-step workflow fails, what exactly do you replay? The tool call result? The LLM reasoning? Both? And how do you prevent replaying a tool that already committed a side effect (sent an email, created a ticket, pushed a config)?
- **Silent failures are the norm** — 40-60% of agent failures go undetected without proper observability. The agent completes the workflow and returns a result. The result is wrong. No exception was raised.

## The Move

Build a layered recovery architecture where every layer has explicit bounds and every failure mode gets a specific recovery path.

### Layer 1: Classify Before You Recover

Not all failures are equal. Route to the right recovery based on error type:

| Error type | Recovery strategy |
|---|---|
| `transient` (rate limit, timeout, 5xx) | Exponential backoff + retry |
| `validation` (wrong output format, hallucinated fields) | Re-prompt with specific error — "self-correction is retry with a better error message" |
| `capability` (unavailable tool, missing permission) | Escalate to parent agent or human gate |
| `budget` (token/cost ceiling hit) | Pause task, notify orchestrator, await top-up |
| `structural` (API contract changed, schema drift) | Dead letter queue, human review |

From: *GitHub Discussion #1341 — "What patterns do you use for AI agent error recovery?"*, anthropics/anthropic-sdk-python — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

### Layer 2: Retry With Hard Bounds

Treat every LLM call like a network call — but with explicit limits:

- **Retry cap**: hard maximum on retry attempts (e.g., 50 total, ~25 minutes). After that, emit DLQ metadata with reason codes and stop.
- **Exponential backoff with jitter**: base 1s → 2s → 4s → 8s, ceiling 60s, 30% jitter to prevent thundering herd.
- **Circuit breaker**: after 5 consecutive failures OR >30% error rate in a 10-minute window, open the breaker and stop calling the failing endpoint for 30 seconds.

From: *miaoquai.com 4-layer stack* — running 5 agents 24/7 for 95+ days — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

### Layer 3: Tool Failure Isolation

Isolate each tool call so one tool's failure doesn't cascade:

- **Per-tool timeout**: 30-second hard timeout per tool call. Log the error, return a structured error object, continue in degraded mode rather than crashing the whole agent.
- **Idempotency keys**: generate a UUID before every tool call that creates side effects. Store it. On retry, check if the operation already succeeded before re-executing. This is what makes DLQ replay safe for agents.
- **Validation gate**: after every executor call, validate output shape against a schema. Reject results that don't match before updating state.

From: *Cordum DLQ Replay Patterns* — https://cordum.io/blog/ai-agent-dlq-replay-patterns

### Layer 4: Checkpoint + Resume

Make long workflows resumable without starting over:

- **Checkpoint after every N steps**: serialize agent state (not just tool results — serialize working memory, loop variables, and the original task payload). On resume, rebuild context from the checkpoint + minimal delta.
- **Checkpoint on every approval gate**: if your agent suspends for human approval before a consequential step, checkpoint immediately before the gate so resume goes to the right step.
- **Resume is a fresh LLM call**: don't replay the old reasoning. Pass the checkpoint state as new context and let the LLM re-plan from where it left off.

From: *Tardigrade resilience middleware* (Apache 2.0, supports LangGraph/CrewAI/OpenAI SDK) — https://github.com/cole-godfrey/tardigrade and *ExplainX loop engineering workshop* — https://www.explainx.ai/blog/ai-agent-loop-architecture-triggers-retries-checkpoints-2026

### Layer 5: Fallback Chain

When the primary model fails, degrade gracefully — don't hard-fail:

- **Model fallback chain**: Primary → Secondary → Tertiary → Queue for retry. Learned during the November 2025 outage when teams with a single model had no fallback and lost entire workflows.
- **Graceful degradation**: if a non-critical tool fails, continue without it. If a critical tool fails, escalate to human.

From: *miaoquai.com production experience* — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

### Layer 6: Watchdog + Observability

You can't recover from failures you can't see:

- **Step counter watchdog**: track total LLM calls per task. If it exceeds a threshold (e.g., 200 calls for a task that should take 20), halt and alert.
- **Trace every tool call**: structured logs (not just console.log) with: timestamp, tool name, arguments, result, duration, error (if any). Feed into a trace viewer.
- **Key metrics to monitor**: error rate by type (transient/client/semantic tracked separately), DLQ depth, retry rate, circuit breaker state changes, escalation frequency, cost-per-task.

From: *Zylos Research — "AI Agent Self-Healing and Failure Recovery"* (May 2026) — https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/

## Evidence

- **GitHub Discussion (Primary Source):** Practitioner from miaoquai.com describes their 4-layer stack running 5 agents 24/7 for 95+ days without a complete outage. Key lesson: "error recovery is 30% code, 70% expecting things to fail in ways you never imagined." — https://github.com/anthropics/anthropic-sdk-python/discussions/1341
- **Engineering Blog (Primary Source):** Cordum documents that standard DLQ patterns break for agents because replay can cause duplicate side effects. Their solution: idempotency keys per tool call, hard retry caps (50), and human gates for uncertain commit state. — https://cordum.io/blog/ai-agent-dlq-replay-patterns
- **Open Source (Primary Source):** Tardigrade (Apache 2.0) implements checkpoint/resume + circuit breakers + retry budgets as framework-agnostic middleware. Their math: 85% step accuracy → 20% end-to-end success over 10 steps without resilience wrapping. — https://github.com/cole-godfrey/tardigrade
- **Research Synthesis:** Zylos Research (May 2026) provides a taxonomy: 42% specification failures, 37% coordination breakdowns, 21% verification gaps across production multi-agent incidents. — https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/

## Gotchas

- **Retrying without idempotency keys creates duplicate side effects** — replaying a tool call that already succeeded (email sent, ticket created) is worse than failing silently. Always generate idempotency keys before tool calls that modify external state.
- **Self-correction loops can accumulate cost without accumulating progress** — an agent that fails validation and re-prompts itself indefinitely burns tokens and time. Combine self-correction with a step cap and a circuit breaker that forces escalation after N failed attempts.
- **Checkpointing LLM reasoning is not the same as checkpointing tool results** — serializing the full conversation history for context rebuild can exceed token limits on long workflows. Checkpoint the *intent and state*, not the raw history.
- **Circuit breakers must protect against the agent's response to failure, not just call volume** — a model outage can cause an agent to keep retrying at a different layer (trying alternative tools, re-planning, escalating) even after the API circuit breaker opens. The breaker needs to cover the entire recovery loop.
- **Silent failures outnumber loud ones** — 40-60% of agent failures produce no exception and no error log. Output validation and result schema checks are your primary detection mechanism, not exception handlers.
