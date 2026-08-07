# S-2208 · The Retry Amplification Stack — When Retrying a Corrupted Tool Call Makes Things Worse

A customer service agent called a database lookup tool. The upstream gateway had an undocumented 4KB response cap. The tool returned a truncated JSON blob. The model correctly identified it was broken — and retried. The tool returned the same truncated payload. The model retried again. Seventeen times. No error fired. No alert tripped. Just escalating context and a quietly compounding token bill.

This is **retry amplification**: the retry loop isn't the problem — the fact that every retry carries the same corrupted input and produces the same corrupted output, while the context grows and the failure mode stays fixed, is what makes it catastrophic.

## Forces

- **Agent retries are 4x more expensive than service retries.** A microservice retry costs one HTTP round-trip. An agent retry resubmits the full conversation context to the LLM. A 3-retry loop burns 4x the tokens at full context window cost — not just the tool call overhead. (tianpan.co, April 2026)

- **Retrying a deterministic failure is compounding loss, not recovery.** When a tool returns a fixed corrupted output — truncated JSON, error HTML, 429 body — retrying with identical parameters produces identical failure. The agent's reasoning noise between attempts grows the context window without changing the outcome.

- **Agents can't distinguish "tool broken" from "no results."** A tool returning an HTML 502 page, a truncated stream, or a malformed JSON blob looks identical to the agent if the tool abstraction layer doesn't surface the distinction. The model generates plausible reasoning for its next retry attempt, masking the structural failure.

- **Consecutive identical failures are the strongest signal available — and the most ignored.** A circuit breaker that tracks payload hash across consecutive calls can detect the retry-on-identical-corruption pattern in O(1) state. Most agent scaffolds don't implement this.

## The Move

**1. Validate tool output at the boundary before the model sees it.**

The agent should never reason about a corrupted tool response. A schema validator, JSON check, and size bound run at the tool abstraction layer — before the response enters the conversation context.

```
def execute_tool(name, args):
    result = call_tool(name, args)
    if not validate_output(result):  # schema, size, type
        raise ToolOutputError(f"Tool {name} returned invalid output")
    return result
```

The model only sees responses that passed validation. (BSWEN, July 2026)

**2. Track consecutive identical-payload failures with a per-tool circuit breaker.**

Maintain a counter per tool. On consecutive failures with the same payload hash, trip the circuit — skip the LLM call and return a structured error. Three states:

- **Closed** (normal): calls pass through
- **Open** (tripped): calls return `ToolUnavailable` after N consecutive identical failures
- **Half-open** (probe): one test call; close on success, reopen on failure

The circuit trips on payload-hash equality across consecutive calls — not just failure count. This catches the truncated-JSON-retry pattern that count-only breakers miss.

**3. Escalate with parameter mutation, not repetition.**

If the failure is structural (wrong arguments, bad schema), retrying with the same args is provably wrong. After one failure, the circuit breaker should either:

- Suggest a corrected parameter schema to the agent, or
- Trigger a `ToolCallError` with specific field-level diagnostics

The model can then reformulate the call correctly — instead of retrying the same broken version.

**4. Bound total retry attempts per tool at the scaffold level.**

Max retries is a single number but it's applied wrong: most implementations retry the *agent loop* on tool failure, burning full LLM calls each time. Instead, cap per-tool-call retries at 1–2. Any further recovery happens through escalation, not blind repetition.

**5. Add a session cost ceiling that fires before budget exhaustion.**

Even a perfect circuit breaker needs a hard ceiling. Set `max_session_cost_usd` at the scaffold level. Track cumulative cost in real time. When the ceiling hits, the session terminates — not after the next model call clears it.

## Tradeoffs

- **Validation at the boundary adds latency** to every tool call. The cost is microseconds per call; the benefit is avoiding the 17-retry scenario.
- **Circuit breaker state is per-session by default** — a tool that fails in session 1 is retried in session 2. For persistent failure tracking, share circuit state across sessions (with TTL to avoid stale blocks).
- **Payload-hash comparison catches deterministic corruption** but not stochastic failures (e.g., a tool that returns random partial data). Combine with output plausibility checks for that case.

## Signs You Need This

- Your agent has ever retried the same tool more than 3 times in one session
- You have no per-tool circuit breaker today
- Your error logs show `json.JSONDecodeError` or `ValidationError` from tool wrappers
- A Waxell-style observability trace would show payload hash stability across consecutive failed calls

## See also

- [S-1003 · The Agent Failure Recovery Stack](/stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — broad failure recovery
- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — budget and liveness scaffolding
- [S-1032 · The Dead Letter Stack](/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — step-level vs. agent-level retry granularity
