# S-2319 · The Agent Failure Domain Stack — When Your Agent Silently Loops for 35 Minutes

You shipped the agent. It passed every test. Then it ran for 35 minutes on a bad input, spawned 12 redundant subprocesses, and deleted a production database — because nobody told you that "the agent failed" and "the agent crashed" are different failure categories requiring different remedies.

## Forces

- **Agents fail qualitatively differently than services** — no stack trace, no crash, just silence or confident wrongness; by the time you notice, irreversible damage is done
- **Retry-with-backoff is necessary but not sufficient** — it handles transient transport errors but makes resource exhaustion worse during partial outages (the April 2026 retry-loop incident cost an estimated $437K)
- **A 10-step pipeline at 85% reliability per step succeeds ~20% of the time end-to-end** — compounding failure is the default, not the edge case
- **~42% of multi-agent failures are specification failures, ~37% coordination breakdowns, ~21% verification gaps** — teams keep building retry loops for the wrong failure class
- **The model never needs to see transient noise** — every failure that propagates to the LLM is an architectural decision, not an inevitability

## The move

Map failures to domains. Assign each domain a dedicated remedy. Never mix them.

**1. Separate the four failure domains — they have different fixes:**

| Domain | What it looks like | Remedy |
|--------|--------------------|--------|
| **Transient transport** | API timeout, 503, rate limit | Retry with backoff + jitter; classify retryable vs. fatal |
| **Semantic** | Tool returns wrong answer, model hallucinates | Validator + self-correction loop (validator tells the model exactly what was wrong) |
| **Resource** | Pod restarts mid-execution, state lost | Checkpoint/resume; workflow engine for orchestration state |
| **Architectural** | Dependency is down, context window full, infinite loop | Circuit breaker, token budget governor, watchdog timer |

**2. Layer defenses from outermost to innermost** (each catches what the layer above missed):
- NeMo Guardrails input rails block malformed/malicious queries before any processing
- Token budget management fails fast if the prompt exceeds context window before making an API call
- Circuit breaker checks dependent service health before attempting calls; fails open, not closed
- Watchdog timer enforces hard execution timeouts — the agent never loops forever
- Checkpoint writes agent state at defined steps so a restart resumes, not restarts

**3. Treat retry budget as financial budget:**
- Define max retry attempts and maximum total retry duration explicitly
- Cordum uses 50 max scheduling retries (~25 minutes worst case) with exponential backoff 1s→30s + 500ms crypto jitter
- Classify retryable errors (timeout, 503) vs. fatal errors (auth failure, invalid request) — don't retry the latter
- Every retry attempt spends time, queue capacity, and dependency headroom; unthrottled retries amplify partial outages

**4. The checkpointer is not optional:**
- Write agent state (tool results, reasoning trace, current step) to durable storage at defined checkpoints
- On interrupt (pod restart, timeout, manual cancel), resume from the last checkpoint rather than re-running from step 1
- Without this, a 30-step agent that dies at step 28 costs you 28 steps of work every time

**5. Self-correction is a retry with a better error message:**
- Validator checks output shape and semantic correctness after each tool call
- If validation fails, the error message back to the model describes exactly what was wrong — not just "failure"
- The model re-plans from the failure point, not from scratch

**6. Watchdog timers for infinite loops:**
- Track the LLM call count, total tokens spent, and wall-clock time per task
- Set hard caps: e.g., max 20 LLM calls or 60 seconds per task
- When exceeded, interrupt and escalate to human-in-the-loop or mark as failed
- This is the only way to catch the agent that "looks like it's thinking" for 35 minutes

## Evidence

- **Research post (Zylos Research, 2026):** Production AI agents fail silently — looping, spawning redundant subprocesses, accumulating context until the model halts, or taking irreversible actions before humans intervene. Found ~42% of multi-agent failures are specification failures, ~37% coordination breakdowns, ~21% verification gaps. A 10-step pipeline at 85% reliability per step succeeds only ~20% of the time. — [https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **GitHub repo (hailports/self-healing-agent):** MIT-licensed reference loop implementing retries, circuit breakers, watchdog timers, checkpoint/resume, and budget governor as a dependency-free Python package. Key philosophy: "The model never sees the noise — transient failures are absorbed by the retry layer; the model only sees clean observations." — [https://github.com/hailports/self-healing-agent](https://github.com/hailports/self-healing-agent)
- **Blog post (Cordum, April 2026):** "Retry policy is budget policy." Documents production retry budgets: 50 max scheduling retries, exponential backoff 1s→30s with 500ms crypto jitter. Warns that "teams usually tune retries first and deadlines later — that order is backwards." — [https://cordum.io/blog/ai-agent-timeouts-retries-backoff](https://cordum.io/blog/ai-agent-timeouts-retries-backoff)
- **HN Ask post (harperlabs, 2025):** Citing Gartner prediction that 40%+ of AI agent projects will fail by 2027. Documents 7 core failure modes including cascade failures ("tool call #1 fails, agent keeps going, by the time a human sees the result, 47 steps of damage are done"). — [https://news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Adding retries doesn't fix the problem** — it treats every failure as a transient transport error; semantic failures (wrong answer, hallucination) retry into the same wrong answer
- **Infinite loops don't produce error logs** — they produce "thinking..." with no exit signal; you need a watchdog timer, not a log observer
- **Circuit breakers are for dependencies, not for the LLM itself** — you can't circuit-break GPT-4; you can circuit-break the vector DB it queries or the API it calls
- **Checkpoint frequency is a trade-off** — too frequent kills throughput; too sparse means a restart re-does expensive work; benchmark the cost of re-doing a step to calibrate
- **Graceful degradation requires explicit design** — if your agent has no "I can't complete this but here's what I know" mode, it either loops or crashes; neither is acceptable in production
