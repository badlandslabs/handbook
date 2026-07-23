# S-1514 · The Stuck Agent Stack — When Your Agent Fails but Keeps Trying Anyway

Your agent hasn't crashed. The process is still running. But it's on step 47 of a task that should have finished at step 12, looping on a malformed JSON response it keeps trying to parse, burning tokens and making no progress. This is the stuck agent problem: agents that fail silently and keep running, the way Ralph Wiggum once declared "I'm not a chunky monkey" while continuing to eat one. The fix isn't a smarter model — it's a recovery architecture built into the scaffold.

## Forces

- **Loops are the default failure mode.** Classic software crashes and exits. Agents keep going because the system expects them to. An LLM that can't find a field will keep looking for it indefinitely — "let me try one more thing" is not a bug, it's a feature — until it isn't.
- **Failure taxonomy matters more than retry counts.** Transient errors (rate limits, timeouts) need different fixes than semantic errors (malformed JSON, hallucinated tool names) or progress failures (alive but stuck). Applying the wrong fix wastes time and money.
- **State is fragile.** Agents checkpoint their memory in memory — until the pod restarts. Long-running agents lose everything when infrastructure fails, not just the current task.
- **External verification is the only honest completion signal.** Agents self-report success. They are not reliable about it. OpenAI's Computer-Using Agent scored 38.1% on OSWorld — it was breaking workflows at least twice per task. Any completion signal that comes from the agent itself is suspect.

## The move

Build a layered recovery architecture with five distinct layers:

**Layer 1 — Hard step caps.** The single most effective guardrail. Stop the agent if it doesn't finish in a bounded number of steps. For LangGraph: `recursion_limit=12`. For raw loops: `MAX_STEPS = 12`. Raise a named exception and route to recovery. This alone prevents infinite loops from burning tokens or crashing your rate limits.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

**Layer 2 — Tool-level retry budgets with exponential backoff.** Route errors by type before retrying. Rate limits (HTTP 429) get backoff + jitter. Server errors (500/503) get fewer retries before fallback. Network timeouts get immediate retry. Each tool gets its own retry budget, tracked independently.

```python
# Strategy: transient errors → retry with backoff
# Strategy: semantic errors (bad JSON, wrong schema) → NO retry, fix prompt or fail
# Strategy: rate limits → backoff + jitter, fallback chain
# Strategy: max retries exceeded → route to DLQ
```

**Layer 3 — Checkpointing with durable persistence.** LangGraph's `MemorySaver` (in-memory, lost on restart) vs `PostgresSaver` / `RedisSaver` (durable across pod restarts). For production: use `AsyncPostgresSaver` with `psycopg_pool.AsyncConnectionPool` — but note the common mistake: wrapping a sync `psycopg.connect()` inside async code silently blocks the event loop under concurrent load. Use `temporal-langgraph-checkpoint-recovery` for heartbeat-based checkpointing with automatic crash recovery.

**Layer 4 — Ralph Loop: external verification as completion signal.** Named after Ralph Wiggum (not particularly smart, never gives up), this pattern traps an AI coding agent in a loop that never ends on its own — it re-invokes the agent after each attempt, using the filesystem as state. The agent self-reviews after each round and keeps iterating until external verification passes (tests, linters, type checkers). This is the anti-pattern for "agent claims done but isn't." One implementation produced 1,100 commits across 6 repos overnight. The key is that verification is external — a test suite, not the model's self-assessment.

```bash
# Ralph Loop core: external verification gate
while :; do
  cat PROMPT.md | agent
  # Verification is external — if tests pass, you break out
  if verify.sh; then break; fi
done
```

**Layer 5 — Dead Letter Queues for unresolvable failures.** Tasks that exhaust retries, step caps, or fallbacks go to a DLQ with full context (error type, step count, token usage, partial output). Route to human review. A production DLQ architecture at scale handles 50,000+ agent tasks per hour by separating retry orchestration (Cloud Tasks) from message durability (Cloud Pub/Sub). DLQ payloads must include the checkpoint state so humans can resume the task, not restart it.

## Evidence

- **Research post:** AI Agent Error Handling & Recovery — Zylos Research found layered error handling (retries → fallbacks → circuit breakers) achieves 24%+ improvement in task success rates, and identified three distinct failure modes: liveness failures (crashes), progress failures (high activity, zero progress), and quality failures (wrong output, hallucinations). — [zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery](https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery)
- **Engineering blog:** Manvendra Rajpoot's 2026 guide documents step caps, tool-level retries, fallback paths, and cost circuit breakers as the core toolkit. Key insight: "Self-correction is just a retry with a better error message — let the validator tell the model exactly what was wrong." — [blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Open-source repo:** beckyeeky/ralph-loop — GitHub repo implementing the Ralph Loop pattern with filesystem state machine and built-in self-review. Named by Geoffrey Huntley, enabled 1,100 commits across 6 repos in one night by treating failure as feedback rather than termination. — [github.com/beckyeeky/ralph-loop](https://github.com/beckyeeky/ralph-loop)
- **GitHub repo:** steveandroulakis/temporal-langgraph-checkpoint-recovery — Production template combining LangGraph with Temporal's heartbeat checkpointing for automatic crash recovery. — [github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery](https://github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery)
- **Industry research:** Coasty's analysis of 14,000+ AI agent sessions found that 40%+ of agentic AI projects will fail by 2027, with the primary cause being lack of observability into agent behavior. OpenAI's Computer-Using Agent scored 38.1% on OSWorld (workflow tasks) vs Coasty's 82%, showing completion verification matters enormously. — [coasty.ai/blog/ai-agent-monitoring-observability-40-percent-failures](https://coasty.ai/blog/ai-agent-monitoring-observability-40-percent-failures)

## Gotchas

- **Don't retry semantic errors.** If the model returns malformed JSON or a hallucinated tool name, retrying with the same prompt produces the same bad output. Fix the prompt or schema, or fail and escalate — don't loop.
- **Async checkpointers are a common production trap.** The LangGraph docs show synchronous PostgresSaver examples. In async FastAPI, a sync `psycopg.connect()` inside the lifespan silently blocks the event loop. Use `AsyncPostgresSaver` with `psycopg_pool.AsyncConnectionPool` instead.
- **Step caps must raise, not return.** If you hit the cap and just return whatever partial state the agent has, callers will treat it as a successful completion. Raise a named exception (`AgentExceededSteps`) so the recovery layer routes it to DLQ, not success.
- **Cost circuit breakers are separate from step caps.** A step cap limits iterations. A cost circuit breaker limits spend. Claude Code saying "successfully completed" while running up a $200 bill is a cost failure, not a progress failure — track them independently.
