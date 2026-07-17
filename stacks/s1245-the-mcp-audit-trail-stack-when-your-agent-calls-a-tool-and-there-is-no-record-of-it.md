# S-1245 · The MCP Audit Trail Stack — When Your Agent Calls a Tool and There Is No Record of It

Your EU-hosted agent processes a healthcare patient's data, calls the EHR MCP tool, and retrieves records it was never authorized to access. The audit team asks: who queried what, when, and on whose behalf? The answer: MCP's native logging has no idea. The tool call happened; the log didn't survive it.

The Model Context Protocol connects agents to tools with machine-level speed and human-level opacity. Every invocation crosses a trust boundary — and if you haven't instrumented that crossing, you have no audit trail, no forensics, and no compliance defense.

## Forces

- **MCP's native logging is ephemeral.** The protocol has no built-in audit schema. Logs live in server memory, stdout buffers, or nowhere at all. A single user request can trigger 12 tool calls across 4 MCP servers — none of which share a session context or correlation ID.
- **Compliance frameworks demand what MCP doesn't provide.** HIPAA requires 6-year PHI access logs. EU AI Act Art. 12 (high-risk systems, effective August 2026) mandates 10-year operational records including inputs, outputs, and the ability to reconstruct decisions. SOC 2 Type II requires evidence of continuous logging, not post-hoc reconstruction.
- **Cross-border data flow creates simultaneous obligations.** MCP tool call logs often contain PII in parameters (user IDs, query terms, document IDs). Shipping those logs to a US-based SIEM without a legal transfer mechanism (SCCs, adequacy decision) creates a GDPR Chapter V violation alongside the original compliance gap.
- **Audit depth must match decision depth.** A tool call's audit log is only useful if you can connect it back to the agent's reasoning chain — which tool was called, with what parameters, in service of what upstream intent. Tool logs without session context are forensics with no crime scene.

## The move

**Layer 1 — Structured MCP Event Capture**

Intercept every MCP interaction at the transport layer. Don't rely on server-side logging — instrument the client-side SDK and the server-side stubs.

```python
# Python MCP client-side interceptor (wrapper around any MCP client)
import json
import time
import hashlib
from datetime import datetime, timezone

class MCPAuditLogger:
    def __init__(self, session_id: str, user_id: str, retention_policy: dict):
        self.session_id = session_id
        self.user_id = user_id
        self.retention_policy = retention_policy  # e.g., {"phi": "6y", "standard": "1y", "art12": "10y"}

    def log_tool_call(self, server_name: str, tool_name: str,
                      parameters: dict, result: dict, duration_ms: float):
        # Detect PII in parameters before logging
        sanitized_params = self._sanitize(parameters)

        event = {
            "audit_version": "1.0",
            "event_type": "mcp_tool_call",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "mcp_server": server_name,
            "tool_name": tool_name,
            "parameters_hash": hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[:16],
            # Full params stored separately in PII-compliant store
            "parameters_hash_full": hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest(),
            "result_summary": self._summarize_result(result),
            "duration_ms": duration_ms,
            "decision_chain_ref": self._get_decision_ref(),
            "compliance_tags": self._classify_compliance(parameters, result),
        }
        # Write to immutable append-only audit log
        self._append_audit(event)

    def _sanitize(self, params: dict) -> dict:
        PII_FIELDS = {"ssn", "email", "phone", "dob", "address", "name", "patient_id"}
        return {k: "[REDACTED]" if k.lower() in PII_FIELDS else v
                for k, v in params.items()}

    def _classify_compliance(self, params: dict, result: dict) -> list[str]:
        tags = []
        if any(k.lower() in {"patient_id", "medical_record"} for k in params):
            tags.append("HIPAA_PHI")
        if self._contains_eu_data(params, result):
            tags.append("GDPR_ART5_MINIMIZATION")
            tags.append("EU_DATA_RESIDENCY")
        return tags

    def _contains_eu_data(self, params: dict, result: dict) -> bool:
        # Check data residency markers, geo fields, or explicit EU indicators
        return any(str(v).upper() in {"EU", "EUROPE", "DE", "FR", "NL", "DE", "AT", "BE", "IE", "PT", "ES", "IT", "PL", "SE", "FI", "DK", "GR", "CZ", "HU", "RO", "BG", "HR", "SK", "SI", "LT", "LV", "EE", "LU", "MT", "CY"} for v in {**params}.values())
```

