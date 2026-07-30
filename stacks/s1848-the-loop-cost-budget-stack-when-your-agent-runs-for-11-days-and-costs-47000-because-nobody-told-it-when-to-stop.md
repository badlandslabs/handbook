# S-1848 · The Loop-Cost Budget Stack — When Your Agent Runs for 11 Days and Costs $47,000 Because Nobody Told It When to Stop

Your agent worked exactly as designed. It planned, it called tools, it retried on failure, it called more tools. There was no crash. No exception. No error log. When the invoice arrived, it was $47,000. Nobody noticed the loop until a finance person opened the billing dashboard.

This is the agent loop cost problem: the cost multiplier between a stateless chatbot and a multi-agent workflow is 30x, and the failure mode looks like success from every internal signal.

## Forces

- **Retry compounds context, context compounds cost** — a retry doesn't re-read a fresh prompt; it re-reads the entire accumulated context window. Iteration 1 costs 100 tokens. Iteration 20 costs thousands, because the model reads every prior failed attempt.
- **"Success" signals are cheap to fake** — agents return 200 OK whether they completed the task or cycled through 50 failed attempts. APM was built for exceptions, not silent loops.
- **Cost-per-action is invisible at design time** — engineers prototype with small inputs. Production workloads hit the same code with 100x more data, triggering proportionally more tool calls and iterations.
- **Rate limits don't solve aggregate cost** — a rate limit caps the size of one request. A doom spiral of 100 normal-sized requests costs hundreds of dollars legitimately.

## The Move

Layer cost and loop controls into the agent's execution environment — not into the prompt.

### The five-layer defense stack

**Layer 1 — Define done before the loop starts.**
Write an explicit termination spec before the first agent call: what "success" looks like, what partial success is acceptable, and what constitutes a permanent failure. Without this, the agent will interpret "keep trying" as a license to keep trying.

**Layer 2 — Hard iteration caps that fire regardless of state.**
Set `max_iterations` and `max_time` as circuit breakers, not guidelines. These must stop execution even mid-step — the agent should not be consulted on whether it should continue. A local Python interpreter raising `KeyError` four times in a row will still return a 200 if `max_steps` hasn't fired.

**Layer 3 — Structured error classification for retry logic.**
Distinguish transient errors (network timeout, rate limit) from terminal errors (invalid input, permission denied). Only transient errors warrant retry. Agents that retry terminal errors enter a doom loop — the error never changes, so the same plan gets re-executed with the same result. Feed the model a structured error object with a `is_retryable` flag rather than a raw stack trace.

**Layer 4 — Live cost tracking with hard-stops.**
Track cost, token usage, iteration count, and elapsed time per agent run in real time. Evaluate every LLM call against a configurable rule engine. Hard-stop the agent the instant a rule fires — not at end-of-run, and not via an alert that requires human action. The Fountain City Tech team, running 9 autonomous agents executing ~62 scheduled jobs daily, found that observability tools tell you an agent went wrong *after the fact*. The circuit breaker stops it *while it's happening*.

**Layer 5 — Idempotency keys for safe retries.**
Every agent action that modifies state should carry an idempotency key. Without it, a retry after a partially-completed write can double-apply the action. With it, the retry is safe regardless of where in the loop it fires.

### The cost multiplier reference

| Interaction type | Cost per interaction | Relative cost |
|---|---|---|
| Chatbot (single prompt) | ~$0.04 | 1x baseline |
| Multi-agent workflow | ~$1.20 | 30x baseline |
| Complex multi-agent (many retries) | ~$2.80–$4.00 | 70x baseline |

## Evidence

- **Engineering blog — Fountain City Tech:** The $47,000 LangChain incident: a 4-agent loop ran in a retry spiral for 11 days. A Reddit r/AI_Agents case hit $30,000. Both used retry logic with no cost circuit breaker. — [fountaincity.tech/resources/blog/ai-agent-cost-circuit-breaker](https://fountaincity.tech/resources/blog/ai-agent-cost-circuit-breaker)
- **Open-source tool — AgentBreaker:** A real-time circuit breaker for AI agent loops with a composable rule engine (cost limit, max iterations, max run time, long-run warnings). Tracks cost trajectory live and hard-stops runaway agents before budget is exhausted. — [github.com/vixde8/agentbreaker](https://github.com/vixde8/agentbreaker)
- **Technical guide — FreeCodeCamp (June 2026):** Documents the July 2025 Claude Code recursion incident ($16,000–$50,000 in 5 hours). Prescribes spec-writer, circuit breaker, ledger, and escalation queue as the five Python primitives for production-safe agent loops. — [freecodecamp.org/news/how-to-build-a-production-safe-agent-loop](https://www.freecodecamp.org/news/how-to-build-a-production-safe-agent-loop-from-exit-conditions-to-audit-trails)
- **Incident reconstruction — Steve Kinney / Arxiv (2025):** Reconstructed from post-mortems: an e-commerce refund agent gave away $1.2M in Q3 2025 because no escalation threshold existed for high-risk actions. Recovery mechanisms that work for harmless failures don't work when the failure mode has financial consequences. — [arxiv.org/abs/2604.11378](https://arxiv.org/abs/2604.11378)

## Gotchas

- **`max_tokens` on a single call is not a loop budget** — it caps one request, not 50 sequential requests. The cost problem is aggregate.
- **Soft warnings don't stop anything** — an alert that requires a human to intervene is not a circuit breaker. The agent keeps running while you're reading the notification.
- **Async summarization for memory creates eventually-consistent failure modes** — if your agent writes to a long-term vector store asynchronously, the summary may lag behind the current session. An agent mid-loop reading stale memory may make the same decision it just made.
- **The cost multiplier hits hardest on the retries** — the first failed iteration is cheap. The 20th, which re-reads 19 prior failures in context, is not.
