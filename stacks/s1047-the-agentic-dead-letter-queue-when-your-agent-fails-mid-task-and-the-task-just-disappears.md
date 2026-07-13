# S-1047 · The Agentic Dead Letter Queue — When Your Agent Fails Mid-Task and the Task Just Disappears

Your agentic pipeline runs 200 tasks/hour across 12 sub-agents. Last Tuesday, 3 tasks failed mid-run due to an upstream API change. No exception. No alert. No trace. The tasks simply vanished from the queue — consumed tokens, generated partial state, and disappeared. Six hours later, a customer reported their request was never processed. Nobody knew it had failed. This is the durability gap: agents that can start a task but cannot survive a failure, cannot checkpoint their state, and cannot hand off to a human when they get stuck.

## Forces

- **Agents are stateful and non-deterministic.** A traditional microservice failure is deterministic — same input, same output, same error. An agent failure is path-dependent: it ran 11 of 14 steps, consumed 40k tokens, and failed at step 12. The "failed task" isn't a crashed function — it's a partial execution with half-completed state.
- **Without durable queues, failures are invisible.** Most agent frameworks (LangChain, CrewAI, AutoGen) run in-process or in ephemeral containers. When the process dies, the task is gone. No audit trail. No retry window. No escalation.
- **Human escalation without context is useless.** Paging an on-call engineer with "something failed" is not a workflow. The receiver needs the full trajectory: what the agent was doing, where it failed, what it had already committed, what state the downstream systems are in.
- **Retry without idempotency is dangerous.** Replaying a failed agent run can produce different outputs — different tool calls, different parameters. If the first run partially wrote to a database or sent a notification, retrying can corrupt state or send duplicate events.
- **Step-level vs. agent-level recovery have completely different tradeoffs.** Replaying 1 failed step costs 1–5% of a full run. But you need checkpointing granularity to isolate which step failed. Most teams don't have it.

## The Move

Build a **three-tier failure recovery architecture**: (1) a durable task queue that survives process crashes, (2) step-level checkpoints that enable selective retry, and (3) a DLQ with full trajectory capture for human escalation.

### Tier 1 — Durable Task Ingestion

```
1. Ingest task → write to durable queue (NATS JetStream, SQS, Temporal workflow)
2. Assign task_id + version stamp before any agent work begins
3. Agent pulls task, processes, writes completion marker on success
4. On any failure → task stays in queue or moves to DLQ sub-queue
```

Use **event sourcing** for agent state: every tool call, every decision, every output is a log entry with task_id + step_num. The "current state" is the last log entry, not a mutable record.

### Tier 2 — Step-Level Checkpointing

```
At each step boundary:
  checkpoint = {
    step_num,
    input_state,
    tool_calls_made,
    tool_results,
    model_output,
    timestamp
  }
  write_checkbar(checkpoint)  # append-only, versioned by step_num
```

After a failure, recovery replays from the last checkpoint — not from step 0. Use idempotency keys on all write operations so replay is safe. Wrap side-effecting tool calls (`send_email`, `write_db`, `call_payment_api`) with explicit **commit/rollback markers** so you know what actually persisted.

### Tier 3 — Dead Letter Queue with Trajectory Capture

```
Failed task → DLQ entry {
  task_id,
  failed_at_step,
  full_trajectory,        # all checkpoints + tool calls + outputs
  failure_classification, # LLM-classified: semantic-error / structural-error / timeout / rate-limit
  downstream_state,       # what the agent already committed
  escalation_policy,      # queue: retry / dead-letter-review / human-escalation
  retry_count,
  created_at
}
```

**Key insight**: the DLQ entry must contain enough to either (a) auto-retry with a fix, (b) hand to a human who can act in under 2 minutes, or (c) mark as permanently failed with a reason. A DLQ that just says "FAILED" is not a DLQ — it's a graveyard.

### Failure Classification Drives Escalation Policy

Route DLQ entries by failure class:

| Classification | Action |
|---|---|
| `structural-error` (timeout, rate-limit, network) | Auto-retry with exponential backoff, max 3 attempts |
| `semantic-error` (wrong tool, bad output, hallucination cascade) | DLQ review — requires human or supervisor-agent to inspect trajectory before retry |
| `idempotency-violation` (partial write, duplicate risk) | Dead-letter-review — manual resolution required |
| `escalation-trigger` (high-value task, user-in-waiting) | Immediate human notification with trajectory summary |

### The HITL (Human-in-the-Loop) Escalation Shortcut

For the 5% of tasks that genuinely need a human:

```
DLQ → human dashboard
  ┌─ task_id, user, priority
  ├─ "Agent was trying to: [one-line summary from trajectory]"
  ├─ "Failed at step N with: [error + LLM-classification]"
  ├─ "Already committed: [list of confirmed side effects]"
  └─ [Resume] [Cancel+Refund] [FixAndRetry] buttons
```

The human should never have to read a raw trace. The agent produced a one-line intent summary + a ranked list of options. This is the difference between a 30-second resolution and a 30-minute archaeology session.

## Receipt

> Verified 2026-07-13 — Research sources: Tian Pan "Distributed Tracing Across Agent Service Boundaries" (Apr 2026); Zylos Research "Agent-to-Human Handoff Patterns" (Apr 2026); Agent.ceo "NATS Dead Letter Queues for AI Agents" (Dec 2026); saisrinivas-samoju agentic-architectures dead-letter pattern; Google ADK checkpoint-resume documentation (2026). Practical reference: Temporal workflow `wait_condition` + checkpoint architecture. Pattern synthesizes queue durability (SQS/NATS) + event-sourced checkpoints + LLM-classified failure routing + structured escalation UI — none of these components individually covers the full three-tier pattern.

## See also

- [S-1032 · The Dead Letter Stack](/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — covers retry granularity and step-level economics; this entry covers durable persistence and structured escalation
- [S-1023 · The Recovery Ladder](/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — covers semantic failure detection; this entry covers what to do after detection fails
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the organizational discipline that makes DLQ governance sustainable
