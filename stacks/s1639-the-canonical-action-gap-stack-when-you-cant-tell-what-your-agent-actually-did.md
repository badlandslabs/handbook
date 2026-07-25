# S-1639 · The Canonical Action Gap Stack — When You Can't Tell What Your Agent Actually Did

Your agent published code, sent an email, approved a transaction, and changed a user permission. Fine. Then the compliance team asks: which action was authorized? Your SIEM says one thing. Your agent framework logs another. Your audit trail shows a third. Your security team spent three days reconciling records and still isn't sure what happened. This isn't a logging problem. It's a structural problem: the same agent action looks like three different events in three different runtimes, and you have no canonical representation to anchor governance decisions against.

This is the **canonical action gap** — and CAVA (Canonical Action Verification and Attestation, arXiv:2607.13716, Wang 2026) is the emerging pattern that closes it.

## Forces

- **One action, N runtime records.** A single agent approval maps to a shell hook log entry, an SDK tool call, an MCP server trace, a workflow engine event, and an A2A task state update. Each runtime has its own schema, timestamp granularity, and semantic encoding. Governance systems that try to enforce policy on these records are enforcing on symptoms, not actions.
- **Approval and execution are decoupled.** Authorization may happen at the policy layer, but the agent executes through a different runtime that has no concept of what was approved. Nothing binds the approval record to the execution record. This is the core problem CAVA addresses: reproducible action identity across runtime forms.
- **Cross-framework deployments make this the default, not the exception.** Production agents use LangGraph for orchestration, MCP for tool access, A2A for delegation, and browser automation for UI tasks. Each layer produces its own action representation. Without a canonical action object, your governance layer is playing telephone with itself.

## The move

**Define a canonical action object.** Before a deployer can decide whether an agent action should proceed, they need a reproducible representation of what action is being decided. The canonical action object is a stable, runtime-agnostic representation that normalizes heterogeneous runtime records into a common schema.

**CAVA's three-layer architecture:**

```
┌─────────────────────────────────────────┐
│         Canonical Action Object          │
│  type + actor + target + impact + proof │
├──────────────┬──────────────┬───────────┤
│   Local      │    MCP/SDK   │  A2A/WF   │
│   Hooks      │    Tools     │  Engines   │
└──────────────┴──────────────┴───────────┘
```

**Step 1 — Normalize heterogeneous records into a canonical action object:**
```python
# arXiv:2607.13716 CAVA canonical action schema
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime

@dataclass(frozen=True)
class CanonicalAction:
    action_type:   Literal["code_publish", "data_export", "permission_change",
                          "payment", "message_send", "config_modify"]
    actor_id:     str           # agent instance, not just model
    target:       str           # resource URI or identifier
    impact_class: Literal["low", "medium", "high", "critical"]
    timestamp:    datetime
    proof_refs:   tuple[str, ...] = field(default_factory=tuple)
    delegation_chain: tuple[str, ...] = field(default_factory=tuple)

    def canonical_id(self) -> str:
        """Stable hash across heterogeneous runtime representations."""
        import hashlib, json
        payload = json.dumps({
            "type": self.action_type, "actor": self.actor_id,
            "target": self.target, "impact": self.impact_class,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
```

**Step 2 — Map runtime records to canonical actions:**

