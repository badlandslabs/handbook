# S-1246 · The Cascading Specification Failure Stack — When Your Multi-Agent System Is Correct at Every Step and Wrong in Aggregate

Your research agent completed its task. Your execution agent completed its task. Your verification agent signed off. The workflow took 3 hours and delivered a financial report recommending a $2.4M capital allocation based on incorrect quarterly projections from a downstream data service that changed its API contract two weeks ago. Every agent was individually correct. The system was catastrophically wrong. No agent flagged the failure — because each one operated on locally valid inputs and produced locally valid outputs. This is the **cascading specification failure**, and it accounts for approximately 42% of multi-agent production failures (Data-Gate, May 2026).

## Forces

- **Individual correctness ≠ system correctness.** Each agent validates its own output against its own spec. None validates that the upstream spec it received matches the upstream spec that was actually in effect when the task started.
- **Specifications drift faster than implementations.** API contracts, business rules, data schemas, and feature flags change. A task handed off from Agent A to Agent B carries a snapshot of A's understanding at handoff time. If B's implementation evolves while the task is in flight, the handoff artifact may be stale.
- **Success criteria are implicit in single-agent thinking.** When one agent owns the full pipeline, success criteria are coherent. When multiple agents share the pipeline, each agent defines success locally — and local success criteria can contradict each other.
- **Verification is downstream of the wrong thing.** You verify that Agent B's output is correct given Agent A's input. You don't verify that Agent A's input was correct given the actual system state at task creation.

## The Move

### 1. Freeze the Shared Spec at Task Creation

At the moment a task enters the multi-agent pipeline, capture a **spec snapshot**: versioned references to all upstream data sources, API contracts, business rule versions, and configuration values the task depends on.

```python
import hashlib, json, time

class SpecSnapshot:
    """Capture immutable spec context at task creation."""
    def __init__(self, task_id: str, upstream_refs: dict):
        self.task_id = task_id
        self.created_at = time.time()
        # Version every upstream dependency the task will consume
        self.upstream_snapshots = {
            name: self._snapshot_ref(ref)
            for name, ref in upstream_refs.items()
        }
        self.spec_hash = self._compute_hash()

    def _snapshot_ref(self, ref: dict) -> dict:
        """Snapshot: {endpoint, version, hash_of_schema, data_hash}."""
        return {
            "endpoint": ref.get("endpoint"),
            "version": ref.get("version"),
            "schema_hash": hashlib.sha256(
                json.dumps(ref.get("schema", {}), sort_keys=True).encode()
            ).hexdigest()[:16],
            "data_hash": ref.get("data_hash"),  # hash of actual data at creation
        }

    def _compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.upstream_snapshots, sort_keys=True).encode()
        ).hexdigest()

    def validate_at_handoff(self, current_refs: dict) -> list[str]:
        """Check whether upstream refs have drifted since task creation."""
        violations = []
        for name, original in self.upstream_snapshots.items():
            current = current_refs.get(name, {})
            if original.get("version") != current.get("version"):
                violations.append(
                    f"{name}: version drift {original['version']} → {current['version']}"
                )
            if original.get("schema_hash") != current.get("schema_hash"):
                violations.append(
                    f"{name}: schema changed since task creation"
                )
            if original.get("data_hash") != current.get("data_hash"):
                violations.append(
                    f"{name}: source data changed since task creation"
                )
        return violations
```

### 2. Confirm Before Consuming

Receiving agents must confirm spec alignment before consuming upstream artifacts. This is the **handoff confirmation loop** — a lightweight handshake that explicitly surfaces spec drift rather than silently propagating stale context.

```python
async def agent_b_handoff(task: dict, upstream_output: dict,
                          spec_snapshot: SpecSnapshot) -> dict:
    """Agent B: validate spec before consuming Agent A's output."""
    # Check upstream refs
    current_refs = await fetch_current_upstream_refs(upstream_output)
    violations = spec_snapshot.validate_at_handoff(current_refs)

    if violations:
        # Log and surface — do NOT silently proceed
        logger.warning(
            f"Spec drift detected on task {spec_snapshot.task_id}: "
            f"{violations}"
        )
        # Options: abort, require human review, or fetch fresh data
        raise SpecDriftError(
            f"Upstream spec changed since task creation: {violations}"
        )

    # Safe to proceed — spec is consistent
    return await agent_b_execute(task, upstream_output)
```

### 3. Test the Specification Interface, Not Just the Agents

Unit tests verify each agent in isolation. You also need **spec interface tests** that verify the handoff contract:

```python
import pytest

class TestSpecInterfaceContract:
    """Verify spec contracts at agent handoff boundaries."""

    def test_successful_handoff_specs_match(self):
        """When A→B succeeds, their specs must be compatible."""
        snap_a = create_snapshot_for_agent_a()
        snap_b = create_snapshot_for_agent_b()
        assert snap_a.spec_hash == snap_b.inherited_spec_hash, (
            "A and B operating on incompatible specs — "
            "check that B received A's spec snapshot, not a stale one"
        )

    def test_spec_drift_is_detected(self):
        """Upstream change must trigger SpecDriftError, not silent failure."""
        snapshot = SpecSnapshot("task-1", {"quarterly_data": mock_ref_v1})
        # Simulate upstream change
        mock_ref_v2 = {**mock_ref_v1, "version": "v2"}
        violations = snapshot.validate_at_handoff({"quarterly_data": mock_ref_v2})
        assert len(violations) > 0
        assert "version drift" in violations[0]

    def test_business_constraints_passed_as_first_class(self):
        """Business rules (e.g., 'budget > $0') must travel with the task artifact."""
        task = create_task_with_business_constraints(
            constraints=["budget > 0", "region in ['US', 'EU']"]
        )
        # Agent A must surface these in its output artifact
        output_a = agent_a.execute(task)
        assert "business_constraints" in output_a, (
            "Agent A output missing business_constraints — "
            "Agent B will use defaults and may violate policy"
        )
        # Agent B must explicitly evaluate these
        result_b = agent_b.execute(task, output_a)
        assert result_b["constraints_satisfied"], (
            f"Agent B violated business constraints: "
            f"{result_b.get('constraint_violations', [])}"
        )
```

### 4. The Three-Level Spec Verification

```
Level 1 — Schema: Does the handoff artifact have the expected shape?
Level 2 — Version: Have upstream dependencies changed since task creation?
Level 3 — Semantics: Do the business constraints embedded in the artifact still hold?
```

Level 1 is automated trivially. Level 2 requires spec snapshots. Level 3 requires business logic to be explicit and testable — not buried in prompts.

## Receipt

> Receipt pending — 2026-07-17

## See also

- [S-1008 · The Orchestration Pattern Match Stack](stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — related: choosing the right orchestration topology determines where spec boundaries fall
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — related: boundary failures between agents are often spec mismatches in disguise
- [S-1063 · The Multi-Agent Orchestration Stack](stacks/s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — related: orchestration structure defines where spec contracts must hold
- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — related: A2A/MCP both need spec contracts to be meaningful
