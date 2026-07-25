# S-1596 · The Directive Conflict Stack

When your agent has two bosses and they don't agree — a user instruction and a system constraint contradict each other at runtime, and nobody specified which wins.

## Forces

- **Instruction hierarchy is unresolved** — agents receive directives from multiple sources (user, system prompt, policy layer, orchestration layer) and must reconcile conflicts at runtime with no canonical priority order.
- **Latency is incompatible with escalation** — the right answer ("ask a human") is often the wrong answer when the agent is mid-flow, holding a lock, or operating at a speed no human can track.
- **Implicit intent beats explicit rule** — users say what they want; policies encode what they're allowed to have; the agent sits between, guessing which layer is the real constraint.
- **Policies were written for human workflows** — most agent-facing policies were designed before agents existed, so they assume human judgment at every conflict point — an assumption that breaks at agent speeds.

## The move

Build a three-layer directive resolution stack that makes conflict explicit, hierarchical, and auditable.

### Layer 1 — Conflict Detection at Intake

Before any agent action, scan the incoming directive against the active policy surface. Flag three conflict types:

```python
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional

class DirectivePriority(IntEnum):
    HARD_POLICY = 3   # Cannot be overridden: legal, safety, compliance
    USER_GOAL   = 2   # The task objective
    SOFT_HINT   = 1   # Preferences, style, formatting

@dataclass
class Directive:
    source: str           # "user", "system_prompt", "policy_layer", "orchestrator"
    priority: DirectivePriority
    content: str
    constraint_tags: set[str]  # {"no-delete", "read-only", "requires-approval"}

@dataclass
class ConflictReport:
    detected: bool
    conflicting_directives: list[Directive]
    resolution: Optional[str]  # What the agent should do
    escalate: bool

def detect_directive_conflict(
    incoming: Directive,
    active_constraints: set[str],
) -> ConflictReport:
    # Hard conflicts: incoming violates a hard policy constraint
    hard_conflicts = {
        c for c in incoming.constraint_tags
        if c in active_constraints and c.startswith("hard:")
    }
    if hard_conflicts:
        return ConflictReport(
            detected=True,
            conflicting_directives=[incoming],
            resolution="BLOCK — hard policy constraint",
            escalate=False,  # Block without asking; policy is the boss
        )

    # Soft conflicts: user goal conflicts with soft constraint
    soft_conflicts = {
        c for c in incoming.constraint_tags
        if c in active_constraints and c.startswith("soft:")
    }
    if soft_conflicts:
        return ConflictReport(
            detected=True,
            conflicting_directives=[incoming],
            resolution=f"SOFT_CONFLICT: proceed with caution ({soft_conflicts})",
            escalate=True,  # Signal upstream but continue
        )

    return ConflictReport(detected=False, conflicting_directives=[], resolution=None, escalate=False)
```

### Layer 2 — Priority Cascade Enforcement

Enforce a strict hierarchy at runtime. When two directives conflict, the higher-priority source wins — unless the lower-priority directive has an explicit `force=true` flag:

```python
def resolve_directive(incoming: Directive, active: Directive) -> Directive:
    if incoming.priority > active.priority:
        return incoming
    elif incoming.priority < active.priority:
        return active
    else:  # Same priority — tie-break by recency, then by explicit force flag
        if getattr(incoming, "force", False):
            return incoming
        return active  # Default to the already-active directive

# Agent execution loop integration:
def agent_step(agent, incoming_directive: Directive):
    conflict = detect_directive_conflict(incoming_directive, agent.active_constraints)
    if conflict.escalate:
        agent.emit_signal("DIRECTIVE_CONFLICT", conflict)
        # Don't block — let the agent proceed with the resolution trace logged
    if conflict.resolution and "BLOCK" in conflict.resolution:
        agent.abort_with_reason(conflict.resolution, conflict.conflicting_directives)
        return
```

### Layer 3 — Conflict Audit Trail

Every conflict — resolved, escalated, or blocked — goes to a structured log with enough context to reconstruct the decision:

```python
import json
from datetime import datetime, timezone

def log_directive_conflict(
    conflict: ConflictReport,
    agent_id: str,
    session_id: str,
    trajectory_snapshot: list[dict],
):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "session_id": session_id,
        "conflict_detected": conflict.detected,
        "directives": [
            {"source": d.source, "priority": d.priority.name, "content": d.content[:200]}
            for d in conflict.conflicting_directives
        ],
        "resolution": conflict.resolution,
        "escalated": conflict.escalate,
        "trajectory_before": trajectory_snapshot[-5:],  # Last 5 steps
    }
    # Write to immutable audit log (append-only, signed)
    append_to_audit_log("directive_conflicts", entry)
    return entry["entry_id"]
```

### The Contrarian Insight

The instinct is to resolve conflicts at the source — write better prompts, tighter policies, clearer system prompts. But this creates a fragile, prompt-engineering arms race. The durable fix is architectural: make conflict detection and resolution explicit, deterministic, and logged — so the agent never has to guess, and the operator can always answer "who won and why."

## Receipt

> Verified 2026-07-24 — Concept validated against: MLflow's "deterministic policy enforcement beneath the model layer" (MLflow blog, July 2026); Okta's "agent kill switches and agent overview IAM" for directive override patterns (Okta blog, 2026); Red Hat's eval-driven CI/CD with mandatory eval gates in PR checks (Red Hat Developer, May 2026). No working code example run — Receipt pending.

## See also

- [S-1594 · The Proposal Gate Stack](s1594-the-proposal-gate-stack-when-your-agent-knows-what-it-wants-but-hasnt-asked-if-it-should.md) — pre-flight validation before action; this entry is the conflict-resolution layer that feeds into it.
- [S-1530 · The Agent Autonomy Tier Stack](s1530-the-agent-autonomy-tier-stack-mapping-agent-autonomy-to-eu-ai-act-risk-tiers.md) — maps directive priority to regulatory risk tiers; S-1596 enforces those tiers at runtime.
- [S-1567 · The Typed Handoff Protocol Stack](s1567-the-typed-handoff-protocol-stack-when-your-multi-agent-system-succeeds-at-every-step-and-fails-at-every-handoff.md) — handoff conflicts between agents are a special case of directive conflicts across system boundaries.
- [S-1398 · The Policy-on-Paths Stack](s1398-the-policy-on-paths-stack-when-every-single-action-is-permitted-and-the-trajectory-is-a-violation.md) — policy enforcement as trajectory constraint; S-1596 provides the resolution mechanism when paths conflict.
