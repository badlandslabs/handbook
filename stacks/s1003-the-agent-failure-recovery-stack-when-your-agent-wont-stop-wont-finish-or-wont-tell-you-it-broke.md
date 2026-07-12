# S-1003 · The Agent Failure Recovery Stack — When Your Agent Won't Stop, Won't Finish, or Won't Tell You It Broke

A demo agent that works on the happy path is two months of engineering away from a production agent that handles the rough edges. Agents fail in shapes single-LLM calls don't: loops that eat tokens indefinitely, silent corruption of state mid-run, partial side effects with no path to resume, and cost spirals that only surface on the monthly bill. You need explicit failure architecture — not hope.

## Forces

- **Loop detection is a production necessity, not a nice-to-have.** A coding agent in an infinite while loop burned ~$800 before producing 1,100 commits — and one instance had to `pkill` itself to escape. Without hard caps, the loop is the only ceiling.
- **Partial execution is the default failure mode.** Tool hangs, rate limits, and malformed JSON don't produce errors — they produce half-finished tasks, corrupted memory, and no way to resume where you left off. Stateless-with-replay is not an architecture; it's a gap.
- **Error taxonomy is non-obvious.** Retrying a transient error (rate limit) works. Retrying a semantic error (wrong tool, malformed JSON) almost never helps — you need to re-prompt with corrective context. Treating all errors the same produces retry loops that make things worse.
- **Recovery must be deterministic, not LLM-generated.** Asking the agent "what should we do now?" after a failure adds non-determinism on top of an already-failed state. Pre-validated recovery workflows stored in the state machine are the production pattern.
- **Observability for agents is not the same as for services.** Latency and token counts are table stakes. The hard part is tracing coordination between agents and reconstructing *why* the agent made each decision — not just what it output.

## The Move

Build failure recovery as an explicit, layered system. These are the five patterns that appear across real deployments, in order of implementation priority.

### 1. Hard Step Caps — The Non-Negotiable Ceiling

The single most important guardrail. Stop execution after N steps regardless of progress.

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

In LangGraph: `recursion_limit=12` on the compiled graph. This is the circuit breaker that prevents cost spirals. Every framework worth using exposes this. If yours doesn't, add it at the orchestration layer.

### 2. Error Taxonomy with Distinct Recovery Paths

Not all errors are equal. Classify before retrying:

| Error Type | Examples | Recovery |
|---|---|---|
| **Transient** | Rate limit (429), timeout, DNS failure | Retry with backoff — the same call will likely succeed |
| **Semantic** | Malformed JSON, wrong tool name, schema violation | Re-prompt with corrective context — retrying the same prompt won't help |
| **Auth/permission** | Expired token, missing scope | Refresh credentials, escalate to human — don't retry blindly |
| **Resource exhaustion** | Context window full, OOM | Truncate oldest memory, checkpoint, resume with compressed state |

The key insight: *retrying a semantic error produces the same error*. Most teams implement retry for everything and are confused why their agents loop on malformed tool responses.

### 3. State Checkpointing — Resume from the Last Good Step

Production LLM agents fail mid-execution. A checkpoint system lets them resume without starting over.

**Two-layer architecture:**

- **Operational state** (conversation messages, tool call history, intermediate results) — serialized at every step boundary, append-only. Never mutate a persisted step.
- **Checkpoint metadata** (step index, agent ID, failure reason, recovery intent) — separate from state, enables the resumption protocol.

```python
# Checkpoint every step boundary — not on every tool call
def checkpoint(state, step_metadata):
    snapshot = {
        "step": step_metadata["index"],
        "messages": state["messages"],
        "tool_results": state["tool_results"],
        "timestamp": now(),
        "failure_context": step_metadata.get("last_error")
    }
    store.append(snapshot)  # append-only, immutable

def resume(thread_id):
    snapshots = store.get(thread_id)
    last = snapshots[-1]
    return {"messages": last["messages"], "resume_from_step": last["step"] + 1}
```

LangGraph users: `MemorySaver()` or `PostgresSaver` with `thread_id` rehydration is the built-in path. Call `graph.invoke()` with the same `thread_id` and LangGraph loads the most recent checkpoint automatically.

