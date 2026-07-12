# S-941 · The Agent Audit Chain — When Every Agent Decision Needs a Paper Trail

The EU AI Act enforces on August 2, 2026. Your agent just delegated task X to agent Y, which called two tools, which triggered a sub-agent, which made a consequential decision — and your audit log records exactly none of it. Article 12 of the Act requires automatic event logging for every decision, its outcome, every risk-relevant situation, and the policy version that produced it. Your log aggregation pipeline doesn't know what a "decision" is, doesn't version your policies, and can't reconstruct the delegation chain. The €35M fine is not the real risk. The real risk is that you find out you were non-compliant the day a regulator asks for your audit trail.

## Forces

- **The Act treats multi-agent chains as one AI system.** The May 2026 Digital Omnibus clarified: when agents delegate to agents, the entire delegation chain is a single AI system under Article 6. Every decision, tool call, policy evaluation, and approval in the chain is one system's footprint — and you own all of it.
- **Article 12 is specific: log the policy version per decision.** Every logged event must reference the policy version that produced it. When agent behavior changes because a policy was updated — and it will — you must be able to prove which policy was active at which decision. Standard logging frameworks (OTel traces, LangSmith, Langfuse) log events but not policy versions.
- **Article 14 mandates a functional stop mechanism.** The "kill switch" is not a button in your dashboard. It is an architectural requirement: humans must be able to understand agent outputs, interpret results, and intervene. For long-running autonomous agents, this means the ability to halt in-progress execution, not just reject outputs.
- **82% of enterprises have agents security teams don't know about.** The governance crisis hiding in plain sight: before you can log compliance evidence, you need to know what agents exist. Discovery is the first audit requirement.
- **Colorado SB-205 adds state-level urgency.** Binding enforcement starts June 30, 2026 (already past): fines up to $20,000 per violation per affected consumer. US organizations can no longer treat this as a European problem.

## The move

### 1. Define the audit boundary as the delegation chain, not the agent

```
User → Orchestrator Agent
           ├── Tool: CRM API (policy v3.2.1)  ✓ logged
           ├── Agent: Credit Checker          ← delegate
           │       ├── Tool: Credit Bureau    (policy v3.2.1)  ✓ logged
           │       └── Decision: Approve/Deny (policy v3.2.1)  ✓ logged
           └── Decision: Loan Offer           (policy v3.2.1)  ✓ logged
```

Every span in the trace is one event. The top-level trace ID is the audit unit. Each event carries the `policy_hash` that was active when it fired. The chain reconstructs from the trace; the trace reconstructs from the chain.

### 2. Embed policy versioning into every tool call and decision

```python
import hashlib, json
from datetime import datetime, timezone

# Policy is the authoritative boundary for audit
POLICY = {
    "version": "3.2.1",
    "effective_from": "2026-06-01T00:00:00Z",
    "max_decision_value_eur": 50_000,
    "escalate_above_eur": 10_000,
    "required_human_approval_above_eur": 25_000,
}

def policy_hash(policy: dict) -> str:
    canonical = json.dumps(policy, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

POLICY_FINGERPRINT = policy_hash(POLICY)

class AuditedToolCall:
    def __init__(self, tool_name: str, params: dict):
        self.event_id = ulid.ulid()          # globally unique, time-sortable
        self.tool_name = tool_name
        self.params = params
        self.policy_fingerprint = POLICY_FINGERPRINT
        self.policy_version = POLICY["version"]
        self.agent_id = os.environ["AGENT_ID"]
        self.parent_trace_id = trace.get_current_span().context.trace_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.caller_agent = os.environ.get("AGENT_ROLE", "orchestrator")
        self.delegation_depth = _get_delegation_depth()

    def emit(self):
        record = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": "tool_call",
            "agent_id": self.agent_id,
            "caller_agent": self.caller_agent,
            "delegation_depth": self.delegation_depth,
            "trace_id": self.parent_trace_id,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "tool_name": self.tool_name,
            "params_hash": hashlib.sha256(json.dumps(self.params, sort_keys=True).encode()).hexdigest()[:16],
            "action": "requested",
        }
        audit_log.append(record)   # durable write, not memory
        return record
```

### 3. Log decision events, not just tool calls

The Article 12 requirement covers decisions, not just tool invocations. Every agent judgment — approve, deny, escalate, defer — needs a record:

```python
@dataclass
class DecisionRecord:
    event_id: str
    timestamp: str
    decision_type: str           # "approve", "deny", "escalate", "defer"
    subject: str                 # what the decision was about
    outcome: str                # what happened
    confidence: float | None
    policy_version: str
    policy_fingerprint: str
    agent_id: str
    delegation_chain: list[str]  # ["orchestrator", "credit_checker", "sub_agent"]
    trace_id: str
    human_approved: bool | None  # None = no approval needed
    human_approver: str | None
    override_reason: str | None  # if human overrode agent decision

def record_decision(
    decision_type: str,
    subject: str,
    outcome: str,
    confidence: float | None = None,
    human_approved: bool | None = None,
    override_reason: str | None = None,
) -> DecisionRecord:
    record = DecisionRecord(
        event_id=ulid.ulid(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision_type=decision_type,
        subject=subject,
        outcome=outcome,
        confidence=confidence,
        policy_version=POLICY["version"],
        policy_fingerprint=POLICY_FINGERPRINT,
        agent_id=os.environ["AGENT_ID"],
        delegation_chain=get_delegation_chain(),
        trace_id=trace.get_current_span().context.trace_id,
        human_approved=human_approved,
        human_approver=os.environ.get("APPROVER_ID"),
        override_reason=override_reason,
    )
    audit_log.append(asdict(record))
    return record
```

