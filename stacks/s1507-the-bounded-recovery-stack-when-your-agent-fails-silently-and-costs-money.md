# S1507 · The Bounded Recovery Stack — When Your Agent Fails Silently and Costs Money

Your agent is still running. It's calling tools. It's producing output. It just isn't getting closer to the goal — and it will burn through your budget until something stops it.

## Forces

- **Silent failure is the norm.** The most dangerous agent failures raise no exception. A malformed JSON tool response returns HTTP 200. A confident hallucination gets passed downstream as ground truth. The agent keeps running and nobody notices until the invoice or the complaint.
- **LLMs make agents non-deterministic in exactly the places where reliability matters most.** Tool selection, retry decisions, and termination signals are all stochastic. A prompt tweak or context shift can flip an agent from working to looping — without any code change.
- **Retries amplify outages, not just survive them.** Traditional retry logic assumes sequential, recoverable failures. Agentic retries are automatic and parallel. Loose budgets amplify cascading failures instead of riding through them.
- **Multi-agent systems multiply every failure mode.** Studies across production deployments report 41%–86.7% failure rates without formal orchestration. With orchestration: 3.2x lower. The seams between agents — handoffs, shared state, ordering assumptions — are where most multi-agent failures originate.
- **Traditional try-catch doesn't apply.** An agent behaving incorrectly raises no exception. You must detect and recover from correct-looking failures.

## The Move

### 1. Classify errors and budget each class separately

Every error class gets its own retry contract before you write the first LLM call: exception type, max attempts, backoff curve, budget ceiling. A rate-limit error and a malformed-output error require different responses. Wrapping the whole run in one try/except is how retry storms start.

Real-world budget: Cordum uses a 50-attempt cap with 1s–30s exponential backoff, which stretches worst-case failure realization to ~25 minutes — enough to alert but not enough to spiral.

### 2. Detect loops at two levels: syntactic and semantic

Single-level loop detection (counting repeated tool calls) misses the most expensive failure mode: the **semantic loop**, where the agent takes different actions each iteration but never advances toward the goal. Effective detection combines both:

- **Syntactic:** repeated identical or near-identical tool calls, same state hashes
- **Semantic:** check if the agent's reasoning state (goals declared, gaps identified) is converging or diverging — not just whether the tool call signature changed

Four loop types to recognize: hard loop (same action → same result), soft loop (similar actions), retry storm (same step retried repeatedly), semantic loop (reasoning stalls despite varying actions).

### 3. Wire structured self-correction into the agent loop

The Aider pattern — `edit → validate → reflect → retry` — is the most proven self-correction loop for code-generating agents. When a tool call fails or output is malformed:

1. Parse and validate the output immediately at the tool layer
2. Feed structured error feedback back to the LLM (not just "no match" — the exact line that didn't match, what was expected, what was found)
3. Retry up to a hard cap (3 is typical for edit operations; track separately from general tool retry budgets)
4. Surface cumulative failure history, not just the last error

Hermes Agent adopted this pattern via [PR #13435](https://github.com/NousResearch/hermes-agent/issues/536), resolving the gap where every failed edit was a fresh debugging exercise.

### 4. Treat multi-agent handoffs as the highest-failure boundary

Formal orchestration (3.2x lower failure rate than unorchestrated) is not optional — it's the cost of admission. Specific handoff failures to engineer for:

- **Context amnesia:** subagents start fresh; only what you explicitly pass survives the handoff
- **Shared state conflicts:** agents overwrite or ignore each other's changes
- **Ordering assumptions:** agents assume tasks complete in a specific sequence
- **Cascading propagation:** one agent's confident error becomes another agent's input

The "context dump" approach (pass everything) causes "lost in the middle" — models exhibit U-shaped accuracy, remembering the first and last items, forgetting the middle. Instead: summarize at handoff, use a structured handoff schema, include failure context alongside task context.

### 5. Build circuit breakers at the system level, not just the tool level

A circuit breaker at the agent level (not just the API level) trips when the agent's behavior pattern indicates systemic failure — repeated semantic loops, exceeding step budgets, or coordination failures in multi-agent setups. The circuit breaker should halt the entire run, checkpoint state for resume, and alert. A tool-level breaker alone misses the highest-cost failure modes.

## Evidence

- **Forge guardrails benchmark:** An 8B model with Forge guardrails achieves 99.3% on multi-step agentic tasks vs. 53% without — error recovery scores were **0% for every model tested** without guardrails. Five layers: retry nudges, tool call validation, output schemas, context windows, and termination criteria. — [HN Show HN · Forge by Antoine Zambelli (AI Director, Texas Instruments)](https://news.ycombinator.com/item?id=48192383) | [GitHub: antoinezambelli/forge](https://github.com/antoinezambelli/forge)

- **Loop detection failure in the wild:** A financial services company running autonomous trading agents burned through $12,000 in compute over a weekend maintenance window. Their retry loop counted *distinct error types*, not total iterations — so retrying different errors was counted as making progress. Three days, 47,000 failed API calls. Loop detection that only watches for repeated identical calls misses the most expensive variant. — [TrackAI · Loop Detection & Breaking](https://trackai.dev/tracks/observability/debugging-tracing/loop-detection/)

- **Multi-agent failure taxonomy:** Production deployment studies: specification failures ~42% of incidents, coordination deadlocks ~37%, memory/state poisoning ~21%. With formal orchestration: 3.2x lower failure rate. Most common post-mortem finding: *"the wrong context reached the wrong agent at the wrong time"* — not *"the LLM gave a bad answer."* — [Tian Pan · Multi-Agent Handoffs](https://tianpan.co/blog/2025-11-02-multi-agent-handoffs-reliable-coordination) | [GitHub Blog · Engineering Reliable Multi-Agent Workflows (Feb 2026)](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/)

- **Failure handling matrix:** The gap between agent demos and production is entirely failure handling. A reference implementation maps naive loop behavior to recovery patterns: retry with exponential backoff + jitter for transient errors, circuit breaker for dependency failures, watchdog for hung requests, checkpoint/resume for interruption recovery, budget governor for runaway loops. — [GitHub · hailports/self-healing-agent](https://github.com/hailports/self-healing-agent)

## Gotchas

- **Counting errors, not iterations, is a trap.** Retry logic that tracks distinct error types rather than total attempts lets the agent burn through budget by cycling through different-but-equally-failed attempts. Count iterations.
- **Retries are budget policy, not reliability policy.** Most teams tune retries before deadlines. That order is backwards. The deadline budget defines what retries are allowed to spend — not the other way around.
- **"Works in demo" is meaningless for failure handling.** Agentic failure modes only emerge under real conditions: rate limits, flaky APIs, partial service outages, and tool responses that succeed technically but fail semantically. Test your recovery paths under degradation, not under ideal conditions.
- **Handoff schemas rot.** As agents evolve, handoff schemas between them drift out of sync. Treat the handoff interface with the same versioning discipline as a public API.
