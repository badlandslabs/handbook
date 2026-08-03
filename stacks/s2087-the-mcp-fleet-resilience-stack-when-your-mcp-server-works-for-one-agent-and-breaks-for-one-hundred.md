# S-2087 · The MCP Fleet Resilience Stack — When Your MCP Server Works for One Agent and Breaks for One Hundred

Your MCP server passes every test. Single agent, sequential tool calls, clean responses, happy demo. You deploy it to production. A multi-agent orchestrator scales to 40 concurrent sessions. Each agent retries on timeout — silently, 3–5 times. Your MCP server receives 200 requests per second instead of the 2 it saw in development. It cascades. Four hours later, 14 customers have duplicate charges, the agent fleet is running on a schema from two hours ago, and nobody has a runbook for this.

MCP fleet resilience is not an MCP server problem. It is the interaction between agent retry behavior, parallel fan-out, schema caching, and deployment cycles. These six failure modes only emerge at scale.

## Forces

- **Agents retry silently.** Every production-grade agent framework retries on timeout or error. These retries are invisible in development (where errors don't happen) and catastrophic in production — where a rate-limit 429 on a "send email" tool becomes 5 emails. The retry discipline that makes agents robust at the LLM layer is exactly what breaks them at the tool layer.
- **Parallel fan-out creates N+1 queries.** An orchestrating agent that calls 10 tools in parallel triggers 10 simultaneous requests to your MCP server's database. If those requests each run independent queries instead of a batch, your connection pool exhausts at 20 concurrent agents — not 200.
- **Schema caching TTLs create fleet-wide staleness windows.** MCP clients cache tool schemas. A 5-minute TTL means your entire agent fleet runs on a broken schema for up to 5 minutes after a server deploys a breaking change. At fleet scale (100+ agents), hundreds of sessions silently produce garbage output before anyone notices.
- **Agent traffic patterns don't match HTTP API patterns.** Traditional API resilience assumes HTTP semantics: idempotent GET requests, explicit retry decisions, connection reuse. Agents generate tool calls that have side effects, carry LLM-generated arguments, and trigger retries that compound non-linearly.
- **Schema drift is fleet-wide, not per-instance.** One MCP server deploys a breaking schema change. Every agent that has cached that schema continues running the old schema until its TTL expires. The gap between deploy and full rollout is measured in minutes; the blast radius is measured in corrupted task state.

## The move

### Pattern 1: Idempotency Keys on Every Stateful Tool

The retry problem is the root cause of the most visible fleet failures. Every tool with side effects must accept an idempotency key and check it before acting.

```python
# MCP server tool with idempotency
@mcp.tool()
async def send_email(to: str, subject: str, body: str, idempotency_key: str = None):
    if idempotency_key:
        # Check if already processed
        result = await db.fetchone(
            "SELECT result FROM idempotency WHERE key = $1", idempotency_key
        )
        if result:
            return result["result"]  # Return cached result, don't re-send

    # Send the email
    result = await email_client.send(to=to, subject=subject, body=body)

    if idempotency_key:
        await db.execute(
            "INSERT INTO idempotency (key, result) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            idempotency_key, result
        )
    return result
```

The agent framework must generate the idempotency key and pass it on every retry. This is a contract between the agent harness and the MCP server — not optional hardening, but a requirement for any tool that touches external state.

### Pattern 2: Batch Queries at the Fan-Out Boundary

When an agent fans out N parallel tool calls to the same MCP server, coalesce them at the transport layer.

```python
# MCP server: coalesce parallel queries to the same database table
class BatchQueryOptimizer:
    def __init__(self, batch_window_ms: int = 50, max_batch: int = 20):
        self.pending: dict[str, list[Callable]] = {}
        self.batch_window_ms = batch_window_ms
        self.max_batch = max_batch

    async def execute(self, query_key: str, fn: Callable):
        fut = asyncio.get_event_loop().create_future()
        if query_key not in self.pending:
            self.pending[query_key] = []
            # Flush after window expires
            asyncio.create_task(self._flush_after(query_key))
        self.pending[query_key].append(fn)
        if len(self.pending[query_key]) >= self.max_batch:
            await self._flush(query_key)
        return await fut

    async def _flush_after(self, query_key: str):
        await asyncio.sleep(self.batch_window_ms / 1000)
        await self._flush(query_key)

    async def _flush(self, query_key: str):
        items = self.pending.pop(query_key, [])
        if not items:
            return
        # Execute as single batch query, dispatch results
        result = await run_batch_query(items)
        for i, fn in enumerate(items):
            fn(result[i] if i < len(result) else result[-1])
```

This transforms N parallel round-trips into 1 batch round-trip. At 40 agents × 10 parallel calls, this is the difference between 400 connections and 40 batched operations.

### Pattern 3: Schema Version Registry with Change-Event Broadcasting

Replace TTL-based schema caching with a version registry. The MCP server maintains a `/schema/version` endpoint; clients subscribe to change events via Server-Sent Events (SSE) or polling with exponential backoff.

```python
# MCP server: schema version registry with change events
from fastapi import FastAPI, Response
from sse_starlette.sse import EventSourceResponse

app = FastAPI()
schema_version = {"version": 1, "hash": None, "last_updated": None}
subscribers: list[asyncio.Queue] = []

@app.get("/schema/version")
async def schema_version_endpoint():
    return schema_version

@app.post("/schema/invalidate")
async def invalidate_schema():
    schema_version["version"] += 1
    schema_version["hash"] = compute_schema_hash()
    schema_version["last_updated"] = datetime.utcnow().isoformat()
    # Broadcast to all subscribed clients
    for q in subscribers:
        await q.put(schema_version.copy())
    return {"status": "ok", "new_version": schema_version["version"]}

@app.get("/schema/stream")
async def schema_stream():
    q = asyncio.Queue()
    subscribers.append(q)
    async def event_generator():
        while True:
            version = await q.get()
            yield {"event": "schema_update", "data": json.dumps(version)}
    return EventSourceResponse(event_generator())
```

Clients that subscribe receive the new schema within milliseconds of a deploy. Critical production deployments can pin a specific schema version and opt out of auto-update until explicitly promoted.

### Pattern 4: Per-Server Circuit Breakers

Track MCP server health at the gateway layer. When a server's error rate exceeds 50% over a 30-second window, trip the circuit breaker — stop routing to it and switch to fallback tools or cached responses.

```python
# Agent gateway: per-MCP-server circuit breaker
from dataclasses import dataclass, field
from collections import deque
import time

@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: float = 0.5       # Trip at 50% error rate
    window_seconds: int = 30
    recovery_timeout: int = 60
    errors: deque = field(default_factory=lambda: deque(maxlen=200))
    last_tripped: float = 0
    state: str = "closed"  # closed | open | half-open

    def record(self, success: bool):
        self.errors.append((time.time(), success))
        # Expire old errors outside the window
        cutoff = time.time() - self.window_seconds
        while self.errors and self.errors[0][0] < cutoff:
            self.errors.popleft()

    def is_open(self) -> bool:
        if self.state == "closed":
            if not self.errors:
                return False
            error_rate = sum(1 for _, s in self.errors if not s) / len(self.errors)
            if error_rate >= self.failure_threshold:
                self.state = "open"
                self.last_tripped = time.time()
                return True
        elif self.state == "open":
            if time.time() - self.last_tripped >= self.recovery_timeout:
                self.state = "half-open"
        return self.state == "open"
```

### Pattern 5: Event-Loop Isolation for I/O-Heavy MCP Servers

Node.js MCP servers are vulnerable to event-loop saturation when fan-out requests arrive faster than I/O completes. Offload blocking I/O to a worker thread pool.

```javascript
// MCP server: worker thread pool for database I/O
import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';
import { cpus } from 'os';

const pool = Array.from({ length: cpus().length }, () => {
  return new Worker('./db-worker.js');
});

// Round-robin work distribution
let nextWorker = 0;
async function queryWithPool(sql, params) {
  const worker = pool[nextWorker % pool.length];
  nextWorker++;
  return new Promise((resolve, reject) => {
    worker.once('message', resolve);
    worker.once('error', reject);
    worker.postMessage({ sql, params });
  });
}
```

### Pattern 6: MCP Fleet Chaos Testing

Before deploying to production, run your MCP server through a fleet-scale chaos harness. The AliveMCP test suite (open source) provides fault injection for this exact scenario.

```bash
# Simulate fleet-scale conditions against your MCP server
npx @alivemcp/chaos-cli run \
  --server-url http://localhost:3000 \
  --concurrency 40 \
  --retry-count 5 \
  --retry-delay 200ms \
  --schema-change-interval 120s \
  --latency-injection "50-500ms" \
  --timeout-rate 0.05
```

Key metrics to capture: duplicate side-effect rate, schema staleness window, error rate under fan-out, event-loop lag under parallel load. If your MCP server passes 1 agent × 1 call but fails at 40 agents × 10 parallel calls, it will fail in production.

## Receipt

> Verified 2026-08-03 — Primary source: AliveMCP blog (2026-06-10), "MCP Server Production Resilience: Six Patterns for Agent-Scale Traffic." Six failure modes validated against production observability patterns (Portkey 2.0, March 2026; Infrabase LLM tooling comparison, 2026). Idempotency key pattern is standard practice in payment APIs (Stripe idempotency keys) and maps directly to agent retry semantics. Batch query coalescing is standard Postgres advisory-lock + `unnest()` pattern applied to MCP tool dispatch. Circuit breaker code is a simplified version of Python's `circuitbreaker` library adapted for MCP server health tracking.

## See also

- [S-427 · MCP Schema Contracts](stacks/s427-mcp-schema-contracts.md) — Schema versioning and drift; this entry extends that to fleet-scale staleness windows
- [S-2082 · The Fault Injection Stack](stacks/s2082-the-fault-injection-stack-when-your-agent-works-in-staging-and-fails-in-production.md) — Agent-level fault injection; this entry covers the MCP infrastructure layer underneath it
- [S-285 · MCP's Security Trap](stacks/s285-mcp-security-trap-the-standard-that-ships-compromised.md) — MCP server trust model; fleet resilience patterns assume an untrusted server population
