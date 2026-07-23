# S-1538 · The Cascade Failure Stack

When a single step in a multi-step agent goes wrong and takes the whole run down with it.

## Forces

- **Agents fail virally, not locally.** A tool returns garbage or a hallucinated argument. The agent reasons from that garbage. Three steps later the output is confident nonsense. There's no crash, no exception — just wrong output that looks right.
- **Traditional try-catch doesn't help.** Agents fail in semantically ambiguous ways: HTTP 200 with bad JSON, a successful tool call that semantically missed the mark, a model that confidently generates an invalid parameter. The error isn't a failure state — it's a wrong answer wearing a success code.
- **Retry logic without classification wastes budget.** Blindly retrying a 401 (auth error) or a validation failure burns tokens and delays escalation. But retrying a 429 (rate limit) without backoff is just hammering a door that's already closed.
- **Failure propagation is the central bottleneck.** A single upstream error cascades through planning, memory retrieval, and tool invocation. The error doesn't stay where it landed — it deforms every downstream step.

## The move

**Build a classified failure-recovery pipeline where each error type gets its own recovery strategy, escalation path, and recovery budget.**

### 1. Classify before recovering

Route every error into one of four buckets before deciding what to do:

| Error Kind | Examples | Recovery |
|---|---|---|
| **Transient** | 429 rate limit, 5xx server error, DNS timeout, connection reset | Retry with exponential backoff + jitter |
| **Auth/credential** | 401 unauthorized, 403 forbidden, expired token | Re-authenticate, then retry once — never retry blindly |
| **Semantic/tool-fail** | Tool returned garbage, invalid JSON, wrong schema, MCP unreachable | Per-tool recovery: fix args, swap tool, or bail |
| **Agentic** | Hallucinated parameters, confident wrong answer, loop detection | Try-different pattern: change strategy or escalate |

### 2. Never retry without classifying

```python
# Wrong: blind retry
try:
    result = tool.call(args)
except Exception:
    result = tool.call(args)  # same args, same failure

# Right: classify then act
error_kind = classify_error(e)
if error_kind == "transient":
    retry_with_backoff(tool.call, args, max_retries=3)
elif error_kind == "auth":
    re_authenticate()
    retry_with_backoff(tool.call, args, max_retries=1)
elif error_kind == "semantic":
    fix_and_retry(tool, args)  # e.g., correct malformed params
else:
    escalate_to_human(context=e, partial_result=partial)
```

### 3. Build a fallback chain, not a single retry

Every critical tool gets a fallback:

```
primary: OpenAI function call
  → fallback: Anthropic function call
    → fallback: cached response (last known good)
      → fallback: human escalation with full context
```

The escalation principle: use the cheapest pattern that works for the failure type. Don't escalate a rate limit. Don't retry a 401.

### 4. Cap recovery budgets per-step and per-run

- **Per-step budget:** 3 retries for transient, 1 retry for auth, 1 fix attempt for semantic.
- **Per-run budget:** Global step ceiling (e.g., 20 steps) + cost ceiling (e.g., $5/task). When either hits, graceful stop — save state, surface partial result.
- **Recovery budget tagging:** Tag each tool call with a risk level (READ/WRITE/DESTRUCTIVE). DESTRUCTIVE writes never retry without an idempotency key.

### 5. Detect semantic failures with LLM-as-judge

The hardest failures are the ones that return HTTP 200. After each tool call, run a lightweight validator:

- **Schema validation** — Pydantic model confirms the output shape matches expectations.
- **Semantic validation** — A small model judges: "Did the tool output actually answer the question?" If no, trigger try-different pattern.
- **Consistency check** — Compare result against prior context. Does this contradict what we already know? Flag and retry.

### 6. Checkpoint long-running pipelines

For agents with 5+ steps, snapshot state after each successful step:

```
checkpoint: {step: 3, context: [...], last_tool: "...", last_result: "..."}
```

On failure, reload from last checkpoint instead of restarting from scratch. This turns a crash into a resume.

### 7. The five-stage self-healing cycle

1. **Detect** — Monitor step success rates, error rates by type, cost per run, token usage.
2. **Diagnose** — Classify the error type; route to the correct recovery handler.
3. **Repair** — Execute the recovery strategy (retry, fix args, swap tool, reload checkpoint).
4. **Verify** — Run post-repair validation before continuing.
5. **Escalate** — If recovery fails, surface a structured handoff to a human with full context — not a screenshot, not a Slack alert with no detail.

## Evidence

- **Engineering blog (LoopLlama, 2025):** "A crew that nails a task on stage will, at scale, loop forever, blow a budget, call a tool with garbage arguments, or quietly produce a confident wrong answer. Most failures aren't about the model being too dumb. They're operational." — [LoopLlama: Why agents fail in production](https://loopllama.ai/blog/why-agents-fail-in-production)
- **Research synthesis (Zylos, 2026):** "67% of AI system failures stem from improper error handling rather than algorithmic issues." — [Zylos: AI Agent Self-Healing Patterns](https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery)
- **Engineering blog (DEV Community, 2025):** "Tool failures in LLM agents are not edge cases — they are the normal operating condition. Most agent code handles this poorly. The tool returns an error string. The model tries the same tool again with the same arguments. The error repeats." — [DEV Community: Three Error Recovery Patterns for LLM Agent Tool Failures](https://dev.to/mukundakatta/three-error-recovery-patterns-for-llm-agent-tool-failures-3dkl)
- **Engineering post (AgentWorks, 2026):** "A demo agent that works on the happy path is two months of engineering away from a production agent that handles the rough edges." — [AgentWorks: Agent Error Handling and Recovery Patterns](https://agent-works.ai/insights/agent-error-handling-and-recovery-patterns-production-ready-resilience)

## Gotchas

- **Classifying is harder than retrying.** Most teams implement retry before classification and then wonder why budget disappears on non-retryable errors. The classify-then-act ordering is the key discipline.
- **Circuit breakers are necessary for external tools, not just model calls.** If a downstream API has failed 5 times in 60 seconds, stop calling it — don't wait for the model to timeout on each attempt. Track failure counts per endpoint.
- **Checkpointing adds latency.** Snapshotting state after every step is cheap; re-executing from checkpoint on a 12-step pipeline that fails at step 9 is not. Budget the checkpoint writes.
- **Escalation without context is useless.** "Agent failed at step 4" tells a human nothing. Escalation must include: what was the goal, what happened at each step, what was the error, what partial output exists, and what recovery was already attempted.
- **Silent failures are worse than loud ones.** A tool call that returns HTTP 200 but with an empty payload is not a success. Instrument every tool call for both HTTP-level and semantic-level success signals.
