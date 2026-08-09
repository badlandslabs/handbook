# S-2371 · The Stuck vs. Looping Stack

When your agent appears active but produces nothing — or when you get the bill before the alert.

## Forces

- **Stuck and looping look identical externally**: Both show "in progress" status. Both consume resources. Only one is actually broken.
- **Retrying is not free for agents**: A microservice retry costs ~few KB. An agent retry re-processes the full conversation context through an LLM. 10 retries ≠ 10x cost — it can be 200x.
- **The retry budget is a design constraint, not an afterthought**: If the agent can't get parameters right in 2 tries, it won't in 10. Retrying logic failures burns tokens on a terminal state.
- **86% of agent failures are recoverable** — but only if the harness knows *which* 86% to retry and which to escalate. Retrying a hallucination doesn't fix it.

## The Move

Separate detection of stuck (halted) vs. looping (active but unproductive), then climb a recovery ladder that matches severity.

### Loop Detection (Four Types)

- **Exact repeats**: same tool, identical arguments
- **Fuzzy loops**: same tool, minor argument variations
- **Cycles**: A→B→C→A repeating sequence
- **Output stagnation**: identical responses across N consecutive calls

Detect via conversation fingerprinting (hash recent tool calls + outputs), output delta tracking, and cycle-graph analysis. All four patterns are addressable — but with different fixes.

### Recovery Ladder (Escalate Until It Works)

1. **Nudge**: inject a targeted correction into the context (e.g., "Note: the last 3 attempts to call `search_db` returned empty. Try a different query or confirm the database is reachable.")
2. **Replan**: clear the agent's recent action history and re-prompt with the original goal + current state snapshot
3. **Reset**: checkpoint rollback to last known good state — discard current trajectory, restore working memory and tool results from before the failure point
4. **Fallback**: graceful degradation — downgrade to a simpler model, cached response, or static template
5. **Escalate**: human handoff — surface the failure mode, what was attempted, current state, and let a person decide

### Retry Budget as First-Class Design

- Allocate: max retries per tool, max tokens for recovery, max total task timeout
- Never retry a 400/401 without fixing the root cause first
- Never retry a hallucination — use an LLM-as-judge validation layer instead
- Use idempotency keys on financial/critical operations to prevent duplicate side effects on retry storms

### Circuit Breaker for Agentic Workflows

- **Trip**: 5 consecutive failures OR >30% error rate in a 10-minute sliding window
- **Open**: reject requests immediately, don't queue them
- **Cooldown**: 30–60 seconds before half-open testing
- **Close**: resume normal operation when error rate drops below threshold
- Per-tool circuit breakers prevent a flaky downstream API from cascading into every agent workflow

## Evidence

- **HackerNews Show HN (2025):** Developer lost $200 from an agent loop on a web scraping task. Built per-tool budget controls as a result — "I left an agent running and came back to a $200 bill." — https://news.ycombinator.com/item?id=46991656

- **Harsh Rastogi (AI Product Engineer, Modelia.ai & Asynq.ai, March 2026):** Asynq.ai's candidate evaluation agent hallucinated tool parameters and got stuck in loops, costing 3× the budget. Modelia.ai's image pipeline approved obviously flawed images while optimizing for "workflow completion." Both failures had identical root cause: the harness had no recovery ladder. — https://harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns

- **GitHub / Anthropic SDK Discussion (April 2026):** Practitioner running 5 autonomous agents 24/7 for 95+ days describes retry patterns: exponential backoff (1s→2s→4s→8s, cap at 60s with 30% jitter), circuit breaker trip after 5 failures / 30s cooldown, idempotency keys on all write operations. A cron timeout caused 50 duplicate Discord posts within 5 minutes before idempotency was added. — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

- **OpenHelm (July 2024, updated):** Production case study: proper error handling (retry + circuit breaker + fallback + timeout management) increased agent reliability from 87% to 99.2% — a 14× reduction in failures. — https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents

- **The Turtle Blogs / HackerNoon (July 2026):** Real incident: refund agent called an order lookup tool that started returning timeouts. Retried. Timed out. Retried. 400 times in 5 minutes. No alert fired. No error surfaced. Support ticket stayed "in progress." The agent was busy by every external metric but was producing nothing. — https://hackernoon.com/your-agent-is-not-stuck-it-is-looping-there-is-a-difference-and-it-costs-you-either-way

## Gotchas

- **Don't retry on silence**: A timeout is not a failure — it's ambiguity. Query the tool's actual state before retrying. Immediate retry on timeout creates duplicate side effects.
- **Slow-but-converging ≠ stuck**: Recovery should only fire when progress metrics are flat across N heartbeats. A healthy agent making small increments is not broken.
- **Cheap fixes fail on wrong loop types**: A nudge (injecting a correction) breaks a repeater. It does nothing for a wanderer or cycle. Match the recovery action to the detected pattern.
- **Token budget kills loops faster than logic**: Per-tool budget caps are simpler and more reliable than pattern detection alone. When in doubt, cut the agent off.
