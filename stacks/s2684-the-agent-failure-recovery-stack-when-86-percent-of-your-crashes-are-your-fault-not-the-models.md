# S-2684 · The Agent Failure-Recovery Stack

When your agent loops infinitely, your API calls time out silently, and your circuit breaker trips at 3 AM — and you realize the model wasn't the problem. The integrations were.

## Forces

- **Deterministic code meets non-deterministic models.** Traditional error handling assumes a function fails the same way every time. Agent tool calls can fail due to model drift, hallucinated arguments, token limits, *and* infrastructure — each requiring a different recovery path.
- **Recovery overhead vs. agent autonomy.** Every retry, checkpoint, and approval gate adds latency and cost. But removing them means a single failure cascades into a corrupted state you can't recover from.
- **86% of failures are recoverable, yet most agents aren't built to recover.** (The Operator Collective, 2026) The gap isn't model capability — it's the system around the model.
- **Multi-agent cascading is the killer.** A failure in one agent can propagate to others if you don't isolate error boundaries. Most orchestration frameworks assume happy paths.

## The Move

Build a failure taxonomy into the agent loop itself — classify the failure mode first, then apply the right recovery primitive. Don't retry blindly.

### Classify before you recover

Route each failure to its recovery path based on type:

| Failure class | Recovery primitive | Rationale |
|---|---|---|
| Tool timeout / network | Retry + exponential backoff + fallback | Transient, likely to succeed on repeat |
| Hallucinated tool args | Output validation before execution | Reject at the gate, don't call the tool |
| Infinite loop / over-thinking | Hard step cap with checkpoint | Detect and halt before token blowup |
| Permission / auth failure | Fail closed — deny on error | Don't allow unknown state |
| Multi-agent cascade | Circuit breaker per agent | Isolate the blast radius |
| Silent tool success (wrong data) | State diff validation post-call | 200 OK ≠ correct result |

### Implement state checkpoints at every tool boundary

```python
# Before tool call — snapshot state
checkpoint_before = serialize(agent_state)

# Execute
result = tool.call(**validated_args)

# After tool call — diff validation
result_is_valid = validate_output_schema(result, expected_shape)
if not result_is_valid:
    rollback(agent_state, checkpoint_before)
    # Fallback or escalate
```

This catches the "200 response, completely wrong data" failure mode — the one that doesn't crash, just silently corrupts.

### Use a circuit breaker per agent in multi-agent systems

```python
circuit_breakers = {agent_id: CircuitBreaker(max_calls=5, window=60)
                    for agent_id in all_agents}

def call_agent(agent_id, task):
    if circuit_breakers[agent_id].is_open():
        raise CircuitOpenError(f"Agent {agent_id} exceeded failure threshold")
    try:
        return dispatch(agent_id, task)
    except AgentFailure as e:
        circuit_breakers[agent_id].record_failure()
        raise
    finally:
        circuit_breakers[agent_id].record_success()
```

Once an agent fails N times within a time window, stop routing tasks to it and alert. This prevents one degraded agent from poisoning the whole system.

### Set hard step-count guards — not soft limits

The model will keep "thinking" if you let it. Set a hard cap (e.g., 20 steps) and checkpoint the agent state before each step. When the cap is reached, evaluate whether to continue, roll back, or escalate to a human. Don't let the model self-correct its way into an infinite loop.

### Fail closed on permission errors

If a tool call fails with an auth/permission error, the agent should fail closed — deny the action, log it, and either escalate or retry with a corrected credential. Don't let the agent proceed with partial or unknown permissions.

### Route to human approval for high-risk actions

Actions that modify external state (payments, deletions, sends) should emit a checkpoint and pause for human approval — not retry. Retry on a destructive action is the wrong default.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" — best production agents use simple composable patterns, not complex frameworks. Most integration failures stem from the surrounding system, not the model. Recommends starting with predefined workflows and escalating to dynamic agents only when branching/parallelism/durability require it. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Industry report:** The Operator Collective's "AI Agent Error Handling" (March 2026) — 86% of agent failures are recoverable; 40%+ of agentic AI projects will be cancelled by 2027 due to failure handling gaps (Gartner); only 14% of enterprise agentic implementations are production-ready. Core finding: "Most multi-agent failures aren't caused by weak models — they're caused by weak reasoning architecture." — [URL](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

- **HN Ask thread:** "How are you orchestrating multi-agent AI workflows in production?" (4 months ago) — practitioners report combining LangGraph + custom orchestrators, running agents as parallel workers in isolation with shared-nothing message-passing. Key pattern: circuit breakers per agent worker. Comments note that most teams over-engineer orchestration before they need it. — [URL](https://news.ycombinator.com/item?id=47660705)

- **Developer blog:** "AI Agents in Production: Architecture Patterns for Reliable, Safe, and Scalable Agentic Systems" (April 2026) — production stack has 5+ layers: LLM core, tool/API layer, memory management, orchestrator, observability. Identifies "silent success" (tool returns 200 with wrong data) as the most dangerous failure mode. — [URL](https://devstarsj.github.io/ai/architecture/2026/04/11/ai-agents-production-architecture-patterns-memory-safety-reliability/)

- **Developer guide:** Fast.io "AI Agent Error Handling: Best Practices & Patterns for 2025" — non-deterministic failures (model drift, token limits, hallucinated arguments) require different recovery than deterministic ones. Recommends state checkpointing and structured retry logic. — [URL](https://fast.io/resources/ai-agent-error-handling)

## Gotchas

- **Retry loops on hallucinated arguments.** If the model keeps calling a tool with wrong params, retrying just burns tokens and cycles. You need output validation *before* the tool call, not retry-after-failure.
- **Hard-coded step limits are a blunt instrument.** A genuinely complex task may legitimately need more than your cap. Checkpoint state before hitting the limit so you can resume, not restart from scratch.
- **Circuit breakers applied at the wrong granularity.** Breaker-per-request vs. breaker-per-agent has very different semantics. Per-agent is what you want — per-request creates false positives on noisy workloads.
- **"200 OK, all good" thinking.** The most dangerous failure mode is a tool call that technically succeeded but returned wrong data. Validate the *shape and content* of the response, not just the HTTP status.
- **Checkpoint explosion.** Saving full state at every tool boundary creates storage pressure on long-running agents. Batch checkpoints or use incremental diffs to keep this manageable.
