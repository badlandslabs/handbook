# S-813 · The Agent Dead-End Stack: Loop Detection, Budget Fences, and Graceful Surrender

An agent that says "successfully completed" while running the same failing tool call for the 47th time is not a broken model — it's a missing safety layer. The dead-end stack covers the detection and escape mechanisms that prevent agents from burning resources indefinitely when they are stuck, looping, or have hit a genuine impasse.

## Forces

- **Agents fail forward, not backward** — unlike a crashed process, a looping agent consumes resources while appearing active. The system sees continued token generation, not a failure.
- **"Done" is self-reported and unverified** — the agent decides when to stop. When that decision is wrong, nothing inside the agent loop fires an alarm.
- **Silence is the worst failure mode** — no exception, no crash log, no alert. Just a task that never finishes and nobody notices until the invoice arrives.
- **Retry amplifies outage, not just attempts** — when a dependency is slow or degraded, backoff-free retries create synchronized herd effects that extend the failure window instead of riding through it.

## The move

Detection must be external to the agent loop — you cannot trust the agent to know it's stuck.

**Layer 1 — Hard budget fences (floor, not target):**
- `max_steps`: cap loop iterations. Most real tasks complete in 3–10 steps; if you're hitting 30+, something is wrong regardless of whether the agent thinks it's making progress.
- `max_tokens`: cumulative spend limit per run. Abort before the model halts on context overflow — by then the failure is already expensive.
- `timeout`: wall-clock deadline for the entire run. If an agent takes longer than 60–90 seconds for a task designed for 10, something is stuck.
- Log every step: tool called, input, output, token count. Post-mortems require the trace.

**Layer 2 — Semantic loop detection (smarter than count):**
- Track the last N tool calls. Flag when the same tool is called with identical or near-identical arguments 3–5+ times consecutively.
- Measure text similarity between consecutive agent reasoning blocks. Jaccard similarity > 0.75 over 3+ consecutive turns signals repetition.
- Detect oscillation: agent calls Tool A → Tool B → Tool A → Tool B with no forward progress.
- Trap the success-condition illusion: the agent declaring "task complete" is not evidence of completion. External verification (run the tests, check the output file, validate the record) must confirm completion.

**Layer 3 — Circuit breaker with state awareness:**
- Count repeated *failed* actions, not just repeated calls. A tool call that consistently returns malformed output after retry is a different failure mode than a transient timeout.
- Implement a fallback ladder before exhausting retries: primary tool fails → retry with modified params → retry with different tool → return cached result → escalate to human.
- Semantically validate outputs: a tool returning HTTP 200 with hallucinated JSON arguments passed schema validation is still a failure. Check whether the output is fit for purpose, not just structurally correct.

**Layer 4 — Graceful surrender protocol:**
- When all guards fire, the agent should not crash silently. It should: (1) stop immediately, (2) log a structured summary of what it tried, where it got stuck, and why, (3) surface a human-readable "I couldn't complete this" message with enough context to resume without starting over.
- Implement compensating actions for irreversible steps taken before the dead-end: if the agent created a file, sent a message, or modified a record before stalling, register a rollback action upfront.

## Evidence

- **GitHub / Blog post:** Ralph Loop — The Agent Loop Pattern Where AI Tests and Fixes Itself — A bash wrapper (`while :; do cat PROMPT.md | agent; done`) that restarts an AI agent whenever it exits, even if it claimed "successfully completed." The core insight: agents self-report completion without verifying it. The author's experiment produced 1,100 commits across 6 repos overnight. Named after Ralph Wiggum — not particularly smart, but never gives up. — [https://ice-ice-bear.github.io/posts/2026-03-06-ralph-loop-ai-automation/](https://ice-ice-bear.github.io/posts/2026-03-06-ralph-loop-ai-automation/)
- **GitHub repo:** agent-watchdog — "A circuit breaker for AI agents: loop detection, budget guards, graceful halts." Explicitly tracks repeated tool calls, monitors cumulative token burn rate, and halts execution before budget exhaustion. Motivated by the author's own experience of a scheduling system firing multiple heartbeat triggers that queued up silently, each loading new context and burning cost. — [https://github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **GitHub / Skill:** stuck-detection skill on skills.rest — Self-monitoring protocol for agents to maintain a dynamic TaskList tracking recent actions and contexts, detecting repetition, oscillation, and analysis paralysis. Recovery actions include switching strategy, escalating BLOCKED status, and proposing alternative approaches. Configurable similarity threshold (default 0.65) for text comparison between consecutive reasoning turns. — [https://skills.rest/skill/stuck-detection](https://skills.rest/skill/stuck-detection)
- **Engineering blog:** AI Agent Timeouts, Retries, and Backoff in Production — "Retry policy is budget policy. Every extra attempt spends time, queue capacity, and dependency headroom." Cordum currently applies two timeout layers: 2s inner SafetyClient guard, 3s outer scheduler guard. A 50-attempt cap with exponential backoff (1s–30s) can stretch failure realization to ~25 minutes — budget math determines what retries are allowed to spend. — [https://cordum.io/blog/ai-agent-timeouts-retries-backoff](https://cordum.io/blog/ai-agent-timeouts-retries-backoff)
- **Case study:** When Your Agent Fails Silently — Supergood Solutions. Lead-enrichment agent ghosted in production: Clearbit API rate limits hit (10 req/sec free tier × 3 instances), returned 429 silently, agent timed out with no exception and moved on. No crash, no alerts. Result: leads never enriched, customer never notified. Fix: exponential backoff, circuit breakers, fallback chain. — [https://supergood.solutions/blog/when-your-agent-fails-silently](https://supergood.solutions/blog/when-your-agent-fails-silently)

## Gotchas

- **Setting max_steps does not prevent loops — it caps their cost.** The goal is early, loud failure with enough context to understand and fix the underlying cause, not a silent stop at iteration 50.
- **Retry without exponential backoff amplifies partial outages.** When a dependency is degraded, immediate retries create a herd effect. Jitter (randomized delay) is required to spread retry load across time.
- **HTTP 200 is not success.** Hallucinated tool arguments and semantically wrong JSON payloads both return 200. Your error handling must reach past the network into meaning — validate output fitness for purpose, not just response structure.
- **Agents cannot self-correct loops they don't recognize as loops.** Context window summarization causes lossy state: the agent at step 12 sees "you called search_docs with query X (summary)" and re-derives the plan because it has no evidence of previous attempts. External loop detection fills this gap.
- **The cost of a stuck agent is asymmetric and invisible until it's too late.** A looping agent can burn $10–50 in 5–15 minutes before a human notices. Budget fences convert this into a predictable, bounded cost rather than an open-ended one.
