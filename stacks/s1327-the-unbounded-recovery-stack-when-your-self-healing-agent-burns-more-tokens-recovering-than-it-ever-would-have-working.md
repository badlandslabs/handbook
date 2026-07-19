# S-1327 · The Unbounded Recovery Stack — When Your Self-Healing Agent Burns More Tokens Recovering Than It Ever Would Have Working

Your agent hit an error. It retried. The retry failed. It retried again with backoff. The backoff succeeded — except the backoff itself triggered a compaction cycle, which failed because the context was too large, so a sub-agent fired to compact, which generated a large context, which triggered another compaction. Somewhere around step 12 of this spiral, your monitoring shows "agent running normally." You are now burning $40/hour while producing nothing. This is the unbounded recovery problem: your self-healing mechanisms have no ceiling, and the agent is the last thing in the system that knows something is wrong.

## Forces

- **Recovery loops compound invisibly.** Each individual retry looks correct. The agent is "doing the right thing." The disaster is the composition: 50 retries × 50 backoffs × 5 compaction attempts = an hour of token burn before anyone notices.
- **Standard observability is a flight recorder, not a collision detector.** Latency and token counts answer "what happened," not "is my agent productive right now or burning tokens standing still?" A looping agent can show healthy-looking metrics until the budget hits zero.
- **The escalation ladder is rarely implemented.** Four rungs exist — retry, fallback, degrade, fail-safe — but most agents implement only the first, indefinitely.
- **LLM confidence is systematically miscalibrated for failure.** Models trained with RLHF express highest confidence on incorrect outputs. A claimed 90% confidence in practice maps closer to 75% accuracy. Chain three agents at "90% confidence" and you have ~42% probability that all three steps are correct.
- **Retry storms are the most expensive failure mode.** Unlike a crashed agent that stops billing, a retry storm keeps generating tokens — often $10–50 before a human notices.

## The move

**Implement the escalation ladder with hard caps at every rung.** The core principle: every recovery mechanism needs an escape valve, and the escape valve needs its own escape valve.

### Bounded retry with exponential backoff
- Cap retry attempts per logical operation (typically 2–3). Beyond that, escalate, don't retry.
- Use exponential backoff with jitter: `delay = min(base * 2^attempt + random_jitter, max_delay)`.
- Never retry permanent failures (400, 401, 403, 404). Retry only transient failures (429 rate limit, 500, network timeout).
- Rate-limit-induced retry storms are a distinct pattern from LLM failures — they need their own circuit breaker that halts the agent loop entirely when an external API is down.

### Loop detection via state hashing
- Hash the last N tool call signatures (not just outputs) and detect when the same (tool, args) pair appears 3+ times consecutively.
- A more aggressive variant: hash the agent's visible state (file system diffs, API response patterns) and flag when no observable state change has occurred in N steps.
- Per-agent step counters are insufficient — the loop must be detected across the full agentic loop, including sub-agents spawned by tools like `parallel()`.

### Graceful degradation (not graceful failure)
- When the primary path fails, fall back to a lower-quality but bounded alternative: a smaller model, a cached result, a heuristic, or a human-in-the-loop queue.
- Degrade feature-by-feature, not whole-agent. The agent should still complete the task — just without the failed capability.
- Asynchronous escalation is production-default for degraded agents — blocking on a synchronous human approval breaks under real infrastructure (AWS API Gateway timesouts at 29 seconds; serverless functions expire mid-queue).

### Dead-end recovery
- Implement explicit success conditions that the agent must verify, not just assume. If the agent completes a task, it should confirm the output exists / the state changed / the API returned success before exiting.
- Persist checkpoint state at each major step so a failed agent can resume from the last completed step rather than restart from scratch.
- For long-running agents, emit heartbeat signals (to a queue, a log, a checkpoint) that external monitoring can use to detect stale agents.

