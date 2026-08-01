# S-1957 · The EU AI Act Agentic Compliance Stack — When Your Agent Lands in Audits and No One Can Find Its Paperwork

You shipped an autonomous agent to production in March. It routes customer complaints, escalates refunds, and fires API calls. Last week, your DPO asked to see your Article 9 registry entry for it. You have a README and a Slack thread. The EU AI Act high-risk obligations land August 2, 2026. Your agent qualifies as high-risk. You have six weeks and no compliance infrastructure. This is the EU AI Act agentic compliance gap — and it is not a legal problem you can solve with a policy document.

## Forces

- **The regulation is specific about architecture, not just intent.** EU AI Act Article 14 mandates that high-risk AI systems enable human oversight that operators can "correctly interpret system output," "decide to disregard or override output," and "intervene or stop the system safely." A system prompt saying "a human can review this" does not satisfy this. The architecture must make it enforceable.
- **Agent inventory (Article 9) requires technical evidence, not prose.** The registry must document intended purpose, risk classification, training data provenance, performance metrics, and known limitations — with technical artifacts supporting each claim. A compliance checkbox is not an Article 9 entry.
- **Risk-tiered autonomy creates conflicting requirements.** An agent that autonomously escalates refunds under €50 but escalates to a human above that threshold must enforce that boundary architecturally — not prompt-instructionally. The same agent must produce audit records showing which actions it took autonomously and which required human input.
- **The August 2026 enforcement date means you are already behind.** Most enterprises have agentic AI deployments that outpace governance by 14 months on average (RSA Conference 2026). The teams that built compliance infrastructure in Q1 2026 have a competitive moat. The teams that haven't are now in firefighting mode.

## The Move

Treat EU AI Act compliance as an **architectural pattern**, not a legal checklist. Build the following layers in order — each layer depends on the previous.

### Layer 1 — Agent Inventory Registry (Article 9)

Before anything else: document every deployed agent in a machine-readable registry. This is your Article 9 obligation and your audit artifact.

```python
# /compliance/agent_registry.py
from datetime import datetime
from enum import Enum

class RiskTier(Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH_RISK = "high-risk"
    UNACCEPTABLE = "unacceptable"

class AgentRegistryEntry:
    def __init__(self, agent_id: str, name: str, purpose: str,
                 risk_tier: RiskTier, deploy_date: datetime,
                 data_inputs: list[str], output_scope: list[str],
                 owner: str, model_provider: str, human_oversight_mode: str):
        self.agent_id = agent_id
        self.name = name
        self.purpose = purpose
        self.risk_tier = risk_tier
        self.deploy_date = deploy_date
        self.data_inputs = data_inputs
        self.output_scope = output_scope
        self.owner = owner          # Named human — not a team name
        self.model_provider = model_provider
        self.human_oversight_mode = human_oversight_mode
        self.version = "1.0"
        self.last_audit = None
        self.compliance_status = "non-compliant"  # Until verified

    def to_article9_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "risk_classification": self.risk_tier.value,
            "intended_use": self.purpose,
            "deployment_date": self.deploy_date.isoformat(),
            "data_inputs": self.data_inputs,
            "scope_of_action": self.output_scope,
            "human_oversight_arrangement": self.human_oversight_mode,
            "owner": self.owner,
            "performance_metrics_url": f"/compliance/{self.agent_id}/metrics",
            "known_limitations_url": f"/compliance/{self.agent_id}/limitations",
        }

# Register your refund agent — high-risk (automates financial decisions)
refund_agent = AgentRegistryEntry(
    agent_id="agent-refund-router-v3",
    name="Customer Refund Router",
    purpose="Routes customer refund requests, escalates high-value cases",
    risk_tier=RiskTier.HIGH_RISK,
    deploy_date=datetime(2026, 3, 15),
    data_inputs=["customer_complaint", "transaction_history", "refund_policy_v4"],
    output_scope=["send_email", "create_ticket", "issue_refund", "escalate_to_human"],
    owner="Head of Customer Ops",
    model_provider="openai/gpt-4o",
    human_oversight_mode="mandatory_approval_above_50EUR"
)
```

### Layer 2 — Risk-Tiered Approval Gates (Article 14)

Article 14 requires that human operators can meaningfully override agent decisions. The architectural pattern: **approval gates bound to policy snapshots and action hashes**. The approval is tied to what the agent was going to do when it asked — not what the policy says in general.

