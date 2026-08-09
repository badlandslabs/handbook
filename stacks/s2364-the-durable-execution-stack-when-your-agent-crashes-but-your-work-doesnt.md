# [S-2364] · The Durable Execution Stack

When your agent spends 6 hours and 47 tool calls on a task, then loses everything on a timeout — and you have no choice but to start over.

## Forces
- LLM API calls timeout. SDKs crash. Network connections drop. Context windows overflow. But the work itself has side effects you can't undo.
- Existing retry logic (S-352) assumes idempotent steps — but a 47-step research pipeline that half-writes a database is not idempotent.
- Recovery (S-1003) handles crashes after the fact. Durable execution prevents them by design — the workflow survives the crash without restarting.
- Checkpoint verification (S-1239) catches corruption. But the failure mode that costs the most isn't corruption — it's recomputation.
- 73% of enterprise AI agent deployments experience reliability failures within their first year. The math gets worse as tasks grow longer: doubling duration quadruples failure probability.

## The move

The pattern: **persist workflow state at every step** — not just data, but the entire execution point. When a crash occurs, the workflow resumes from the last valid step, not from scratch.

Three structural layers:

**1. Checkpoint-per-step**: Serialize agent state (memory, tool results, conversation history, pending actions) after every LLM call. Use deterministic hashes to detect whether a step actually completed before resuming.

**2. Workflow orchestrator (Temporal / Restate / DBOS / Inngest)**: Wrap the agent loop in a durable execution runtime. The runtime guarantees at-least-once execution and provides built-in pause/resume, human-in-the-loop checkpoints, and automatic retry with backoff.

**3. Replay safety guard**: Not all agent steps are safe to replay. Before resuming, verify which tool calls were committed (side effects) vs. only computed. Replay only the safe prefix.

```python
# Minimal durable execution wrapper for an agent loop
from temporalio import workflow
from temporalio.common import RetryPolicy
import asyncio

async def run_agent_task(task_id: str, goal: str):
    """Durable agent task — survives API crashes and worker restarts."""
    async with workflow.unsafe.import_workflow_modules():
        pass  # In real code: import from worker module

    # RetryPolicy: exponential backoff, max 3 attempts, non-retryable on timeout
    retry_policy = RetryPolicy(
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(minutes=5),
        backoff_coefficient=2.0,
        non_retryable_error_types=["IdempotencyKeyConflict"],
    )

    result = await workflow.execute_activity(
        "run_agent_step",
        task_id,
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=retry_policy,
    )
    return result

# LangGraph checkpoint + Temporal integration (Temporal Jul 2026 plugin)
# Agents can now run on Temporal without rewriting their codebase.
# Human-in-the-loop: workflow durable_pause() waits indefinitely at a step,
# resuming only when a human approves or provides input — zero cost while paused.
```

```python
# LangGraph checkpointer — minimal Postgres-backed persistence
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])

graph = build_agent_graph()
config = {"configurable": {"thread_id": task_id}}

# First run: executes all steps and persists state after each
app = graph.compile(checkpointer=checkpointer)
result = await app.ainvoke({"input": goal}, config)

# Crash here — task fails on step 48 of 50

# Second run: resumes from last checkpoint, not from scratch
result = await app.ainvoke(None, config)  # state loaded from DB
# Continues from step 48 → 49 → 50
```

**Key signals for when you need this:**
- Tasks exceeding 30 minutes
- More than 10 sequential tool calls
- Any tool call with side effects (write, send, execute)
- Multi-agent handoffs
- Tasks where recomputation costs > $1/task

**The 73% failure math**: if each step has 99% success probability, a 50-step pipeline succeeds with probability 0.99^50 ≈ 60%. A 200-step task drops to 0.99^200 ≈ 13%. Durable execution converts this to a guaranteed completion with retries, not a coin flip.

## Receipt
> Verified 2026-08-09 — Temporal's LangGraph Python plugin (July 16, 2026) enables durable execution without code rewrite; LangGraph's built-in checkpointer persists state after each graph step to Postgres/Memory; DBOS (dbos-project) offers open-source durability with Postgres; Inngest provides serverless durable execution with SDK. Real failure scenario confirmed from Temporal blog: 6-hour agent pipeline with 47 tool calls loses all progress on API timeout — exact problem durable execution solves. AppScale analysis (Satyam Kumar, Jun 2026) covers the 73% failure rate statistic and the quadratic cost math.

## See also
- [S-352 · Agentic Compensation Keys](s352-the-agentic-compensation-keys-stack-when-your-agent-must-work-twice.md) — idempotency as the prerequisite for safe retries
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery after the fact vs. prevention
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop-stack.md) — checkpoint verification for correctness
- [S-940 · Agent Drift Recovery Stack](s940-the-agent-drift-recovery-stack-when-your-agent-is-off-the-rails.md) — recovery from behavioral drift
