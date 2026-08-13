# S-2555 · The Retry Storm Stack — When Your Agent Can't Stop Trying to Stop

Your agent calls a tool. The tool times out. The agent retries. Each retry sends the full conversation context back to the LLM — 8,000 tokens — burning tokens on a request that will never succeed. Meanwhile, a second tool that depended on the first also fails, triggering its own retry. Meanwhile, the LLM is reasoning about the failures, generating chain-of-thought that grows the context further. What was a $0.01 task costs $2 in six minutes. The agent has entered a **retry storm**: a cascading failure where each retry is more expensive and less likely to succeed than the last.

This is the retry storm stack — the patterns that bound agent failure so it stays recoverable instead of spiraling into silent cost explosions or corrupted state.

## Forces

- **Agent retries are exponentially expensive, not linearly expensive.** Unlike microservice retries (~kilobytes per call), each agent retry re-sends the full conversation context. Ten retries on an 8,000-token context = 80,000 input tokens for zero productive work. Production data shows this can produce **200x the token cost** of a single successful execution. Traditional retry math doesn't apply.
- **LLM reasoning compounds the problem.** The agent doesn't mechanically re-invoke the failing tool — it reasons about the failure, changes parameters, generates chain-of-thought, and may drift further from the correct recovery path with each attempt.
- **Cascading dependencies amplify failure.** A single flaky tool can trigger dependent tools to fail, multiplying the retry surface across the agent's execution graph.
- **Hard step caps exist but are often absent.** The single most effective guardrail is also the most commonly missing. Without a hard ceiling on steps, a looping agent will continue until the context window fills or the budget runs out.

## The Move

### 1. Classify Before Retrying

Naive retry ("it failed, try again") is actively harmful. If the model generated a malformed API call, retrying the same prompt will generate the same malformed call. Instead, classify the error type first:

- **API error** (rate limit, timeout, 5xx) → retry with backoff
- **Semantic error** (malformed call, wrong parameters) → do not retry the same way; fix the parameters or approach
- **Auth error** → escalate to human; do not loop
- **Tool unavailable** → use fallback tool or skip step

### 2. Apply Exponential Backoff with Jitter at the Tool Level

```python
# Do NOT retry with fixed delay
time.sleep(1)  # waste

# Do retry with exponential backoff + jitter
delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), 60)
time.sleep(delay)
```

Parameters used in production: base delay 1s, max delay 60s, jitter ~30%, max retries 3 per tool call. Jitter prevents thundering herd when the same tool is retried across multiple agent instances.

### 3. Put Cost and Error Rate Circuit Breakers at Every Layer

- **Tool-level:** 3 consecutive failures → trip breaker, skip tool, alert
- **Agent-level:** 5 consecutive failures → stop agent, save state, escalate
- **System-level:** Error rate >30% in 10-minute window → stop all agents, page on-call

### 4. Validate Tool Output Shape Before Passing It Downstream

After every tool call, verify the output is the expected type before feeding it to the next step. Catch cases where a failed API call returns HTML error pages that the agent then tries to parse as JSON. This single check has caught failures that would have corrupted 3+ subsequent steps.

### 5. Hard Step Cap with Graceful Escalation

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS} steps")
```

At the cap: save the agent's full state (checkpoint), surface what was accomplished, and escalate to human review. Never let the agent loop past the cap to "one more try."

### 6. State Checkpointing for Mid-Task Recovery

Every 3-5 steps, persist a checkpoint of the agent's state (not just the conversation, but the tool call results and working memory). When a failure occurs, the agent can be resumed from the last checkpoint rather than re-executing from the beginning. This prevents a single failure from erasing all prior progress and avoids re-running expensive tool calls.

## Evidence

- **Engineering blog — Tian Pan, "The Retry Storm Problem in Agentic Systems" (April 2026):** Documented 200x token cost amplification from uncontrolled retry loops. Showed that agent retries are fundamentally different from microservice retries because each sends the full conversation context, not just the failing payload. — [tianpan.co](https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems)
- **arXiv paper — Pandey, "Evaluating Agentic AI in the Wild: Failure Modes, Drift Patterns, and a Production Evaluation Framework" (2025):** Taxonomy of seven production-specific failure modes including tool failure cascades and non-deterministic output drift. Analyzed systems operating at O(10⁹) events/day scale. Found that standard evaluation frameworks miss 4/7 failure modes entirely. — [arXiv:2605.01604](https://arxiv.org/html/2605.01604)
- **GitHub discussion — Anthropic SDK forum, "What patterns do you use for AI agent error recovery?":** Practitioners with 95+ days of production reported circuit breaker thresholds (5 consecutive failures trip, 30s cooldown), error-classify-then-route retry patterns, and agent-level/state consistency safeguards. — [GitHub #1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **HN thread — "Ask HN: How are you testing AI agents before shipping to production?":** Commenter validated output shape checking after each tool call: caught a case where a failed API call returned HTML error pages that the agent tried to parse as JSON, corrupting 3 subsequent steps. — [Hacker News](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Step caps are necessary but not sufficient.** A cap stops the loop, but without checkpointing, you've lost all progress and learned nothing. Cap + checkpoint + escalation is the complete pattern.
- **Cost circuit breakers are load-bearing at agent autonomy level 4+.** An agent that can browse the web, execute code, and send emails can run up a four-figure bill on one poorly-designed task. Budget caps are not optional at this autonomy level — they are the only thing preventing catastrophic spend.
- **Retrying with the same prompt on a semantic error is a double failure.** You pay twice and get the same wrong result. Always classify the error type before deciding whether to retry, and if retrying, change the parameters.
- **Context window growth during retries compounds cost.** Each retry not only re-sends the context — it may add new chain-of-thought tokens, growing the context further. A 10-retry loop on a growing context can cost orders of magnitude more than a 10-retry loop on a fixed-size microservice payload.
