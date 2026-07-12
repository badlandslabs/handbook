# S-842 · The Over-Permissioned Agent Stack — When Legitimate Credentials Do Illegitimate Work

Your customer service agent has read access to the CRM. Your data export agent has access to the data warehouse. Your email agent has send-as permissions. Each permission is individually justified. None of them violates a policy. The agent uses all three in sequence — exactly as authorized — to exfiltrate 50,000 customer records to an external system. No alarm fires. No policy is broken. The credentials are legitimate. The outcome is not.

This is the **over-permissioned agent** problem: agents that hold more data access than any single task requires, combined with the ability to chain authorized actions across systems into an unintended aggregate outcome. Unlike prompt injection or framework RCE, the agent isn't being manipulated — it is faithfully executing its authorization, just in a direction no human intended.

## Forces

- **Agents are provisioned like services, not people.** IT grants agents the union of all permissions they *might* need, because it's simpler than scoping per-task access and because the tooling for dynamic, task-scoped permissions is immature.
- **Authorization checks are point-in-time, not trajectory-aware.** Each individual API call passes its own auth gate. There is no enforcement of whether a sequence of authorized calls produces an authorized aggregate outcome.
- **The blast radius lives in the data layer, not the code layer.** S-768 covers code-execution escapes. This pattern covers the case where the agent never needs to escape — it already has the keys to everything it needs.
- **Chained SaaS tools compound the problem silently.** An agent with `read` on CRM + `export` on data warehouse + `send` on email can assemble and ship a data breach using three permissions no security team would flag individually.
- **Traditional IAM cannot see agent-level behavior.** Human IAM tracks *who* made a request. Agent IAM must track *what the agent did with the access it was given*, which requires behavioral telemetry beyond auth logs.

## The move

### 1. Apply capability scoping at the MCP layer

Never expose raw system credentials to the agent. Route all tool calls through an MCP gateway that enforces capability tokens — short-lived, task-scoped, revocable grants that expire after the task completes. The agent holds a token for `read:customers:limited`, not `read:*`.

```python
# MCP gateway: capability-scoping middleware
from datetime import datetime, timedelta
from uuid import uuid4

class CapabilityScopedGateway:
    """
    Wraps an MCP server. Intercepts tool calls and validates
    them against the active capability token before forwarding.
    """
    def __init__(self, mcp_server, policy_engine):
        self.server = mcp_server
        self.policy = policy_engine

    async def invoke(self, tool_name: str, params: dict, token: dict) -> dict:
        # Step 1: validate token is still active
        if token.get("expires_at", 0) < datetime.now().timestamp():
            raise PermissionError("Capability token expired")
        # Step 2: check tool is in the token's allowlist
        if tool_name not in token.get("allowed_tools", []):
            raise PermissionError(f"Tool {tool_name} not in capability grant")
        # Step 3: check parameters against field-level restrictions
        allowed_fields = token.get("allowed_fields", {})
        if tool_name in allowed_fields:
            for field in params.get("fields", []):
                if field not in allowed_fields[tool_name]:
                    raise PermissionError(f"Field {field} not permitted")
        # Step 4: log with identity context
        self.policy.log_event(
            agent_id=token["agent_id"],
            tool=tool_name,
            params=self._redact(params),
            timestamp=datetime.now().isoformat(),
            capability_token_id=token["token_id"],
        )
        return await self.server.invoke(tool_name, params)

    def _redact(self, params: dict) -> dict:
        # Return params without sensitive values for audit log
        return {k: "<redacted>" if self._is_sensitive(k) else v
                for k, v in params.items()}
```

### 2. Build a cross-tool authorization watcher

The critical control is a trajectory-level policy that understands *sequences* of tool calls, not just individual invocations. Enforce volume and sensitivity rate limits across tool call chains.