```python
def normalize_shell_hook_event(event: dict) -> CanonicalAction:
    """Shell hook: 'published /repo/main to prod'."""
    return CanonicalAction(
        action_type="code_publish",
        actor_id=event["agent_instance_id"],
        target=event["destination_path"],
        impact_class="high",          # prod deployment
        timestamp=datetime.fromisoformat(event["ts"]),
        proof_refs=(f"hook:{event['hook_id']}",),
    )

def normalize_mcp_tool_result(result: dict) -> CanonicalAction:
    """MCP server: 'completed tool call send_email'."""
    return CanonicalAction(
        action_type="message_send",
        actor_id=result["server_name"],
        target=result["args"].get("recipient", "unknown"),
        impact_class="medium",
        timestamp=datetime.fromisoformat(result["completed_at"]),
        proof_refs=(f"mcp:{result['call_id']}",),
    )

def normalize_a2a_task_update(update: dict) -> CanonicalAction:
    """A2A: 'task status changed to completed with artifact'."""
    return CanonicalAction(
        action_type="data_export" if update.get("artifact_type") == "file" else update["status"],
        actor_id=update["agent_id"],
        target=update.get("artifact_uri", update["task_id"]),
        impact_class="low",
        timestamp=datetime.fromisoformat(update["updated_at"]),
        proof_refs=(f"a2a:{update['task_id']}",),
    )
```

**Step 3 — Governance on canonical actions, not runtime records:**

```python
from enum import Enum

class PolicyRule:
    def __init__(self, action_type: str, max_impact: str, requires_approval: bool):
        self.action_type = action_type
        self.max_impact = max_impact
        self.requires_approval = requires_approval

POLICY_RULES: list[PolicyRule] = [
    PolicyRule("code_publish",        "high",   True),
    PolicyRule("permission_change",    "medium", True),
    PolicyRule("data_export",          "low",    False),
    PolicyRule("payment",              "low",    True),
]

def governance_decision(action: CanonicalAction) -> str:
    """Policy enforced on canonical form — same logic regardless of source runtime."""
    for rule in POLICY_RULES:
        if rule.action_type != action.action_type:
            continue
        impact_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if impact_rank[action.impact_class] > impact_rank[rule.max_impact]:
            return f"BLOCKED: {action.action_type}@{action.impact_class} exceeds policy threshold"
        if rule.requires_approval and not action.proof_refs:
            return f"PENDING: {action.action_type} requires approval proof"
        return f"APPROVED: {action.canonical_id()}"
    return f"DEFAULT ALLOW: {action.action_type} unconstrained"
```

**Step 4 — Attest and bind the action record:**

```python
def attest_and_bind(action: CanonicalAction, approval_record: dict) -> dict:
    """
    Bind approval to execution via the canonical action ID.
    Enables reproducible verification: can any independent verifier
    reproduce the same action identity from the same runtime records?
    """
    return {
        "canonical_action_id": action.canonical_id(),
        "approval_proof": {
            "approved_by":   approval_record["approver"],
            "approved_at":   approval_record["ts"],
            "scope":         approval_record["scope"],    # bounded scope
        },
        "execution_proof": {
            "runtime_refs":  list(action.proof_refs),
            "delegation":    list(action.delegation_chain),
        },
        "verifiable": True,   # independent verifier can reconstruct from records
    }
```

## Receipt

> Receipt pending — 2026-07-25. The CAVA paper (arXiv:2607.13716, Wang, July 15 2026) provides the theoretical framework. The code above is a pattern-level implementation derived from the paper's canonical action object schema and governance composition model. No live run yet — the arXiv paper is 10 days old as of this writing.

## See also

- **[S-1204 · The PTV Stack](/stacks/s1204-the-ptv-stack-when-your-agent-has-no-hardware-roots-but-the-network-demands-proof.md)** — Hardware-rooted identity that CAVA's proof binding can anchor into
- **[S-972 · The Agent Trust Negotiation Stack](/stacks/s972-the-agent-trust-negotiation-stack-when-your-agent-has-to-prove-itself-to-another-agent.md)** — A2A trust negotiation that benefits from canonical action attestation
- **[S-1552 · The AI-BOM Stack](/stacks/s1552-the-ai-bom-stack-when-your-agent-supply-chain-has-no-ingredient-label.md)** — Supply chain inventory that CAVA's proof_refs chain can trace through
- **[S-500 · Action Hallucination Detection](/stacks/s500-action-hallucination-detection.md)** — Detecting actions the agent claims vs. what the runtime recorded; canonical action reconciliation surfaces these discrepancies
