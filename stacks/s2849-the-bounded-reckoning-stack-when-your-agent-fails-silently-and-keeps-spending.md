# S-2849 · The Bounded Reckoning Stack — When Your Agent Fails Silently and Keeps Spending

An agentic system that has no budget circuit breaker, no retry budget, and no escalation path is a system where a single flaky API turns into a runaway cost center. The **Bounded Reckoning** problem: agents are autonomous by design, but autonomy without limits is a liability. Failure handling for agents must be architectural — not an afterthought wrapped around a single giant prompt.

## Forces

- **Agents fail differently than traditional software** — they return HTTP 200 with confident nonsense, hallucinate valid tool arguments, and loop on misinterpreted outputs. Traditional try/catch doesn't cover these failure modes. (Source: Preporato NCP-AAI course — https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **Retry logic alone is not recovery** — retrying a transient error is fine; retrying a semantic error (wrong tool, hallucinated path) just burns budget and compounds the mistake. Teams confuse "bouncing back" with "bouncing forward into more damage." (Source: https://www.bigyan.dev/blog/autonomous-error-recovery-ai-agents/)
- **Long-running agents mutate state before they fail** — a timeout after a tool already wrote data, or a worker that dies mid-step. Without idempotency or checkpointing, a retry replays the same side effects. (Source: https://negiadventures.github.io/blog/agent-retry-recovery.html)
- **Cost accumulates on unhappy paths** — rate-limited calls, recursive tool loops, and context overflows all happen at scale. Without spending limits, a degraded agent can run up significant bills before anyone notices. (Source: https://github.com/ankitlade12/AgentArmor)
- **Enterprise teams under-invest in this** — only 1 in 3 teams report satisfaction with observability and guardrail solutions; 70% of regulated enterprises rebuild their agent stack every 3 months. (Source: Cleanlab enterprise survey — https://cleanlab.ai/ai-agents-in-production-2025)

## The Move

Separate error taxonomy from error response. Classify first, then apply targeted recovery — not a blanket retry wrapper around everything.

**1. Classify failures into three buckets, each with a different response:**

| Failure type | Examples | Response |
|---|---|---|
| **Transient** | 503, timeout, 429 rate limit | Exponential backoff retry with jitter |
| **Client** | 400 bad request, 401 auth expired | Fix root cause, then one retry |
| **Semantic** | Hallucinated tool name, wrong schema, reasoning error | Validation layer, not retry — re-prompt with corrective context |

(Adapted from Preporato's agentic error taxonomy — https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

**2. Layer circuit breakers around external dependencies:**

Wrap every external API call (model provider, vector store, tool endpoint) with a circuit breaker. Trip threshold: 5 consecutive failures or >30% error rate in a 10-minute window. When the breaker trips, downstream agents receive a "degraded mode" signal and fall back to cached responses or a simpler path — rather than feeding them garbage input. (Source: Anthropic SDK community discussion — https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

**3. Make tool steps small enough to checkpoint and retry independently:**

Break agent workflows into discrete, idempotent steps. Each step should be small enough to re-execute after a failure without re-running the entire pipeline. If a tool call mutates state, make it idempotent using an idempotency key. On failure, restore from the last successful checkpoint rather than replaying from scratch. (Source: https://negiadventures.github.io/blog/agent-retry-recovery.html)

**4. Add budget circuit breakers for cost control:**

Set a maximum dollar amount or token budget per session or per day. Kill the agent run when the budget is exhausted. Combine with a step-count limit (e.g., max 50 tool calls per run) to catch recursive loops before they drain resources. (Source: https://github.com/ankitlade12/AgentArmor)

**5. Separate idempotent from non-idempotent retry configs:**

Not all failures should be retried the same way. Idempotent operations (read-only tool calls, GET requests) can safely retry with exponential backoff. Non-idempotent operations (writes, payments, deletions) need a manual review step or human escalation before retry. (Source: https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

**6. Implement a dead-letter queue for unrecoverable failures:**

When an agent exhausts its retry budget, escalate to a human-in-the-loop queue rather than silently failing or looping. Track the failed state, the error history, and the partial output so a human can diagnose and resume. (Source: https://antigravitylab.net/en/articles/agents/ai-agent-error-recovery-resilient-pipeline-design)

## Evidence

- **GitHub discussion (Anthropic SDK):** Practitioners at miaoquai.com and kinthai.ai use a tiered approach — exponential backoff (1s→2s→4s, max 3 retries), circuit breaker with 5-failure threshold and 30-second breaker duration, and idempotency-key separation for write operations. — https://github.com/anthropics/anthropic-sdk-python/discussions/1341
- **Framework analysis (r/LocalLLaMA):** Analysis of 44 AI agent frameworks found that "tool call retries, error recovery, and graceful degradation matter way more in production than which models they support." — https://www.reddit.com/r/LocalLLaMA/comments/1r84o6p/i_did_an_analysis_of_44_ai_agent_frameworks
- **Enterprise survey (Cleanlab):** Of 95 engineering teams with agents live in production, <1 in 3 were satisfied with their observability and guardrail solutions. 70% of regulated enterprises rebuild their agent stack every 3 months. — https://cleanlab.ai/ai-agents-in-production-2025

## Gotchas

- **A retry wrapper on the whole agent run restarts from scratch** — every token, every tool call. For 429 errors, this is wasteful. Apply retry logic at the individual tool level, not just the outer agent loop. (Source: Pydantic AI issue #928 — https://github.com/pydantic/pydantic-ai/issues/928)
- **Context overflow during recovery** — if you retry by re-prompting with the error appended, you add tokens to an already-large context. Prepend a concise recovery instruction instead of appending the full error, or summarize the failure history before retrying.
- **Circuit breakers don't help if you never close them** — a breaker stuck in "open" state blocks recovery even after the service recovers. Implement half-open state (probe requests) so the breaker automatically tests for health and closes when the service responds.
- **Recovery can introduce new failures** — a fallback model may have different tool-calling schemas, a fallback tool may behave differently, and a degraded-mode path may expose different outputs to users. Test failure paths as thoroughly as happy paths.
