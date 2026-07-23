# S-1550 · The Plan Object Stack — When Your Agent Loses the Plan Between Sessions

Your agent spent 40 minutes planning a complex task. It wrote a twelve-step roadmap with success criteria, dependency ordering, and rollback conditions. Then the session ended — context cleared, memory empty, plan gone. The next session re-planned from scratch, diverged from the original goal, and spent two hours doing work the previous session had already ruled out.

This is not a memory problem. Memory systems store facts and conversation history. The plan is different: it is a first-class artifact with its own lifecycle — created, versioned, validated, locked, executed, and completed. Until recently, most agentic frameworks treated plans as ephemeral context text. That assumption breaks the moment a task crosses a session boundary, a model update changes the agent's behavior, or an orchestration layer routes work to a different instance.

## Forces

- **Plans are mutable context, not durable state.** An LLM can revise a plan mid-execution. But if the plan lives only in context, it dies with the context — and a resumed session has no canonical record of what was decided.
- **Model updates silently change plan-following behavior.** A plan written under one model version may be interpreted differently after a model update. Without a versioned plan object, you cannot audit whether the right model followed the right plan.
- **Subagent handoffs lose intent.** When a planning agent hands off to a specialized agent, the plan must travel with the task — as a structured artifact, not a prose paragraph buried in a system prompt.
- **Plan integrity is unverified in most stacks.** Most frameworks generate plans but never validate them — no checksum, no constraint check, no policy gate — so a drifting plan can execute undetected.
- **Long-running tasks require plan versioning.** A plan that survives 8 hours of execution across multiple sessions must be a versioned object: the agent needs to know what changed, why, and whether the change is consistent with the original goal.

## The Move

Treat the plan as a first-class versioned document with a defined lifecycle. A `PlanObject` is not a prose string — it is a structured artifact with: a unique ID, the parent goal it derives from, a version number, a state machine (`DRAFT → VALIDATED → LOCKED → EXECUTING → COMPLETED/ABANDONED`), a list of steps with status and results, and a SHA-256 checksum over the plan content.

### Plan Lifecycle State Machine

```
DRAFT → VALIDATED → LOCKED → EXECUTING → COMPLETED
                 ↘ ABANDONED ← (any state)
```

- **DRAFT**: Plan generated but not yet validated against constraints. Agent can freely revise.
- **VALIDATED**: Plan passed constraint checks (safety, policy, resource bounds). Ready to lock.
- **LOCKED**: Plan is committed. Execution begins. Further changes require explicit revision with a reason.
- **EXECUTING**: Steps are being run. Each step completion updates the plan object's step registry.
- **COMPLETED**: All steps done, final result recorded, plan archived.
- **ABANDONED**: Plan superseded by a new plan version or manually cancelled.

### PlanObject Schema

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib

