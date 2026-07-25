# S-1608 · The Failure Recovery Stack — When Your Agent Breaks and Keeps Running

Your agent went down at 2am. Not hard — it kept running, burning tokens, producing garbage, and looping on the same failed tool call 40 times before anyone noticed. It cost $2,300 in 15 minutes on a task worth $0.08. This is the stack for making agents fail safely, recover gracefully, and stop when they should.

## Forces

- **LLM failures are non-deterministic.** Traditional software throws exceptions. LLMs return rate-limit 429s, malformed JSON tool calls, hallucinated function signatures, or simply time out after 90 seconds — none of which crash the loop.
- **Agents keep running when they should stop.** Without explicit guardrails, an agent that can't reach its goal will try again, differently, forever. Cost scales linearly with failure count.
- **Fallback chains require planning before deployment.** You cannot improvise a second-best response at 2am. The fallback model, the degraded output format, the human-escalation path — all must exist before the first production request.
- **Root causes are layered.** A failed tool call is not the same failure mode as a rate limit, which is not the same as context overflow. Each layer needs its own recovery logic.

## The move

Build a layered failure-recovery stack with five distinct layers, each with its own detection and response logic:

**Layer 1 — Error Classification.** Every failure must be classified into a known bucket before recovery is chosen. The canonical taxonomy from production systems: *syntactic* (malformed output, invalid JSON), *semantic* (tool returns wrong-looking data), *environmental* (network, API, timeout), *rate-limit* (429, 503), *context-overflow* (token limit reached mid-session). Classification determines the recovery path, not gut instinct.

**Layer 2 — Retry with Exponential Backoff and Jitter.** Transient failures (timeouts, rate limits, 5xx errors) get retries, not errors. Standard config: 3–4 retries, initial delay ~1s, exponential backoff, max delay 60s, full jitter to avoid thundering herd. Most SDKs (OpenAI, Anthropic, Google GenAI) implement this automatically for HTTP-layer failures — but tool-level failures (LLM returned a malformed tool call) require manual retry logic.

**Layer 3 — Fallback Chain.** When retries are exhausted, fall to a cheaper or more reliable alternative — typically a smaller/faster model, a cached response, or a static fallback message. The chain is priority-ordered from most-capable to least-capable. Each hop is cheaper and less capable. The chain stops at the first level that succeeds. Example fallback order: GPT-4o → GPT-4o-mini → cached embedding search → "I'm having trouble, please try again."

**Layer 4 — Circuit Breakers.** When a provider or tool is experiencing sustained failures, stop calling it. A circuit breaker tracks failure rates and opens (stops calling) after a threshold is crossed — typically 50% errors in a 10-second window or 5 consecutive failures. Prevents cascading failures from propagating to downstream systems. Closed after a recovery window (30–60 seconds) with a "half-open" probe to test if the provider is back.

**Layer 5 — Max-Step Caps and Loop Detection.** Cap the total number of agent steps (commonly 20–50 depending on cost tolerance). Beyond a step count, terminate and surface a failure. Loop detection specifically catches repeated identical or near-identical actions — a symptom that max-step alone misses. One real production case: a task that normally costs $0.08 escalated to $12 because an agent kept retrying a failing tool 60+ times over 15 minutes with no loop detection in place.

**Bonus — Checkpoint/Resume.** For long-running agents, periodically snapshot state (current step, tool results so far, conversation history) to durable storage. On failure, the agent can resume from the checkpoint rather than restart. Patterns include Temporal workflows, Postgres + custom logic, or Redis for ephemeral checkpointing.

## Evidence

- **GitHub community-curated catalog:** Vectara's `awesome-agent-failures` repo (190 stars, started Aug 2025) documents 8 canonical failure modes: tool hallucination, response hallucination, goal hijacking, infinite loops, unauthorized tool use, and role confusion. Each entry includes real incident examples and mitigation strategies. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Engineering post-mortem (Agentbrisk, March 2026):** Real incident database from 2025–2026 showing three representative failures: a refund agent that issued $1.2M in unauthorized refunds (prompt trained to approve on specific phrasing), a travel agent that booked $43K in unauthorized reservations (weak action boundaries), and a chess game agent that let users manipulate game state through injection in the move input field. — [agentbrisk.com/blog/ai-agent-failure-modes-real-incidents](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/)
- **Hacker News discussion thread (Apr 2025):** An "Ask HN: How are you testing AI agents before shipping to production?" thread surfaced seven core failure modes from practitioners including Hallucination under unexpected inputs, edge case collapse (null values, Unicode names like O'Brien or 北京), prompt injection via external content, and context limit surprises. One commenter cited Gartner predicting 40%+ of AI agent projects will fail by 2027. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **Real-world loop cost data:** The `agentpatterns.tech` infinite-loop page documents a production case where a task type that normally closed in 3–4 steps began spinning for 20+ steps and timing out. In 15 minutes, the agent made 60+ steps and spent ~$12 on a task that should cost ~$0.08. No max-iteration cap was in place. — [agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **Open-source implementation patterns:** The `tanayshah11/ai-agent-error-patterns` repo (Nov 2025) implements four production patterns — circuit breaker, partial batch failure handling, human-in-the-loop escalation, and graceful degradation — on Trigger.dev v4 with standalone CLI tests. — [github.com/tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)

## Gotchas

- **SDK retry != tool-level retry.** Most LLM SDKs handle HTTP-level retries automatically, but if the LLM returns a malformed tool call (syntax error in JSON), that is not an HTTP failure — it passes through as a successful response. You must detect and retry this case explicitly.
- **Graceful degradation has a cost floor.** Even the best fallback degrades user experience. A fallback to a smaller model still consumes tokens and may return lower quality. Don't treat fallback chains as free — budget for them.
- **Circuit breakers can hide real outages.** If you open a circuit breaker on a provider that is genuinely down, you prevent both failure cascades and legitimate recovery. Tune thresholds on production data, not assumptions.
- **Loop detection is not max-step alone.** A max-step cap prevents unbounded runs but doesn't catch the case where an agent oscillates between two different (but equally wrong) actions. Pattern-match on repeated state, not just step count.
- **Checkpointing adds complexity that kills simple agents.** If your agent runs in under 60 seconds and has no multi-step critical state, checkpointing is overkill. Add it when agents have 5+ steps of state that would be expensive to recompute on resume.
