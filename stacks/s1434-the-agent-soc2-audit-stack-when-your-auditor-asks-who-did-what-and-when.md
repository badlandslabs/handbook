# S-1434 · The Agent SOC2 Audit Stack — When Your Auditor Asks "Who Did What, and When"

Your agent just approved a $40,000 vendor payment, routed a support ticket, and updated a customer record — all autonomously, all in the last hour. Your SOC2 auditor asks: "Show me who approved what, which system changed, what data left the boundary, and how to undo it." If your answer is "our SIEM shows API traffic," you have a finding. Agents are not exempt from SOC2 Trust Services Criteria — but most teams have never mapped them to agent infrastructure. This entry provides the five-layer audit event schema and the compliance stack to survive a Type II audit.

## Forces

- **SIEM logs ≠ agent audit trails.** API traffic logs prove a call was made; they don't prove which agent identity made it, what reasoning led to the call, what the tool returned, or whether the output was validated. SOC2 requires the chain.
- **Every agent is a non-human identity (NHI) multiplying access.** One compromised or misconfigured agent accumulates permissions from every tool it calls. CC6 demands you prove each agent has a unique identity and that access decisions were enforced, not assumed.
- **Agent determinism breaks traditional log semantics.** A traditional service call is idempotent and logged atomically. An agent step involves: trigger → reasoning → tool selection → execution → state mutation → output validation. Each layer is a separate auditable event.
- **The evidentiary burden is continuous, not point-in-time.** SOC2 Type II requires evidence that controls operated effectively over the audit period — not just that you *have* logging, but that you can demonstrate it was running, tamper-evident, and queryable.

## The Move

### Map Agent Behavior to the Five Trust Services Criteria

Three of the five SOC2 Trust Services Criteria apply directly to agent deployments:

| Criterion | Agent Application | Audit Question |
|-----------|-------------------|----------------|
| **CC6** — Logical Access Controls | Each agent has a unique identity; each tool call is gated on explicit permission; access decisions are enforced pre-execution, not post-hoc | "Can you prove agent X could only call tool Y?" |
| **CC7** — System Operations | Agents are monitored for anomalous behavior; loops, excessive retries, and unauthorized escalation paths are detected; capacity limits prevent runaway execution | "How do you know the agent didn't run 10,000 calls in an hour?" |
| **CC8** — Change Management | Agent behavior changes (prompt updates, model swaps, new tool grants) are versioned, approved, and deployed through a controlled pipeline | "When you updated the agent's instructions, was that change reviewed?" |

The other two — **Availability (A1)** and **Confidentiality/Privacy (P series)** — apply to agent infrastructure as systems, not agent-specific behaviors.

### Build the Five-Layer Audit Event Schema

Every agent step generates five discrete events that must be captured independently:

