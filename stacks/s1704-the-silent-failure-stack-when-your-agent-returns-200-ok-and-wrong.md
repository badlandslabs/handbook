# S-1704 · The Silent Failure Stack — When Your Agent Returns 200 OK and Wrong

Agents don't crash. They return HTTP 200 with results that are subtly, fundamentally wrong. A model hallucinating a tool call, an API rate-limiting you silently, an agent stuck in a loop generating irrelevant responses — none of these surface as errors. They surface as confidence. This stack handles the failure modes that monitoring misses.

## Forces

- Agents accumulate state during execution — prior tool results, reasoning traces, memory writes. A naive retry re-runs all of it, wasting tokens and potentially re-triggering side effects like duplicate messages.
- Silent failures (wrong but successful-looking results) are far more dangerous than loud ones — no alert fires, no circuit breaker trips, the agent just produces garbage.
- Multi-agent systems amplify failure rates dramatically: teams report 41–86.7% failure rates in production multi-agent pipelines without proper resilience patterns.
- Agents fail differently at every layer: model hallucinations, malformed JSON tool parameters, API rate limits, unexpected schema changes, and infinite loops — each needs a different recovery strategy.

## The move

Five interlocking patterns that close the gap from ~87% to 99.2% agent reliability, backed by production data:

- **Checkpoint before every major operation.** Snapshot agent state (conversation history, tool results, completed steps) to external storage — Redis or a database, never in-memory. When a container restarts or a process dies, recovery survives. "A human or a scheduled retry process can pick it up" instead of discarding the work.

- **Retry with exponential backoff, but only for idempotent operations.** Determine retry safety at tool-definition time: `read_file` is safe to retry, `send_email` is not. Re-sending completed side-effect steps on retry wastes tokens and creates duplicate outputs. Typical backoff: 1s → 2s → 4s → 8s → 16s over 3–5 attempts.

- **Per-tool circuit breakers.** Track failure rates per tool, not globally. If the search tool is failing but the database tool works, only the search circuit opens. Open after 5 consecutive failures, wait 60s before testing half-open state. "Frequent CLOSED → OPEN → HALF_OPEN → CLOSED oscillation indicates an unstable dependency."

- **Fallback chain, not a single fallback.** Chain fallback strategies by cost and capability: primary model → cheaper fallback model → cached result → static response → human escalation. If >20% of requests hit fallback, the primary strategy has a systemic issue — track this as an alert trigger.

- **Dead letter store for exhausted retries.** When a workflow exhausts all retries and all fallbacks, save the partial state with enough context to resume or replay. Never discard work silently. A dead letter row beats a silent failure that looks like success.

## Evidence

- **Engineering blog (OpenHelm):** Proper error handling increased agent reliability from 87% to 99.2% — a 14× reduction in failures. OpenAI API timeouts alone affect 2–5% of requests during peak hours. — [OpenHelm Blog](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Research post (Zylos):** Multi-agent systems fail at 41–86.7% rates in production without resilience patterns. Teams implemented circuit breakers at every agent boundary: "If Agent A fails, Agent B gets a 'degraded mode' signal instead of garbage input." — [Zylos Research](https://zylos.ai/en/research/2026-02-20-graceful-degradation-ai-agent-systems/)
- **Engineering guide (Let's Build Solutions):** Dead letter handling: "When a workflow exhausts all retries and all fallbacks, save the partial state to a dead letter store with enough context to resume or replay. Do not discard the work." — [Let's Build Solutions](https://letsbuildsolutions.com/blog/ai-ml/ai-agent-reliability-engineering-retry-semantics-fallback-chains-and-graceful-degradation/)

## Gotchas

- **In-memory checkpointing dies with the process.** Kubernetes restarts containers. Use Redis or a database — not a Python dict.
- **Not all tools are safe to retry.** Mark tool idempotency at definition time. A `send_payment` tool retried 3 times sends 3 payments.
- **200 OK is not success.** Build semantic validation: does the returned JSON match the expected schema? Are the values in a plausible range? Did the tool produce anything at all?
- **Fallback chains drift in capability.** A fallback to GPT-4o-mini may pass a request but produce lower-quality reasoning that downstream tools can't use. Log which fallback was hit and flag for review.
