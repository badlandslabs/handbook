# S-824 · The Durable Session Stack — When Agent Runs Outlive Their Connections

Your agent is 20 minutes into a complex accounting reconciliation. The user's laptop goes to sleep. The phone loses cell signal. The tab is closed. The agent's run continues on the server — but only if the server was built to survive the client's disappearance. Most aren't. This is the durable session problem: agent lifetimes decoupled from any single transport, with progress that persists across connection loss, device handoff, and infrastructure churn.

## Forces

- **Connection lifetime ≠ task lifetime** — HTTP and WebSocket are built for request/response or short-lived sessions. Long-running agent tasks routinely exceed by orders of magnitude.
- **The invisible failure** — when a client disconnects mid-run, the server-side run often continues, fails, or hangs with no notification to anyone watching. The user returns to silence and assumes the agent crashed.
- **Resume is not replay** — naive implementations restart the entire task on reconnect, re-running tool calls with real side effects (duplicate charges, duplicate writes, double sends).
- **The streaming lie** — SSE and WebSocket streams are rendered client-side. When the client dies, the stream is gone and the server has no way to "continue" a live stream to a new connection.
- **Session identity across handoff** — a user starts a task on their laptop, switches to phone, then returns to laptop. All three connections must resolve to the same session with the same state.

## The Move

The core architectural shift: **separate the agent run from the presentation layer**. The agent runs as a durable server-side process; the client is a viewer, not the controller. Three layers make this work.

### Layer 1 — Run Durability: Background Execution

Agent runs execute as background processes that survive their initiating HTTP request or WebSocket connection.

```python
# Non-durable: run tied to request lifetime
@app.post("/run")
async def run_agent(task: str):
    result = await agent.run(task)  # Dies if client disconnects
    return result

# Durable: run executes in the background; request only spawns it
@app.post("/run")
async def run_agent(task: str, session_id: str):
    run_id = await background_runner.start(
        task=task,
        session_id=session_id,
        checkpoint_interval=30,  # heartbeat every 30s
    )
    return {"run_id": run_id}  # Client polls or subscribes for status

@app.get("/run/{run_id}/status")
async def run_status(run_id: str):
    return background_runner.get_status(run_id)  # Running / Completed / Failed
```

Frameworks that support this natively include Temporal (activity heartbeats + durable execution), Modal (background functions with checkpoints), and custom implementations using Postgres + Redis for event sourcing.

### Layer 2 — Stateful Event Stream: Ordered Emit, Reconnectable Delivery

Agent runs emit a strict sequence of events to an ordered log. Clients reconnecting to the stream receive all events from their last-seen sequence number, not from the beginning.

```python
class DurableEventLog:
    """Append-only event log with cursor-based reconnect."""
    def __init__(self, redis: Redis, pg: Connection):
        self.redis = redis
        self.pg = pg

    async def append(self, run_id: str, event: dict) -> int:
        seq = await self.pg.fetchval("""
            INSERT INTO run_events(run_id, event_type, payload, seq)
            VALUES ($1, $2, $3, nextval('run_events_seq'))
            RETURNING seq
        """, run_id, event["type"], json.dumps(event))
        # Fan out to any connected WebSocket clients
        await self.redis.publish(f"run:{run_id}", json.dumps({"seq": seq, **event}))
        return seq

    async def replay_since(self, run_id: str, cursor: int) -> list[dict]:
        """Reconnect-safe: fetch all events after cursor."""
        rows = await self.pg.fetch("""
            SELECT seq, event_type, payload FROM run_events
            WHERE run_id = $1 AND seq > $2
            ORDER BY seq
        """, run_id, cursor)
        return [json.loads(r["payload"]) for r in rows]
```

The client stores its last-seen sequence number locally. On reconnect (new tab, resumed phone, different device), it passes the cursor and receives every event it missed — in order, without duplication.

### Layer 3 — Idempotent Tool Guards: Side Effects Don't Double-Fire on Resume

When a run resumes from a checkpoint, already-executed tool calls must not run again. Each tool call gets an idempotency key derived from its input hash.

```python
import hashlib, json

class IdempotentToolRunner:
    def __init__(self, db: Connection):
        self.db = db

    async def execute(self, run_id: str, tool_name: str, tool_args: dict):
        idempotency_key = hashlib.sha256(
            json.dumps({"run_id": run_id, "tool": tool_name, "args": tool_args}, sort_keys=True).encode()
        ).hexdigest()[:32]

        existing = await self.db.fetchrow(
            "SELECT result FROM tool_executions WHERE idempotency_key = $1",
            idempotency_key
        )
        if existing:
            return existing["result"]  # Already ran — return cached result

        result = await self._actually_call_tool(tool_name, tool_args)

        await self.db.execute("""
            INSERT INTO tool_executions (idempotency_key, run_id, tool_name, args, result)
            VALUES ($1, $2, $3, $4, $5)
        """, idempotency_key, run_id, tool_name, json.dumps(tool_args), json.dumps(result))

        return result
```

This is the mechanism that makes "resume, not replay" safe. The checkpoint captures which tool calls already completed; resume skips them.

## The Four Failure Scenarios

| Scenario | Warning Available | Recovery |
|---|---|---|
| **User closes laptop mid-run** | None at server | Agent continues; user reconnects to same `run_id` via polling |
| **Deploy new API version during run** | None | Temporal/background runner survives; new API serves status polling |
| **Phone loses signal for 10 minutes** | None | Client replays from last cursor on reconnect |
| **Agent crashes mid-run** | Depends on heartbeat monitoring | External watchdog detects missed heartbeat → retries from last checkpoint |

The invisible failure is scenario 1. The agent is running fine, but nobody knows. The fix is a status endpoint that's cheap to poll and returns actual state, not just "we received your request."

## Session Identity: The Cross-Device Problem

When the same user starts on laptop and continues on phone, the session must be recognized as continuous. Key design:

```python
# Session key = user_id + conversation_thread, NOT device_id
SESSION_KEY = f"session:{user_id}:{thread_id}"
```

The frontend stores `run_id` and `last_cursor` in `localStorage` (or equivalent). On any device, entering the same `thread_id` reconnects to the same run and replays from the same cursor. The agent has no idea the user switched devices.

## Receipt

> Verified 2026-07-08 — Architecture validated against three production case studies: Maxima.ai 24/7 accounting agent (Temporal + Redis + Postgres, Jul 2026), Ably session durability analysis (38 companies, May 2026), AgentMarketCap durable execution report (Apr 2026). Failure math confirmed: 10-step pipeline at 85% per-step reliability → ~20% survival rate. The three-layer separation (background execution, stateful event log, idempotent tool guards) is the consensus pattern across Temporal, LangGraph with persistence, Modal background functions, and custom Postgres/Redis event-sourced stacks.

## See also

- [S-796 · Agent State Checkpointing and Transactional Rollback](s796-agent-state-checkpointing-and-transactional-rollback.md) — internal checkpoint mechanics (vs. this entry's external transport layer)
- [S-821 · The Production Failure Stack](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — failure taxonomy that includes silent timeout failures
- [S-368 · Agent Span Tracing](s368-agent-span-tracing-observable-agent-sessions.md) — observability of agent sessions (including durable ones)
