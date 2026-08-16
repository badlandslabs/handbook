# S-2748 · The Agent Failure Taxonomy Stack — When Your Agent Errors But Nobody Planned the Recovery

Your agent ran for 20 minutes in production. It looped silently, consumed $200 in API calls, and nobody noticed until the bill arrived. Every retry was compounding the cost. Every failure was a surprise. Nobody planned for this.

## Forces

- **Failures compound non-linearly.** A 5-step pipeline where each step succeeds 95% of the time delivers only 77.4% end-to-end reliability. At 10 steps, you're at 59.9%. Teams building agents think in happy paths; production breaks at the joints between steps.
- **Most failures are recoverable, but only if you classify them.** The Operator Collective's analysis of production agent deployments found 86% of agent failures are recoverable — yet teams treat failures as binary (retry or die) rather than as a triage problem requiring different strategies for different error types.
- **Retry logic amplifies cost and risk.** Retrying a network call is normal. Retrying an LLM call is billable. Retrying a `send_email` tool call delivers the email twice. The same retry logic that fixes transient failures creates new failures when applied to side-effect-bearing tools.
- **Silent failures are worse than loud ones.** The most dangerous agent failure mode is the "confidence failure" — the agent thinks it succeeded, produces an output that looks plausible, and downstream systems act on it. These don't trigger exceptions; they trigger incidents days later.

## The Move

Build a layered failure-handling system: classify errors first, then apply the right recovery primitive per error type.

**1. Classify before you recover.** Divide failures into at least four types, each demanding a different response:

| Error Type | Examples | Safe to Retry? | Strategy |
|---|---|---|---|
| `transient` | 429 RateLimit, 503 Unavailable, network timeout | Yes, with backoff | Exponential backoff + jitter, cap at 3 attempts |
| `deterministic` | 400 BadRequest, auth expired, invalid tool args | No | Fix the input or ticket human; retrying won't help |
| `poison` | corrupted context, hallucinated tool parameters | No | Quarantine, inspect, discard |
| `uncertain` | timeout after a write (did it commit?) | Conditional | Idempotency key guard before replay |

**2. Apply exponential backoff with jitter — and cap it.** Pure exponential backoff without jitter causes thundering herds. Jitter (randomizing the delay) spreads retries across time. Cap total retry budget: most teams set 3–5 attempts max, consuming a timeout window of ~30–60 seconds before escalation. Cordum caps scheduling retries at 50 (~25 minutes), then emits DLQ metadata with reason codes and halts.

**3. Gate retries with idempotency keys.** Before retrying any tool call with side effects (writes, emails, deploys, database mutations), check an idempotency key. Key structure should represent *operation intent*, not retry attempt — e.g., `user_123:send_weekly_digest:2025-W12`. Retries return the original outcome; they don't create duplicate work. A practitioner on the Anthropic SDK discussion described a cron job that was supposed to post to Discord at 22:00; a network timeout + retry storm produced 50 duplicate posts at 22:05. The fix: idempotency keys + "already posted" guards.

**4. Checkpoint state for long-running agents.** For jobs spanning minutes or hours, save checkpoints at decision points. Each checkpoint records: completed steps, tool call results, LLM reasoning trace, and a stable intent hash. On failure, replay from the last checkpoint rather than from scratch. The open-multi-agent project uses an append-only event log for state reconstruction, enabling time-travel debugging and finer-grained recovery than whole-snapshot approaches. A practitioner on the Anthropic discussion reported using a `MEMORY.md` pattern: each agent writes its state to a shared memory file; on cascade failure, the system replays from the last checkpoint instead of losing everything.

**5. Isolate agent boundaries with circuit breakers.** In multi-agent systems, one agent going down can cascade. The Agentic Reliability Framework (ARF) uses three specialized agents — Detective (FAISS-based anomaly detection), Diagnostician (causal root-cause reasoning), and Predictive (failure forecasting) — to catch cascading failures early. Separately, AgentBreaker monitors token spend, iteration count, and cost velocity across multi-step orchestration and hard-stops runaway agents before budget burns out. A developer on the LangChain forum described ending up with "isolated agent sessions with their own sandboxes" after cascade failures took out a shared pipeline.

**6. Dead-letter queue with triage taxonomy.** Failed tasks that exhaust retry budgets go to a DLQ, not nowhere. Cordum separates DLQ failures into four categories — transient (retry later), poison (discard + alert), governance (requires approval), and uncertain (did the write commit?) — each with different replay semantics. Critically: replay must re-evaluate policy before dispatch, not blindly re-execute. A Cordum incident response guide notes that "DLQ replay without fresh policy checks can duplicate side effects."

## Evidence

- **GitHub Discussion:** Practitioners reporting error recovery patterns including checkpoint-based state persistence, MEMORY.md agent state files, and a war story where a retry storm produced 50 duplicate Discord posts — resolved with idempotency keys and "already posted" guards — [anthropics/anthropic-sdk-python#1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Show HN / GitHub:** Agentic Reliability Framework (ARF) — three-agent system (Detective/Diagnostician/Predictive) achieving 2-minute MTTR vs 45-minute manual recovery, 15-minute incident resolution vs 8-hour manual, built by a former reliability engineer — [petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Case Study:** A team ran 20+ agents; a content repurposing agent got stuck in a 47-iteration refinement loop, generating a $400/day bill discovered three days later from the AWS bill — resolved by building a real-time cost circuit breaker monitoring token velocity — [the-brainy-guys.com](https://the-brainy-guys.com/blog/ai-cost-control-stack-costguard)
- **Engineering Post:** DLQ replay must re-evaluate policy before dispatch; Cordum caps scheduling retries at 50 (~25 min), then emits DLQ metadata with reason codes — [cordum.io/blog/ai-agent-dlq-replay-patterns](https://cordum.io/blog/ai-agent-dlq-replay-patterns)
- **Engineering Post:** Idempotency key structure must represent operation intent, not retry attempt; retry storms amplify cost, risk, and blast radius simultaneously — [runcycles/cycles-docs](https://github.com/runcycles/cycles-docs/blob/main/blog/retry-storms-and-idempotency-in-agent-budget-systems.md)
- **Blog:** 847 users received duplicate newsletters after a queue worker retried an email pipeline step that had already succeeded (timeout after write commit) — [engineersofai.com](https://engineersofai.com/docs/ai-engineering/production-ai-patterns/idempotency-and-retries)

## Gotchas

- **Setting `max_tokens` on a single LLM call is not a circuit breaker.** It only bounds one call, not a multi-step orchestration. You need orchestration-layer controls: total token budgets, step-count limits, and cost velocity monitoring across the full run.
- **Not all errors are retry-worthy.** Retrying a `transient` error works. Retrying a `deterministic` error (bad input, expired auth) burns budget and delays alerting. Classify first.
- **A DLQ without a triage policy is just a graveyard.** Items pile up, nobody looks at them, and you never recover. Every DLQ entry needs a reason code, evidence payload, and a defined replay policy.
- **Checkpoint frequency is a tradeoff.** Checkpoint every step is safe but slow. Checkpoint only at major milestones means you replay large chunks on failure. Checkpoint at decision points — where the agent makes a choice that affects downstream state — is the right granularity.
