# S-860 · The Agent Failure Handling Stack — When a Broken Tool Burns Your Entire Daily Budget

Your agent's demo works. Your agent in production costs $437 in 90 minutes — not because the LLM is expensive, but because a tool starts returning garbage and the retry logic compounds it exponentially until your budget is gone and nobody noticed until the alert fired at 2 AM. This is the failure handling gap: agents that work on happy paths and silently destroy value on real ones. You need the patterns that catch this before it costs real money.

## Forces

- **Agents don't crash — they spiral.** A failing HTTP tool doesn't throw a stack trace. The agent retries with "slightly different approaches," each burning tokens, each reinforcing a bad plan. The failure mode is silent budget consumption, not a dramatic crash. A single broken tool can exhaust a daily API budget in under an hour.
- **Fail-open is the default in most frameworks.** When an external guard service times out, many frameworks fall back to "execute anyway." For a research agent that's harmless. For a financial agent issuing refunds, it's catastrophic. FailWatch (HN Show HN, 2025) was built specifically because a developer couldn't trust his production wallet without hard deterministic constraints layered over prompts.
- **Traditional retry logic breaks for AI.** Classic retry-with-backoff assumes the operation becomes more likely to succeed with time. For an LLM endpoint that's rate-limited, maybe. For a model drifting on a corrupted context window or a hallucinated tool argument, retries just re-run the same broken reasoning.
- **The pilot-to-production chasm is real.** ~88% of AI agent projects never reach production. One dominant cause: teams have evals, tracing dashboards, and prompt libraries, but no escalation layer — no defined gate between what the agent handles autonomously and what routes to a human. The failure that kills production isn't technical; it's the absence of a human-in-the-loop boundary.

## The move

Five layered patterns that handle failure at different time constants — from instant guardrails to async human review:

1. **Classify failures before retrying.** Not all errors are equal. Transient errors (429 rate limit, 503 outage, network timeout) warrant retry with exponential backoff. Persistent errors (provider down, quota exhausted, invalid API key) warrant fallback routing. Bad-input errors (400 content policy, malformed request) warrant a modified prompt or different tool. Partial errors (wrong JSON format, hallucinated tool syntax) warrant a correction prompt. Timeout errors warrant retry only with modified parameters. Classify first; the retry strategy follows from the type.

2. **Layer circuit breakers on tools, not just API calls.** Track failure counts per tool. After N consecutive failures, trip the circuit — stop calling that tool and surface the error to the agent as structured context (not a raw exception). Feed the agent enough information to attempt graceful degradation rather than looping. When the circuit opens on a search API that's rate-limited, tell the agent "search tool unavailable (circuit open), proceeding with cached results."

3. **Treat your own resource budget as a health signal.** The traditional circuit breaker watches downstream services. For agents, also watch inward: KV write counts, LLM token budgets, API call counts per session. A usage circuit breaker for Cloudflare Workers (HN Show HN, 2026) paused scheduled jobs before hitting Cloudflare's $5/M KV-write overage — flipping the Hystrix pattern to face the agent's own resource consumption. You can exhaust your budget just as catastrophically as any external service can fail.

4. **Implement dead letter queues for unresolvable failures.** Failed agent tasks don't belong in the same queue as pending ones. Route them to a DLQ with full execution context: what was attempted, where it failed, what the error was, how many retries were attempted. For AI agents specifically, the DLQ must handle model-specific failure modes — token limit violations, non-deterministic outputs that break downstream parsers, and hallucinated tool arguments that look like valid requests. Process DLQ items asynchronously with human review or scheduled retry with modified parameters.

5. **Define risk tiers for human escalation.** Read-only actions (search, summarize, analyze) — let the agent proceed autonomously. Boundary actions (send email, create record, modify data) — require confidence threshold before execution. Sensitive actions (financial transactions, deletions, external API writes) — require pre-action human approval or deterministic constraint verification. Irreversible actions (database deletes, payment execution, public posts) — require explicit human-in-the-loop with structured justification. Escalation is async-first: queue the item, notify the reviewer, continue processing independent work.

## Evidence

- **HN Show HN (FailWatch):** Developer built a fail-closed circuit breaker after discovering that when an external validation service crashed, most frameworks default to "execute the action anyway" — the fail-open default is dangerous for financial agents. FailWatch uses deterministic Python (Pydantic/Regex) for hard constraints, not prompts, and blocks actions if the guard server is unreachable. — https://news.ycombinator.com/item?id=46529092

- **HN Show HN (Usage Circuit Breaker for Cloudflare Workers):** Developer running 3mins.news (AI news aggregator) treated internal resource budgets as health signals. 10+ cron triggers were burning KV writes and LLM calls. The circuit breaker paused scheduled jobs before hitting billing limits ($5/M KV writes overage). "Treat your own resource budget as a health signal, just like you'd treat a downstream service's error rate." — https://news.ycombinator.com/item?id=47322794

- **Tanay Shah, "Four Production Reliability Patterns for AI Agents" (2026):** Documented the $437 retry-loop incident from April 2026 — an agent hit a transient upstream error, retried with exponential backoff as designed, but without a max-retries cap. Proposes circuit breakers, partial success handling, human-in-the-loop escalation, and graceful degradation as the four patterns that actually keep agents up at 3 AM. — https://tanayshah.dev/blog/agent-reliability-patterns-production

- **Brandon Lincoln Hendricks, "Dead Letter Queues and Retry Policies for AI Agent Systems" (2026):** AI-agent DLQs must handle unique failure modes beyond traditional software: model hallucinations, token limit violations, non-deterministic outputs that break downstream parsers. Covers implementation on Google Cloud (Vertex AI Agent Engine) handling 50,000+ agent tasks per hour. — https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production

- **Digital Applied, "Human-in-the-Loop Escalation Design for AI Agents" (2026):** Documents that ~88% of agent projects never reach production partly due to missing escalation layers. 3-agent chain reliability at ~90% claimed confidence collapses to ~42% in practice. Proposes four action-risk tiers from read-only to irreversible, with async-first escalation (queue, notify, continue) to survive real infrastructure. — https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026

## Gotchas

- **Exponential backoff without a max-retries cap is a budget bomb.** The $437 incident happened because backoff was implemented but the retry count wasn't bounded. Always pair backoff with a hard max-attempts limit and a circuit breaker that trips before you hit it.
- **Retry logic that re-runs the same input through the same model will produce the same failure.** If the failure is a hallucinated tool argument or corrupted context, retrying without modifying the prompt or session state just burns more tokens. Classify failures; only transient errors (rate limits, timeouts) get blind retry.
- **Fail-open is the default in most agent frameworks for a reason — it feels like availability.** But for any agent handling money, data, or irreversible actions, fail-open is a liability. Use deterministic constraint enforcement (not prompts) for hard limits, and make the default behavior block when uncertain.
- **Observability that records failures is not the same as recovery.** Logging that an agent failed at step 7 tells you what happened, not how to recover. Build recovery paths explicitly: DLQ routing, fallback tool chains, escalation queues. The goal is not visibility — it's resumed execution.
