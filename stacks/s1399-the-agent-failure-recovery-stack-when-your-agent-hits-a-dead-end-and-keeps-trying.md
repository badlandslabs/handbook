# S-1399 · The Agent Failure Recovery Stack — When Your Agent Hits a Dead End and Keeps Trying

Your agent hits a malformed JSON response from a tool. It retries the same call. Same error. It retries again — 47 times — before anyone notices. Or: your agent's API key rotates and every downstream tool call starts returning 401s. The agent reports "all tools unavailable" and stops. Or: your agent loops forever calling a tool that exists in the spec but not in the runtime. These aren't edge cases. They're the default failure modes of agentic systems, and the difference between a resilient agent and a budget-burning loop is a small set of concrete patterns that most teams discover too late.

## Forces

- **LLM errors aren't exceptions** — a model returning malformed JSON isn't throwing; it's completing. Traditional try-catch doesn't catch it. You need to detect and correct the output itself.
- **Failures cascade** — one 429 rate limit can trigger a retry storm that burns through tokens on a frozen endpoint while a perfectly healthy backup sits idle.
- **Monitoring lies to you** — LangSmith, LangFuse, Arize, Helicone show traces, latency, token counts. They answer "what happened" but not "is my agent actually reliable right now" or "will I know before my users do?" ([DEV Community](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai))
- **Context loss on crash** — if your agent process dies mid-run, you get no recovery, no resume, no state. Every step starts over from scratch. This is the durability problem underneath every "agent forgot everything" incident.
- **Self-correction requires error-as-input** — agents can only recover from mistakes they receive as feedback. An error that gets swallowed is an error that gets repeated.

## The Move

Build a layered failure recovery system with five distinct layers. No single layer is sufficient; value is in composition.

**Layer 1 — Error Taxonomy and Typed Responses**
Categorize failures precisely, because each type demands a different recovery. From Neel Mishra's analysis, agent errors fall into four categories requiring different strategies:
- **Transient** (HTTP 429, 503, timeout): retry with backoff — retrying will likely succeed
- **Semantic** (malformed JSON, wrong schema, hallucinated tool call): re-prompt with the error as corrective context — identical retry won't help
- **Resource** (token limit, context full): compact context or chunk the task — the request is valid but can't fit
- **Loop** (same action repeated N times): hard stop and escalate — this isn't recoverable by retrying

**Layer 2 — Structured Exception-Feedback Loops**
Treat exceptions as observations, not crashes. From the Hive framework's production experience: "In a standard Python script, a FileNotFoundError is a crash. In Hive, we catch that stack trace, serialize it, and feed it back into the Context Window as a new prompt: 'I tried to read the file and failed with this error. Why? And what should I try instead?'" ([Hacker News](https://news.ycombinator.com/item?id=46979781), citing vincentjiang's comment on the Hive agent framework). This turns every failure into a self-correction opportunity without a hard restart.

**Layer 3 — Loop Detection and Circuit Breakers**
Implement three hard stops before letting an agent loop indefinitely:
- **Max iterations** — cap the number of agent-loop turns (typically 20–50 depending on task complexity)
- **Action deduplication** — track recent action sequences; if the same action appears N times in a row, interrupt and escalate
- **Circuit breaker** — after N consecutive failures against a service, open the circuit and fail fast for a cooldown period, preventing retry storms against a failing endpoint. ([GitHub: tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns))

**Layer 4 — Checkpointing and Stateful Resume**
Save agent state at decision points so runs can resume after interruption. LangGraph provides native `MemorySaver` and `PostgresSaver` checkpointer primitives — each graph state transition is persisted, and a crashed agent can resume from the last checkpoint rather than restarting from scratch. ([LangGraph Checkpointing documentation](https://github.com/pydantic/pydantic-ai-harness/issues/115)) For production-scale systems, durable execution platforms like Restate pair checkpointing with suspendability: if an API call blocks (rate limit, outage), the agent suspends to durable storage and resumes when the resource recovers — without holding memory, without crashing, without restarting. ([Restate Blog: Durable Coding Agent](https://www.restate.dev/blog/durable-coding-agent-with-restate-and-modal))

**Layer 5 — Graceful Degradation and Human Escalation**
When autonomous recovery fails, degrade gracefully rather than failing silently:
- **Fallback chains** — if tool A fails, try tool B; if model A fails, call model B; if all else fails, surface a structured failure to the user with what was attempted and why
- **Confidence-gated escalation** — agents should evaluate their own confidence on outputs that have business consequences; outputs below threshold get flagged for human review before being acted on. Zylos Research found optimal confidence thresholds of 80–95% depending on task risk level. ([Zylos Research: Human Handoff](https://zylos.ai/research/2026-01-30-ai-agent-human-handoff/))
- **Human-in-the-loop for destructive actions** — any agent action that writes to production systems, sends external communications, or modifies state should require explicit human confirmation, regardless of confidence score

## Evidence

- **GitHub README:** The `ai-agent-error-patterns` repo (tanayshah11) documents four production-grade patterns — circuit breaker, partial success, human-in-the-loop, graceful degradation — built on Trigger.dev v4, specifically targeting the gap between "happy path tutorials" and real cascading failures. ([GitHub](https://github.com/tanayshah11/ai-agent-error-patterns))
- **Engineering blog:** Restate's durable coding agent architecture pairs Modal (code sandbox) with Restate (durable execution) to achieve resilience against crashes, outages, and rate limits. Key features: suspend/resume on blocking calls, automatic retry with idempotency, per-step observability — described as the production requirements for scaling a coding agent to "millions of users." ([Restate Blog](https://www.restate.dev/blog/durable-coding-agent-with-restate-and-modal))
- **HN discussion:** The Hive agent framework's comment thread (107 points, HN) documents treating exceptions as feedback to the LLM context, rather than crashes — specifically to solve the "agent doesn't know it failed" problem. Commenter vincentjiang: "The hardest mental shift was treating Exceptions as Observations." ([Hacker News](https://news.ycombinator.com/item?id=46979781))
- **DEV Community analysis:** A developer documented their LangChain agent entering a recursive loop in production with no alert. Identifies that existing observability tools (LangSmith, LangFuse) show traces but not "is my agent actually reliable right now?" — the gap between monitoring infrastructure and production reliability signals. ([DEV Community](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai))

## Gotchas

- **Don't retry semantic errors with the same prompt** — if the model produced malformed JSON, re-sending the same request will likely produce the same malformed JSON. Include the error message in the retry prompt so the model can correct its output format.
- **Circuit breakers must be per-endpoint, not global** — if your agent calls three tools and one endpoint fails, you want to stop calling that endpoint while continuing to call the other two. A global circuit breaker would halt all tool calls.
- **Checkpoint frequency is a tradeoff** — saving state after every step protects against crashes but adds latency and storage cost. Save at decision points (before a major tool call, after a significant state change), not on every token.
- **Loop detection needs a memory window** — checking for repetition in the last 1–2 actions produces false positives (agents legitimately re-check state). The detection window should span 5–10 recent actions and compare action *types*, not exact parameters.
- **Human escalation is only useful if humans can actually act** — if your escalation channel is an email that nobody checks for 4 hours, you've added latency without adding safety. Define escalation SLAs that match the business risk of the task.
