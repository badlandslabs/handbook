# S-1662 · The Runaway Retry Stack — When Your Agent Spends 47 Attempts on the Same Failing Call

Your agent calls an external API. It times out. The agent retries. It times out again. The agent re-analyzes the context, decides the API is the right tool, and retries a third time. One hour later you've spent $83 on a single ticket that was never resolved. There was no error message. The agent was confident throughout. This is not a bad prompt — it is an architectural gap between traditional retry logic and the reasoning loop that drives it.

## Forces

- **Retries compound at two levels.** A per-call retry cap (e.g., `max_retries=5`) does not bound total attempts. If the agent's reasoning loop calls the same tool 10 times, that's 50 total attempts — each burning tokens re-evaluating the same failing context.
- **Agents retry semantically, not just mechanically.** Unlike a microservice that throws a 503 and catches it, an agent interprets a timeout as "this approach didn't work yet, try again with a different angle." The angle is often the same angle. No exception propagates to stop it.
- **Failure is non-obvious mid-loop.** A looping agent produces plausible intermediate outputs. The tool calls are happening. Observations are being made. Cost accumulates invisibly until someone checks the bill.
- **Soft failures don't trigger retries.** When a tool returns malformed data or a partial result, the agent often continues — silently accepting degraded state and compounding errors downstream.

## The Move

Three interlocking mechanisms contain retry loops in production agents:

**1. Tool-level circuit breakers.** Track failures per tool per session. After N consecutive failures (e.g., 3), mark that tool as unavailable for a cooldown window (e.g., 30 seconds) and surface an explicit error to the agent's reasoning layer. This breaks the semantic retry loop — the agent knows the tool is unavailable, not just that it failed once.

```python
# Per-tool failure tracking prevents same-tool spam
circuit_breaker = {"tool_name": {"failures": 0, "cooldown_until": 0}}
```

**2. Progress-degradation detection.** Track whether tool outputs are changing state. If the same tool is called with identical arguments and produces identical results N times in a row, halt. This catches the "confident but stuck" pattern — the agent is running but making no progress, regardless of whether errors are being raised.

**3. Bounded cost-per-task.** Set a maximum token spend or step count per task invocation. This is a hard floor — it prevents runaway costs even when all other safeguards fail. Several teams implement this as a budget-paused state that surfaces to the orchestrator rather than crashing.

Supporting these, standard transient-error retry with exponential backoff + jitter handles rate limits (HTTP 429) and server errors (503) at the infrastructure layer. The circuit breaker sits above that — it handles cases where retries won't help because the underlying problem is persistent.

## Evidence

- **Reddit r/AI_Agents:** A practitioner woke to a $83 OpenAI bill from a single agent run. The agent called a ticket-routing API that timed out ~15% of the time. Each timeout triggered a fresh reasoning pass that re-selected the same tool. 47 total attempts for one ticket. Solution: tool-level circuit breaker tracking consecutive failures per session, with the agent receiving an explicit unavailable signal rather than a bare timeout. — [reddit.com/r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1rap64j/my_agent_burned_83_in_retries_before_i_realized/)
- **GitHub agentguard-llm:** A production fault-tolerance library (MIT, pure stdlib) codifies five failure modes it targets: infinite loops, silent LLM failures, duplicate expensive calls, rate limit crashes, and token limit blindness. Documents circuit breaker configuration with per-tool thresholds and recovery windows. — [github.com/maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)
- **Forge (antoinezambelli/forge, 2,200+ stars):** A reliability layer for self-hosted LLM tool-calling that adds guardrails around tool execution — rescue parsing, retry nudges, response validation — independent of the underlying model. Lifted an 8B local model from ~53% to 99.3% task completion on their 26-scenario eval. Also raised Claude Sonnet from 87.2% to 100% on the same workload. Accepted to ACM CAIS '26. — [github.com/antoinezambelli/forge](https://github.com/antoinezambelli/forge), [news.ycombinator.com/item?id=48192383](https://news.ycombinator.com/item?id=48192383)

## Gotchas

- **Per-call retry caps don't propagate to the reasoning layer.** Setting `max_retries=5` on a tool wrapper is not a loop safeguard. The agent's loop can re-instantiate the call fresh each iteration. Budget-level and step-level limits are what actually bound total attempts.
- **Circuit breakers for LLM calls differ from API circuit breakers.** LLM calls can return 200 OK with garbage output — a semantic failure, not a technical one. Monitor response quality (schema conformance, null rates, retry-worthy content) in addition to HTTP status codes.
- **Silence is not success.** If an agent stops producing tool calls but keeps generating text, it may be in a degraded state, not a completed one. Add an explicit silence watchdog that fires after N seconds of no state-changing action.
- **Checkpoint before loops become expensive.** For long-running multi-step tasks, checkpoint state after each completed step. On resume, skip completed steps entirely — avoids re-sampling the same reasoning decisions that already succeeded.
