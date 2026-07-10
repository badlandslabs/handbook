# S-920 · The Failure Triangle Stack: When Agents Don't Crash — They Spiral

[Agents don't throw exceptions. They silently loop, accumulate context until the model halts, burn tokens on failed attempts, or take irreversible actions on a hallucinated premise. The fix is not exception handling — it's a layered system of loop detection, idempotency bounds, and supervisor oversight.]

## Forces
- [LLM calls fail probabilistically, not deterministically. A retry is not guaranteed to produce the same output, unlike a REST API call — so naive retry logic compounds failure into waste.]
- [Agents often return HTTP 200 with subtly wrong content — hallucinated tool parameters, malformed JSON, wrong classifications. Classic error handling never fires because nothing "errors."]
- [A single failure in an agent loop cascades. One bad tool result feeds the next reasoning step, which feeds the next tool call. By step 10 you're deep in a failed regime that looks identical to progress from the inside.]
- [The LLM itself is the worst agent to handle its own errors — it has no awareness of cost, token budget, or step count, and will happily keep trying the same failing strategy indefinitely.]

## The move

The **Failure Triangle**: three interlocking safeguards — loop detection, idempotency boundaries, and supervisor oversight — that catch failures before they become spirals.

- **Loop detection is the first line.** Track step-level state signatures (tool calls made, outputs seen, reasoning patterns). CAUM's analysis of 80K real sessions found 88.7% of sessions entering a loop end in total failure, wasting 3.4× more tokens than successful runs. Detection at step 10 predicts failure with AUC=0.814. Enforce a hard max-turns cap in production pipelines; in interactive settings, surface the loop risk to the user before it escalates.
- **Idempotency bounds contain blast radius.** Every tool call that modifies state must carry a unique idempotency key. If a step fails mid-execution and the agent retries, the system detects the duplicate request and returns the cached result rather than re-executing. This prevents double-sends, double-writes, and double-charges from LLM retries.
- **Supervisor oversight catches what the agent misses.** A parent/superior agent monitors the execution trace for patterns the sub-agent cannot see: cost accumulation, step count relative to task complexity, repeated tool failures, goal drift. The supervisor can abort, redirect, or escalate to a human. Key design: the supervisor operates on structured outputs and explicit state, not natural-language reasoning — it makes deterministic decisions based on metrics.
- **Circuit breakers on the LLM call layer.** After N consecutive failures from a specific provider (rate limit, timeout, 5xx), open the circuit and route to a fallback: cached response, simpler model, or human-in-the-loop. Standard distributed-systems thresholds apply but need LLM-specific tuning because "failure" includes malformed responses andhallucinated parameters, not just HTTP errors.
- **Graceful degradation at the output layer.** When tools fail, don't let the agent silently proceed. Structured error responses with explicit recovery options (retry, skip, abort, escalate) constrain the LLM's error-handling decisions to known-good paths. LangChain's error handling guide recommends wrapping every tool call in a try/catch that returns structured `ToolMessage` objects with explicit `error_type`, `can_retry`, and `recovery_action` fields.
- **Token budgets as failure pre-emption.** Set per-session and per-task token limits enforced at the execution layer, not at the model. On breach, cap the session and return partial results. This prevents the $1,847-in-38-minutes failure mode where a looping agent exhausts a monthly budget before anyone notices.

## Evidence
- **Research post:** CAUM analyzed 2.6M steps from 80K real agent sessions and found tight reasoning loops as the dominant failure mode — 88.7% of looping sessions end in total failure, with failed sessions consuming 3.4× more tokens than successful ones. Early detection (step 10) predicts failure with AUC=0.814. — [https://news.ycombinator.com/item?id=47606768](https://news.ycombinator.com/item?id=47606768)
- **Engineering blog:** Zylos Research taxonomizes agent failures as 42% specification failures, 37% coordination breakdowns, and 21% verification gaps — noting that agents may silently loop, spawn redundant subprocesses, or take irreversible actions before intervention is possible. — [https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)
- **Framework pattern:** AgentSurface documents the supervisor pattern where a parent agent monitors sub-agent traces for cost, step count, and failure patterns — enforcing explicit bounds the sub-agent cannot self-observe. — [https://agentsurface.dev/docs/multi-agent/supervisor-pattern](https://agentsurface.dev/docs/multi-agent/supervisor-pattern)

## Gotchas
- Don't use the LLM to decide if it should retry. LLM-based error handling has no awareness of cost, step count, or blast radius — it will retry itself into a worse state.
- Idempotency only works if every state-modifying tool call is instrumented with it. A single untracked side effect breaks the entire containment strategy.
- Hard max-turns caps are blunt instruments — they kill productive long-horizon tasks. Loop detection (semantic pattern matching on recent steps) is a better trigger than a step counter alone.
