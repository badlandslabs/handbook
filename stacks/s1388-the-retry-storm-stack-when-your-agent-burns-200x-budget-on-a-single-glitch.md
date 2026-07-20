# S-1388 · The Retry Storm Stack — When Your Agent Burns 200× Budget on a Single Glitch

Your agent encounters a rate limit. It retries. Each retry resubmits the full conversation context to the LLM — burning tokens at the cost of the entire context window, not just one HTTP call. One transient error becomes $2 of compute instead of $0.01. Without circuit breakers and semantic error detection, naive retry logic is a runaway budget sink.

## Forces

- Agent retries are fundamentally more expensive than microservice retries — each retry resubmits the full conversation context, multiplying token cost
- Agents fail in ways traditional software doesn't: hallucinations return HTTP 200, tool calls succeed technically but semantically, reasoning chains produce confident nonsense
- Most eval failures are actually software bugs (broken URLs, missing keys) not model failures — but error taxonomy blurs these categories
- Without loop detection and circuit breakers, a single degraded component cascades into unbounded compute spend
- Tool failures are often silent: an MCP server can break for days without surfacing an error to the caller

## The Move

**Separate error taxonomy into three tiers, with targeted recovery per tier:**

- **Tier 1 — Transient (retry with backoff):** Rate limits (429), timeouts, DNS failures, 503s. Apply exponential backoff (1s → 2s → 4s → 8s → cap 60s) with ~30% jitter. Cap at 3 retries max.
- **Tier 2 — Structural (circuit breaker + fallback):** Consecutive failures after N attempts, degraded tool responses, ambiguous LLM outputs. Trip circuit breaker; fall back to simpler model (Opus → Sonnet → Haiku), or queue for human review.
- **Tier 3 — Semantic (no HTTP error at all):** Hallucinations, confident wrong answers, tool calls that succeed technically but fail semantically. Requires semantic/behavioral validation — not caught by try/catch.

**Layer your recovery stack:**

1. **Connection resilience:** Exponential backoff + jitter + circuit breaker after 5 consecutive failures. Cap retry token burn at 60s delay max.
2. **Model fallback chain:** Define an ordered fallback chain (e.g., Opus → Sonnet → Haiku → queue). Learned hard after the November 2025 Anthropic outage.
3. **Tool isolation:** Hard 30-second timeout per tool call. On failure: log structured error, continue degraded — never let one broken tool kill the entire session. After an MCP server silently broke for 3 days, teams started requiring 100% self-testing of tools before deployment.
4. **Loop detection:** Track conversation pattern hashes and action sequences. If the same 3-step sequence repeats more than N times, halt and escalate. Production monitors (Sentrial, Honeycomb) catch loops, hallucinations, and cost overruns in real time.
5. **Idempotency guards:** For non-idempotent operations (writes, payments, sends), use idempotency keys + "already processed" checks before retrying. A retry on a non-idempotent operation without guards causes duplicate execution.

**Measure retry waste:** Track retry token burn vs. successful request token burn. A well-tuned system reduces retry token cost from ~$2/incident to ~$0.01 — a 200× reduction.

## Evidence

- **HN Launch Post:** Sentrial (YC W26) — production monitoring for AI agents that detects loops, hallucinations, and cost overruns before users notice. Notes that "no stack traces or 500 errors" means failures only surface when customers complain. — [https://news.ycombinator.com/item?id=47337659](https://news.ycombinator.com/item?id=47337659)
- **Engineering Blog:** "The Retry Storm Problem in Agentic Systems" — measured 200× token cost reduction ($2 → $0.01) by adding circuit breaker to a naive retry loop. Documents that a single 3-retry policy with 429 error and 8,000-token context burns 32,000 input tokens per incident. — [https://tianpan.co/blog/2026-04-10-retry-storm-agentic-systems-cascading-failure](https://tianpan.co/blog/2026-04-10-retry-storm-agentic-systems-cascading-failure)
- **GitHub Discussion:** Anthropic SDK community discussion on error recovery patterns — battle-tested 4-layer stack from a team running 5 agents 24/7 for 95+ days. Key lessons: separate retry logic by error type, model fallback chains, tool isolation, idempotency keys. — [https://github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Certification Guide:** Preporato "Error Handling in AI Agents" — formal taxonomy distinguishing traditional software errors (NullPointer, 500) from agentic failures (hallucinations returning 200, semantically wrong tool outputs). Covers circuit breakers, fallback chains, graceful degradation, and recovery patterns. — [https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

## Gotchas

- **Treating all errors the same.** `InvalidAPIKeyError`, `AuthenticationError`, and `ContentPolicyViolationError` should never retry — they won't resolve on their own and each attempt burns tokens and increments failure counters.
- **No max-retries cap.** Without a hard cap, a glitching service will retry forever. Circuit breakers and max-retry limits are not optional.
- **Retrying non-idempotent operations without idempotency keys.** A retry on a payment, email send, or database write without guards causes duplicate execution — sometimes invisible until the charge appears on the customer's statement.
- **Missing tool-level timeout.** If a tool hangs indefinitely, the agent blocks the entire session. Hard timeouts per tool call (recommend 30s) with structured error return enable graceful degradation.
- **No semantic error detection.** Hallucinations and confident wrong answers return HTTP 200 — traditional monitoring misses them. Behavioral/assertion-based validation catches what status codes cannot.
