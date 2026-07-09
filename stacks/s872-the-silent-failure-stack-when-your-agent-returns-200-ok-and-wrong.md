# S-872 · The Silent Failure Stack — When Your Agent Returns 200 OK and Wrong

When your agent completes a task but gives you the wrong answer — and logs nothing. When an API silently rate-limits and the agent ghosts. When two agents amplify each other's errors by 17x. This is the failure mode that kills production agentic systems, and nobody teaches you to see it until it hits at 3 AM.

## Forces

- **HTTP 200 ≠ success** — The most dangerous agent failures return technically valid responses that are semantically broken. Traditional error handling (try-catch, status codes) doesn't see them.
- **Cascade speed** — A bad tool call in step 3 of 12 corrupts the context for steps 4–12. By the time you notice, the whole run is garbage.
- **Multi-agent amplification** — Independent parallel agents without coordination amplify errors by 17.2x, according to empirical research.
- **Eval coverage gap** — Outcome metrics alone don't catch "silent failures" where the agent reaches the right number through the wrong path. You need trajectory visibility.
- **The observability lag** — Most teams instrument their agentic systems less than their microservices. The debugging primitives exist but aren't applied.

## The Move

Build a three-layer resilience architecture: **detect** silent failures at the trajectory level, **contain** cascade with circuit breakers and retries, **recover** with stateful rollbacks and fallback chains.

### Layer 1 — Trajectory-Level Failure Detection

- Log every reasoning step, tool call, and intermediate output — not just the final result. Treat agent trajectories like distributed traces.
- Implement **semantic validation**: after each tool call, use a lightweight LLM or rule to verify the output makes sense before passing it downstream. Don't wait for the final answer.
- Instrument with OpenTelemetry (OTEL) + LGTM stack for latency, token counts, and cross-agent tracing. The same observability stack used for microservices works here.
- Track **trajectory metrics** (how the agent reasoned) separately from **outcome metrics** (final result). An agent can be right for the wrong reasons, which is a failure.

### Layer 2 — Cascade Containment

- **Circuit breakers** on every external tool call — especially rate-limited APIs. Track request counts per endpoint, per agent instance. Trip the breaker before the API silently starts dropping requests.
- **Exponential backoff with jitter** on retries. A single retry often fails immediately (same transient condition); backoff gives the system time to recover.
- **Retry budgets per step**: cap the number of retries per step to prevent agents from looping indefinitely on a broken tool. After budget is exhausted, fail fast and log the failure point.
- **Graceful degradation chains**: for every non-critical tool call, define a fallback. If enrichment API fails, fall back to cached data. If that fails, proceed with partial context and flag the gap. Never hard-fail on non-critical dependencies.

### Layer 3 — Stateful Recovery

- Use framework-native checkpointing (LangGraph `MemorySaver`, Postgres, or Redis checkpointer) to snapshot agent state at each node. On failure, rewind to the last clean checkpoint — not to step 1.
- The LangGraph rollback pattern is three lines of code: load the last checkpoint for the `thread_id`, then `ainvoke()` or `invoke()` again. The agent resumes from the next pending node.
- For production: use Postgres or Redis checkpointer, not `MemorySaver`. MemorySaver loses state on restart; Postgres/Redis persists across crashes.
- Intelligent rollback triggers: configure nodes to automatically rollback when an external API fails or when semantic validation detects corruption. Don't wait for a human to notice.

### Bonus — The Hybrid Deterministic Escape Hatch

- For brittle browser/API automation tasks, record deterministic scripts (Playwright-style) for the happy path. When a step breaks, fall back to agentic mode to repair it, then return to deterministic execution.
- This gives you 90% reliability of scripted automation with 100% coverage of edge cases that agents handle better.
- Browser Use / Workflow Use's approach: 10x faster than pure agentic, ~90% cost reduction, self-healing when steps break.

## Evidence

- **HN Ask: Multi-agent debugging:** A practitioner raised the problem on HN and got pointed to OTEL+LGTM as the production standard for tracing across agent call chains. The distributed systems parallels were direct — retry policies, circuit breakers, SLOs. — [news.ycombinator.com/item?id=47358618](https://news.ycombinator.com/item?id=47358618)
- **Case study — Supergood Solutions:** Lead-enrichment agent ghosted in production with no logs. Root cause: Clearbit API rate limit (10 req/sec free tier) was exceeded by 3 concurrent agent instances pushing 30 req/sec. Fix: circuit breaker + exponential backoff + per-instance request tracking. The API was silently returning 429s; the agent received no response and timed out silently. — [supergood.solutions/blog/when-your-agent-fails-silently](https://supergood.solutions/blog/when-your-agent-fails-silently)
- **Show HN — Workflow Use (Browser Use team):** Launched May 2025 with a hybrid approach: deterministic Playwright scripts for the happy path, agentic fallback when steps break. 10x faster and ~90% cost reduction versus pure agentic. The self-healing mechanism is the fallback to agentic mode on step failure. — [news.ycombinator.com/item?id=44007065](https://news.ycombinator.com/item?id=44007065)
- **Research — Error amplification:** A study found independent multi-agent systems (agents working in parallel without coordination) amplified errors by 17.2x. Critically: correct architectural patterns (SAS — shared agency system) had the lowest error rates. — [news.ycombinator.com/item?id=46847958](https://news.ycombinator.com/item?id=46847958)
- **Google Cloud — Silent failure framing:** Google Cloud's agent evaluation guide explicitly frames "silent failures" as the core problem: agents producing correct outputs through incorrect processes. Requires trajectory-level visibility to debug. — [cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **Documented failures (Air Canada, DPD, NYC MyCity):** Six documented agentic AI deployment failures from 2024–2025 share a structural pattern: the agent confidently produced wrong outputs that appeared authoritative. All covered by the OWASP Agentic AI Top 10 control framework. — [agentmodeai.com/agentic-ai-failure-case-studies/](https://agentmodeai.com/agentic-ai-failure-case-studies/)
- **LangGraph checkpointing pattern:** LangGraph's checkpointer saves agent state at each node; recovery uses `graph.invoke()` with the same `thread_id`. Postgres or Redis recommended for production. Intelligent rollback triggers can fire automatically on API failure. — [aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)
- **HN on evals:** Practitioners on HN confirmed: "If you don't have evals, you really don't know if you're moving the needle at all." But skeptical of LLM-as-judge effectiveness — one well-respected researcher found LLMs were "not good critics" in internal experiments. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

## Gotchas

- **Don't instrument only the final output.** The failure is in the trajectory. If you only log the response, you can't distinguish correct reasoning from lucky hallucination.
- **Don't retry without backoff.** Immediate retries on rate-limited APIs will keep you rate-limited. Use exponential backoff with jitter, not a fixed-delay loop.
- **Don't let agents loop indefinitely.** Every step that can fail needs a retry budget. Without it, a broken tool call becomes an infinite loop.
- **Don't skip circuit breakers on third-party APIs.** Rate limit errors often return HTTP 200 with an error body. You need semantic validation, not just status-code checks.
- **Don't evaluate only outcomes.** An agent that gives the right answer for the wrong reason will pass outcome-only evals and fail in production when the wrong path is invalidated. Track trajectory quality.
- **Don't over-engineer the recovery path for critical failures.** Some failures (wrong facts, hallucinations propagating downstream) can't be fixed by retrying — they require human review gates or explicit output validation before the result is acted upon.