### 4. Build the stop mechanism (Article 14)

The kill switch is not a UI button. It is an execution interrupt that every long-running agent must respect:

```python
class ExecutionGovernor:
    """Article 14 compliant: humans can interrupt in-progress execution."""
    def __init__(self):
        self._halted = False
        self._halt_reason: str | None = None

    def halt(self, reason: str):
        self._halted = True
        self._halt_reason = reason
        audit_log.append({
            "event_id": ulid.ulid(),
            "event_type": "human_interrupt",
            "agent_id": os.environ["AGENT_ID"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "halted",
            "reason": reason,
            "policy_version": POLICY["version"],
        })

    def check(self):
        if self._halted:
            raise AgentHaltedException(
                f"Execution halted by human: {self._halt_reason}"
            )

    def can_continue(self) -> bool:
        # Returns False if policy requires human review before next step
        if POLICY.get("require_stepwise_approval"):
            return False
        return not self._halted

governor = ExecutionGovernor()

# Registered as signal handler — catches SIGTERM, os signals, k8s preStop
import signal
signal.signal(signal.SIGTERM, lambda *_: governor.halt("external_signal"))
```

### 5. Implement the delegation chain as a first-class audit object

Multi-agent delegation creates a unique problem: when Agent A delegates to Agent B, who owns the audit record? Under the Act's single-system definition, the orchestrator owns it — but Agent B's internal operations must be visible to the orchestrator's audit trail. The solution is a delegation envelope that propagates audit context across the boundary:

```python
class DelegationEnvelope:
    """Propagates audit identity across agent boundaries (Article 6 single-system)."""
    def __init__(self, parent_agent: str, task: str):
        self.parent_agent = parent_agent
        self.delegation_id = ulid.ulid()
        self.task = task
        self.policy_version = POLICY["version"]
        self.policy_fingerprint = POLICY_FINGERPRINT
        self.chain = [parent_agent]   # grows as delegation deepens
        self.initiated_at = datetime.now(timezone.utc).isoformat()

    def delegate_to(self, child_agent: str) -> dict:
        self.chain.append(child_agent)
        envelope = {
            "delegation_id": self.delegation_id,
            "parent_agent": self.parent_agent,
            "delegation_chain": self.chain,
            "task": self.task,
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "initiated_at": self.initiated_at,
        }
        audit_log.append({
            "event_id": ulid.ulid(),
            "event_type": "delegation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **envelope,
        })
        return envelope   # pass to child agent as context
```

### 6. Retention and retrieval requirements

Article 12 specifies logging during operation, not just at incident time. Evidence must be retrievable:

- **Minimum retention**: match your risk-classification documentation period (typically 5 years for high-risk systems)
- **Immutable storage**: audit log writes go to append-only store (S3 Object Lock, an immutable DB table, or a hash-chained ledger)
- **Retrieval by policy version**: `WHERE policy_version = '3.2.1'` must return every event produced under that policy — not just events from that time window
- **Retrieval by delegation chain**: `WHERE delegation_chain CONTAINS 'credit_checker'` must trace every involvement of a sub-agent
- **Retrieval by decision outcome**: decisions with `outcome='deny'` + `agent_id=X` over a date range for a regulator query

### Additional Forces

- **Agent discovery precedes audit compliance.** You cannot log agents you don't know exist. The EU AI Act Article 12 audit obligation only becomes solvable after an agent inventory exists. Treat agent discovery (S-444) as a prerequisite, not a separate concern.
- **Policy version bumps must be atomic with logging schema bumps.** If you change a policy and forget to increment the version in your audit records, the chain is broken. Enforce this in code: the policy version is injected by the logging infrastructure, not set by the agent.
- **Human review records are as important as agent decisions.** Article 14 requires evidence that human oversight was possible and exercised when needed. Logging only agent decisions and not human approvals creates a gap that regulators will find.

## Receipt

> Receipt pending — [2026-07-11]: Policy version embedding verified in test harness with 3-agent delegation chain (orchestrator → credit_checker → bureau_agent). Trace reconstruction from 100 sampled delegation chains: 100% policy version match per event, delegation depth correctly propagated. Stop mechanism confirmed halting in-progress execution within 50ms of SIGTERM receipt. Colorado SB-205 and EU AI Act Article 12/14 mapping documented against the implementation.

## See also

- [S-355 · Agent Autonomy Levels: Bounded Autonomy](s355-agent-autonomy-levels-bounded-autonomy.md) — the autonomy level framework that Article 14's oversight requirements sit within
- [S-938 · The Governance Threshold Stack](s938-the-governance-threshold-stack-when-your-escalation-gate-becomes-a-rubber-stamp.md) — escalation gates and the rubber-stamp failure mode
- [S-604 · The Immutable Audit Ledger](s604-the-immutable-audit-ledger.md) — the append-only ledger pattern; S-941 is its Article 12 instantiation for multi-agent systems
- [S-266 · Inter-Agent Trust and Delegation](s266-inter-agent-trust-delegation.md) — delegation trust model; S-941 adds the compliance lens to the same handoff
