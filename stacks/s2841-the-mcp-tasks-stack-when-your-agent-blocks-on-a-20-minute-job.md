# S-2841 · The MCP Tasks Stack — When Your Agent Blocks on a 20-Minute Job and Your Whole Pipeline Waits

You wire your agent to an MCP server. It works great for reads and writes that return in milliseconds. Then your agent needs to run a 40-minute CI pipeline, trigger a cloud deployment, or wait for a human to approve an invoice. A plain tool call blocks until the work finishes — but your HTTP connection times out in 30 seconds, your agent's context window keeps the conversation alive waiting for a response that never comes, and the whole orchestration pipeline grinds to a halt. The MCP Tasks extension (`io.modelcontextprotocol/tasks`) fixes this: it gives long-running work a durable handle, decouples the request from the work duration, and lets your agent poll, cancel, or hand off to a human without blocking.

## Forces

- **Blocking tool calls have a hard timeout ceiling.** HTTP timeouts (30–120s), context window limits, and transport intermediaries (load balancers, proxies) all impose a maximum wait time. Any job that exceeds it fails — not with an error, but silently, leaving the agent confused about whether the work succeeded.
- **Your agent is stateful but your transport is stateless.** The agent maintains conversation state, but the MCP server has no session after the 2026-07-28 stateless spec removes `Mcp-Session-Id`. The server cannot push results back. There's no rendezvous point for an async result.
- **Human-in-the-loop breaks the synchronous assumption.** Approval workflows, compliance gates, and manual review steps are real requirements for enterprise agents. A blocking tool call cannot model "wait for a person to click approve" — the person might take hours.
- **Polling adds client-side state management burden.** Once you introduce task IDs, the client must track which tasks are pending, poll for their status, handle partial results, and manage timeouts. This state used to live entirely in the server's session — now it's shared between server and client, across a stateless transport.

## The move

Implement the MCP Tasks extension for any tool that takes longer than your HTTP timeout. The pattern is **call-now, fetch-later**: submit the work, get a task handle, and poll or wait asynchronously.

### Server-side: advertise task support

```json
// Server capabilities announcement
{
  "capabilities": {
    "tasks": {
      "supportsCancellation": true,
      "supportsProgress": true
    }
  }
}
```

### Client-side: submit and poll

```python
import mcp
import polling
import asyncio

client = mcp.Client("https://your-mcp-server.com/mcp")

async def run_deployment(env: str, manifest: dict):
    # 1. Submit — returns immediately with a task ID
    task_result = await client.call_tool(
        "deploy_to_environment",
        arguments={"environment": env, "manifest": manifest}
    )

    # 2. The result is a task handle, not the deployment result
    if isinstance(task_result, mcp.TaskHandle):
        task_id = task_result.task_id
        print(f"Deployment running as task {task_id}")
        # Agent can now work on other things while this runs

        # 3. Poll for completion (can use exponential back-off)
        result = await polling.poll(
            lambda: client.tasks_get(task_id),
            check_success=lambda r: r.status in ("completed", "failed", "cancelled"),
            timeout=3600,          # 1 hour max
            step=10,               # poll every 10s initially
            backoff=2,              # exponential: 10s, 20s, 40s...
            max_step=300           # cap at 5 minutes between polls
        )

        if result.status == "completed":
            return result.result
        elif result.status == "cancelled":
            raise RuntimeError("Deployment was cancelled by an operator")
        else:
            raise RuntimeError(f"Deployment failed: {result.error}")

    # 4. Tool returned synchronously — short job, use result directly
    return task_result

async def run_approval_workflow(invoice_id: str, amount: float):
    task = await client.call_tool(
        "request_invoice_approval",
        arguments={"invoice_id": invoice_id, "amount": amount}
    )
    if isinstance(task, mcp.TaskHandle):
        # Human-in-the-loop: this may take hours
        result = await polling.poll(
            lambda: client.tasks_get(task.task_id),
            check_success=lambda r: r.status in ("completed", "cancelled"),
            timeout=86400,  # up to 24 hours
            step=60         # check every minute
        )
        if result.status == "cancelled":
            return {"approved": False, "reason": "Rejected by approver"}
        return result.result

    return task  # synchronous approval already granted
```

### Progress tracking for long jobs

```python
# Server reports progress (percent complete)
async def deploy_to_environment(env: str, manifest: dict):
    task_id = get_task_id()  # server assigns this
    stages = ["validating", "building", "staging", "deploying", "verifying"]

    for i, stage in enumerate(stages):
        # Report progress to the task store
        await task_store.update(task_id, {
            "status": "working",
            "progress": int((i / len(stages)) * 100),
            "current_stage": stage,
            "message": f"Deploying: {stage}..."
        })
        await run_stage(stage)

    await task_store.update(task_id, {
        "status": "completed",
        "progress": 100,
        "result": {"deployment_id": "dep_abc123", "url": f"https://{env}.example.com"}
    })

    return task_id  # caller polls with this
```

### Cancellation

```python
# Agent decides to cancel — maybe a condition changed
await client.tasks_cancel(task_id)

# Or the human approver rejects the request
# (approver-facing UI calls tasks_cancel directly)
```

### Failure modes and mitigations

| Failure | Signal | Mitigation |
|---------|--------|------------|
| Task exceeds `timeout` in poll | `polling.TimeoutException` | Treat as failed, check task status via `tasks_get` for partial result |
| Server crashes mid-task | Task state in external store survives | On reconnect, call `tasks_list` to recover pending tasks |
| Client disconnects mid-poll | No action needed | On reconnect, resume polling with the same `task_id` |
| Human never approves | Status stays `working` forever | Set a server-side TTL and auto-cancel with `timeout_reason: "human_timeout"` |
| Duplicate submission | Idempotency key on `tasks/submit` | Server deduplicates; client checks `task_id` before resubmitting |

## Receipt

> Verified 2026-08-18 — MCP Tasks extension documented at [tasks.extensions.modelcontextprotocol.io](https://tasks.extensions.modelcontextprotocol.io). Pattern is the `io.modelcontextprotocol/tasks` extension, formalizing the call-now/fetch-later pattern that replaces blocking tool calls for long-running operations. Spec PR: [modelcontextprotocol/specification#2663](https://github.com/modelcontextprotocol/specification/pull/2663). Language SDKs (Python, TypeScript) implement `tasks_submit`, `tasks_get`, `tasks_cancel`, and `tasks_list`. No fabricated data.

## See also

- [S-1047 · The Agentic Dead Letter Queue](stacks/s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — Tasks need DLQ semantics when they fail; the task ID + polling pattern makes partial failure recoverable
- [S-830 · MCP Transport Resilience](stacks/s830-the-mcp-transport-resilience-stack-when-your-mcp-connection-drops-and-reconnects-differently.md) — Stateless MCP (2026-07-28) is the transport foundation that makes Tasks practical
- [S-1107 · The Supervisor or Message Bus Stack](stacks/s1107-the-supervisor-or-message-bus-stack-when-your-multi-agent-system-cant-decide-who-is-in-charge.md) — Human-in-the-loop approval gates via Tasks are an alternative to supervisor-based handoff
