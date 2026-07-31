# S-1923 · The Loop Breaker Stack — When Your Agent Runs All Night Burning Tokens Doing Nothing

When an agent silently loops on a failing operation — same tool, same arguments, same failure — burning budget and producing nothing. You discover it hours later by checking your invoice.

## Forces

- **Persistence is a virtue until it isn't** — agents are trained to keep trying. A missing Kubernetes secret won't materialize on attempt twelve. A broken API won't recover between retries.
- **"Working" looks identical to "stuck"** — a looping agent shows the same status as a healthy one. No crash. No error message. Just hours of silent waste.
- **Failures are non-deterministic** — traditional try/catch doesn't cover hallucinated tool parameters, semantically wrong outputs, or reasoning chains producing confident nonsense that return HTTP 200.
- **Retry logic must be operation-aware** — idempotent reads deserve more retries than a write that doubles your Stripe charge.

## The Move

Layer five distinct failure-handling mechanisms, from fastest to most expensive:

1. **Iteration cap with semantic duplicate detection.** Hard-stop at N=5 repeated identical tool calls. But track semantic duplicates too — same tool with minor argument variations within a short window signals the same underlying failure. OpenAI's harness guide says: one task per session, verify before building.

2. **Tiered retry with exponential backoff and jitter.** 1s → 2s → 4s → 8s, capped at 60s, with ±30% jitter to prevent thundering-herd on shared resource recovery. Separate retry configs for idempotent vs non-idempotent operations — writes get fewer retries. Max 3 retries for immediate tier; sustained failures trip the circuit breaker.

3. **Circuit breaker at the service level.** After 5 consecutive failures (or >30% error rate over 10 minutes), open the breaker for 30 seconds. Signal "degraded mode" to downstream agents and orchestrators so the whole fleet routes around the problem.

4. **Tool parameter validation before execution.** Wrap every tool call with schema validation — check enum values, ID formats, date ranges. Catch hallucinated parameters at the wire, not at runtime. This is the "zombie agent" fix: it keeps chatting but stops calling tools.

5. **Durable checkpoint/resume over context-stuffing.** Use PostgresSaver or SqliteSaver (not InMemorySaver) for LangGraph or similar stateful frameworks in production. On failure, recover from the last durable checkpoint, not from scratch. CockroachDB's analysis makes this explicit: reliable agent loops depend on durable database state, not just accurate model reasoning.

6. **Graceful degradation chain.** When primary model fails: drop to cheaper model (e.g., GPT-4o → GPT-3.5) → cached response → human escalation. A customer support agent that degrades to 70% accuracy still helps. One that errors out resolves zero tickets. Confidence thresholds of 80–95% (depending on risk domain) trigger escalation per Zylos research.

7. **Human-in-the-loop as last resort.** Preserve full conversation context, tool history, and decision state during handoff. Don't just escalate a vague "it failed" — push the full trace.

## Evidence

- **Production incident report:** A fullstack agent spent 2h 28m stuck in the same tool-call cycle, burning 58,000 tokens with zero progress. GenBrain AI's rule: "same action repeated five or more times with no success — STOP. Decompose into smaller steps, mark BLOCKED, or escalate." — [Agent.ceo Blog](https://agent.ceo/blog/detect-break-agent-retry-loops-production)
- **GitHub issue (open-multi-agent):** Original system triggered `cascadeFailure()` marking all downstream tasks failed on any single error. Replaced with configurable `retryPolicy` supporting `maxRetries: 3`, exponential backoff, and `retryableErrors` allowlist — [open-multi-agent/issue#3](https://github.com/open-multi-agent/open-multi-agent/issues/3)
- **Anthropic SDK community discussion:** miaoquai.com tiered approach: exponential backoff (1s→2s→4s→8s capped at 60s + 30% jitter), circuit breaker at 5 consecutive failures, separate retry configs for idempotent operations, and state cleanup on mid-task failure — [anthropics/anthropic-sdk-python/discussion#1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Gist (Anthropic + OpenAI):** "Verify before building" — always check the previous session didn't break things. Checkpointer-based recovery from durable state, not from scratch. "Separation of generation from evaluation" — agents can't objectively judge their own work. — [GitHub Gist](https://gist.github.com/celesteanders/21edad2367c8ede2ff092bd87e56a26f)
- **CockroachDB Labs:** Agent loops move from one-off assistance to operational execution. Reliable loops require transactions, serializable isolation, and persistent workflow state — corrupted memory gets worse with each iteration, not better. — [CockroachDB Labs Blog](https://www.cockroachlabs.com/blog/agent-loops-production-database-patterns/)
- **LangGraph production guidance:** `InMemorySaver` is for tests only. Production requires `PostgresSaver` or `SqliteSaver`. Error recovery loop explosion (LLM tries again with slightly different wrong arguments → same error → repeat) requires explicit structural detection, not just count-based limits.
- **Research synthesis:** 70% of organizations use AI agents in operations; two-thirds require human verification. Confidence thresholds of 80–95% (per risk domain) trigger escalation. 70% accuracy from a degraded agent still beats 0% from a crashed one. — [Zylos Research](https://zylos.ai/en/research/2026-01-30-ai-agent-human-handoff)

## Gotchas

- **Confusing crash detection with loop detection.** A crashed agent gives you an error. A looping agent gives you silence. You need separate monitoring for each.
- **Using InMemorySaver in production.** State lives in RAM. One restart and your agent has no idea where it was. Switch to a durable checkpointer before you ship.
- **Assuming retries are always safe.** Non-idempotent operations (payments, sends, writes) can double-execute. Build idempotency keys into retry logic.
- **Making every circuit breaker global.** A rate limit on one tool shouldn't trip the breaker for the entire agent. Scope breakers per tool or per service.
- **Escalating to humans without context.** "The agent failed" is not actionable. Push the full tool trace, decision history, and what it was trying to accomplish.
