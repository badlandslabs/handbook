# S-1835 · The Escalation Boundary Stack — When Your Agent Loops Forever Because It Doesn't Know When to Give Up

An agent is stuck in a loop: it can't fix the database schema mismatch, so it tries again. And again. Each attempt costs money, burns tokens, and moves no closer to resolution. The error isn't a crash — it's a confident, ongoing failure that looks like work. This is the escalation boundary problem: agents have no native signal for "I should stop and ask for help," and retry logic without a ceiling becomes an infinite loop.

## Forces

- **The LLM retry impulse is learned behavior.** Models are trained to try again when output is wrong. In tool-calling loops, this manifests as the agent re-executing the same failed tool with slightly different parameters — until the context window fills or the API bill arrives.
- **Error classification drives recovery quality, not error volume.** Retrying a 401 authentication failure wastes resources identically to retrying a 429 rate-limit — but one is recoverable with different input, the other with different timing. An agent that treats all errors the same applies the wrong recovery every time.
- **Step caps feel like surrender but prevent catastrophe.** Hard limits (e.g., `MAX_STEPS = 12`) are the single most important guardrail an agent can have — and engineers resist them because they feel like admission of failure.
- **Environment containment beats supervision fatigue.** Human-in-the-loop approval works until humans approve 93% of prompts without reading them. Automated environment-level containment (sandboxing, read-only guards, API key isolation) now does the heavy lifting that human oversight cannot sustain.

## The move

Build a layered escalation architecture where each layer handles a distinct failure class:

- **Classify before retry.** Map each error to a closed `ErrorKind` enum: `TRANSIENT` (retry ok), `PERMANENT` (never retry), `AUTH` (fix credentials then retry), `RATE_LIMIT` (wait then retry), `SEMANTIC` (tool succeeded but output is wrong — requires re-planning). The classification is the most impactful decision in the recovery path.

- **Tiered retry with exponential backoff + jitter.** Transient errors: retry at 1s → 2s → 4s → 8s (max 3 attempts), with 30% random jitter to prevent thundering herd. Separate retry configs for idempotent vs. non-idempotent operations — non-idempotent calls need idempotency keys or request deduplication before retrying.

- **Hard step cap.** If the agent doesn't complete in N steps (LangGraph: `recursion_limit=12`), stop the loop and escalate. The cap is not a failure — it is the boundary that makes recovery possible.

- **Circuit breaker.** Trip after 5 consecutive tool failures or >30% error rate in a 10-minute window. During cooldown, fail fast and surface the error to a human rather than continuing to hammer a degraded service.

- **Checkpoint + rollback.** For long-running multi-step tasks, snapshot state at each major step. On failure, rollback to the last checkpoint rather than restarting from scratch. This prevents a partial write from corrupting downstream state.

- **Fallback chain, not a single fallback.** A degraded but functional response is better than a crash. Define a cascade: primary tool → fallback tool → cached result → human escalation. Each step in the chain should be observable so you know where in the fallback path you ended up.

- **Escalate to a human with full diagnostic context.** When escalation fires, include: what was attempted, what error occurred, what was classified as, how many retries fired, what the state checkpoint shows. A human receiving "the agent failed" does not have enough to resolve the issue. A human receiving "the agent failed after 3 retries on the payment gateway with a 503 — rate limit fallback not available for this tool — last checkpoint: order confirmed but payment pending" can act.

## Evidence

- **Engineering blog:** Anthropic's "How We Contain Claude Across Products" — 93% human approval rate on permission prompts demonstrates that supervision fatigue makes human-in-the-loop unreliable at scale. Their fix: automated environment-level containment (sandboxing, read-only guards, blast-radius limits per capability tier) handles 83% of overeager-behavior catches automatically, with 17% still slipping through. — [anthropic.com/engineering/how-we-contain-claude](https://www.anthropic.com/engineering/how-we-contain-claude)
- **HN Ask thread:** "Ask HN: How are you testing AI agents before shipping to production?" — harperlabs identified 7 core failure modes including "cascade loop" (retrying a failure that was caused by a prior retry) and "context limit surprises" (agent silently misbehaves when context fills, no error thrown). Community responses emphasize hard step caps and circuit breakers as the most universally applicable patterns. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **GitHub discussion (Anthropic SDK):** Practitioners at miaoquai.com described a tiered approach: exponential backoff with jitter, separate circuit breaker per tool (trip at >30% error rate over 10 min), model fallback chain (Claude → GPT → local), and idempotency keys to prevent duplicate operations on retry. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

## Gotchas

- **Retrying without classifying is worse than not retrying.** A 401 retried 3 times is 3 wasted calls plus the same auth failure each time. Classify first.
- **Step caps without escalation context turn a controlled failure into a silent one.** If your agent hits its step limit and just stops, the user has no idea what happened or what to do next.
- **Circuit breakers must be per-tool, not global.** A payment gateway failure shouldn't trip the breaker for a separate document service. Per-tool isolation prevents cascading shutdowns.
- **Checkpointing overhead must be justified.** For 3-step tasks, checkpointing adds latency without meaningful recovery benefit. Start checkpointing at 5+ steps or when the task has side effects (writes, API calls, state mutations).
- **Fallback chains that end in "return an error" are not fallback chains.** Every step in the chain should be a degraded but useful output, not just progressively more apologetic error messages.
