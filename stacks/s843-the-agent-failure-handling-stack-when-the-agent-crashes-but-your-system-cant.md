# S-843 · The Agent Failure-Handling Stack — When the Agent Crashes But Your System Can't

Your agent ran for eleven days straight. The API returned 200. No exceptions fired. A Slack message at 3 AM told you the cloud bill hit $47,000. The agent had been retrying the same failed action on loop — burning tokens, burning credits, burning trust. This is what production failure handling looks like when it's an afterthought.

## Forces

- **Agents fail non-deterministically** — unlike traditional software, a working prompt can fail the next run due to model drift, token limits, or output format changes, making failures hard to reproduce and test
- **The compounding math is brutal** — 98% per-agent reliability across five sequential agents yields only ~90% end-to-end; multi-agent systems report 41–86.7% failure rates in production (coordination failures, spec ambiguity, cascade)
- **Silent failures are the worst kind** — the worst production failures arrive with HTTP 200 and a confident tone; they don't look like failures, so they don't get caught
- **Retry loops are a financial risk** — an unattended agent retrying a failed tool call can burn $47K in eleven days with no observable symptom until the bill arrives
- **Human escalation trades speed for safety** — synchronous human review kills latency; asynchronous review requires queue infrastructure and operator capacity most teams don't build

## The Move

Layered failure handling across five concentric rings, from innermost to outermost:

**Ring 1 — Tool call guardrails (inside the agent loop):**
- Hard maximum iteration limits (e.g., `max_steps=50`) enforced by the orchestration layer, not the agent's judgment
- Tool call budget tracking: abort if `total_tokens_spent > task_budget * 1.5`; cuts token waste in runaway loops by ~40%
- Detect loop drift: compare the last N tool-call signatures; if >3 identical consecutive calls, inject a "reflect: why are you repeating?" prompt before continuing
- Timeout per tool call (e.g., 30s); a hanging tool doesn't orphan the session

**Ring 2 — Transient failure recovery (retry logic):**
- Exponential backoff with jitter: `delay = min(base * 2^attempt + random(0, base), max_delay)` — handles 429s, 503s, and brief network blips
- Retry only on idempotent-safe failures (network timeout, 502/503/429); do NOT retry on 400s, auth failures, or schema errors — retries amplify these
- Cap retry attempts (3–5 is typical); exhausted retries go to the dead letter queue, not silent drop

**Ring 3 — Persistent failure routing (circuit breakers + DLQ):**
- Circuit breaker per external dependency: after N consecutive failures, stop calling the degraded service for a cooldown period — prevents retry storms from cascading
- Dead letter queue (DLQ) for exhausted tasks: capture the full state (input, agent history, error metadata) to a separate store; route to human reviewer queue
- DLQ for AI agents must handle unique failure modes: hallucinated tool names, token limit violations, non-deterministic parse failures — not just exceptions

**Ring 4 — Semantic validation gates (pre-execution):**
- Validation gates check the agent's output BEFORE it executes a tool call — catches ~70% of hallucinated outputs before they cause side effects
- Output schema validation (is this JSON? does it match the expected shape?)
- Semantic sanity checks (did the agent just output a DELETE query on the production database? a SQL safety hook fires before execution)
- Cross-reference the agent's action against a policy hook: "Should this action run NOW given current system state?"

**Ring 5 — Human escalation (outer boundary):**
- Four-tier action-risk classification: routine → attention-worthy → escalation-required → irreversible; irreversible actions (DELETE, payment, external transmission) require explicit human approval before the agent can proceed
- Confidence-scored routing: if the agent's confidence score (derived from tool or prompt) falls below threshold, route to human queue instead of continuing
- Async-first escalation: human review operates on a priority queue with SLA timers; agent continues on other tasks rather than blocking

## Evidence

- **Engineering blog:** ValueStream AI measured LLM API errors at 5% of all spans (60% rate-limit errors), agent task failure rates up to 75% across repeated runs, and multi-agent system failure rates of 41–86.7% — attributed to spec ambiguity and coordination failures. Budget guardrails reduced token waste in complex loops by ~40% average; validation gates caught ~70% of hallucinated outputs before execution. — [ValueStream AI Engineering Blog, May 2026](https://valuestreamai.com/blog/ai-error-handling-patterns-2026)
- **Systems engineering blog:** Supergood Solutions derived the compounding failure math: 98% per-agent reliability × 5 sequential agents = ~90% end-to-end. Described the 3 AM scenario where an external API returned 503 for 8 minutes and the agent silently dropped 140 records — found four days later. Documented exponential backoff with jitter, circuit breakers per service, idempotent agent actions, and DLQ routing as the four essential production patterns. — [Supergood Solutions, March 2026](https://supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026/)
- **Primary incident report:** Coasty AI documented a production agent that ran in an infinite loop for eleven days, costing $47,000 in API credits. The agent was retrying a failed action, no external guardrail existed, and no budget cap was in place. — [Coasty AI Engineering Blog, May 2026](https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories)
- **GitHub issue (18.4k stars):** Agent Zero (agent-zero repo) confirmed a class of bug where tool hangs cause the agent to enter a repeat loop with no recovery without manual restart — filed as issue #1011, closed after community discussion of loop-detection patterns. — [GitHub agent-zero#1011](https://github.com/agent0ai/agent-zero/issues/1011)
- **Engineering blog:** GetATeam described waking to 47 Slack alerts from a cascading agent failure triggered by a single unhandled API timeout. Primary failure modes catalogued: API rate limits and timeouts, unexpected input variations (50MB attachments, unknown Unicode), network instability, silent failures (200 OK with wrong output). — [GetATeam Blog, November 2025](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it)

## Gotchas

- **Don't retry on everything** — retrying a 400 Bad Request or auth failure makes it worse; idempotent-safe retry classification is not automatic
- **Hard limits are non-negotiable** — don't trust the agent to decide when to stop; the orchestration layer must enforce `max_steps`, budget caps, and timeout walls independently of agent judgment
- **200 OK is not success** — the most dangerous failures in agentic systems are semantically wrong responses with correct HTTP status codes; validation gates are required even when the API call succeeds
- **DLQ for AI is not the same as a traditional message broker DLQ** — you need to capture the full agent state (conversation history, tool call chain, token usage, error metadata) so a human reviewer can reconstruct what happened and decide whether to replay, adjust, or abandon
- **Human escalation latency kills throughput** — synchronous human-in-the-loop gates work for low-volume irreversible actions; for high-volume production agents, async queues with SLA timers and batched review are the only viable pattern