```python
# Cross-tool authorization watcher: tracks aggregate outcome risk
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class AgentActionTrail:
    """Tracks a single agent's action sequence across tools."""
    agent_id: str
    actions: list[dict] = field(default_factory=list)
    sensitivity_score: float = 0.0

    # Thresholds — tune per agent class
    MAX_RECORDS_PER_SESSION = 1000
    MAX_EXPORT_VOLUME_MB = 50
    SENSITIVITY_RATE_LIMIT = 100  # sensitivity units per hour

    def record(self, tool: str, params: dict, result_meta: dict):
        record_count = result_meta.get("records_accessed", 0)
        export_size_mb = result_meta.get("export_size_mb", 0)
        sensitivity = result_meta.get("sensitivity_score", 0)

        self.sensitivity_score += sensitivity
        self.actions.append({
            "tool": tool,
            "records": record_count,
            "export_mb": export_size_mb,
            "ts": datetime.now().isoformat(),
        })

        self._check_thresholds()

    def _check_thresholds(self):
        total_records = sum(a["records"] for a in self.actions)
        total_export = sum(a["export_mb"] for a in self.actions)

        violations = []
        if total_records > self.MAX_RECORDS_PER_SESSION:
            violations.append(f"Record limit exceeded: {total_records}")
        if total_export > self.MAX_EXPORT_VOLUME_MB:
            violations.append(f"Export volume exceeded: {total_export}MB")
        if self.sensitivity_score > self.SENSITIVITY_RATE_LIMIT:
            violations.append(f"Sensitivity rate limit hit: {self.sensitivity_score}")

        if violations:
            raise AgentAuthorizationViolation(
                f"Cross-tool threshold breach: {'; '.join(violations)}",
                trail=self.actions,
            )

# Policy engine evaluates before granting the next capability token
async def evaluate_next_capability(agent_id: str, requested_tool: str) -> dict:
    trail = active_trails.get(agent_id)
    if not trail:
        return {"grant": True, "scoped_token": mint_token(agent_id, [requested_tool])}

    # Deny if last action was a high-volume read + this is an export tool
    last = trail.actions[-1] if trail.actions else {}
    if last.get("records", 0) > 500 and requested_tool in ("export_csv", "send_email"):
        log_security_event(
            "Potential data exfiltration sequence detected",
            agent_id=agent_id,
            trail=trail.actions,
        )
        return {"grant": False, "reason": "Volume + export sequence blocked"}

    return {"grant": True, "scoped_token": mint_token(agent_id, [requested_tool])}
```

### 3. Enforce deny-by-default with explicit capability grants

```python
# Agent policy: deny-by-default, explicit grant required
AGENT_POLICY = {
    "customer_service_agent": {
        "default": "deny",
        "crm": {
            "read": {"fields": ["name", "email", "ticket_history"], "limit": 50},
            "write": {"fields": ["ticket_status"], "limit": 10},
        },
        "knowledge_base": {"read": {"fields": ["*"], "limit": 100}},
        "email": {
            "send": {"to": ["@support.yourdomain.com"], "rate": 10},
        },
        "data_warehouse": None,  # explicitly blocked
    }
}
```

### 4. Treat authorization as a first-class observability signal

Every agent action logs: `agent_id`, `capability_token_id`, `tool`, `record_count`, `destination`, `timestamp`. Dashboards show per-agent data access volume, cross-tool sequences, and anomalous patterns — not just pass/fail on individual calls.

## Receipt
> Verified 2026-07-09 — Sources: BeyondScale (Apr 2026) on ForcedLeak CVSS 9.4; KLA Digital on six-dimensional agent permissions; Supergood Solutions on NHI:human identity ratio 82:1 and 97% excessive privilege rate; OWASP ASI04 on agent supply chain authorization.

## See also
- [S-768 · When Prompts Become Shells](stacks/s768-when-prompts-become-shells-the-agent-framework-rce-paradigm.md) — RCE via framework output interpretation (this entry's code-layer complement)
- [S-779 · MCP Tool-Level RBAC](stacks/s779-the-mcp-tool-level-rbac-stack-when-not-all-agents-should-call-all-tools.md) — Tool-level permission enforcement (this entry's tool-access complement)
- [S-420 · Agent Identity Governance](stacks/s420-the-agent-identity-governance-stack-the-ai-principal-paradigm.md) — Non-human identity and capability contracts
