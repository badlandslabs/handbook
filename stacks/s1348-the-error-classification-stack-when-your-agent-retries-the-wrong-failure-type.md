# S-1348 · The Error Classification Stack — When Your Agent Retries the Wrong Failure Type

Your agent hits an error and retries. Then retries again. Then gives up. The real problem: you never classified what kind of error it was. A 401 means "abort now and alert ops" — retrying it twelve times wastes tokens and signals to the model that the request might eventually succeed. A 429 means "wait and retry" — giving up on the first hit means missing work the system could have completed. A context-overflow means "reduce the payload" — retrying the same 200K-token input with the same model is not a retry, it's a re-enactment of failure. The move is to classify before you retry, and route each error class to its appropriate recovery strategy.

## Forces

- **Retry is a reflex, not a strategy.** Most agent frameworks default to "retry on error" because it works for transient infrastructure blips. But agents encounter four fundamentally different error classes, and the correct response for each is different — or outright opposite. Retrying a fatal error (revoked API key) until the model gives up is not resilience, it's waste.
- **Silent failures look like success.** An agent producing confident wrong output returns HTTP 200. Traditional APM that treats "2xx = success" misses the most expensive failure mode in agentic systems. You need semantic success detection on top of infrastructure monitoring.
- **The taxonomy is non-obvious.** LLM errors don't map cleanly to HTTP codes. A model that returns malformed JSON is not the same failure as a model that hits a rate limit, even though both surface as "the tool call failed." Teams apply uniform retry logic across heterogeneous error classes because they haven't built the classification layer.

## The Move

Classify every failure at the boundary before routing to a recovery strategy. The error taxonomy has four classes, each with a distinct response:

- **Transient** (rate limits, timeouts, 503s) — retry after exponential backoff. Same request will likely succeed.
- **Semantic** (malformed JSON, missing tool arguments, schema violations) — re-prompt with corrective context. Don't retry the same input; give the model information about what went wrong.
- **Resource** (context overflow, token budget exceeded, spending cap) — reduce the payload. Summarize prior results, drop oldest context, switch to a smaller model. Retrying unchanged is a predictable failure.
- **Fatal** (401/403, revoked keys, removed endpoints, policy violations) — abort immediately, log structured metadata, alert ops. Do not retry. Do not pass Go.

Layer three detection mechanisms on top of classification:

1. **Pre-tool-use hook** with recent failure counting — catches obvious loops before they start. Track: same tool called N times with no intermediate state change → intervene.
2. **Periodic pattern detection** — scans the execution trace for repeated failure signatures across a sliding window. Catches slow drift that single-step counting misses.
3. **Structural stuck-loop detection** — compares the agent's current state (tool chain, intermediate outputs, context occupancy) against a baseline. Catches the 58,000-token loop that isn't technically repeating the same call but is also not making progress.

For silent semantic failures (agent returned 200 but produced wrong output), add a lightweight **semantic success validator** — a small classifier or rule-based check that confirms the output meets success criteria before treating the run as complete. This is the gap between "ran without errors" and "accomplished the goal."

## Evidence

- **OpenHelm blog (Jul 2024):** Documented 5 critical reliability patterns for production agents — retry with exponential backoff, circuit breakers, fallback mechanisms, timeout management, graceful degradation. Reported that proper error handling increased agent reliability from 87% to 99.2% (14× fewer failures). — [OpenHelm](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Neel Mishra — Agent Error Taxonomy (2025):** Formalized four-class error taxonomy (Transient / Semantic / Resource / Fatal) with the design principle: "Classify before you retry. A retry loop that hammers a fatal error until the model gives up is not resilience." — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Agent.ceo blog (2026):** Documented a real production incident: "A fullstack agent spent 2 hours and 28 minutes stuck in the same thinking/tool-call cycle. 58,000 tokens burned. Zero shipping progress." Introduced three detection layers: real-time failure counting, pattern-based learning, and structural stuck-loop detection. Core rule: same action repeated five or more times with no success — stop. — [Agent.ceo](https://agent.ceo/blog/detect-break-agent-retry-loops-production)
- **SmartCR / ICML 2026:** Formalized a 6-category, 15-mode failure taxonomy from one year of production agent deployments. Found that 89% of mid-market agentic deployments have no eval harness — they cannot measure failure modes. The remaining 11% use eval harnesses that cost $1–15M to build. — [SmartCR](https://smartcr.org/ai-technologies/agentic-loop-failure-modes-a-production-taxonomy-at-the-end-of-year-one)
- **Wolyra (May 2026):** "An agent that drifted into recommending deprecated SKUs for two thousand customers produced no exception, no latency spike, no suspicious log line. No 2xx was harmed." Identified that traditional APM treats success as a 200 response, which misses the dominant failure mode in agentic systems — confident wrong output. — [Wolyra](https://wolyra.ai/ai-observability-monitoring-agent-failures/)
- **FixBrokenAIApps (Dec 2025):** Documented "Loop Drift" — agents misinterpreting termination signals, re-summarizing completed work, calling save_file repeatedly because the model believed "summarized" was not truly done until re-summarized for quality. Identified solution: deterministic external enforcement of maximum iteration limits, not prompt-based termination signals. — [FixBrokenAIApps](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops)

## Gotchas

- **Uniform retry logic is a bug, not a feature.** If your agent retries on every error with the same backoff, you are treating a revoked API key the same as a network blip. The retry budget should be reserved for errors that are actually likely to succeed on retry.
- **"No error thrown" ≠ "task succeeded."** For agents, semantic validation must be layered on top of infrastructure success signals. Track output quality against explicit success criteria, not just HTTP status codes.
- **Circuit breakers belong at the tool level, not the agent level.** Track failure rates per downstream service independently — your agent can still reach GitHub even if Stripe has opened its circuit. Per-tool circuit breakers prevent a single degraded dependency from taking down the entire agent.
- **Checkpoint before escalation.** Before human handoff on a fatal error, serialize the agent's full state (context window contents, tool chain executed, intermediate outputs, error metadata) so the human reviewer can reproduce, understand, and resume — not restart from scratch.