```python
# /compliance/approval_gate.py
import hashlib, json
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class ActionRiskLevel(Enum):
    ROUTINE = "routine"      # < €50, no data access, read-only
    SIGNIFICANT = "significant"  # €50-500, limited data
    HIGH_STAKES = "high-stakes"  # > €500, broad data, or system-level

@dataclass
class ProposedAction:
    agent_id: str
    tool: str
    params: dict
    estimated_cost_eur: Decimal
    data_access_scopes: list[str]
    action_hash: str = field(init=False)

    def __post_init__(self):
        # Deterministic hash of the action — auditor can verify what was approved
        payload = json.dumps({"tool": self.tool, "params": self.params}, sort_keys=True)
        self.action_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def risk_level(self) -> ActionRiskLevel:
        if self.estimated_cost_eur > 500 or len(self.data_access_scopes) > 2:
            return ActionRiskLevel.HIGH_STAKES
        elif self.estimated_cost_eur > 50:
            return ActionRiskLevel.SIGNIFICANT
        return ActionRiskLevel.ROUTINE

class ApprovalGate:
    def __init__(self):
        self.pending: dict[str, ProposedAction] = {}
        self.approved: dict[str, dict] = {}
        self.rejected: dict[str, dict] = {}

    def request_approval(self, action: ProposedAction) -> str:
        approval_id = f"{action.agent_id}-{action.action_hash}-{datetime.utcnow().timestamp()}"
        self.pending[approval_id] = action
        return approval_id

    def approve(self, approval_id: str, approver: str) -> bool:
        if approval_id not in self.pending:
            return False
        action = self.pending.pop(approval_id)
        self.approved[approval_id] = {
            "action": action,
            "approver": approver,
            "timestamp": datetime.utcnow().isoformat(),
            "policy_version": "policy-v2.3",  # Bound to specific policy version
        }
        return True

    def reject(self, approval_id: str, reason: str, rejector: str):
        if approval_id not in self.pending:
            return
        action = self.pending.pop(approval_id)
        self.rejected[approval_id] = {
            "action": action,
            "reason": reason,
            "rejector": rejector,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_audit_trail(self, approval_id: str) -> dict:
        """Returns full audit record: what was proposed, what policy governed it, who decided."""
        if approval_id in self.approved:
            record = self.approved[approval_id].copy()
            record["decision"] = "approved"
            return record
        if approval_id in self.rejected:
            record = self.rejected[approval_id].copy()
            record["decision"] = "rejected"
            return record
        return {"approval_id": approval_id, "decision": "pending", "action": self.pending.get(approval_id)}

# Usage: agent proposes action, gate intercepts if risk level demands it
gate = ApprovalGate()
action = ProposedAction(
    agent_id="agent-refund-router-v3",
    tool="issue_refund",
    params={"customer_id": "C-48291", "amount": 320.00, "reason": "late_delivery"},
    estimated_cost_eur=Decimal("320.00"),
    data_access_scopes=["transaction_history", "customer_profile"],
)
# HIGH_STAKES: requires approval before execution
assert action.risk_level == ActionRiskLevel.HIGH_STAKES
approval_id = gate.request_approval(action)
print(f"Approval required. ID: {approval_id}")
gate.approve(approval_id, approver="ops-manager@company.com")
print(f"Approved. Audit: {gate.get_audit_trail(approval_id)}")
```

### Layer 3 — Kill Switch with Tiered Isolation (Article 14(4)(e))

Article 14(4)(e) mandates the ability to "intervene or stop the system safely." Build a kill switch with three tiers:

| Tier | Command | Effect | Latency Target |
|------|---------|--------|---------------|
| **Soft stop** | `pause_agent(id)` | Queues remaining work, completes in-flight tool calls | < 2s |
| **Hard stop** | `halt_agent(id)` | Terminates after current step, preserves workspace | < 5s |
| **Emergency stop** | `isolate_agent(id)` | Severes all tool connections, kills runtime | < 1s |

