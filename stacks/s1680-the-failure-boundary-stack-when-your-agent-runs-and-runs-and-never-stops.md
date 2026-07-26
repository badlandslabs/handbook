# S-1680 · The Failure Boundary Stack — When Your Agent Runs and Runs and Never Stops

Your agent enters a loop: it calls a tool, the tool returns an error, it tries a different approach, that approach also fails, it retries the first tool — and 45 minutes later it has consumed $23 in API tokens and accomplished nothing. The process eventually times out, but nobody was watching. A conventional web service would crash and log a stack trace. Your agent just... kept going, confidently, until something external stopped it. The failure was not an exception — it was a silent, expensive, reversible-in-principle event that nobody had prepared for.

## Forces

- **Agents fail creatively, not predictably.** A conventional microservice fails via a crash, a timeout, or a non-200 response. An agent fails by returning plausible nonsense with HTTP 200, by looping on a tool that cannot succeed, by consuming context until the model stops responding, or by taking an irreversible action before a human can intervene.
- **The model is not the failure surface — the orchestration is.** Most production agent failures are not model capability problems. They are unspecified retry contracts, missing circuit breakers, no loop guards, and no escalation path. The agent is blamed; the engineering gap is the real culprit.
- **Resilience retrofits are 10x harder than designing for them.** Teams build an agent prototype, ship it, watch it fail in ways they did not anticipate, and then try to bolt on retry logic, watchdog timers, and checkpointing. By that point the architecture often needs redesign.
- **Silent failures cost more than loud ones.** A crashed service is obviously broken. An agent running a $40 loop for 30 minutes looks like it is working until the invoice arrives.

## The Move

Build explicit, layered failure handling into your agent architecture from the start. Treat every LLM call as a network call that can fail — and design the retry contract, the fallback chain, and the escape hatch before you write the first tool definition.

**1. Classify failures before you handle them.** Not all errors are equal. Separate:
- *Transient transport failures* (rate limits, timeouts, 5xx API errors) — retry with backoff
- *Output validation failures* (model returns wrong format, hallucinates a tool name) — re-prompt with the specific error
- *Semantic failures* (output is valid JSON but wrong content) — require a separate validator, not just format checking
- *Reasoning failures* (loops, confidence drift, context overflow) — require architectural guards, not retry logic

**2. Retry with exponential backoff + jitter, scoped by error type.** Use `tenacity` or equivalent to wrap transport-layer calls. Never retry hallucinated output — a malformed JSON is not fixed by waiting. Only retry when the error is likely to be transient (429, timeout, 503). Add jitter to avoid thundering-herd retry storms when a provider comes back online.

**3. Implement circuit breakers for external dependencies.** When an LLM provider or tool API is degraded, naive retries amplify load and extend the outage. A circuit breaker tracks failure rates per provider, opens the circuit after a threshold, and half-opens it periodically to check recovery. Production implementations (e.g., OpenAI outage coverage via circuit breaker → Ollama fallback) show near-zero user-visible errors during third-party API outages.

**4. Add watchdog timers for silent reasoning failures.** Agents can loop indefinitely without throwing an exception. Set a `max_iterations` guard in your agent loop. Track repeated identical or near-identical tool call sequences. If the agent hits the iteration cap, halt and escalate. Claude Code's production architecture uses a single-threaded master loop with hard loop-termination guards specifically to prevent silent runaway execution.

**5. Build checkpoint/resume for long-running workflows.** Stateless agents can be horizontally scaled and recover from crashes without re-running completed work. LangGraph's `MemorySaver` for development, SQLite or Postgres `Checkpointer` for production. Temporal's event-history replay reconstructs in-memory state after a pod restart. Without checkpointing, any interruption forces a full restart from step one — which is expensive for multi-step research or synthesis agents.

**6. Design a fallback chain, not a single provider.** When the primary model is unavailable, the fallback should be pre-specified: a smaller model, a cached response, a human-in-the-loop queue. The fallback chain should be tested under load, not just designed on a whiteboard. Teams treating "model unavailable" as a single error code with no recovery path discover the gap on the day the primary provider goes down.

**7. Escalate to a human when uncertainty exceeds the cost of waiting.** Preserve the full reasoning trace (not just the error message) for the reviewer. Present structured options: approve, reject, modify. Define a maximum wait SLA — if no human responds within the window, execute the safest default action. Feed human decisions back into the training data or rules engine to improve future behavior.

## Evidence

- **Zylos Research (2026-05-06):** Production agents fail across four distinct domains — semantic, transport, reasoning, and resource. The central thesis: "Fault tolerance for AI agents is not optional engineering hygiene — it is the core engineering challenge of the agentic era, and it requires deliberate, systemic design." — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **Open Empower (June 2026):** Survey of enterprise deployments finds "runaway loops" as a primary failure pattern — agents that encounter an error, retry, create a new error, and loop indefinitely, each iteration consuming tokens and potentially taking irreversible actions. Notes that 2026's first wave of enterprise agent deployments is revealing systematic failure patterns that no demo ever surfaced. — [openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)
- **Anthropic Engineering (Claude Code architecture, 2025):** Production autonomous coding agent uses a single-threaded master loop with disciplined loop-termination guards and permission systems to prevent silent runaway execution. Weekly usage limits were added after users ran Claude Code continuously for 24/7 development — demonstrating that agents without explicit time/budget boundaries will push into unbounded execution. — [zenml.io/llmops-database/claude-code-agent-architecture](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding)
- **LangGraph/Temporal checkpointing (2025–2026):** LangGraph ships `MemorySaver` for development and SQLite/Postgres `Checkpointer` for production. Temporal replays event history to reconstruct in-memory state after crashes. Both are now first-class primitives in production agent frameworks — [zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability](https://zylos.ai/research/2026-03-04-ai-agent-workflow-checkpointing-resumability)
- **Markaicode (March 2026):** Circuit breaker architecture for LLM API resilience tested on AWS EKS — OpenAI recorded 4 incidents in Q1 2025 averaging 47 minutes each. Circuit breaker with Ollama fallback eliminated user-visible errors during outages. — [markaicode.com/architecture/circuit-breaker-resilient-ai-systems](https://markaicode.com/architecture/circuit-breaker-resilient-ai-systems)

## Gotchas

- **Retrying hallucinated output wastes tokens and does not fix the problem.** If the model generates an invalid tool name or wrong JSON schema, retrying the same prompt will likely produce the same error. Instead, return the specific validation error to the model as a `ModelRetry` message so it can correct the *content*, not just re-generate.
- **A circuit breaker without a tested fallback is theater.** Teams implement the open/closed/half-open states, then discover at 2am that the fallback path was never actually tested under load. Test the fallback path quarterly.
- **`max_retries=3` on everything is not a resilience strategy.** Transient errors (429, 503) deserve retries. Logic errors, semantic failures, and reasoning loops do not. Classify errors before deciding whether to retry.
- **Checkpointing without idempotent tools produces corrupted state on resume.** If your agent sent an email at step 4 and crashes before step 5, resuming from the checkpoint will re-send the email unless the tool call was idempotent or the checkpointer tracks completion at the tool-call level, not the step level.
- **Human escalation without a defined SLA defaults to infinite wait.** If your agent flags an uncertain decision and nobody is watching the queue, the escalation blocks indefinitely. Define a maximum wait time and a safe default action for the timeout case.
