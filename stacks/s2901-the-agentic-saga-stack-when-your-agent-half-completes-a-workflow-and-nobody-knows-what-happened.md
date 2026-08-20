# S-2901 · The Agentic Saga Stack — When Your Agent Half-Completes a Workflow and Nobody Knows What Happened

An agent tasked with booking a trip reserves a flight, charges the card, sends a confirmation email — then hangs on the hotel reservation and silently moves on. The flight is booked and charged. The hotel never got reserved. The customer got a confirmation email for a partial itinerary. Conventional transactions have ACID rolls back on any failure. Agentic workflows have no such boundary.

## Forces

- **Agents mutate external state without atomic commits.** An agent that sends an email, writes a DB record, and calls a payment API cannot roll those back with a database revert. Each side effect needs an explicit inverse — or it stays done.
- **Partial completion looks like success.** The agent's loop completes. HTTP calls returned 200. The orchestrator marks the task done. The blast radius of what actually succeeded is invisible unless you tracked it.
- **Compensation logic is as complex as forward logic.** Unbooking a flight is not "call cancel API" — it requires checking cancellation windows, applying the right fare rules, issuing credits, notifying downstream systems. Compensation is a second first-class workflow.
- **The failure that triggers compensation is not always the step that needs compensating.** A downstream step (hotel reservation failure) may need to roll back an upstream step (the card charge). The agent needs a global state view to determine what to compensate and in what order.
- **Compensation chains can fail.** A card charge that succeeds may not reverse cleanly if the payment processor is down. A refund email may bounce. Compensation failures compound the original incident unless handled explicitly.

## The move

### Layer 1 — Declare compensation at step registration

Every side-effecting step registers its compensation before executing. The registration is not optional — the orchestrator refuses to dispatch a step with no declared compensation unless it is provably idempotent (read-only queries, read-only fetches).

```
step(
  id="charge_card",
  action=charge_card(order_id, amount),
  compensation=refund_payment(order_id, amount),  # declared upfront
  idempotency_key=order_id,
  timeout=30s,
)
```

The compensation declaration answers: *"What is the explicit inverse of this action?"* Not "what might undo it" — what is the defined undo operation. If no clean inverse exists (e.g., "send a notification that was read"), the compensation is `alert_ops_then_skip` — acknowledge the limitation and surface it.

### Layer 2 — Checkpoint state before each step

Before dispatching a step, snapshot the pre-action state of every system the step will touch. This is not the agent's memory — it is the *external system's* state. The checkpoint lives outside the agent's context window.

For a DB mutation: record the current row values as JSON before the write.
For a file write: record the file hash before modification.
For an API call: record the resource state implied by prior calls.
For an email send: record the recipient list and message ID.

Checkpoint cost is proportional to step risk. Low-risk read steps skip checkpointing. High-risk writes get a full snapshot. This is copy-on-write semantics applied to agent state, not agent memory.

Tools like MatrixOne/Memoria provide Git-level versioning for agent memory. DeltaBox (Du et al., 2026) achieves 5ms checkpoint and 14ms rollback via CRIU + overlayfs at the process/sandbox level. Replit's branching filesystem uses process forking from a frozen template to achieve sub-second state branching. These are complementary: filesystem checkpoints for tool-layer mutations, process-level checkpoints for sandbox state.

### Layer 3 — Failure triggers saga manager

When a step returns `FAILED_FATAL`, the saga manager activates:

1. **Halt forward execution** — no further steps dispatch until compensation resolves.
2. **Pop the compensation stack** — the orchestrator maintains a per-workflow LIFO stack. Each completed step pushed its compensation. Pop in reverse order.
3. **Dispatch compensations as CRITICAL-priority jobs** — not background jobs. Compensations race against time (cancellation windows, SLA breaches, compounding interest on failed charges).
4. **Route all compensations through the Safety Kernel** — every compensation action is checked against the same guardrails as forward actions. A compensation that would violate a policy (e.g., refunding a fraud-flagged account) must escalate, not silently skip.
5. **Record every compensation in the audit trail** — what failed, what was compensated, what failed to compensate, what the system state is now. This is the evidence the EU AI Act Article 14 requires for high-risk autonomous decisions.

### Layer 4 — Idempotency is load-bearing infrastructure

Compensation actions must be idempotent. A refund API called twice should not issue two refunds. An email sent twice with "please disregard the previous message" is a compliance incident. Design compensation actions as:

- **Idempotency-keyed API calls** — pass the same `order_id` or `transaction_ref` on retry. Most payment processors (Stripe, Braintree) honor idempotency keys within a 24h window.
- **Conditional execution** — `DELETE` if exists, not unconditional delete. `UPDATE SET refunded=true WHERE refunded=false`. Compensations that check preconditions before executing are safe to retry.
- **Compensation status polling** — if the compensation API is async (e.g., bank transfers), poll status rather than retry blindly. A pending refund is not a failed refund.
- **Dead letter queue for compensation failures** — if a compensation cannot execute (payment processor down, network partition), it goes to the DLQ with a reason code, and ops is paged. The workflow is *paused*, not silently marked complete.

### Layer 5 — Durable execution orchestration

For workflows that span hours or days (email sequences, scheduled jobs, human-in-the-loop approvals), durable execution frameworks (Temporal, Restate, LangGraph with persistence) provide the infrastructure:

- **Workflow history** — every step and result is logged. On worker crash, the workflow resumes from the last completed step, not from scratch.
- **Activity heartbeats** — long-running steps emit heartbeats. If the worker dies mid-activity, Temporal times it out and retries or re-runs it on a different worker.
- **Saga support built-in** — Temporal's ` compensate()` pattern and Restate's explicit compensation declarations map directly to the saga manager described above.
- **Cross-agent saga** — when a workflow spans multiple agents (orchestrator + specialized sub-agents), the saga boundary must be the workflow, not the agent. The orchestrator owns the compensation stack; sub-agents cannot unilaterally commit side effects outside it.

## Receipt

> Verified 2026-08-20 — Pattern synthesized from: Cordum AI Agent Rollback & Compensation (2026) — saga pattern with LIFO Redis compensation stack and Safety Kernel gating; AgentMarketCap Agent Checkpoint & Rollback Engineering (April 2026) — DeltaBox (5ms/14ms C/R via CRIU/overlayfs), Replit branching filesystem, MatrixOne/Memoria Git-level versioning for agent memory; AgentNative Runtime Rollback Pattern (2026) — LangGraph checkpoints + Temporal durable execution + EU AI Act Article 14 audit trail requirements; IBM STRATUS (NeurIPS 2025) — undo operator for agent-level transactional semantics; Adaline Labs Reliable Tool-Using Agents (April 2026) — idempotency keys per tool call, timeout per tool, state-mutation risk classification; Zylos Research Organizational KM for AI Agent Teams (March 2026) — knowledge management patterns for agentic teams.

## See also

- [S-2896 · The Agent Failure Recovery Stack](/stacks/s2896-the-agent-failure-recovery-stack-when-your-agent-silently-does-the-wrong-thing-for-three-hours.md) — detection and response to silent behavioral failures
- [S-1054 · The Agent Interrupt Stack](/stacks/s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — halting runaway agents; complements saga by covering the "stop" problem before the "undo" problem
- [S-1247 · The Durable Execution Stack](/stacks/s1247-the-durable-execution-stack-when-langgraph-meets-temporal-and-your-agent-stops-dying-halfway-through.md) — Temporal/Restate workflow durability; saga compensation is the complement to durable execution's forward-progress guarantees
