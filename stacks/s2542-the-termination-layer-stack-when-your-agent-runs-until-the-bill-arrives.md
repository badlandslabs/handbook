# S-2542 · The Termination Layer Stack — When Your Agent Runs Until the Bill Arrives

Your agent entered a feedback loop, consumed $47,000 over 11 days, and nobody noticed — because the process exited cleanly with no error code. The first signal was the invoice.

## Forces

- LLM calls are non-deterministic and expensive — you cannot naively replay them and get the same result, which breaks traditional retry-at-source patterns
- Agent crashes don't look like errors — the process exits zero, the stack is clean, but the work unit is incomplete
- The reflexion/self-correction loop (retry with reflection) compounds the problem if not bounded — each failed attempt generates context that makes the next attempt more expensive
- Multi-agent pipelines amplify failure surface area: one stuck agent takes the others with it, and cascading failures produce zero useful output at maximum cost
- Budget alerts notify after spending occurs; they do not stop the agent — the distinction between visibility and enforcement is the difference between a $500 incident and a $47,000 one

## The Move

### Classify errors before choosing a recovery path

Not all failures are equal. Treat them as distinct:

| Error Type | Shape | Recovery |
|---|---|---|
| `transient` | Network hiccup, 429, 500 | Exponential backoff + retry with jitter |
| `semantic` | LLM output fails schema validation | Retry with explicit format correction prompt |
| `budget` | Cost ceiling hit | Pause in `budget-paused` state, await top-up |
| `capability` | Missing or ambiguous tool | Escalate to parent agent or abort |
| `fatal` | Unrecoverable state (resource exhaustion) | Mark failed, return partial result, notify |

Classifying first prevents spending compute budget on retrying the wrong class of failure.

### Build idempotency into every side-effecting tool

Before executing a write action (email, API call, DB write, Discord post), check whether it has already been done:

```
if not db.exists("posts", idempotency_key):
    db.insert("posts", {..., "idempotency_key": key})
    send_discord(...)
```

One team running 5 autonomous agents 24/7 learned this after a cron job's network timeout + retry storm produced 50 duplicate Discord posts. The fix: idempotency keys and `already_posted` guards on every write path.

### Bound the reflexion loop explicitly

The self-correct / reflect-on-failure pattern is powerful but dangerous unbounded:

- Set a hard cap on iteration count (e.g., `max_reflections = 3`)
- Check semantic distance between attempts, not just tool call counts — if two consecutive LLM responses are >80% similar, break the loop even if under the count cap
- Use a circuit breaker: after N consecutive failures on the same tool, stop retrying that tool and escalate

```
attempts = 0
while attempts < max_reflections:
    result = agent.act(task)
    if result.success:
        break
    if semantic_distance(previous_result, result) < threshold:
        break  # stuck in local minimum, not making progress
    reflection = agent.reflect(previous_result, result)
    memory.append(reflection)
    attempts += 1
```

### Persist state durably — not just in memory

Agents crash mid-flight. The question is not *if* but *when*. The answer is not retry-from-scratch but replay-from-checkpoint:

- Persist every completed tool result with its output (not just the call) — LLM outputs are not replayable
- Store state as structured events (not mutable variables) — OpenAI's Threads and Temporal's Event History both model this as an append-only log
- On restart, replay the event log to reconstruct state; re-execute only the pending step

Temporal and DBOS both implement this automatically: the workflow engine records each step's output, and on crash, resumes from the last completed step without re-executing completed work.

### Instrument tool call history — detect loops before they cost money

Track the last N tool calls with their arguments. Flag two patterns:

1. **Exact repeat**: same tool, same args, immediate — classic LangChain loop (common when tool descriptions lack stop conditions)
2. **Semantic drift**: same tool, similar args, no meaningful state change across 3+ calls — the agent is making non-progress

Pattern detection is implementable as grep-plus-counts across the full run log: look for recurring failure classes, files, or regex hits. LangSmith's loop detection flags tool-call loops automatically in production traces.

### Budget enforcement, not budget alerts

A budget alert fires *after* spending. A termination guard stops the agent *before* the ceiling:

- Set `max_tokens_per_session` and `max_cost_per_run` as hard runtime limits
- Check remaining budget before every LLM call, not after
- When budget is exhausted, persist state and enter a named paused state (`budget-paused`), not a crash — so the session can be resumed once topped up

## Evidence

- **$47K Case Study (Vectara):** Four LangChain agents (Analyzer + Verifier pair) in a market-research pipeline entered an undetected feedback loop for 264 hours (11 days); discovery mechanism was a billing dashboard threshold, not any termination safeguard; total output: zero useful work. The team had observability but no enforcement. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures/blob/main/docs/case-studies/langchain-a2a-47k-infinite-loop.md)
- **Reddit/r/LocalLLaMA (NovaHokie1998, 2025):** Practitioner rebuilt their agent loop's evaluator-orchestrator workflow and concluded the real leverage was in workflow structure, not prompt length. Previously the evaluator passed PASS/FAIL and the orchestrator read the result — but subtle edge cases in that read caused non-obvious failures. Fixing the workflow routing logic had more impact than adding instructions to the prompt. — [reddit.com/r/LocalLLaMA/comments/1snsync](https://www.reddit.com/r/LocalLLaMA/comments/1snsync/i_rebuilt_part_of_my_agent_loop_and_realized_the/)
- **Temporal + OpenAI Agents SDK Integration (July 2025):** OpenAI and Temporal launched a formal integration adding durable execution to the OpenAI Agents SDK. The pattern: workflow logic runs as an append-only event log in Temporal; LLM calls happen in Activities; on crash, the workflow resumes from the last completed activity without replaying completed LLM calls. — [temporal.io/blog/announcing-openai-agents-sdk-integration](https://temporal.io/blog/announcing-openai-agents-sdk-integration) · [github.com/temporal-community/openai-agents-demos](https://github.com/temporal-community/openai-agents-demos)

## Gotchas

- A process that exits zero is not a successful process — agents can complete their execution loop while producing no useful output; you need outcome validation, not just exit-code checks
- Reflexion loops compound costs exponentially: a failed attempt generates reflection context that gets fed into the next attempt, so each retry is more expensive than the last; a 50x token blowup on restart is common
- Idempotency must cover the LLM call side too — not just the side effect; if the tool call succeeds but the result write fails, a retry re-executes the LLM call and may produce a different output
- Adding more prompt instructions to fix a failing agent is often the wrong lever — if the agent loops or produces wrong outputs, audit the workflow routing logic before lengthening the system prompt
