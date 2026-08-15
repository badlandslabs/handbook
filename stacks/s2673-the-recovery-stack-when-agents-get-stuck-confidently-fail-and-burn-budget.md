# S-2673 · The Recovery Stack — When Agents Get Stuck, Confidently Fail, and Burn Budget

Your agent is running. It has been for twenty minutes. It is calling the same three tools with the same arguments, printing confident output it cannot evaluate, and it just crossed $80 in API costs. Nobody is watching. This is not an edge case — it is the default state of an agent without recovery infrastructure.

## Forces

- **LLM calls are expensive but naive retry logic makes them catastrophic.** A single unhandled rate-limit error can trigger an infinite retry loop against GPT-4 that burns through a budget before the user sees any output. Five retry attempts on a dead endpoint means five API round-trips, five billing events, zero progress.
- **Traditional error handling assumes errors are detectable.** LLM agents return HTTP 200 with confident nonsense. Tools succeed technically but hallucinate parameters. The reasoning chain produces coherent-sounding dead ends. None of these look like errors to a try-catch block.
- **Agents optimize for completing the task, not for stopping when stuck.** A candidate evaluation agent at Asynq.ai was observed optimizing for workflow completion — it would approve flawed outputs if they let it finish the pipeline, rather than admit failure.
- **The cost of a loop is invisible until it's catastrophic.** Unlike a crashed service, a looping agent produces output that looks plausible. By the time you notice, you've paid for 200 LLM calls.

## The move

Build a layered recovery system before you deploy. The layers work from outermost (cheapest failure) inward (most expensive failure):

1. **Iteration and cost circuit breakers at the orchestration layer.** Set hard limits on max iterations (commonly 3–10 per tool-call tuple), total cost per task ($2–10), and time elapsed (30–120s). When any limit hits, terminate and return partial results. Do this at the orchestrator level, not per LLM call — individual `max_tokens` limits don't catch a looping multi-step pipeline.

2. **Loop detection with mandatory pivot.** Track (tool, args) tuples. If the same tuple appears 3+ times in one session, inject a forced pivot instruction: *"You have tried [tool] with [args] three times. This path is dead. Try a different tool or admit you are stuck."* This costs one LLM call and either unblocks the task or produces a clean failure.

3. **Exponential backoff with jitter for transient errors.** When a rate limit (HTTP 429), timeout, or 503 hits, retry with `delay = base * 2^attempt + random_jitter`. Jitter (typically ±25% of delay) prevents thundering herd — when the API recovers, your retried requests don't all hit at the same instant and re-trigger the rate limit. Common base: 1–2s, max 3–5 retries.

4. **Stateful rollback / checkpointing for long tasks.** After every successful tool call, save the agent's state (message history, tool results, intermediate outputs) to durable storage. On logical failure (detected by circuit breaker or human), rollback to the last safe state and either retry with a modified approach or escalate. LangGraph and Microsoft Agent Framework both expose `checkpoint` and `resume` primitives for this.

5. **Per-tool error wrappers that return corrective context, not exceptions.** A tool that raises an unhandled exception gives the agent nothing to work with. Wrap tools with validators that catch the error and return a structured message: `{"error": "invalid_format", "expected": "ISO date string", "received": "yesterday"}`. This lets the agent self-correct on the next reasoning step rather than looping blindly.

6. **Graceful degradation chain.** When the primary model (e.g., Claude Opus, GPT-4o) fails validation or exceeds budget, fall back to a smaller, cheaper model (e.g., Haiku, GPT-4o-mini) with a reduced toolset. Accept lower quality on a subset of tasks over complete failure. The fallback chain should be defined declaratively, not improvised at runtime.

7. **Return partial results over complete failure.** A multi-tool workflow where one tool fails should return what succeeded with a clear statement of what is missing. *"Found 3 flights and 12 hotels in Paris. Weather API is currently unavailable — check back shortly."* This is the correct answer in almost every multi-tool scenario. Abandoning the whole task because one tool failed is the wrong trade.

## Evidence

- **Hacker News (447 points, 320 comments, May 2025):** David Crawshaw (sketch.dev) published the core loop architecture — a 9-line `while True` with an LLM calling tools — and noted that the main unsolved problem is "getting that last 10% of reliability." The thread consensus was that the simplicity of the loop pattern is deceptive: it works in demos where APIs are up and inputs are clean, but production surfaces every failure mode the loop wasn't designed for. — [https://news.ycombinator.com/item?id=43998472](https://news.ycombinator.com/item?id=43998472)
- **GitHub (open source):** AgentCircuit (`simranmultani197/AgentCircuit`, MIT, 2026) implements a circuit-breaker decorator with loop detection (`Fuse(limit=3)`), auto-repair on schema violations, output validation, and budget control. The README explicitly cites "infinite loops silently draining API budgets — $200+ losses before detection" as the problem it solves. — [https://github.com/simranmultani197/AgentCircuit](https://github.com/simranmultani197/AgentCircuit)
- **Engineering post (Asynq.ai / Modelia.ai, March 2026):** Harsh Rastogi documented two production failures: a candidate evaluation agent hallucinating tool parameters and burning 3x budget, and an image pipeline approving flawed outputs to optimize for pipeline completion. Both failures were caught by adding validation layers and budget circuit breakers — not by improving the model. — [https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Enterprise survey (Cleanlab, 2026):** Survey of 1,837 engineering and AI leaders found that 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster, partly due to reliability and failure-handling issues. Only 5% cited accurate tool calling as a top technical challenge they had solved. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Setting `max_iterations` alone is not enough.** A loop that generates different (but equally wrong) arguments every iteration will pass the counter check. Loop detection needs to track semantic state (tool + args hash or output hash), not just iteration count.
- **Retries without idempotency keys are unsafe.** If a tool call succeeds on the server but the network drops before the response arrives, retrying it can produce duplicate side effects (double charges, duplicate records). Add idempotency keys to any tool call that modifies state.
- **Jitter is not optional.** Fixed-interval retry against a recovering API creates a thundering herd — every client retries at the same moment and re-triggers the rate limit. Jitter distributes the retry load and is the difference between a retry that works and one that extends an outage.
- **Graceful degradation requires planning the fallback chain at design time.** Runtime improvisation of fallback behavior is itself a failure mode — you end up calling expensive models as de facto fallbacks because the cheap ones weren't wired up.
- **"Return partial results" sounds simple but requires instrumentation.** You can only return partial results if you know which steps succeeded. Without per-step state tracking, a late-stage failure forces you to return nothing or guess which results are valid.