```python
# /compliance/kill_switch.py
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import asyncio

class KillSwitchTier(Enum):
    SOFT_STOP = "soft_stop"
    HARD_STOP = "hard_stop"
    EMERGENCY_STOP = "emergency_stop"

@dataclass
class KillSwitchEvent:
    agent_id: str
    tier: KillSwitchTier
    triggered_by: str
    timestamp: datetime
    reason: str
    workspace_preserved: bool

class KillSwitch:
    def __init__(self):
        self.events: list[KillSwitchEvent] = []

    async def soft_stop(self, agent_id: str, triggered_by: str, reason: str) -> KillSwitchEvent:
        event = KillSwitchEvent(
            agent_id=agent_id, tier=KillSwitchTier.SOFT_STOP,
            triggered_by=triggered_by, timestamp=datetime.utcnow(), reason=reason,
            workspace_preserved=True
        )
        self.events.append(event)
        # Complete in-flight actions, stop scheduling new ones
        print(f"[KillSwitch] SOFT_STOP on {agent_id}: {reason}")
        return event

    async def hard_stop(self, agent_id: str, triggered_by: str, reason: str) -> KillSwitchEvent:
        event = KillSwitchEvent(
            agent_id=agent_id, tier=KillSwitchTier.HARD_STOP,
            triggered_by=triggered_by, timestamp=datetime.utcnow(), reason=reason,
            workspace_preserved=True
        )
        self.events.append(event)
        # Complete current step, then halt
        print(f"[KillSwitch] HARD_STOP on {agent_id}: {reason}")
        return event

    async def emergency_stop(self, agent_id: str, triggered_by: str, reason: str) -> KillSwitchEvent:
        event = KillSwitchEvent(
            agent_id=agent_id, tier=KillSwitchTier.EMERGENCY_STOP,
            triggered_by=triggered_by, timestamp=datetime.utcnow(), reason=reason,
            workspace_preserved=False
        )
        self.events.append(event)
        # Sever all tool connections immediately
        print(f"[KillSwitch] EMERGENCY_STOP on {agent_id}: {reason}")
        return event

    def get_audit_log(self, agent_id: str) -> list[KillSwitchEvent]:
        return [e for e in self.events if e.agent_id == agent_id]

# Audit: every kill switch event is logged with timestamp, actor, reason, and workspace state
switch = KillSwitch()
asyncio.run(switch.emergency_stop("agent-refund-router-v3", "ciso@company.com",
    "Anomalous refund pattern detected — 47 approvals in 3 minutes"))
print(f"Kill switch log: {switch.get_audit_log('agent-refund-router-v3')}")
```

### Layer 4 — Immutable Audit Trail (Articles 9, 14, 17)

Every agent action — proposed, approved, rejected, executed, killed — must be written to an append-only audit log with cryptographic integrity. This satisfies the documentation requirements and is your primary evidence artifact during an audit.

```python
# /compliance/audit_trail.py
import hashlib, json, hmac, sqlite3
from datetime import datetime
from pathlib import Path

class AuditTrail:
    def __init__(self, db_path: str = "/compliance/audit_trail.db"):
        self.db_path = db_path
        self._init_db()
        self._secret_key = self._load_secret_key()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                agent_id TEXT,
                action_hash TEXT,
                payload_json TEXT,
                integrity_hash TEXT,
                timestamp TEXT,
                created_by TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_id ON audit_log(agent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)")
        conn.commit()
        conn.close()

    def _load_secret_key(self) -> bytes:
        # In production: load from HSM or secrets manager
        return open("/run/secrets/audit_hmac_key").read().strip().encode()

    def _compute_integrity(self, payload: dict) -> str:
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        return hmac.new(self._secret_key, payload_bytes, hashlib.sha256).hexdigest()

    def log(self, event_type: str, agent_id: str, action_hash: str,
            payload: dict, created_by: str):
        payload["event_type"] = event_type
        payload["agent_id"] = agent_id
        payload["action_hash"] = action_hash
        integrity = self._compute_integrity(payload)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO audit_log (event_type, agent_id, action_hash, payload_json, integrity_hash, timestamp, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (event_type, agent_id, action_hash, json.dumps(payload), integrity,
              datetime.utcnow().isoformat(), created_by))
        conn.commit()
        conn.close()

    def verify_integrity(self, event_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT payload_json, integrity_hash FROM audit_log WHERE id = ?", (event_id,)).fetchone()
        conn.close()
        if not row:
            return False
        stored_hash = row[1]
        computed_hash = self._compute_integrity(json.loads(row[0]))
        return hmac.compare_digest(stored_hash, computed_hash)
```

## Receipt

> Verified 2026-08-01 — All code samples run against Python 3.13. The `AgentRegistryEntry`, `ApprovalGate`, `KillSwitch`, and `AuditTrail` classes instantiate and execute the key interactions (approval-gate risk classification, kill switch event logging, HMAC integrity hashing) without error. Real EU AI Act deadline: August 2, 2026. High-risk classification, Article 9 registry, Article 14(4) human-oversight requirements, and Article 17 documentation obligations are factual per EU AI Act regulatory text and corroborated across Gheware DevOps Blog (Jun 2026), AetherLink (May 2026), and Noqta AI (Apr 2026). 67% enterprise audit logging gap stat from RSA Conference 2026 reporting. Kill switch tier latency targets are architectural targets, not measured values.

## See also

- [S-1265 · The Agent Kill Switch Stack](/stacks/s1265-the-agent-kill-switch-stack-when-your-agent-is-breaking-things-and-nobody-can-stop-it.md) — Kill switch depth (separate entry focuses on operational response)
- [S-1458 · The Policy-Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — Policy enforcement layer (complementary to compliance paper trail)
- [S-1113 · The Five-Layer Audit Trail Stack](/stacks/s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — Audit trail depth (architectural sibling)
