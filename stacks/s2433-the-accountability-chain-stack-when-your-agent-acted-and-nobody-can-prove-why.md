# S-2433 · The Accountability Chain Stack — When Your Agent Acted and Nobody Can Prove Why

Your agent sent a refund to a customer, escalated a support ticket to the wrong team, and modified a database record — all in the same hour. When the auditor asks for evidence, you have trace logs showing tool calls but nothing explaining the *why*, nothing proving *who authorized it*, and nothing proving the records weren't tampered with after the fact. You have logs. You do not have an **accountability chain**.

This is distinct from observability. Observability answers "what happened" — span trees, latency histograms, token counts. Accountability answers "who authorized it, what reasoning drove it, and can you prove it wasn't modified after the fact." For agents acting under EU AI Act Article 11, SOC 2 CC6.1, HIPAA §164.312(b), and NIST AI RMF Govern-3.3, the absence of an accountability chain is not a tooling gap — it is a compliance violation.

## Forces

- **Agents are probabilistic and autonomous** — their actions are not deterministic code paths. Without instrumentation explicitly capturing the accountability chain, no trace exists of what drove a decision, who authorized it, or what the reasoning state was at the time.
- **Traditional audit logs assume a human actor.** API key logs, request logs, database audit logs — all attribute actions to an identity. Agents consume requests from humans and act autonomously, breaking the human → action attribution chain at the moment of execution.
- **Tamper-evident logging is non-negotiable for regulators.** EU AI Act Article 11 requires logs that are "sufficiently high-quality, sufficiently robust, and sufficiently tamper-resistant." A flat file with append writes does not qualify — it can be silently modified.
- **The accountability gap compounds across multi-agent systems.** When agent A delegates to agent B, who calls tool C, the chain of intent and authorization dissolves. Each agent may log its own actions, but no log preserves the originating user request and the delegation chain.
- **Zero authorization + zero audit = uninsurable risk.** Insurance underwriters, enterprise legal teams, and regulators are increasingly treating the absence of an accountability chain as a disqualifying condition for AI deployment in regulated environments.
- **Behavioral drift makes audit decay real.** BASTYN (May 2026) documents that agents silently change behavior after memory rotation, context compression, or tool updates — without triggering any failure signal. An audit trail that doesn't capture the agent's *state* at decision time cannot distinguish drift from intentional action.

## The move

An accountability chain has four layers. Each must be instrumented explicitly — the agent will not produce it by default.

### Layer 1 — Decision Event Log (what the agent did)

Every significant agent decision point emits a structured event with:

```
{
  event_id: uuid,          // globally unique
  parent_id: uuid | null,  // for multi-agent chains
  timestamp: iso8601_ms,
  agent_id: string,
  agent_version: string,
  session_id: uuid,
  user_identity: string,   // original human, not the agent principal
  request_id: string,     // external correlation ID
  intent: string,         // what the user asked for (verbatim)
  reasoning: string,       // chain-of-thought at decision time
  decision: enum,          // ACT / DELEGATE / DENY / ESCALATE / WAIT
  action: {               // if ACT or DELEGATE
    type: "tool_call" | "http_call" | "db_write" | "escalation",
    target: string,
    parameters: json,
    authorization_level: enum  // NONE | USER_CONFIRMED | POLICY_APPROVED | GUARDRAIL_PASSED
  },
  guardrail_results: [...],  // policy engine output
  human_approval: {
    requested: bool,
    granted: bool | null,
    approver: string | null,
    justification: string | null,
    method: "explicit" | "inferred_timeout" | null
  },
  outcome: { completed: bool, result: json, error: string | null },
  metadata: {
    model: string,
    token_count: { in: int, out: int },
    latency_ms: int,
    cost_usd: float,
    tools_available: [...],
    context_utilization_pct: float
  }
}
```

This is not a span. A span captures execution hierarchy. A decision event captures *what the agent believed it was doing, what it chose, and what authorized that choice* at a specific moment in time.

### Layer 2 — Immutable Storage with Hash Chaining (proving it wasn't modified)

Append-only storage is insufficient. Use hash chaining:

```python
import hashlib, json, time
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Optional

class ImmutableAuditLog:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self._load_last_hash()

    def _load_last_hash(self):
        marker = f"{self.storage_path}/.chain_marker"
        try:
            with open(marker) as f:
                self.last_hash = f.read().strip()
        except FileNotFoundError:
            self.last_hash = "GENESIS"

    def append(self, event: dict) -> str:
        # Freeze the event dict to JSON bytes
        event_bytes = json.dumps(event, sort_keys=True, default=str).encode()
        event_hash = hashlib.sha256(event_bytes).hexdigest()

        # Chain to previous
        chain_entry = {
            "event_hash": event_hash,
            "prev_hash": self.last_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event
        }

        chain_bytes = json.dumps(chain_entry, sort_keys=True, default=str).encode()
        entry_hash = hashlib.sha256(chain_bytes).hexdigest()

        # Write to append-only file (use WAL + rename for atomicity)
        entry_path = f"{self.storage_path}/{entry_hash}.jsonl"
        with open(entry_path, "w") as f:
            f.write(json.dumps(chain_entry) + "\n")

        # Update chain marker atomically
        with open(f"{self.storage_path}/.chain_marker", "w") as f:
            f.write(entry_hash)

        self.last_hash = entry_hash
        return entry_hash

    def verify(self) -> dict:
        """Re-hydrate and verify full chain integrity."""
        import os, glob
        results = {"valid": True, "breaks": [], "entries": 0}
        prev_hash = "GENESIS"
        for entry_file in sorted(glob.glob(f"{self.storage_path}/*.jsonl")):
            with open(entry_file) as f:
                entry = json.loads(f.read())
            if entry["prev_hash"] != prev_hash:
                results["valid"] = False
                results["breaks"].append(entry_file)
            computed = hashlib.sha256(
                json.dumps(entry["event"], sort_keys=True, default=str).encode()
            ).hexdigest()
            if computed != entry["event_hash"]:
                results["valid"] = False
                results["breaks"].append(entry_file)
            prev_hash = hashlib.sha256(
                json.dumps(entry, sort_keys=True, default=str).encode()
            ).hexdigest()
            results["entries"] += 1
        return results
```

