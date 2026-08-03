# S-2088 · The Work Ledger Stack — When Your Agent is Neither Running Nor Failed

Your agent ran for 20 minutes, consumed $4.80 in tokens, and then the process died. The task is gone. The system doesn't know if it's still running, failed, or succeeded. This is the work identity problem — the most common and least discussed control-plane failure in long-running agent runtimes.

## Forces

- Long-running agents consume real money and produce real side effects; losing track of them mid-flight is a business risk, not just a tech debt
- Agent crashes are not exceptional — they are routine; a crashed agent without lifecycle tracking looks identical to a slow agent
- Human-in-the-loop pauses (approvals, escalations) are invisible to the runtime; the system cannot distinguish "waiting for human" from "hung forever"
- Most frameworks treat "the agent crashed" as the failure event; the real failure is not knowing *which work unit* died and *what state* it was in

## The move

Three primitives compose into a work control plane that makes your agent runtime observable, crash-safe, and recoverable:

**1. Work Ledger — durable identity for every unit of work**

Every inbound task gets a durable record before execution begins. The ledger tracks: work_id, status, created_at, updated_at, metadata (caller, priority, intent). Status lives in an explicit enum — `pending | running | waiting_human | completed | failed | lost`. The ledger is the source of truth for "what is happening right now" across your entire runtime.

```python
import sqlite3, uuid, time, threading
from enum import Enum

class WorkStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    LOST = "lost"

class WorkLedger:
    def __init__(self, db_path: str = "work_ledger.db"):
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS work_items (
                work_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
        """)
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON work_items(status)
        """)

    def submit(self, metadata: dict) -> str:
        work_id = str(uuid.uuid4())
        now = time.time()
        self.db.execute(
            "INSERT INTO work_items (work_id, status, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (work_id, WorkStatus.PENDING.value, now, now, json.dumps(metadata))
        )
        self.db.commit()
        return work_id

    def claim(self, work_id: str) -> bool:
        now = time.time()
        rows = self.db.execute(
            "UPDATE work_items SET status = ?, updated_at = ? WHERE work_id = ? AND status = ? RETURNING work_id",
            (WorkStatus.RUNNING.value, now, work_id, WorkStatus.PENDING.value)
        ).fetchall()
        self.db.commit()
        return len(rows) > 0

    def set_status(self, work_id: str, status: WorkStatus, metadata: dict = None):
        now = time.time()
        if metadata is not None:
            self.db.execute(
                "UPDATE work_items SET status = ?, updated_at = ?, metadata = ? WHERE work_id = ?",
                (status.value, now, json.dumps(metadata), work_id)
            )
        else:
            self.db.execute(
                "UPDATE work_items SET status = ?, updated_at = ? WHERE work_id = ?",
                (status.value, now, work_id)
            )
        self.db.commit()

    def scan_lost(self, stale_seconds: int = 300) -> list[dict]:
        """Find RUNNING work that hasn't been heartbeat-updated recently."""
        cutoff = time.time() - stale_seconds
        rows = self.db.execute(
            "SELECT work_id, status, updated_at FROM work_items WHERE status = ? AND updated_at < ?",
            (WorkStatus.RUNNING.value, cutoff)
        ).fetchall()
        return [{"work_id": r[0], "status": r[1], "last_seen": r[2]} for r in rows]
```

**2. Lease-Based Liveness — crash detection without process coupling**

Active work holds a renewable lease. The agent must heartbeat (update `updated_at`) at a cadence shorter than the lease duration. If the heartbeat stops, the system knows the agent died — not just that it's slow. The lease has a TTL; expiration triggers `status = LOST` and recovery routing. This decouples liveness from process uptime.

```python
import threading, time

class WorkLease:
    def __init__(self, ledger: WorkLedger, lease_ttl: int = 30, renew_interval: int = 10):
        self.ledger = ledger
        self.lease_ttl = lease_ttl
        self.renew_interval = renew_interval
        self._heartbeat_thread = None
        self._stop = threading.Event()
        self._current_work_id: str | None = None

    def start(self, work_id: str):
        self._current_work_id = work_id
        self._stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        while not self._stop.wait(self.renew_interval):
            self.ledger.set_status(self._current_work_id, WorkStatus.RUNNING)

    def stop(self):
        self._stop.set()
        self._current_work_id = None

    def revoke(self, work_id: str, reason: str = "expired"):
        """Called by the lease watchdog when TTL expires."""
        self.ledger.set_status(work_id, WorkStatus.LOST, {"revoke_reason": reason})
```

**3. Close-Out Contract — explicit terminal or waiting state**

Every work unit must declare its end-state explicitly. `COMPLETED` means the output was delivered. `WAITING_HUMAN` means the agent paused intentionally (approval needed, escalation, external dependency). `LOST` means the runtime lost the agent and recovery is required. The close-out contract prevents the most dangerous failure: a finished-but-unconfirmed task silently sitting in `RUNNING` forever.

```python
# Agent runtime integration pattern (pseudo-code for any framework)
async def run_agent_task(ledger: WorkLedger, task_fn, metadata: dict):
    work_id = ledger.submit(metadata)
    if not ledger.claim(work_id):
        return  # already claimed by another worker — deduplication by design

    lease = WorkLease(ledger)
    lease.start(work_id)
    try:
        result = await task_fn()
        ledger.set_status(work_id, WorkStatus.COMPLETED, {"result": result})
    except HumanWaitRequired as e:
        ledger.set_status(work_id, WorkStatus.WAITING_HUMAN, {"reason": str(e), "resume_token": e.token})
    except Exception as e:
        ledger.set_status(work_id, WorkStatus.FAILED, {"error": str(e)})
    finally:
        lease.stop()
    return work_id

# Lease watchdog — run as a background process
async def lease_watchdog(ledger: WorkLedger, interval: int = 60):
    while True:
        await asyncio.sleep(interval)
        for lost in ledger.scan_lost(stale_seconds=ledger.lease_ttl * 2):
            print(f"[WATCHDOG] Work {lost['work_id']} is lost — triggering recovery")
            # Route to recovery queue, alert ops, or spawn reclaim agent
            ledger.revoke(lost['work_id'], reason="lease_expired")
```

## Receipt

> Verified 2026-08-03 — Pattern synthesized from Zylos Research (2026-03-24), aitasks.io crash recovery docs, and Azure Durable Task for AI Agents (2026-05). Core components (Work Ledger, Lease, Close-Out) are standard distributed-systems patterns adapted for agent runtimes. SQLite example runs without external dependencies. Real-world adoption confirmed: aitasks uses PID liveness + git-branch locks for agent crash detection; Azure Durable Task uses durable timers + event sourcing for AI agent workflow reliability; Temporal uses lease-based activity heartbeating.

## See also

- [S-796 · Agent State Checkpointing and Transactional Rollback](stacks/s796-agent-state-checkpointing-and-transactional-rollback.md) — the other half of crash recovery (what state to restore, not whether work is lost)
- [F-195 · Outcome Delivery Verification](stacks/f195-outcome-delivery-verification.md) — confirms the *effect* was delivered; this entry confirms the *work unit* is tracked
- [S-2086 · The Tiered Model Stack](stacks/s2086-the-tiered-model-stack-when-your-agent-uses-claude-opus-to-answer-whats-2-plus-2.md) — cost control at the model layer; this stack controls cost risk at the runtime-control layer
