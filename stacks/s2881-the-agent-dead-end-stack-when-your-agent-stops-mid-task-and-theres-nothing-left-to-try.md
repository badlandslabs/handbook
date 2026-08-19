# S-2881 · The Agent Dead-End Stack — When Your Agent Stops Mid-Task and There's Nothing Left to Try

Your agent is 4 steps into an 8-step task. The API call times out. It retries — succeeds. But the response is garbled. Did the action happen? Should it retry? The agent has no answer, so it invents one and presses on. Three steps later the whole output is wrong and nobody knows why. The failure wasn't the timeout — it was everything after it.

## Forces

- **Agents fail across time, not at a point.** Traditional software fails with a stack trace. An agent fails across a sequence of partial states: step 3 of 8 succeeded but returned malformed output, step 4 ran on bad data, and by step 5 the agent is confidently wrong.
- **Errors and "wrong answers" look identical.** The LLM returns HTTP 200 with valid JSON — but the value is hallucinated. Your retry logic never fires because nothing errored. The agent silently drifts off-course.
- **Policy in the prompt is not policy.** Telling an agent "do not issue refunds over $500" is not the same as refusing to issue them. The agent processes the instruction but will find workarounds when users rephrase their intent. Policy enforcement belongs in the tool layer, not the system prompt.
- **Retries without idempotency cause double-write.** Retrying a refund call that already succeeded — because you never knew it succeeded — is worse than the original failure. Agents retry on ambiguous state, which is the most dangerous failure mode.
- **Step caps prevent runaway loops but don't recover partial work.** Setting MAX_STEPS=12 stops the infinite loop. It doesn't save the 11 completed steps. Every interruption becomes a full restart.

## The move

Build a failure-aware agent architecture: classify errors by type, route them to different recovery strategies, checkpoint progress durably, and escalate to a human before the agent causes harm.

### 1. Classify errors into a taxonomy with distinct handlers

Not all errors are equal. Route by type:

| Error Type | Examples | Handler |
|---|---|---|
| **Transient infrastructure** | 429 rate limit, 408 timeout, 503 unavailable | Exponential backoff + jitter, max 3–5 retries |
| **Tool-call failure** | API returns error, invalid params, auth expired | Retry once, then fallback to alternative tool |
| **Ambiguous state** | Tool called, response malformed, uncertain if action succeeded | Do NOT retry blindly — query state externally, then decide |
| **LLM failure** | Malformed JSON output, schema mismatch | Re-prompt with stricter format instructions |
| **Hallucination / wrong reasoning** | HTTP 200, valid JSON, wrong value | Output validation against ground truth, self-correction loop |
| **Hard limit reached** | MAX_STEPS exceeded, token budget exhausted | Stop, checkpoint, escalate |

### 2. Make tools idempotent or stateless-verifiable

This is the single highest-leverage change for retry safety:

- Design tools so duplicate calls produce the same result (GET endpoints, DELETE by ID with idempotency key)
- If a tool is not idempotent, the tool itself must expose a state-query endpoint: *"did X already happen?"*
- Never retry a tool call that modified state without first verifying the current state
- Add idempotency keys to write operations: `tool_call_id = hash(task + timestamp + caller)`

```python
# Before retrying a non-idempotent tool call
current_state = await verify_state(action_id)  # must exist
if current_state == expected_state:
    return  # already succeeded, don't retry
# otherwise, safe to retry
```

### 3. Checkpoint after every significant step — not just on completion

Save execution state durably (database, file, or workflow engine) after each step, not only on success:

- Completed tool calls with their inputs and outputs
- Agent's reasoning state at that point
- Which step number and what remains

CrewAI's checkpointing (v1.14+, backed by Temporal) and open-source tools like `agent-resume` (MukundaKatta) and `ai-agent-checkpoint-and-resume` (AxmeAI) handle this. The key property: if the agent crashes at step 47 of 50, the next run resumes at 48, not 1.

### 4. Set hard step caps and escalate on exhaustion

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    # MAX_STEPS exceeded — agent is looping or stuck
    # Do NOT let it continue. Checkpoint. Escalate.
    await save_checkpoint(state)
    await escalate_to_human(state, reason="step_limit_exceeded")
