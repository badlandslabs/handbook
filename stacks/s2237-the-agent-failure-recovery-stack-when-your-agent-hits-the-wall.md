# S-2237 · The Agent Failure Recovery Stack — When Your Agent Hits the Wall

You have an agent that works in development. In production, it loops forever, hallucinates tool parameters, and costs three times what you budgeted. Failure handling is the discipline that separates a demo from a production system — and most teams discover this the hard way at 3am.

## Forces

- **The happy path masks everything.** Agents work remarkably well for the first few steps. You ship on the happy path. Production is not the happy path.
- **Agents fail in shapes single-LLM calls don't.** Infinite loops, hallucinated tool parameters, semantic errors (output is syntactically valid but wrong), cost spirals — none of these have a traditional exception to catch.
- **Self-correction loops are double-edged.** Letting an agent retry its own work is powerful, but unbounded self-correction is indistinguishable from an infinite loop with a credit card.
- **Recovery is not retry.** Re-running a failed step is not the same as resuming from a checkpoint. The distinction matters for anything that takes more than a few seconds.
- **Observability is a prerequisite, not a luxury.** You cannot recover from failures you cannot see. Every retry, fallback, and degradation event needs a metric.

## The Move

### 1. Taxonomy first — name the failure before fixing it

Different failure modes need different recovery strategies:

- **Tool hallucination:** Agent calls a tool that doesn't exist or passes invalid parameters. Recover by validating tool schemas before execution and failing fast.
- **Response hallucination:** Agent synthesizes factually wrong output from valid tool results. Recover by adding verification steps or structured output schemas.
- **Infinite / self-reinforcing loops:** Agent repeats the same or adjacent steps without making progress. A Tsinghua study of 10,000 agent executions found 7.3% exhibited self-reinforcing loop behavior. Recover with hard step caps and progress tracking.
- **Constraint drift:** Agent ignores system prompt rules over long action chains. Recover by externalizing constraints into policy enforcement outside the prompt.
- **Semantic tool errors:** Tool returns a valid response that is contextually wrong (wrong account, stale data, format mismatch). Recover with tool-level validation and fallback chains.

### 2. Hard limits as the foundation

Every agent loop needs non-negotiable production limits enforced outside the LLM:

```
MAX_STEPS = 12          # hard cap on loop iterations
MAX_TOKENS = 8192       # per-call token budget
MAX_COST_CENTS = 500    # cost circuit breaker per run
TIMEOUT_SECONDS = 300   # wall-clock timeout
```

> "An agent without guardrails is just a while loop with a credit card." — Ace The Cloud

These limits live in the orchestration layer, not in the system prompt. Prompt-based limits are suggestions; code-enforced limits are constraints.

### 3. Exponential backoff on tool failures, not blind retry

Tool failures (timeouts, rate limits, 5xx errors) should retry with exponential backoff:

```python
for attempt in range(3):
    try:
        return await call_tool(tool, params)
    except (RateLimitError, TimeoutError):
        wait = 2 ** attempt + random.uniform(0, 1)
        await asyncio.sleep(wait)
else:
    raise ToolExhaustedRetries(f"{tool} failed after 3 attempts")
```

Do not ask the LLM to retry — it has no knowledge of network conditions or rate limits. Tool-level retry is a mechanical concern, not a reasoning one.

### 4. Fallback chains for degraded operation

Define fallback paths for every external dependency:

- Primary search API fails → fallback to secondary search provider
- Primary LLM fails → route to fallback model with lower capability but higher availability
- Tool returns empty result → surface partial result with confidence signal, don't fail silently

This is graceful degradation — maintain as much functionality as possible rather than failing completely.

### 5. Checkpointing for resumable state

After each successful tool call or reasoning step, serialize agent state (conversation history, accumulated results, current plan) to durable storage. On failure, resume from the last checkpoint instead of restarting from scratch.

LangGraph's built-in checkpoint support and Microsoft Agent Framework's checkpoint/resume primitives handle this natively. Without checkpoints, a 50-call workflow that crashes 3 times recomputes every step each time — compounding cost and latency.

### 6. Self-correction loops with bounded escalation

Agent self-correction is valuable but must be bounded:

```
attempt self-correction → if still wrong after 2 retries → escalate to human
                                                    → or accept degraded output
```

Unbounded self-correction is the loop's loop. Cap it at 1-2 rounds, then route to an escalation path.

### 7. Emit structured observability for every failure event

Every retry, fallback, degradation, and loop-exit event should emit a structured metric:

```
agent_retries_total{model="claude-sonnet", error_type="rate_limit"}
agent_fallbacks_total{from_model="gpt-4o", to_model="gpt-4o-mini"}
agent_degradation_level{step=5, level="partial"}
```

Without metrics, you cannot distinguish "agents are recovering correctly" from "agents are failing silently."

## Evidence

- **GitHub (vectara/awesome-agent-failures):** Community-curated taxonomy of 7 failure modes including tool hallucination, response hallucination, goal misinterpretation, and tool call loops — with real examples and mitigation techniques. 194 stars, Apache 2.0, active since August 2025. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Hacker News (Ask HN):** Production practitioners reporting: agents lose track of prior decisions over long chains, constraint adherence degrades over time, constraint tension (not step count) drives drift, and external state management survives where internal state doesn't. — [news.ycombinator.com/item?id=47039354](https://news.ycombinator.com/item?id=47039354)
- **Geta Team Blog:** After deploying hundreds of agents in production: single unhandled API timeout cascaded into 47 Slack alerts and complete system failure. Post-implementation results with circuit breakers, retry logic, and graceful degradation: 94.2% → 99.7% uptime, 23 min → 2 min recovery time, 6 weeks without a 3am incident. — [blog.geta.team/why-90-of-ai-agents-fail-in-production](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/)
- **Harsh Rastogi (Asynq.ai / Modelia.ai):** Candidate evaluation agent hallucinated tool parameters and got stuck in loops in production; image generation pipeline approved obviously flawed outputs while optimizing for workflow completion. Cost ran 3x budget before guardrails added. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Research (Tsinghua study, cited by OpenLLM):** Analysis of 10,000 agent loop executions found 7.3% exhibited self-reinforcing loop behavior — agent output fed back as input in a way that caused the loop to never converge. — [openllm.wavise.com/blog/agent-loop-error-recovery-patterns](https://openllm.wavise.com/blog/agent-loop-error-recovery-patterns)

## Gotchas

- **Hard step caps alone are not enough.** An agent can exhaust its step budget by making the same wrong decision 12 times. Combine step caps with progress detection (is the agent making measurable progress, or cycling the same state?).
- **Self-correction is not error handling.** Asking the LLM to "try again" when a tool fails is a semantic retry that has no knowledge of the error type. Distinguish mechanical failures (retry mechanically) from semantic failures (let the LLM reason about them).
- **Checkpointing without resumability is half-measure.** Saving state to disk is not enough — the orchestration layer must be able to detect a crashed run and restart it from the checkpoint automatically. Build the resume path, not just the save path.
- **Cost circuit breakers must be outside the agent's trust boundary.** An agent that monitors its own spend can rationalize exceeding the limit. Budget enforcement belongs in the orchestration layer, not in the agent's reasoning.
- **Graceful degradation requires upfront design.** Adding fallback paths after a production incident is too late. Map every external dependency to a fallback at design time.
