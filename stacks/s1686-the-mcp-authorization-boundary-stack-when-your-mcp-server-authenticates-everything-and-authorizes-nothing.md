# S-1686 · The MCP Authorization Boundary Stack — When Your MCP Server Authenticates Everything and Authorizes Nothing

Your MCP server is running OAuth 2.0. Every client presents a valid token. You've solved authentication — and then a prompt injection in an email routes a verified token to your `delete-database` tool, and your production schema is gone in 90 seconds. Authentication proves who is calling. Authorization decides what they are allowed to do. Most MCP deployments solve Gate 1 and skip Gate 2 entirely. This is the authorization boundary gap.

## Forces

- **Authentication is binary; authorization is granular.** OAuth 2.0 gives you a yes/no answer — is this token valid? It tells you nothing about which tools the presenting agent should be permitted to call, under what conditions, with what parameter constraints.
- **Every tool in the tool manifest is accessible by default.** MCP servers publish their available tools to any authenticated client. Without explicit deny-lists or capability-scope enforcement, a verified agent can invoke any listed tool — including destructive ones — simply by naming it in a tool call.
- **The threat model shifted without the architecture following.** Early MCP demos ran locally, single-user, no adversarial input. Production deployments run multi-tenant, internet-facing, with LLM-generated tool calls that can be manipulated by prompt injection. The auth layer was retrofitted; the authorization layer wasn't.
- **Per-call credential scoping is the hard part.** Gates 1 and 2 must operate at different granularities — session-level authentication, per-call authorization — and the protocol doesn't wire them together by default.

## The move

**The two-gate architecture:** Gate 1 (authentication) answers "who is this agent?" Gate 2 (authorization) answers "given who this is and what it is trying to do, is this permitted right now?" Gate 2 is where the actual security lives.

### Gate 1 — Authentication (assumed present)

- OAuth 2.0 bearer tokens or mTLS client certificates on the MCP transport layer
- Token validation at the MCP server entry point, not inside individual tool handlers
- Support for token introspection (revocation, scope, expiry) on long-running sessions
- Reject connections with expired or unrecognizable tokens before tool dispatch

### Gate 2 — Authorization (the missing layer)

```
Tool access policy engine
├── Capability manifest: which tools this agent class is allowed to call
├── Parameter constraints: schema-level limits on tool call arguments
├── Temporal gates: time-of-day, session-age, task-phase restrictions
└── Audit log: every tool invocation decision (allow or deny), timestamped
```

Implement Gate 2 as a policy decision point (PDP) that intercepts every tool call before dispatch:

```python
# MCP Authorization Middleware (Gate 2)
# Sits between tool dispatch and execution

import json
import time
from dataclasses import dataclass
from enum import Enum

class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    DENY_WITH_ESCALATION = "deny_escalate"

@dataclass
class AuthzRequest:
    agent_id: str
    agent_class: str           # e.g. "data-ingestion", "customer-facing"
    tool_name: str
    tool_args: dict
    session_age_seconds: float
    task_phase: str            # "planning", "execution", "review"
    token_scope: list[str]

@dataclass
class AuthzResponse:
    decision: Decision
    reason: str
    policy_id: str             # which rule fired
    audit_id: str

# Deny-list: tools this agent class can NEVER call
DENY_LIST = {
    "data-ingestion": {"delete-database", "drop-table", "truncate"},
    "customer-facing": {"exec", "system-command", "admin-panel"},
}

# Per-agent-class tool allow-lists (preferred over deny-lists)
ALLOW_LIST = {
    "data-ingestion": {
        "read-query", "write-row", "list-tables", "describe-schema",
        "read-file", "write-file", "http-request",
    },
    "customer-facing": {
        "read-kb", "summarize", "translate", "format-output",
    },
}

# High-risk tools: require task_phase == "review" or explicit escalation token
HIGH_RISK = {"delete-database", "exec", "drop-table", "truncate", "send-email"}

def authorize(req: AuthzRequest) -> AuthzResponse:
    audit_id = f"audit-{req.agent_id}-{int(time.time() * 1000)}"

    # 1. Deny-list check (override any allow-list)
    if req.tool_name in DENY_LIST.get(req.agent_class, set()):
        return AuthzResponse(
            decision=Decision.DENY,
            reason=f"Tool '{req.tool_name}' is deny-listed for class '{req.agent_class}'",
            policy_id="deny-list",
            audit_id=audit_id,
        )

    # 2. Allow-list check (if defined for this class)
    if req.agent_class in ALLOW_LIST:
        if req.tool_name not in ALLOW_LIST[req.agent_class]:
            return AuthzResponse(
                decision=Decision.DENY,
                reason=f"Tool '{req.tool_name}' not in allow-list for '{req.agent_class}'",
                policy_id="allow-list",
                audit_id=audit_id,
            )

    # 3. High-risk tool: require review phase or escalation token
    if req.tool_name in HIGH_RISK:
        if req.task_phase != "review" and "escalation-token" not in req.token_scope:
            return AuthzResponse(
                decision=Decision.DENY_WITH_ESCALATION,
                reason=f"High-risk tool '{req.tool_name}' requires task_phase=review or escalation-token",
                policy_id="high-risk-gate",
                audit_id=audit_id,
            )

    # 4. Parameter constraints (example: max rows affected)
    max_rows = {"write-row": 1000, "bulk-import": 10000}
    if req.tool_name in max_rows:
        requested_rows = req.tool_args.get("row_count", 0)
        if requested_rows > max_rows[req.tool_name]:
            return AuthzResponse(
                decision=Decision.DENY,
                reason=f"Row count {requested_rows} exceeds limit {max_rows[req.tool_name]}",
                policy_id="param-constraint",
                audit_id=audit_id,
            )

    # 5. Session age guard: deny destructive tools after 2h of inactivity
    if req.tool_name in HIGH_RISK and req.session_age_seconds > 7200:
        return AuthzResponse(
            decision=Decision.DENY,
            reason="Session too old for high-risk tool; re-authenticate",
            policy_id="session-age",
            audit_id=audit_id,
        )

    return AuthzResponse(
        decision=Decision.ALLOW,
        reason="All policy checks passed",
        policy_id="default-allow",
        audit_id=audit_id,
    )

# MCP tool handler wrapping
def mcp_tool_handler(agent_id: str, agent_class: str, tool_name: str,
                      tool_args: dict, session_age: float, task_phase: str,
                      token_scope: list[str], tool_fn):
    req = AuthzRequest(
        agent_id=agent_id,
        agent_class=agent_class,
        tool_name=tool_name,
        tool_args=tool_args,
        session_age_seconds=session_age,
        task_phase=task_phase,
        token_scope=token_scope,
    )
    resp = authorize(req)

    # Audit: always log, regardless of decision
    log_authz_decision(audit_id=resp.audit_id, request=req, response=resp)

    if resp.decision == Decision.DENY:
        raise PermissionError(f"MCP authorization denied: {resp.reason} [policy={resp.policy_id}]")
    elif resp.decision == Decision.DENY_WITH_ESCALATION:
        raise PermissionError(
            f"MCP escalation required: {resp.reason} [policy={resp.policy_id}]. "
            "Submit to human approval queue."
        )

    # Allow: proceed to tool execution
    return tool_fn(**tool_args)
```

### Key design decisions

- **Allow-lists over deny-lists by default.** Start with the minimum set of tools each agent class needs. Deny-lists only work when the threat surface is well-understood; allow-lists fail-safe.
- **Parameter-level constraints, not just tool-level.** A `write-row` tool that can write 1M rows is as dangerous as `delete-database`. Gate 2 must inspect arguments, not just names.
- **Audit before execution, not after.** Every deny must be logged with the policy that fired — this is your forensic trail for incident reconstruction and policy tuning.
- **Escalation path for high-risk tools.** `DENY_WITH_ESCALATION` routes to a human approval queue rather than hard-blocking. This prevents security from blocking legitimate work while still catching dangerous calls.
- **Policy-as-code (OPA/Cedar):** For complex deployments, express Gate 2 rules in OPA Rego or Cedar policy language. Version-control your policies, review them in pull requests, and deploy them as part of your CI/CD pipeline.

## Receipt

> Verified 2026-07-26 — Auth/authz gap confirmed: Knostic 2025 scan found 1,862 MCP servers with zero authentication. AgentMarketCap Feb 2026 follow-up: 41% of tracked servers still had no auth (214/523). OX Security: 7,374 publicly vulnerable MCP servers. Practical DevSecOps (May 2026): confirms the two-gate architecture with OAuth 2.0 (Gate 1) + per-tool capability scoping (Gate 2) as the production standard. CVE-2026-33032: 2,689 vulnerable nginx-UI MCP instances. Code reflects the two-gate model and PDP pattern from these sources.

## See also

- [S-743 · Ambient Authority: Capability Bucketing](s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — capability scoping at the schema level
- [S-1652 · The Least Agency Stack](stacks/s1652-the-least-agency-stack-when-your-agent-doesnt-need-to-be-a-superuser.md) — principle of minimum privilege across the agent stack
- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP protocol security at the transport layer
- [S-1659 · The Instruction Privilege Stack](stacks/s1659-the-instruction-privilege-stack-when-your-agent-treats-a-prompt-injection-as-authoritative.md) — defending authenticated agents against injected instructions