```

When escalation fires, the agent's work product goes to a human review queue — not the user. This is the last line of defense before harm reaches customers.

### 5. Wrap external dependencies in circuit breakers

If an external API is failing, don't keep hammering it — open the circuit and fall back:

```python
breaker = CircuitBreaker(
    failure_threshold=5,      # open after 5 failures
    recovery_timeout=60,       # try again after 60s
    expected_exception=APIError
)
with breaker:
    result = await external_api.call()
```

When the circuit is open, the agent uses cached data, a fallback model, or skips the step — never hangs waiting for a dead service.

## Evidence

- **Blog post:** AI Agent Failures: Real Incidents — reconstructed incident where a Q3 2025 e-commerce refund agent processed ~$1.2M in unauthorized refunds because refund policy was in the system prompt ("do not issue refunds over $500") rather than enforced in the tool layer. Users discovered that rephrasing requests to match the agent's training distribution bypassed the soft constraint. Also documents a document-processing agent that hallucinated a missing field value, confirmed the hallucination to the user, and then acted on it. — [agentbrisk.com/blog/ai-agent-failure-modes-real-incidents](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents/)
- **Blog post / technical guide:** Reliable AI Agent Pipelines — 30-min technical guide covering error taxonomy (6 types), retry strategies (idempotent vs. non-idempotent), circuit breakers for LLM tool calls, idempotent tool design, human-in-the-loop escalation gates, and fault-injection testing. States the core thesis: "Reliability in AI agent pipelines is not primarily an LLM problem. The problem is the engineering scaffolding around them." — [chaitanyaprabuddha.com/blog/reliable-ai-agent-pipelines-orchestration-retries](https://www.chaitanyaprabuddha.com/blog/reliable-ai-agent-pipelines-orchestration-retries)
- **Ask HN thread:** "How are you testing AI agents before shipping to production?" — practitioner discussion of 7 common failure modes including hallucination under unexpected inputs, edge-case collapse (nulls, Unicode names), prompt injection, context limit surprises, and the demo-to-production gap. Notes Gartner prediction that over 40% of AI agent projects will fail by 2027. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **GitHub:** `MukundaKatta/agent-resume` — open-source checkpoint-and-resume for batch agent jobs. Crash on item 47, next run resumes at item 48. JSONL store, zero dependencies, MIT license. — [github.com/MukundaKatta/agent-resume](https://github.com/MukundaKatta/agent-resume)
- **GitHub:** `AxmeAI/ai-agent-checkpoint-and-resume` — durable execution by default for AI agents. Compares to LangGraph (requires manual checkpoint code + PostgresSaver) and CrewAI (restarts from zero) — claims automatic step-47 resume without framework lock-in. — [github.com/AxmeAI/ai-agent-checkpoint-and-resume](https://github.com/AxmeAI/ai-agent-checkpoint-and-resume)
- **Documentation:** CrewAI Checkpointing (v1.14+) — automatic execution state saves during run. Crews, flows, and agents resume after failure or can be forked into alternate branches. Temporal workflow engine provides durability. — [docs.crewai.com/v1.14.0/en/concepts/checkpointing](https://docs.crewai.com/v1.14.0/en/concepts/checkpointing)

## Gotchas

- **Treating 4xx and 5xx the same in retry logic.** 4xx means the caller sent bad input — retrying will never help. 5xx means the server is having trouble — retry with backoff. 429 (rate limit) means wait and retry. Conflating these causes agents to waste cycles on impossible requests.
- **Adding retry logic without idempotency.** If a refund call succeeds but the response is lost, retrying it issues the refund again. Always check state before retrying non-idempotent operations, or use idempotency keys at the API level.
- **Soft validation in the system prompt instead of hard guards in tools.** "The agent should refuse requests over $500" will be overridden by a carefully worded user request. "$500+ refunds require human_approval=true" as a tool parameter forces the check at the infrastructure level — the model cannot bypass it by rephrasing.
- **Checkpointing to memory instead of durable storage.** In-process checkpointing survives a retry but not a crash. Persist to a database, file store, or workflow engine (Temporal, etc.) for true durability.
- **Missing observability on escalation queues.** The escalation path is your last line of defense — and it's useless if nobody is monitoring the queue depth and reviewing escalations daily. Set alerts on queue depth and circuit breaker state.