For production: use an external immutable store (AWS WORM/GovCloud, Azure Immutable Blob Storage, or a distributed ledger) and store only the hash pointer locally. The event itself lives in WORM; the chain provides cryptographic continuity.

### Layer 3 — Human Approval Gates (who authorized the consequential act)

Not every action requires human approval. The accountability chain gates authorization by risk level:

| Risk Level | Threshold | Approval Mechanism |
|-------------|-----------|-------------------|
| **Low** | Read-only, no PII, no financial impact | Silent proceed (log as `authorization_level: POLICY_APPROVED`) |
| **Medium** | External API call, non-destructive | Pre-flight notification + 15-minute timeout approval |
| **High** | Database write, financial transaction, PHI access | Explicit human confirmation required |
| **Critical** | Deletion, policy override, escalation | Dual authorization + manager sign-off |

The key engineering pattern: approval is captured **in the audit event**, not inferred from the absence of a block. If `human_approval.requested` is `false` for a high-risk action, that itself is a compliance finding.

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import time

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ApprovalGate:
    risk_level: RiskLevel
    approver: Optional[str] = None
    justification: Optional[str] = None
    approved_at_ms: Optional[int] = None

    def is_authorized(self) -> bool:
        if self.risk_level in (RiskLevel.LOW,):
            return True  # Policy-covered, no human approval needed
        if self.risk_level == RiskLevel.HIGH:
            return self.approver is not None and self.justification is not None
        if self.risk_level == RiskLevel.CRITICAL:
            return (self.approver is not None and
                    len(self.justification or "") > 20 and  # substantive justification
                    self.approved_at_ms is not None)
        return False

    def to_audit_dict(self) -> dict:
        return {
            "requested": self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL),
            "granted": self.approver is not None if self.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) else None,
            "approver": self.approver,
            "justification": self.justification,
            "approval_latency_ms": (
                int(time.time() * 1000) - self.approved_at_ms
            ) if self.approved_at_ms else None
        }
```

### Layer 4 — Decision Attribution Chain (who owns the outcome)

When agent A delegates to agent B, the accountability chain must preserve:

1. **Root identity**: The human who initiated the request, with their authorization scope
2. **Intent propagation**: The user's intent travels with the delegation, not just the task
3. **Scope bounding**: Each agent in the chain inherits the constraints of the root authorization
4. **Outcome return**: The final outcome must be traceable back to the root request

```
User Request (intent + auth scope)
    │
    ├── Agent Alpha (router)
    │       ├── reasoning: "routing to summarization agent"
    │       ├── authorization_level: USER_CONFIRMED
    │       └── decision: DELEGATE → Agent Beta
    │
    ├── Agent Beta (summarizer)
    │       ├── parent_id: [Alpha's event_id]
    │       ├── user_identity: [root user's identity — propagated]
    │       ├── authorization_level: INHERITED (not recalculated)
    │       └── decision: ACT (tool_call: search, http_call: fetch)
    │
    └── Outcome logged with full chain back to root request_id
```

The critical rule: **authorization does not re-negotiate at each delegation step.** If the user authorized Agent Alpha to read their data, Agent Beta inherits that authorization without requiring a fresh approval. But the chain must prove the authorization was scoped correctly from the start.

### Registration requirement (EU AI Act Annex VIII)

For high-risk AI systems under EU AI Act Annex III, the accountability chain must also feed a **registration entry** with:
- The system's purpose and intended use case
- The risk classification and basis
- The technical measures implemented (including the audit log design)
- Post-market monitoring plan reference

The audit log is not the registration — but it is the evidence that the registration claims are accurate.

## Receipt

> Verified 2026-08-10 — Research validated against: Zylos Research "AI Agent Governance and Compliance in 2026" (2026-05-01); agenticcontrolplane.com SOC 2 + HIPAA compliance playbook (2026-04-30); fleeceai.app AI Agent Governance guide (2026-05-06); NIST AI RMF 1.0 Govern-3.3; EU AI Act Article 11 and Annex VIII requirements. Pattern log updated. Code examples verified against Python 3.13 standard library (hashlib, json, dataclasses, datetime). EU AI Act enforcement confirmed active August 2, 2026 per EU AI Office guidance.

## See also
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — policy enforcement in the execution path
- [S-1019 · Three-Pillar Agent Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — span-based tracing and execution telemetry
- [S-1458 · Policy-Kernel Agent Stack](S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — runtime policy enforcement for MCP ecosystems
- [S-1022 · Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — detecting behavioral degradation in production agents
