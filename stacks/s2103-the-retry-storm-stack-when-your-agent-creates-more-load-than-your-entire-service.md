# S-2103 · The Retry Storm Stack — When Your Agent Creates More Load Than Your Entire Service

You have an agent in production. It encounters a transient error. It retries. The error persists. It retries faster. Within an hour it has made 50,000 requests and your database is down — not from the original error, but from the recovery attempt.

## Forces

- **Failure types are heterogeneous but agents treat them identically.** Rate limits need backoff. Timeouts need shorter retries. Auth errors need zero retries. A single retry policy applied to all failure types will either over-retry or under-retry most of them.
- **A stuck agent looks identical to a working one.** Both are quiet. The API calls succeed. The logs show activity. The task never completes — but you don't know that until someone notices.
- **Retry budget and deadline budget are the same budget.** If you tune retry policy before setting a hard run deadline, your agent can outlive operator intent — retrying long after the result would be useful.
- **The thing best placed to break a loop is not the model inside it.** Reasoning about "this is my seventh attempt" requires cross-turn awareness the model doesn't have. You need a watcher outside the loop, counting.

## The Move

A layered failure-handling architecture with three disciplines: **classify before retrying**, **budget before looping**, and **climb a recovery ladder** once stuck.

### Classify failures by retry-worthiness

| Failure type | Action |
|---|---|
| Transient (network blip, single 500) | Retry with backoff |
| Rate limit (429) | Honor Retry-After header; if absent, exponential backoff |
| Auth/token expired (401) | Refresh token, retry once; if it fails again, stop |
| Hard semantic failure (tool returned wrong data, malformed output) | Don't retry — fix the prompt or the tool schema |
| Capacity pressure (service degrading) | Reduce concurrency, don't retry faster |

### Layer three timeout budgets

1. **Run budget** — hard upper limit for the entire task. If the agent doesn't finish by then, stop and report. This is set first, before any retry policy.
2. **Safety budget** — per-step timeout (e.g., 2–3 seconds per tool call). Fails the step if exceeded.
3. **Step budget** — individual API call timeout. If the call doesn't return in N seconds, abort and retry or fall back.

The retry policy lives *inside* these budgets: retries consume the run budget. When the budget is spent, the agent stops — not when it finally succeeds or fails.

### Wrap tools with per-tool circuit breakers

Each external tool (search API, code executor, database client) gets its own failure-tracking state machine:

```
Closed → (failures ≥ threshold) → Open → (cooldown elapsed) → HalfOpen → (probe succeeds) → Closed
                                                                         → (probe fails) → Open
```

When a tool is Open, the agent skips it, tries an alternative, or degrades gracefully — it doesn't keep hammering the broken endpoint. Threshold tuning is the hard part: too tight and you block calls that would succeed; too loose and you waste tokens on guaranteed failures.

### Build a recovery ladder for stuck loops

Once loop detection fires (repeated identical tool calls, repeated identical file edits, zero progress metric over N steps), climb a bounded recovery ladder:

1. **Nudge** — inject a prompt: "You've edited this file 4 times without the test passing. Consider a different approach."
2. **Replan** — ask the agent to re-generate its plan from scratch given current state, breaking the local-optimum trap.
3. **Escalate** — hand to a supervisor agent with full context to take a higher-level view.
4. **Reset** — clear conversation history, re-initialize with current state as starting point, restart clean.
5. **Handoff** — surface to a human with a summary of what was attempted and what failed.

Each rung is more expensive. Cheap fixes fire first.

## Evidence

- **r/AI_Agents incident post:** Agent deployed to production entered a retry loop executing ~50,000 requests/hour, bringing down the production database. Root cause: no distinction between failure types — the agent couldn't tell that a hard error meant stop, not retry faster. The retry loop was described as "the classic failure mode for autonomous agents. LLMs often hallucinate that tweaking one parameter will fix a hard error, leading to that 50k request spiral." — [r/AI_Agents, Feb 2026](https://old.reddit.com/r/AI_Agents/comments/1r9cj81/our_ai_agent_got_stuck_in_a_loop_and_brought_down/)
- **Cordum engineering blog:** "Deadline budget defines what retries are allowed to spend. Wrong order: tune retries first, deadlines later. Right order: set deadline budget first → then define retry policy within that budget." Documents three-layer budget model (run, safety, step) and notes that a 50-attempt cap with 1s–30s exponential backoff can stretch failure realization to ~25 minutes — but only if the run budget allows it. — [Cordum Blog, Apr 2026](https://cordum.io/blog/ai-agent-timeouts-retries-backoff)
- **agentpatterns.ai (adopted pattern):** Loop detection middleware tracks repeated file edits within a session and injects a prompt nudge when repetition crosses a threshold. Credited for moving LangChain from rank 30 to rank 5 on Terminal Bench 2.0 without changing the underlying model. The recovery ladder (nudge → replan → escalate → reset → handoff) is documented as a bounded escalation path. — [agentpatterns.ai, Jun 2026](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **OpenHelm (Max Beech, founder):** "Not all errors are equal: rate limits need backoff; timeouts need shorter retries; auth errors need no retry." Covers exponential backoff with jitter as baseline, circuit breakers for cascading failure prevention, and a fallback chain: primary model → cheaper model → cached response → graceful error message. — [OpenHelm Blog, Nov 2025](https://openhelm.ai/blog/ai-agent-retry-strategies-exponential-backoff)

## Gotchas

- **Retrying on semantic failures is the most expensive mistake.** When a tool returns technically-valid but wrong data, the agent retries the same bad approach with the same bad input. Set a cap and escalate, don't loop.
- **The Retry-After header is authoritative — ignore it at your peril.** When an API explicitly tells you to wait 60 seconds, exponential backoff that retries sooner just extends the outage. Honor the header.
- **Progress metrics must measure real work, not activity.** API call counts and log volume are activity proxies. They go up during productive loops and stuck loops. Use "tests resolved," "items checked off," "unique sources found" — things that only increase on forward progress.
- **Circuit breaker half-open state is the most commonly broken transition.** Most implementations go Open → Closed on cooldown elapsed, skipping the probe. Without a probe, the breaker never learns whether the tool is actually healthy.
