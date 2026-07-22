# S-1475 · The Layered Defense Stack — When Your Agent Breaks Instead of Recovers

Your agent ran fine in demos. In production, a rate limit hit mid-workflow and the agent froze. A JSON parse error corrupted the state and every retry made it worse. The session never recovered — it just silently degraded until the user noticed hours later. The problem isn't that the agent failed. It's that it had no architecture for recovery.

## Forces

- **AI errors are non-deterministic** — the same prompt produces valid output once and hallucinated tool arguments the next. Traditional exception handling doesn't cover this class of failure.
- **Failures cascade in multi-step workflows** — a single tool timeout can corrupt shared state, making downstream steps meaningless or destructive.
- **Retrying blindly amplifies cost and latency** — exponential backoff without a circuit breaker just burns tokens and latency on a dependency that is already failing.
- **Graceful degradation is architecturally expensive to retrofit** — building fallback chains after the fact requires restructuring every tool call site.
- **Human escalation is under-designed** — most agents either escalate for everything or never, because nobody defined the threshold criteria.

## The Move

Design failure recovery as a layered defense system, not a try/catch wrapper.

- **Tier 1 — Retries with exponential backoff and jitter.** Catch transient failures (rate limits, network timeouts, API 429/503) with exponential backoff and random jitter. Cap retry attempts (3-5 is typical) and set per-failure-type budgets. Never retry on 4xx client errors or parse failures — those won't resolve with time.

- **Tier 2 — Circuit breakers for external dependencies.** Wrap every external tool call (APIs, file I/O, MCP servers) behind a circuit breaker. On repeated failures, open the circuit, skip the dependency, and fall through to the degradation path. Track failure counts per tool, not globally — one broken tool shouldn't kill unrelated ones.

- **Tier 3 — Output validation guards.** Before the agent acts on tool output, validate it against an expected schema. A malformed response from a web search or database query should trigger recovery, not silently propagate. Use JSON schema validation or structured output parsing — do not pass raw tool output directly to the next LLM call without a validation layer.

- **Tier 4 — Graceful degradation chains.** Define explicit fallback paths: if the primary tool fails, try the fallback; if the fallback also fails, return a safe partial result or cached response rather than failing open. The degradation chain is a first-class artifact, not a best-effort afterthought. Document what each degradation level loses so the agent can communicate degraded state to the user.

- **Tier 5 — Checkpointing and state recovery.** Persist workflow state at each step boundary (input, tool calls made, outputs received). On failure, the agent resumes from the last checkpoint rather than restarting. MongoDB, SQLite, or Redis are commonly used for this — teams report that checkpoint granularity of "one tool call" balances recovery fidelity against storage overhead.

- **Tier 6 — Human-in-the-loop escalation.** Define escalation criteria explicitly: tool failures after N retries, actions with financial or data-destructive implications, repeated failures on the same step (>3 loops), or confidence below a threshold. Escalation should present a structured summary (what was attempted, what failed, what the agent's confidence is) and pause execution, not silently route to a human and continue.

## Evidence

- **Hacker News thread (Ask HN):** Practitioners building production agent pipelines reported that custom error handling built on Express endpoints with V8 isolates and MongoDB state management allowed granular per-agent failure recovery without cascading across the system. One engineer (pablovarela) described each agent as an isolated Express endpoint sharing state through MongoDB — failures are contained at the agent boundary. — [HN discussion on multi-agent orchestration](https://news.ycombinator.com/item?id=47660705)

- **Fast.io engineering guide:** Detailed the five failure categories that production agents encounter (transient infra errors, LLM quality failures, tool call failures, context overflows, and loop traps) and documented that building error handling into the architecture from day one is 10x cheaper than retrofitting it. — [AI Agent Error Handling: Best Practices for 2025](https://fast.io/resources/ai-agent-error-handling/)

- **Cowork.ink engineering post:** Documented a complete layered defense implementation including circuit breaker state machines (closed/open/half-open), checkpointing with state serialization, and Prometheus metrics for retry counts, fallback activations, and degradation levels. Reported that AI agents fail *creatively* — a prompt that produces valid JSON once can produce a hallucinated schema the next — making output validation a required guard rather than optional hardening. — [AI Agent Error Handling: Retries, Fallbacks & Recovery](https://cowork.ink/blog/ai-agent-error-handling)

- **Redis.io architecture guide:** Framed agent memory as a three-tier system (working/episodic/semantic) and noted that checkpointing state at each step boundary is essential for recovery — the agent must be able to resume mid-workflow, not restart from scratch after a failure. — [AI Agent Memory: Building Stateful AI Systems](https://redis.io/blog/ai-agent-memory-stateful-systems/)

## Gotchas

- **Retrying everything is the most common mistake.** Teams add retries globally without distinguishing between recoverable (transient) and unrecoverable (schema, logic) failures. Retrying a malformed JSON parse or a hallucinated tool argument wastes tokens and may produce the same bad output.
- **The circuit breaker must be per-dependency, not global.** A circuit breaker around the entire agent kills all tools when one fails. Track per-tool failure state so a broken web search doesn't prevent file writes or database reads.
- **Checkpointing without a recovery path is theater.** Saving state to disk but having no mechanism to load and resume it is a common pattern — the checkpoint exists but on failure the agent restarts anyway. The recovery path must be explicitly wired, not assumed.
- **Escalation without structured context is useless.** Routing failures to a human who receives only "tool failed" is worse than no escalation — they can't make an informed decision. Escalation must include the full trajectory: what the agent tried, what each step returned, and what the failure mode was.