**Sync vs. async:** Sync checkpointing adds 50–200ms per step. Async flush trades 5–15ms latency for configurable risk of losing the last step on crash. For latency-sensitive agents, async with a 1-step lag is the practical choice.

### 4. Self-Verification Loops — Catch Errors Before They Compound

The biggest obstacle to production agents is error accumulation across multi-step workflows. Self-verification closes the gap: the model checks its own output before treating it as input to the next step.

**Verification patterns in practice:**

- **Output validators:** A separate LLM call (or structured schema check) validates the output of each step before the agent proceeds. A tool call that returned a list of 0 results gets flagged, not silently passed to the next step.
- **Reflection loop:** Inspired by Aider's approach — when an edit fails, lint errors are detected or tests fail, the system automatically retries with structured feedback injected back into context. The feedback includes the exact error message, not a vague "something went wrong."
- **Confidence thresholding:** Some teams run multiple independent inferences and only proceed if a majority or quorum threshold is met. Cost becomes a function of required reliability.

> "The question shifts from 'is this output correct?' to 'how much certainty do we need, and what are we willing to pay for it?'" — *mapace22, HN discussion on consensus-based agent systems*

### 5. Structured Observability — Tracing Beyond Latency

Standard service observability (latency, error rates, token counts) misses the agent-specific failure modes. What you actually need:

- **Step-level traces:** Every agent loop iteration as a span — with input state, tool calls made, tool results, and LLM output. This is how you answer "which step caused the failure?"
- **Agent coordination traces:** When multiple agents chain together, OpenTelemetry + LGTM stack handles individual call latency. Breaking down *coordination failures between agents* requires custom instrumentation.
- **Cost-per-task tracking:** Not per-call — per-task. Because a task with 8 retries costs 8x more than one with 1 retry, and they may have identical accuracy.

## Evidence

- **HN Thread (425 pts, 308 comments):** repoMirror/ralph ran coding agents in a `while true` loop — $800 total cost, 80–90% completion rate on porting tasks, ~1,100 commits across projects. Key finding: at one point the agent used `pkill` to terminate itself when stuck in an infinite loop. Also: prompt improvements ballooned to 1,500 words and made the agent *worse* — minimal, tightly-scoped prompts outperformed detailed orchestration. — [HN 45005434](https://news.ycombinator.com/item?id=45005434)
- **Optio (Show HN):** Open-source Kubernetes orchestration for coding agent swarms. Implements self-healing as a first-class feature: auto-resume on CI failures, merge conflicts, and reviewer change requests. Every task goes through intake → isolated K8s pod execution → PR monitoring → self-healing cycle. — [HN 47520220](https://news.ycombinator.com/item?id=47520220)
- **HN Thread:** Multi-agent debugging in production. Practitioners report reaching for the same o11y primitives used in distributed systems — tracing, circuit breakers, retry policies, SLOs — but the tooling doesn't yet map cleanly onto agent coordination failures. One contributor noted OpenTelemetry works for per-call latency but "breaks down when debugging coordination between agents." — [HN 47358618](https://news.ycombinator.com/item?id=47358618)

## Gotchas

- **Hard step caps without escalation are half-measures.** An agent that hits its step cap and raises an exception is still a failure from the user's perspective. Wire the cap-exceeded path to an escalation: human notification, ticket creation, or at minimum a coherent error message with the checkpoint location for manual resume.
- **Checkpointing without append-only semantics creates corruption.** If you mutate persisted state in place (overwrite step 3 with step 4's result), a crash during write leaves you with neither. Always append; treat checkpoints as immutable snapshots.
- **Treating all errors as retryable is the most common mistake.** The retry loop is the new infinite loop. Rate limit → retry. Malformed JSON → re-prompt. Wrong tool → re-plan. Auth failure → refresh or escalate. Each error type has exactly one right response.
- **Self-verification adds 2–3x token cost per step.** This is the real cost of reliability. Budget for it explicitly. A verification chain that doubles token count is still cheaper than a task that runs 8 extra steps because errors weren't caught early.
- **Context window overflow is a failure mode, not an edge case.** Long-running agents accumulate memory, tool results, and intermediate outputs. Design for truncation and compression as first-class operations, not afterthoughts.