```python
# Layer 1: Trigger — what initiated this agent action
{
    "event_layer": "trigger",
    "agent_id": "agent_001",
    "trigger_type": "user_request | scheduled | agent_handoff | tool_callback",
    "principal": "user:jane@acme.com | agent:coordinator_01",
    "session_id": "sess_abc123",
    "timestamp": "2026-07-21T14:23:11Z",
    "raw_input_hash": "sha256:...",        # for PII redaction reproducibility
    "input_classification": "public | internal | confidential",
}

# Layer 2: Reasoning — what the agent decided to do and why
{
    "event_layer": "reasoning",
    "session_id": "sess_abc123",
    "model_id": "claude-sonnet-4-20250514",
    "step_index": 3,
    "tool_calls_planned": ["sql_query", "email_send"],
    "tool_calls_rejected": ["web_scrape"],   # blocked by policy
    "rejection_reason": "tool 'web_scrape' not in allowed_scope",
    "confidence_score": 0.91,
    "context_tokens_used": 4821,
    "cost_usd": 0.0032,
}

# Layer 3: Tool Execution — what actually ran
{
    "event_layer": "tool_execution",
    "session_id": "sess_abc123",
    "step_index": 3,
    "tool_name": "sql_query",
    "tool_provider": "mcp:postgres-analytics",
    "input_args_hash": "sha256:...",        # not the raw args (may contain PII)
    "output_status": "success | error | truncated",
    "output_size_bytes": 2048,
    "execution_duration_ms": 340,
    "credentials_used": "svc_account:analytics_reader",  # NHI, not human
}

# Layer 4: Data Access — what data moved
{
    "event_layer": "data_access",
    "session_id": "sess_abc123",
    "data_source": "table:customers.orders",
    "access_type": "read | write | delete",
    "rows_affected": 12,
    "data_classification": "confidential | PII | public",
    "retention_policy_applied": "90d | indefinite | erased",
    "cross_boundary": false,                  # data didn't leave the system
    "compliance_tags": ["GDPR-ART6-LC", "PCI-DSS"],
}

# Layer 5: Side Effects — what changed outside the agent system
{
    "event_layer": "side_effect",
    "session_id": "sess_abc123",
    "downstream_system": "salesforce | jira | slack | payment_gateway",
    "action": "record_updated | ticket_created | message_sent | payment_authorized",
    "action_id": "SFDC_00Dxx0000xxx",        # external system's record ID
    "rollback_possible": true,
    "rollback_procedure": "void_payment(payment_id)",
    "human_approval_required": false,       # true if action exceeds auto-threshold
    "approval_record": null,                 # or {approver, method, timestamp}
}
```

### Instrument for Tamper-Evident Storage

SOC2 auditors expect logs that cannot be retroactively edited. The minimal compliance stack:

```
┌─────────────────────────────────────────────┐
│  Agent Runtime (emits structured events)    │
└──────────────┬──────────────────────────────┘
               │ async, non-blocking
┌──────────────▼──────────────────────────────┐
│  Audit Relay (stateless, no buffering)      │
│  - Validates schema                         │
│  - Redacts PII before storage               │
│  - Attaches immutable timestamps            │
└──────────────┬──────────────────────────────┘
               │ 
┌──────────────▼──────────────────────────────┐
│  Immutable Log Sink                        │
│  - Append-only (WORM semantics)            │
│  - Examples: AWS S3 Object Lock,           │
│    Chronicle AutoAudit, Hive metastore     │
│    with write-once, Teleport Auth         │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│  Audit Query Layer                         │
│  - Compliance reporting                     │
│  - Evidence package generation              │
│  - Anomaly alerting (CC7)                   │
└─────────────────────────────────────────────┘
```

### Handle Delegation Chains (Multi-Agent Handoffs)

When one agent hands off to another, the audit trail must remain continuous. Each handoff appends a delegation record to the originating session:

```json
{
    "event_layer": "agent_handoff",
    "session_id": "sess_abc123",
    "handoff_from": "agent_001",
    "handoff_to": "agent_002",
    "handoff_reason": "task_type:routing | escalate | specialize",
    "context_hash": "sha256:...",     // hash of shared state at handoff
    "chain_of_custody": "sess_abc123 → sess_def456",
    "consent_recorded": true,          // downstream agent consented to receive context
}
```

This creates a delegation chain that satisfies both CC6 (who acted) and CC8 (was the handoff approved).

## Receipt

> Verified 2026-07-21 — Compiled from: Teleport Blog (McGladrey, CISSP, Feb 2026), Intercis (Cabello, Apr 2026), ICMD (May 2026, updated Jul 2026). The five-layer schema is synthesized from published practitioner guidance and real audit findings. No fabricated audit requirements.

## See also

- [S-992 · Agent Verifiable Credential Infrastructure](s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — NHI identity and the credential problem that makes CC6 hard
- [S-1019 · Three-Pillar Observability](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — tracing architecture that powers layers 1–3 of the audit schema
- [S-1000 · Structural Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — enforcement layer that makes CC6 controls actually operative
- [S-1043 · Dreaming Pattern](s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — memory consolidation raises CC8 questions about which version of the agent "decided"
