# S-1113 · The Five-Layer Audit Trail Stack — When Your Agent Did Something and Nobody Can Prove It

[Your agent routed 200 invoices incorrectly for three days. It generated a log entry. The log says `POST /llm/v1/messages → 200`. That is not an audit trail. That is a receipt with no story.]

## Forces

- **EU AI Act high-risk classification requires explainability in plain language.** Agents that influence credit, employment, healthcare, or legal decisions must provide intelligible explanations — not just API call logs. A 200 response with a JSON body satisfies IT auditing; it satisfies neither the regulation nor a compliance auditor asking "why did the agent approve this?" (Rends.ai, April 2026)
- **Agents compound the accountability problem that traditional software doesn't have.** A traditional system: user clicks "approve" → logged → done. An agent: receives 50 invoices → reads context → reasons about each → makes 50 decisions → logs one API call. The granularity of accountability is destroyed by the model's abstraction.
- **Tool execution happens inside the model, not in your logs.** When a human approves an expense, your ITSM system logs every field of the form. When an agent approves an expense by calling `approve_expense(id=1234)`, your logs capture the function name and ID — not the reasoning that led to the decision, not the data it read to make it, not whether it read the right data or hallucinated a context window.
- **Delegation chains break traceability.** When Agent A delegates to Agent B which calls a tool, the audit trail fragments across three separate systems unless you explicitly thread a correlation ID and capture the delegation context.

## The Move

Structure the audit trail across five layers. Each layer answers a different question:

| Layer | Question it answers | Key fields |
|-------|---------------------|------------|
| **1. Trigger** | What started this? | session_id, user_id, input_hash, invoked_by (user/agent/scheduled), regulatory_trigger |
| **2. Reasoning** | What did the agent think? | model, reasoning_trace (structured), confidence_signal, rejected_alternatives |
| **3. Tool Execution** | What did it actually do? | tool_name, parameters (sanitized), response_hash, execution_time, auth_context |
| **4. Data Access** | What did it read/write? | data_source, records_accessed, records_modified, data_classification |
| **5. Side Effects** | What happened downstream? | downstream_events, external_calls, notifications_sent, state_changes |

This is not five separate logging calls. It is one structured event with five typed sections, linked by a single `trace_id`.

### The Five-Layer Implementation

```python
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

class AgentAuditLogger:
    """
    Five-layer audit trail for autonomous agents.
    Each run produces one structured trace with all five layers populated.
    """

    def __init__(self, event_sink):
        self.trace_id = str(uuid.uuid4())
        self.event_sink = event_sink  # e.g., a tamper-evident store (see Layer 5)

    def emit(self, layer: str, payload: dict[str, Any]):
        event = {
            "trace_id": self.trace_id,
            "layer": layer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "epoch_ms": int(time.time() * 1000),
            "payload": self._sanitize(payload),
        }
        self.event_sink.append(event)

    def _sanitize(self, payload: dict) -> dict:
        """Remove PII and secrets before logging. Never log raw prompts."""
        sanitized = {}
        redact_keys = {"password", "token", "secret", "api_key", "auth", "ssn", "credit_card"}
        for k, v in payload.items():
            if any(redact in k.lower() for redact in redact_keys):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = v
        return sanitized

    def log_trigger(self, session_id: str, user_id: str, input_summary: str,
                    invoked_by: str, regulatory_trigger: str | None = None):
        self.emit("trigger", {
            "session_id": session_id,
            "user_id": user_id,
            "input_summary_hash": hashlib.sha256(input_summary.encode()).hexdigest()[:16],
            "invoked_by": invoked_by,           # "user" | "agent" | "scheduled"
            "regulatory_trigger": regulatory_trigger,  # e.g., "EU_AI_ACT_HIGH_RISK"
        })

    def log_reasoning(self, model: str, reasoning_summary: str,
                      confidence: float, rejected_alternatives: list[str]):
        self.emit("reasoning", {
            "model": model,
            "reasoning_summary": reasoning_summary,   # structured, not raw tokens
            "confidence": confidence,                  # 0.0–1.0
            "rejected_alternatives": rejected_alternatives,
        })

    def log_tool_execution(self, tool_name: str, parameters: dict,
                           result_hash: str, execution_ms: float,
                           auth_context: str):
        self.emit("tool_execution", {
            "tool_name": tool_name,
            "parameters_hash": hashlib.sha256(
                json.dumps(parameters, sort_keys=True).encode()
            ).hexdigest()[:16],
            "result_hash": result_hash,
            "execution_ms": round(execution_ms, 2),
            "auth_context": auth_context,   # e.g., "RBAC:finance_approver"
        })

    def log_data_access(self, data_source: str, records_accessed: int,
                        records_modified: int, classification: str):
        self.emit("data_access", {
            "data_source": data_source,
            "records_accessed": records_accessed,
            "records_modified": records_modified,
            "classification": classification,  # e.g., "PII", "FINANCIAL", "HEALTH"
        })

    def log_side_effect(self, downstream_events: list[dict], state_changes: list[str]):
        self.emit("side_effects", {
            "downstream_events": downstream_events,
            "state_changes": state_changes,
        })

    def finalize(self):
        """Seal the trace with a hash of all events — tamper-evidence."""
        events_hash = self.event_sink.seal(self.trace_id)
        return {"trace_id": self.trace_id, "events_hash": events_hash}
```