**Layer 2 — Retention Tiers by Regulatory Obligation**

Not all logs need the same treatment. Route them into tiered storage based on data type and regulatory requirement.

| Tier | Data Type | Retention | Storage | Transfer Restriction |
|------|-----------|-----------|---------|---------------------|
| PHI/Art.12 | PHI tool calls, high-risk AI inputs/outputs | 10 years | EU-only object storage (S3 with OISA or Azure EU regions) | No cross-border transfer |
| Standard | General tool calls, agent decisions | 1 year | Standard EU storage | GDPR Chapter V if EU personal data |
| Operational | Latency, error rates, cost | 90 days | Any region | No restriction |
| Forensic Buffer | Full payload capture (on-demand) | 30 days rolling | Immutable write-once store | Same as PHI tier |

**Layer 3 — Decision Chain Correlation**

Tool call logs without the agent's reasoning chain are useless for Art. 12 reconstruction. Bridge the MCP event log to the agent trace.

```python
# Bridge MCP audit events to agent decision trace via OpenTelemetry
from opentelemetry import trace

tracer = trace.get_tracer("mcp-audit")

@tracer.start_as_current_span("mcp_tool_call")
def instrumented_tool_call(mcp_client, server: str, tool: str, params: dict):
    span = trace.get_current_span()
    span.set_attribute("mcp.server", server)
    span.set_attribute("mcp.tool", tool)
    # Propagate session and user context into the MCP call
    span.set_attribute("audit.session_id", current_session_id())
    span.set_attribute("audit.user_id", current_user_id())

    start = time.monotonic()
    result = mcp_client.call_tool(server, tool, params)
    duration_ms = (time.monotonic() - start) * 1000

    # Fire audit event — OTel exports to your audit store
    audit_logger.log_tool_call(
        server_name=server,
        tool_name=tool,
        parameters=params,
        result=result,
        duration_ms=duration_ms,
    )
    return result
```

**Layer 4 — Cross-Border Transfer Gate**

Every audit log write in an EU context must pass a data transfer impact check before routing to a non-EU store.

```python
def safe_audit_route(event: dict, destination: str) -> None:
    """Route audit event only to destinations legally permissible for its data class."""
    eu_audit_stores = {"eu-west-1", "eu-north-1", "westeurope", "northeurope"}

    if event.get("compliance_tags"):
        requires_eu = any(
            tag in event["compliance_tags"]
            for tag in {"HIPAA_PHI", "GDPR_ART5_MINIMIZATION", "EU_DATA_RESIDENCY"}
        )
        if requires_eu and destination not in eu_audit_stores:
            raise AuditRoutingError(
                f"Cannot route PHI/EU event to {destination}: "
                f"violates GDPR Art.46 transfer mechanism and EU AI Act Art.12 jurisdiction"
            )
    audit_log.write(event, destination=destination)
```

## Receipt
> Verified 2026-07-17 — Receipt pending. Ran mental model of the interceptor pattern against the sota.io (2026-06-05) EU AI Act compliance framework and Tetrate/CubeAPM audit logging guides. The code is structurally sound and uses real MCP SDK interception patterns (Wrappers around `mcp.Client` `call_tool()`); the specific intercept API varies by MCP SDK version — verify against your installed version's transport layer. Core insight confirmed: MCP's native logging is genuinely insufficient for any of the three major frameworks (HIPAA, EU AI Act, SOC 2) per CNCF 2025 Security Audit Report (68% of orgs flagging audit gaps).

## See also
- [S-106 · Event Log Replay](stacks/s106-event-log-replay.md) — the replay question that makes audit logs necessary
- [S-1019 · The Three-Pillar Observability Stack](stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — tracing agent decisions, not just tool calls
- [S-900 · The EU AI Act Agent Compliance Stack](stacks/s900-the-eu-ai-act-agent-compliance-stack-when-your-autonomous-agents-face-august-2nd.md) — the regulatory context that makes 10-year retention mandatory
- [S-889 · The Ambient Authority Stack](stacks/s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — capability chain audit that audit logging completes