### Compaction guardrails
- Context compaction is the most dangerous self-healing mechanism because it operates at the largest token scale. A compaction that fails to compact (context too large) can trigger re-compaction in a loop.
- Cap compaction attempts (Claude Code added `max_compact_errors` for exactly this reason — a missing cap previously let 1,279 sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a day).
- Disable background compaction when the user is idle (the compaction agents fire on idle sessions, burning tokens while the user sleeps).

## Evidence

- **GitHub Issue (anthropics/claude-code #72672):** `parallel()` workflow with ~98 planned `agent()` calls triggered a runaway retry storm when external API rate limits hit. Consumed **8.6M tokens in 226 seconds**, hit the **1000-agent hard cap**, returned **zero usable output**. Root cause: unbounded retry on 429-style rate-limit responses with no circuit breaker. — [URL](https://github.com/anthropics/claude-code/issues/72672)
- **GitHub Issue (anthropics/claude-code #41198):** 5 context compaction agents fired within 5 minutes on an idle session with no user input. Each carried ~19MB/~200K tokens. Estimated **~1M tokens burned in 5 minutes** while user was asleep. Compaction exceeded context limits, triggering re-compaction in a loop. — [URL](https://github.com/anthropics/claude-code/issues/41198)
- **GitHub Issue (anthropics/claude-code #26171):** Agent stuck in unbounded thinking loops after compaction — burns tokens indefinitely without producing tool calls, requires manual escape. — [URL](https://github.com/anthropics/claude-code/issues/26171)
- **Blog post (AgentMarketCap, April 2026):** Documents the central paradox: a missing retry cap let 1,279 Claude Code sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. Notes Gartner estimate: **40% of agentic AI projects will be abandoned by 2027** — not because models failed, but because **pipelines failed**. — [URL](https://agentmarketcap.ai/blog/2026/04/10/self-healing-agent-pipelines-2026-production-architectures-autonomous-failure-recovery)
- **Blog post (DigitalApplied, June 2026):** Documents the escalation design gap: LLM confidence systematically miscalibrated (claimed 90% ≈ 75% real-world), miscalibration compounds across agent chains (3 agents × 90% → ~42% probability all three steps correct). Proposes action risk classification: read-only → reversible → external → high-risk/irreversible. — [URL](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)
- **Blog post (Focused.io, April 2026):** Error classification matrix for LangGraph: transient (system handles via RetryPolicy) → LLM-recoverable (agent retries with adjusted prompt) → permanent (engineer fixes) → irreversible (human approves). Key insight: "The fix isn't add a try/except. The fix is classifying errors by who can fix them." — [URL](https://focused.io/lab/langgraph-agent-error-handling-production)
- **Guide (SynapseAI):** Loop detection taxonomy: retry-without-backoff, undetected task completion, dependency deadlock. Token burn table: 5 min loop → $4.50–9.00; 15 min → $13.50–27.00; 1 hour → $54–108. — [URL](https://ddaekeu3-cyber.github.io/synapse-ai/guide/loop-stuck-errors)

## Gotchas

- **GitHub stars do not predict production readiness.** LangGraph, CrewAI, and AutoGen each make fundamentally incompatible bets on state management and control flow. All three have documented failure modes around error recovery in their GitHub issue trackers.
- **The 1000-agent cap is not a safety feature — it is a last resort.** When an unbounded retry storm hits it, you've already burned millions of tokens. The cap should never be the thing that stops a loop; a step-count or token-budget guard should stop it first.
- **Async human-in-the-loop breaks under real infrastructure.** Blocking on synchronous approval fails at AWS API Gateway (29s timeout), serverless functions (expiration mid-queue), and dropped connections. Production escalation queues must be async-first.
- **Rate-limit retry storms and LLM failure loops are different failure modes.** They need different circuit breakers. Retrying a rate-limited external API with exponential backoff is correct; continuing to spawn `parallel()` sub-agents when the underlying API is down is not.
- **Idle-session agents still burn tokens.** If your agent spawns background compaction or maintenance sub-agents, gate them on actual user activity — not just "no new user message" — or you will wake up to a bill from a sleeping session.
