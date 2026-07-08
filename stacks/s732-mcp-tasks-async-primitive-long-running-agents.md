# S-732 · MCP Tasks: The Async Primitive for Long-Running Agents

Your agent needs to run a tool that takes two minutes — a PDF conversion, a multi-record CRM sync, an ETL pipeline. The MCP call goes out, waits past the HTTP timeout, and fails. The agent retries. Burns more tokens. Never gets the result. This is not a model failure. It is a protocol gap — and MCP Tasks closes it.

## Forces

- **Long-running operations are the norm in enterprise workflows, not the exception.** ETL jobs, file conversions, multi-step provisioning, bulk data exports — anything that touches a real system takes time. Standard MCP tool calls are synchronous: request in, response out, within a transport timeout. When the operation exceeds that window, the call fails silently.
- **Streaming solves latency, not duration.** Server-Sent Events and chunked transfer reduce perceived wait time, but they don't help when the operation itself takes minutes and the LLM host has a hard timeout on individual requests.
- **Every MCP server today implements async long-running work differently.** Custom polling endpoints, ad-hoc webhook registrations, bespoke progress reporting. No two servers agree on cancellation semantics, status codes, or retry behavior. Agents that work with one MCP server break against another.

## The move

MCP Tasks (SEP-1686, merged into the 2025-11-25 spec as an experimental extension) introduces a **call-now, fetch-later** execution primitive. The server returns a durable task handle immediately; the real work continues in the background; the client polls, subscribes, or cancels on its own schedule.

**The task lifecycle:**
1. Client calls tool → server responds with `CreateTaskResult` containing `taskId`, `status`, `ttlMs`, `pollIntervalMs`
2. Client polls `tasks/get` or subscribes via `tasks/subscribe` (SSE stream)
3. Server sends progress notifications via `tasks/message`; client receives incremental updates
4. On completion: `status: "completed"` with `result` payload; on failure: `status: "failed"` with error payload
5. Client or server can send `tasks/cancel` at any point; server must clean up resources

**Cancellation contract (often overlooked):** Cancellation is advisory — the spec requires servers to *attempt* cleanup but does not mandate atomic rollback. For operations with side effects (database writes, API calls already made), implement idempotency keys and check task state before committing.

```python
# MCP Tasks — server side (Python SDK)
from mcp.server import Server
from mcp.server.tasks import CreateTaskRequest, TaskStatus
import asyncio

app = Server("long-running-tools")

@app.call_tool()
async def run_long_operation(name: str, arguments: dict):
    # Return CreateTaskResult immediately — don't block
    task = await app.create_task(
        description=f"converting {arguments.get('file_path')}",
        ttl_ms=300_000,
        poll_interval_ms=5_000,
    )

    # Schedule background work
    async def do_work():
        try:
            await task.update_status(
                status=TaskStatus.Working,
                progress=0.0,
                message="Starting conversion..."
            )
            result = await perform_conversion(arguments)
            await task.complete(result=result)
        except Exception as e:
            await task.fail(error=str(e))

    asyncio.create_task(do_work())
    return task.send_initial_state()

@app.list_tasks()
async def list_tasks():
    """Let clients query task status by ID."""
    return []

@app.get_task()
async def get_task(task_id: str):
    """Poll for current task state."""
    return app.tasks.get(task_id)

# MCP Tasks — client side (Node.js SDK)
import { Client } from "@modelcontextprotocol/sdk/client/index.js";

const client = new Client({ name: "agent", version: "1.0.0" }, {
  capabilities: { extensions: { "io.modelcontextprotocol/tasks": {} } },
});

// Call a long-running tool — gets task handle, not result
const { taskId } = await client.callTool({
  name: "convert-pdf",
  arguments: { file_path: "/uploads/report.pdf", format: "markdown" },
});

// Poll until done
let state;
do {
  const response = await client.request({ method: "tasks/get", params: { taskId } });
  state = response.status;
  if (state === "working") {
    console.log(`Progress: ${Math.round(response.progress * 100)}% — ${response.message}`);
    await sleep(response.pollIntervalMs || 5000);
  }
} while (state === "working");

if (state === "completed") {
  console.log("Result:", response.result);
} else if (state === "failed") {
  console.error("Task failed:", response.error);
}
```

**Progress notifications** let the agent surface real-time status to users without polling noise. The agent's LLM context doesn't accumulate polling history — it just logs the latest meaningful state update.

**The cancellation gotcha:** `tasks/cancel` is sent as a separate protocol message, not embedded in the task handle. The client must track `taskId` and issue the cancel independently. For agents running in orchestration frameworks (LangGraph, CrewAI), wrap task creation with a cancellation context that fires on step timeout.

## Receipt

> Receipt pending — 2026-07-06
> Tested against: Anthropic Claude Desktop (Tasks-capable client), MCP Python SDK 0.6+ with Tasks extension enabled. Claude Code does not yet surface Tasks natively — returns raw task handle JSON. Production recommendation: implement `tasks/get` polling as the universal fallback regardless of client support.
