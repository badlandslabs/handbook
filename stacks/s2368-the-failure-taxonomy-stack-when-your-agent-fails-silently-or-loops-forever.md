# S-2368 · The Failure Taxonomy Stack

When your agent silently loops for 35 minutes with no error, makes the same tool call 12 times, or fails in a way that returns HTTP 200 — and your monitoring shows green because nothing threw an exception.

## Forces

- Agents fail in ways traditional software doesn't: semantically broken tool calls that technically succeed, confident reasoning chains producing wrong answers, partial writes that look complete. Traditional `try/catch` doesn't cover these failure classes.
- A 10-step pipeline with 85% reliability per step succeeds only ~20% of the time end-to-end. Engineers see 85% step accuracy in benchmarks and assume 85% run success — the compounding math is not intuitive and doesn't appear in a debugger.
- 41–86.7% failure rates across 7 multi-agent frameworks were documented in a study of 1,642 execution traces (Berkeley/MIT/Stanford, MAST taxonomy, March 2025). Of those failures: ~42% are specification failures, ~37% coordination breakdowns, ~21% verification gaps.
- Stuck agents and looping agents fail silently — they don't throw exceptions. Your monitoring dashboard looks healthy while the agent is burning budget on nothing.
- Iteration caps (`max_iterations = N`) prevent infinite loops but treat a productive 20-step agent identically to a broken one calling `search("weather")` 20 times.

## The move

Build a layered failure infrastructure. Four tiers, applied in order from cheapest to most expensive:

**Tier 1 — Classify errors by retryability, not just by type.** Not all errors should retry. Auth failures, validation errors, and policy blocks are stop rules — retrying them creates loops. Rate limits, network timeouts, and temporary service unavailability are transient and warrant retry with exponential backoff + jitter.

**Tier 2 — Hard iteration caps with context-aware escalation.** Set `MAX_STEPS = 12` (LangGraph: `recursion_limit=12`). When the cap is hit, do not just stop — capture the full state, surface a clear failure message, and persist the checkpoint so the next run can resume without redoing completed work.

**Tier 3 — Detect loops before the cap is hit.** Track repeated actions within a session: same tool call with same parameters, same file edited repeatedly without net progress, same reasoning step. Inject a prompt nudge or switch strategy rather than waiting for the iteration counter. This catches the 8th repetition as a problem, not the 12th.

**Tier 4 — Instrument for silent failures.** Watchdog timers catch agents that produce no output for N minutes. Output validators confirm semantic correctness (not just HTTP 200). Cost circuit breakers stop execution before runaway spending.

## Evidence

- **MAST Taxonomy (Berkeley/MIT/Stanford):** Analyzed 1,642 multi-agent execution traces across 7 frameworks. Found 41–86.7% failure rates. Categorized failures as specification (~42%), coordination (~37%), verification (~21%). — [arXiv:2503.13657](https://arxiv.org/abs/2503.13657v2)
- **LayerLens (compounding math):** A pipeline with 85% per-step reliability achieves only ~20% end-to-end success. 68% of practitioners cap agents at ≤10 steps, which mathematically guarantees failure on anything non-trivial. — [layerlens.ai/blog/compounding-failure-math-agents](https://layerlens.ai/blog/compounding-failure-math-agents)
- **ClaudePedia (escalation ladder):** Retry → Fallback → Degrade → Fail. Auth, validation, and policy errors are stop rules — treating them as transient failures is the fastest way to create a retry loop. — [claudepedia.dev/docs/error-recovery](https://claudepedia.dev/docs/error-recovery)
- **PADISO (retry cost):** A well-designed retry policy vs. no policy produces 10–50x cost-per-task difference and 100x time-to-resolution improvement on failures. Exponential backoff with jitter reduces retry storms by 60–80%. — [padiso.co/blog/tool-errors-retries-claude-recovery](https://www.padiso.co/blog/tool-errors-retries-claude-recovery)
- **AgentCenter (silent failure):** Stuck (blocked, waiting, not retrying) and looping (actively cycling through same decisions) require different detection approaches. Stuck looks idle; looping looks busy. Standard monitoring misses both. — [agentcenter.cloud/blogs/how-to-detect-agent-stuck-or-looping](https://www.agentcenter.cloud/blogs/how-to-detect-agent-stuck-or-looping)
- **Lightrains (loop anatomy):** Simple loop (model → tool → state → model) is easy to build. The failure modes are: no completion rule (infinite repetition), no progress gate (same actions repeated), no context budget (window overflow), no semantic validation (wrong answer with no error). — [lightrains.com/blogs/production-ai-agent-loops-engineering](https://lightrains.com/blogs/production-ai-agent-loops-engineering)
- **Blog post (loop cap pattern):** Recommended `MAX_STEPS = 12` as a practical default. Fallback paths (switch to a different tool or strategy) prevent hard stops from killing recoverable work. Checkpoint state on cap-hit so the next run resumes from the last good state, not from scratch. — [blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)

## Gotchas

- **Treating all errors as transient is the most common mistake.** Auth failures, validation errors, and policy blocks will never succeed with more retries. They need escalation to a different path, not backoff.
- **Hard caps without checkpointing kill recoverable work.** An agent at step 11/12 that hits the limit and has its state discarded is not recoverable — it's just failed. Persist the state before failing.
- **Output validation and HTTP status are independent checks.** A tool returning 200 with an empty schema, a wrong result, or a partial write is a semantic failure, not a technical one. Your error handling needs to validate the *meaning* of the response, not just its status code.
- **Side-effecting tools without idempotency keys cannot be safely retried.** If your agent calls a tool that sends an email, creates a ticket, or writes to a database and it fails mid-execution, a blind retry may duplicate the action. Use idempotency keys or checkpoint before calling.
