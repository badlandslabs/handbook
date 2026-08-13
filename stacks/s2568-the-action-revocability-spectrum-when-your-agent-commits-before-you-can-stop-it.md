# S-2568 · The Action Revocability Spectrum — When Your Agent Commits Before You Can Stop It

[Your agent sent the email, posted the Slack message, and updated the CRM — all before you could blink. The agent was "working correctly." The problem is that your system treats every completed tool call the same way: as permanently committed. But actions are not binary. Some can be undone within a time window. Most agents don't know the difference.]

## Forces

- **Irreversibility is not uniform.** Sending an email is permanent. Updating a draft document in a versioned store is reversible. Creating a Stripe payment object with a 24-hour void window is conditionally revocable. Most agent frameworks treat all three the same.
- **Agents operate at machine speed; humans need time to react.** Kore.ai Agent Productivity Index 2026 (n=408): 79.4% of consequential agent actions required manual reversal — not because agents were wrong, but because the action fired before any human could assess it. The gap between action velocity and correction bandwidth is structural.
- **Traditional software has no revocability model.** Databases have ACID transactions. Message queues have dead-letter queues. Nothing in the agentic stack has a built-in concept of "this action can be undone within N seconds if a human raises a flag."
- **Deterministic rollbacks require compensation planning at action design time.** You cannot retroactively add undo logic to an email send. The revocability window must be established before the action fires — or the action must be designed with a compensable form upfront.

## The move

### 1. Classify every action by revocability at tool-definition time

Tag each tool with a revocability descriptor — not in a comment, but in the tool schema:

```json
{
  "name": "send_email",
  "revocability": "irrevocable",
  "revocability_window_seconds": null,
  "compensation": null
}
{
  "name": "update_crm_draft",
  "revocability": "revocable",
  "revocability_window_seconds": 30,
  "compensation": "restore_previous_record"
}
{
  "name": "create_stripe_payment",
  "revocability": "conditionally_revocable",
  "revocability_window_seconds": 86400,
  "compensation": "void_payment"
}
```

Three tiers:
- **Irrevocable** — the action cannot be undone by any API. Email send, public Slack post, database DELETE. Requires pre-action human approval before execution.
- **Revocable** — the action has a built-in reversal mechanism (API-supported undo, version control, trash/restore). The agent can proceed autonomously; the revocation path is logged but does not require human intervention.
- **Conditionally revocable** — the action has a time-bounded reversal window (e.g., Stripe void within 24h, calendar invite cancellation, draft publish with pending review period). The revocation window must be tracked and acted upon before it closes.

### 2. Use a grace-period queue for conditionally revocable actions

Before firing a conditionally revocable action, the agent enqueues it in a **pending commit log** instead of executing it immediately. A background process holds the action in a staged state for the revocability window:

```
Agent: "Send follow-up email to Acme Corp"
  → Tool: send_email (irrevocable)
     → BLOCK: requires pre-action human approval
  → Tool: create_calendar_invite (conditionally_revocable, 15min window)
     → ENQUEUE: pending commit, 15-minute grace period
     → Notify: "Calendar invite created. Will commit in 15 minutes unless you cancel."
     → After 15min: mark committed
     → If cancel within window: cancel_calendar_invite
```

This is the **staged commit pattern**: actions enter a two-phase lifecycle (staged → committed) rather than binary (pending → done). The grace period gives humans and downstream systems time to detect errors before the action propagates.

### 3. Pre-compensate irrevocable actions

For actions that are genuinely irrevocable, the only recovery is *prevention*:
- Enumerate the irrevocable actions in your agent's tool catalog explicitly.
- Require human-in-the-loop approval for every irrevocable action, regardless of confidence score.
- Log the decision context (what the agent knew when it decided to act) so that rollback decisions — compensating through other channels (a follow-up email, a CRM correction) — can be made with full information.

### 4. Track revocability state in the action log

Every action record should carry:
```
{ tool, args, revocability_type, window_start, window_end, status, compensated? }
```

This turns the action log into a **revocation audit trail**: for any failed or problematic action, you can immediately see (a) whether it was revocable, (b) whether the window had closed, (c) whether compensation was attempted, and (d) what the outcome was. Without this, operators flying blind after an incident.

## Receipt

> Receipt pending — [2026-08-13]

**Research sources:**
- Kore.ai Agent Productivity Index 2026 (Jun 2026, n=408): 82% consequential actions, 79.4% manual reversal required
- Tian Pan, "The Agent Undo Button Is a Saga, Not a Stack" (tianpan.co, Apr 2026): 12-tool fan-out undo scenario, non-API-reversible operations classification
- Ultima Systems, "Undoing Agent Actions" (Jun 2026): 2-minute grace queue pattern, snapshot-before-action, saga rollback
- arXiv:2605.00424v2 Metere, "Skills as Verifiable Artifacts" (Aug 2026): revocability taxonomy (memory-buffered writes commit on confirm = reversible; email send = irreversible)
- Microsoft AI Red Team, "Taxonomy of Failure Modes in Agentic AI Systems v2.0" (Apr 2026): reversibility as action-classification dimension
- Fast.io, "AI Agent Rollback Strategy" (2026): 30% of autonomous runs hit exceptions requiring recovery

## See also

- [S-1288](s1288-the-saga-compensation-stack-when-your-multi-agent-workflow-partially-succeeds-and-leaves-the-database-wrong.md) — saga pattern for multi-step compensation (extends from "how to undo" to "build undo into every step")
- [F-51](f51-agent-action-rollback.md) — agent action rollback (single-action undo after execution)
- [F-09](f09-human-in-the-loop.md) — HITL modes (pre-action approval is the irrevocable action guard; this entry extends it to the revocability spectrum)
- [S-1329](s1329-the-authorization-velocity-gap-when-your-agent-runs-before-the-controls-know-it-exists.md) — authorization velocity gap (the systemic problem this pattern addresses: governance can't keep up with agent action velocity)
- [S-1433](s1433-the-confidence-gated-autonomy-stack-when-your-agent-decides-it-knows-best-and-it-doesnt.md) — confidence-gated autonomy (confidence scoring without action-type taxonomy misses the revocability dimension)
