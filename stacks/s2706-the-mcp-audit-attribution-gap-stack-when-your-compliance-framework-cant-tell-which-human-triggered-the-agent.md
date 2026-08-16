# [S-2706] · The MCP Audit Attribution Gap

When your agent traces a tool call to a service account but your compliance auditor needs the human who initiated it — and neither the protocol nor your gateway can bridge that gap.

## Situation

You're in a SOC 2 audit. An MCP tool called `write_to_customer_db` at 03:17 UTC. The audit log shows the call came from `agent-prod-service@company.com`. But the real question — *which employee triggered this?* — has no answer in the log. The agent ran under a shared service account. The human who asked the question is invisible.

This is the MCP Audit Attribution Gap. The protocol makes no provision for threading human identity through tool execution. Every standard solution — gateways, STDIO proxies, service accounts — drops the chain somewhere.

## Forces

- **Compliance requires it**: SOC 2 CC6.1, HIPAA §164.312(b), GDPR Art. 5(2) all demand that actions be attributable to a natural person, not a service account
- **MCP's design drops it**: The JSON-RPC 2.0 stateless architecture carries no concept of originating identity; sessions are transient and debugging logs are optional
- **Agents need shared credentials**: A single agent acting on behalf of many users can't hold per-user credentials — it operates as the agent identity, not the human behind it
- **Gateways miss STDIO**: Local MCP server executions over STDIO bypass HTTP gateways entirely — no intercept, no trace, no attribution
- **Remediation fragments observability**: Every team solves this differently, creating inconsistent audit coverage across the same fleet

## The Move

### 1. Establish the attribution invariant before the session starts

Before the agent receives its first tool, the orchestration layer injects an **identity context object** into the agent's system prompt and attaches it as a signed header to every MCP request. This is not a credential — it's a binding receipt.

```json
{
  "attribution-context": {
    "human_id": "user:jsmith@company.com",
    "session_id": "sess_01J9K",
    "permissions_scope": ["read:customer", "write:customer"],
    "issued_at": "2026-08-15T09:00:00Z",
    "expires_at": "2026-08-15T10:00:00Z",
    "signed_by": "identity-provider.company.com",
    "signature": "eyJhbGc..."
  }
}
```

The MCP server validates the signature on every inbound request and logs the `human_id` from the payload — not from the transport layer. This works for both HTTP transport and STDIO, because the binding travels in the payload, not the channel.

### 2. Wrap MCP servers with an attribution proxy

For every MCP server in production, insert a thin proxy that extracts the attribution context, appends it to the server's own audit log, and rejects requests with missing or expired signatures:

```python
class AttributionProxy:
    def handle_request(self, method: str, params: dict, context: dict) -> Any:
        sig = context.get("attribution_signature")
        if not sig or not self.validate(sig):
            raise PermissionError("Attribution context missing or invalid")

        human_id = self.decode(sig)["human_id"]
        self.audit_log.append({
            "timestamp": utcnow(),
            "human_id": human_id,
            "method": method,
            "params_hash": sha256(json.dumps(params, sort_keys=True)),
            "server": self.server_name,
            "session_id": context.get("session_id"),
        })
        return self.server.handle(method, params)
```

This proxy is the single enforcement point. Every tool execution gets one audit entry with the human ID attached. No exceptions — the proxy rejects calls that lack valid attribution.

### 3. Tag traces with human identity at the orchestration layer

At the agent orchestrator level, the span representing each agent turn is tagged with the human identity:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def run_agent(human_id: str, prompt: str):
    with tracer.start_as_current_span("agent_turn") as span:
        span.set_attribute("human.initiator", human_id)
        span.set_attribute("human.team", get_team(human_id))
        span.set_attribute("human.permissions_scope", get_scope(human_id))
        result = agent.run(prompt)
        span.set_attribute("agent.action_count", len(result.tool_calls))
        return result
```

This connects every downstream MCP call to the originating human in the distributed trace, regardless of how many agents or tools the request passes through.

### 4. Build a compliance-grade audit log as an append-only ledger

The audit log is not the MCP debug log. It's a dedicated append-only store with three properties the protocol-level log lacks:

| Property | Implementation |
|----------|---------------|
| **Immutability** | Write-once storage (S3 Object Lock or equivalent) with SHA-256 chain linking between entries |
| **Identity completeness** | Every entry must contain `human_id`, `session_id`, `method`, `params_hash`, `server`, `timestamp`, `signature` |
| **Retention** | Configurable per framework: 7 years for HIPAA, 1 year for SOC 2, 6 years for GDPR |

```python
class ComplianceAuditLog:
    def append(self, entry: dict):
        entry["entry_hash"] = sha256(json.dumps(entry, sort_keys=True))
        entry["prev_hash"] = self.last_hash
        self.store.append(entry)
        self.last_hash = entry["entry_hash"]
```

### 5. Map to compliance requirements explicitly

| Compliance requirement | What you need | Where the gap was |
|------------------------|---------------|-------------------|
| SOC 2 CC6.1 — access attribution | Human ID in every tool call log | MCP has no field for this |
| HIPAA §164.312(b) — access verification | Immutable log with who did what | MCP debug logs are ephemeral |
| GDPR Art. 5(2) — accountability | Human-to-action binding | Service account hides the person |
| SOC 2 CC7.2 — anomaly detection | Human-scoped baselines | Agent actions attributed to agent only |

## Receipt
> Verified 2026-08-15 — Research synthesis from authzed.com (MCP audit attribution blind spots), cubeapm.com (68% of orgs cite audit logging gaps as critical — CNCF 2025 Security Audit Report), rafter.so (MCP treats logging as optional debugging utility), CSA (cloud service agent identity attribution failures), aviatrix.ai (shared service account privilege escalation via AI agents). Primary sources: authzed.com/learn/auditing-logging-mcp-server-activity-compliance, cubeapm.com/blog/mcp-server-security-monitoring-audit-logs-compliance, labs.cloudsecurityalliance.org/research/csa-research-note-ai-agent-cloud-privilege-escalation-202604, aviatrix.ai/threat-research-center/ai-agent-privilege-escalation-enterprise-2026.

The attribution gap is structural, not incidental. MCP's specification treats logging as an optional debugging concern. The JSON-RPC 2.0 stateless layer carries no identity context. Gateways can intercept HTTP traffic but miss STDIO entirely. The fix requires: (1) a signed identity context injected before session start, (2) an attribution proxy on every MCP server, (3) OpenTelemetry spans tagged at the orchestration layer, and (4) an append-only compliance ledger. No single point solution closes this — it requires the full stack.

## See also
- [S-889 · MCP Ambient Authority: Capability Bucketing Against Session-Scoped Token Chains](s889-the-mcp-ambient-authority-stack-capability-bucketing-against-session-scoped-token-chains-and-the-confused-deputy-problem.md) — the token chain that enables confused-deputy attacks on MCP; attribution gap is what makes these escalations invisible
- [S-444 · The 97/12 Gap: Agent Governance Discovery](s444-the-97-12-gap-agent-governance-discovery-the-surprising-survey-where-nobody-knew-what-their-agents-could-do.md) — enterprise governance discovery; attribution is the missing link between governance policy and individual accountability
- [S-635 · Silent Failure Detection in Agentic Loops](s635-the-silent-failure-detection-stack-when-your-agent-succeeds-but-does-nothing.md) — silent failure taxonomy; attribution gap makes silent failures untraceable to the human who commissioned them
