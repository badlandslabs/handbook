# S-1614 · The Agentic Failure Gate Stack — When Your Agent Doesn't Crash But Spends 35 Minutes Doing Nothing Wrong

Agents don't fail like software. Software throws an exception, logs a stack trace, and dies. An agent loops for 35 minutes, burns tokens, and returns a confident answer that happens to be wrong. The failure gate is the discipline of detecting these non-deterministic failures before they compound — and building the rollback infrastructure to recover cleanly.

## Forces

- **Traditional try-catch is useless here.** Agents fail silently: hallucinations return HTTP 200, tool calls succeed technically but semantically miss, reasoning chains produce confident nonsense. The failure surface has no exception to catch.
- **Loops look like progress.** A retrying agent is still consuming tokens and making API calls. Without hard bounds and fingerprinting, a loop can run until someone notices a cost spike on the billing dashboard.
- **Classification must precede retry.** Not all errors are equal: a 401 (bad API key) never improves with retry, but a 429 (rate limit) or 529 (overload) does. Blind retry amplifies failures under backpressure — the "thundering herd" problem.
- **State is the recovery vehicle.** When an agent takes a wrong turn at step 7 of 12, you don't want to restart from scratch. Checkpointed state lets you roll back to step 5 and re-plan, not re-execute.
- **Escalation is a feature, not a failure.** Human-in-the-loop escalation when all automated recovery is exhausted is a successful stop rule, not a system failure. It preserves safety and gives humans enough context to finish the job.

## The Move

Build a layered failure gate around every agent run. Each layer catches a distinct failure class before it cascades into the next.

**Layer 1 — Hard step cap.** The single most important guardrail. Recommended limit: 12 steps per run. When cap is hit, the agent must stop or escalate — never keep trying. This prevents the worst failure mode: a silent, expensive loop that runs until someone notices a cost spike.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

**Layer 2 — Error classification before retry.** Inspect the error type or HTTP status code first, then branch into the appropriate recovery path. Never retry a 400 (bad parameters), 401 (bad API key), or validation error. Retry a 429 (rate limit), 529 (overload), or network timeout. A naive fixed-interval retry on an auth error wastes tokens and time.

**Layer 3 — Retry with exponential backoff + jitter.** For transient errors, the formula is: `delay = min(base × 2^attempt + random(0, jitter), max_delay)`. Jitter prevents synchronized retries across distributed agents — without it, every agent in a fleet wakes up at the same moment and hits the rate limit together again.

**Layer 4 — Circuit breaker.** Track recent failure rate and open the breaker when it crosses a threshold (e.g., 50% of the last 20 requests failed). An open circuit breaker stops requests to a degraded service before they pile up, preserving both budget and downstream health.

**Layer 5 — Loop detector.** Track a fingerprint of the last action + last result. Stop when the fingerprint repeats beyond a small threshold. This catches the "call the same tool five times with the same arguments" pattern that hard step caps miss.

**Layer 6 — State checkpointing with rollback.** Use LangGraph's checkpoint API (or equivalent) to persist state at each step. When a failure occurs, roll back to the last known-good checkpoint and either re-plan from there or escalate. Production gotcha: use async Postgres checkpointer (`AsyncPostgresSaver` + `AsyncConnectionPool`) — a synchronous `psycopg.connect()` inside an async FastAPI lifespan blocks the event loop during checkpoint writes, invisible in testing, catastrophic under concurrent load.

**Layer 7 — Escalation path.** When all automated recovery is exhausted, preserve full state and hand off to a human with enough context to continue. Escalation is a successful stop rule — the system worked correctly by detecting its limits.

## Evidence

- **Engineering blog (Rajpoot, May 2026):** Hard step caps (12 steps), tool-level retry with classification, loop detector via action fingerprint — documents "Agents fail in ways single-LLM calls don't: loops, runaway tool calls, infinite 'let me try one more thing.'" — [blog.rajpoot.dev](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Research analysis (Zylos, May 2026):** 42% of multi-agent failures are specification failures, 37% are coordination breakdowns, 21% are verification gaps (attributed to Galileo's 2025 production deployment analysis). Microsoft's 2025 whitepaper identified six failure categories unique to agents: tool misuse, context loss, goal drift, retry loops, cascading errors, and silent quality degradation. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Developer guide (MatrixTrak, Jan 2026):** "Loops are repeat failures, not model failures." — root causes are no termination state, retry amplification multiplier, and unmapped failure classes. Bound the run with max steps, max wall clock time, max token budget. — [matrixtrak.com](https://matrixtrak.com/blog/agents-loop-forever-how-to-stop)
- **Technical guide (ClaudeGuide, Apr 2026):** Error taxonomy by HTTP status: 429 → retry with backoff; 529 → retry with backoff; 401/400 → never retry, fix the code; network failure → retry immediately; tool failure → depends on tool. Circuit breaker at ~50% failure rate of last 20 requests. — [claudeguide.io](https://claudeguide.io/claude-agent-error-handling)
- **AI systems guide (ombharatiya/ai-system-design-guide, GitHub):** "Agents fail in non-deterministic ways. Error handling has moved from Try-Catch blocks to Agentic Self-Correction and Stateful Rollbacks. Frameworks like LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives." — [GitHub](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Async/sync checkpointer mismatch kills concurrent agents.** Production LangGraph deployments on FastAPI must use `AsyncPostgresSaver` — the synchronous version silently blocks the event loop during checkpoint writes. Test under concurrent load to find this; it never surfaces in single-request testing.
- **Retries stack across layers and amplify.** HTTP client retry + tool wrapper retry + agent policy retry creates a multiplier. Under backpressure, this turns a transient outage into a persistent loop. Audit every retry layer and ensure they share state or are explicitly bounded.
- **"Done" is not a state transition.** If the system can't detect completion (record written, ticket closed, API call confirmed), the agent keeps trying. Build explicit termination checks into the loop condition — don't rely on the agent to notice it's done.
- **Cost spiral is a failure mode, not just a concern.** A looping agent without a token budget cap can run until the credit card maxes out. Set per-run cost limits in dollars, not just step counts, and alert on approach.