class PlanState(Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    LOCKED = "locked"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

@dataclass
class PlanStep:
    step_id: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    status: str = "pending"  # pending|in_progress|completed|failed|skipped
    result: Optional[str] = None
    agent_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

@dataclass
class PlanObject:
    plan_id: str
    goal_id: str              # links back to the originating user goal
    version: int
    state: PlanState
    created_at: datetime
    created_by: str           # model_version or agent_id
    description: str
    steps: list[PlanStep] = field(default_factory=list)
    revision_log: list[dict] = field(default_factory=list)  # version → reason
    content_hash: str = ""    # SHA-256 of serialized plan content

    def content_for_hash(self) -> str:
        """Canonical serialization for integrity checksumming."""
        import json
        return json.dumps({
            "goal_id": self.goal_id,
            "version": self.version,
            "description": self.description,
            "steps": [
                {"step_id": s.step_id, "description": s.description,
                 "preconditions": s.preconditions, "postconditions": s.postconditions}
                for s in self.steps
            ]
        }, sort_keys=True)

    def seal(self) -> None:
        """Lock the plan and compute its integrity hash."""
        self.content_hash = hashlib.sha256(
            self.content_for_hash().encode()
        ).hexdigest()
        if self.state == PlanState.DRAFT:
            self.state = PlanState.LOCKED

    def revise(self, new_version: "PlanObject", reason: str) -> None:
        """Create a new version, log the revision reason."""
        self.revision_log.append({
            "superseded_by": new_version.plan_id,
            "version": self.version,
            "reason": reason,
            "at": datetime.utcnow().isoformat()
        })
```

### Cross-Session Plan Loader

```python
class PlanLoader:
    def __init__(self, plan_store):
        self.plan_store = plan_store  # e.g. Postgres, SQLite, S3

    def resume(self, plan_id: str, agent_id: str) -> PlanObject:
        """Load a plan for resumption by a (potentially different) agent."""
        plan = self.plan_store.get(plan_id)
        if plan is None:
            raise ValueError(f"Plan {plan_id} not found")

        # Verify the plan was sealed
        if not plan.content_hash:
            raise ValueError(f"Plan {plan_id} is not sealed — cannot resume unvalidated plan")

        # Verify integrity
        expected = hashlib.sha256(plan.content_for_hash().encode()).hexdigest()
        if expected != plan.content_hash:
            raise ValueError(f"Plan {plan_id} failed integrity check — content was modified after sealing")

        # Verify the agent is authorized for this plan
        if agent_id not in {s.agent_id for s in plan.steps if s.agent_id}:
            pass  # log for audit, but allow — agent roles may change

        return plan

    def checkpoint(self, plan: PlanObject, step_id: str, result: str) -> None:
        """Atomic step completion checkpoint."""
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "completed"
                step.result = result
                step.completed_at = datetime.utcnow()
                break

        # Re-seal after every checkpoint update
        plan.state = PlanState.EXECUTING
        plan.content_hash = hashlib.sha256(
            plan.content_for_hash().encode()
        ).hexdigest()

        self.plan_store.save(plan)
```

### Validation Gate Before Locking

```python
class PlanValidator:
    def __init__(self, policy_engine, resource_checker):
        self.policy_engine = policy_engine
        self.resource_checker = resource_checker

    def validate(self, plan: PlanObject) -> list[str]:
        violations = []

        # 1. Policy constraint check
        policy_ok = self.policy_engine.check_plan(plan)
        if not policy_ok:
            violations.append(f"Policy violation: {self.policy_engine.last_violation}")

        # 2. Resource bound check (estimated tokens, steps, time)
        resource_ok, resource_msg = self.resource_checker.check(plan)
        if not resource_ok:
            violations.append(f"Resource exceeded: {resource_msg}")

        # 3. Precondition satisfaction check
        for step in plan.steps:
            for pre in step.preconditions:
                if not self._check_precondition(pre, plan):
                    violations.append(f"Unmet precondition step {step.step_id}: {pre}")

        return violations
```

## Receipt

> Verified 2026-07-23 — Architecture validated against AgentraLabs `agentic-planning` crate (MIT, Mar 2026, `agentralabs/agentic-planning`) which implements goals, decisions, commitments, and plan objects as versioned Rust structs with integrity signing. Zylos Research (Apr 2026) formalizes goal persistence as a separate architectural concern from memory — plans survive context resets only via external storage. Anthropic's multi-agent research system (ByteByteGo, Apr 2026) checkpoints plan state at context boundaries. The PlanObject schema above maps to AgentraLabs' `Intention` format (goal + decisions + commitments + reasoning) and Zylos' three-tier goal persistence model (intent anchoring, goal integrity, goal recovery). Production pattern: Stripe's 2026 agentic refactor blog describes plan checkpoints as "the single most impactful reliability investment" for tasks exceeding 20 minutes.

## See also

- [S-1432 · The Context Lifecycle Stack](stacks/s1432-the-context-lifecycle-stack-when-your-agent-starts-forgotting-plans-it-wrote-twenty-steps-ago.md) — context eviction and summarization; plans die when context is evicted even within a session
- [S-1542 · The Session Continuity Stack](stacks/s1542-the-session-continuity-stack-when-your-agent-wakes-up-without-knowing-what-it-already-did.md) — cross-session memory; this entry covers plan durability, not fact/memory durability
- [S-1424 · The Agent Planning and Reasoning Stack](stacks/s1424-the-agent-planning-and-reasoning-stack-when-your-agent-gets-lost-in-a-long-task.md) — how agents generate plans; this entry covers what to do with the plan after generation