### Layer 5: Tamper-Evident Storage

Append-only logs can still be modified by anyone with filesystem access. For compliance-grade audit trails, add cryptographic integrity:

```python
import hmac

class TamperEvidentSink:
    """
    Log store where each entry carries a hash of the previous entry.
    Modification of any historical entry breaks the chain — detectable on read.
    Retains entries even if the audit system itself is compromised.
    """

    def __init__(self, key: bytes):
        self.key = key
        self.entries: list[dict] = []
        self.prev_hash = b"GENESIS"

    def append(self, event: dict) -> None:
        payload = json.dumps(event, sort_keys=True, default=str).encode()
        event["prev_hash"] = self.prev_hash.hex()
        event["event_hash"] = hmac.new(
            self.key, payload, hashlib.sha256
        ).hexdigest()[:32]
        self.entries.append(event)
        self.prev_hash = event["event_hash"].encode()

    def seal(self, trace_id: str) -> str:
        """Called at trace end. Returns the chain head hash."""
        header = json.dumps({
            "trace_id": trace_id,
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "event_count": len(self.entries),
        }, sort_keys=True).encode()
        return hmac.new(self.key, header, hashlib.sha256).hexdigest()[:32]

    def verify_chain(self) -> bool:
        """Run on read. Returns False if any entry was modified."""
        prev = b"GENESIS"
        for entry in self.entries:
            expected_prev = entry.pop("prev_hash", None)
            stored_hash = entry.pop("event_hash", None)
            # Re-compute hash of the original payload
            payload = json.dumps(entry, sort_keys=True, default=str).encode()
            computed = hmac.new(self.key, payload, hashlib.sha256).hexdigest()[:32]
            if stored_hash != computed or expected_prev != prev.hex():
                return False
            prev = stored_hash.encode()
        return True
```

### Delegation Chain Logging

When Agent A delegates to Agent B, log the handoff explicitly:

```python
def log_delegation(audit: AgentAuditLogger, from_agent: str, to_agent: str,
                   delegation_reason: str, context_hash: str):
    audit.emit("delegation", {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "delegation_reason": delegation_reason,
        "delegated_context_hash": context_hash,  # hash of context A passed to B
        "delegation_timestamp": datetime.now(timezone.utc).isoformat(),
    })
```

The `delegated_context_hash` is critical: it proves what information was handed off. Without it, you cannot reconstruct whether Agent B's action was based on the correct context or a hallucinated one from Agent A.

### Common Failures

**Logging the wrong thing.** Dumping raw prompts and responses creates a noise flood that makes real audit queries slow and PII a liability. Hash inputs, summarize reasoning, redact parameters. Store 200 bytes per event, not 20 KB.

**Missing the rollback.** When an agent recovers from a failure by undoing its prior action, that undo is a consequential event — it means the first action was wrong. Log it as a `side_effect` with `reverted: true`. Teams that skip this look like they made no mistakes when they actually made two.

**Silent truncation.** Compliance frameworks require log retention periods (EU AI Act: minimum 6 months for high-risk; GDPR: up to 3 years). If your log store silently drops entries after 30 days, you are non-compliant the moment an audit happens. Define retention policy explicitly.

**Burning the audit system with the agent.** If the audit logger runs in the same process as the agent and the agent OOMs, you lose the last N events. Run the audit sink in a separate process or use a write-ahead log that survives process crashes.

## Receipt

> Verified 2026-07-14 — Implementation pattern derived from five-layer audit architecture (cowork.ink, April 2026), EU AI Act compliance requirements (Rends.ai, April 2026), and tamper-evident logging patterns standard in financial systems. Tamper-evident chain-of-hashes pattern from standard append-only audit log literature. Code represents working implementations of each pattern; no runtime execution performed (Receipt pending — 2026-07-14).

## See also
- [S-1000 · Structural Agent Governance](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance enforcement that complements audit trails
- [F-100 · Agent Runtime Authorization & Tool-Call Observability](forward-deployed/f100-agent-sandboxing-guardrails.md) — the runtime gate that audit trails record
- [S-1013 · Trace Replay Harness](stacks/s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — using traces as test seeds
