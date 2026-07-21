# S-1446 · The NHI Perimeter — When Your Agent Runs on a Shared API Key and You Can't Revoke It

An AI agent needs to read your customer database, query your CRM, and send emails. You give it a service account. Six months later, that account has permissions the agent never needed, is shared across four other agents, and you have no idea which agent touched which record at 3 AM. Revoking it would break three pipelines. Leaving it alone is the real risk. This is the NHI (Non-Human Identity) perimeter problem.

## Forces

- **Authentication ≠ identification.** Most agents authenticate (they have a valid token) but aren't identified (the token is shared, not per-agent). Every action logs as the same principal — you can't tell Agent A from Agent B, and you can't revoke one without breaking the other.
- **NHIs outnumber human identities 50:1.** In the average enterprise, non-human identities already vastly outnumber human ones — and AI agents are accelerating that ratio. Each agent, tool, and pipeline becomes a new identity that your security team can't see.
- **The MCP layer is a control plane, not a pipe.** Most MCP integrations pass requests through without enforcing permission boundaries. The agent presents a token; the MCP server doesn't ask whether this agent should be allowed to delete records, only whether the token is valid.
- **Scope creep is the default, not the exception.** An agent provisioned with "Reader" access for a demo gets upgraded over time as workflows expand. Nobody re-evaluates the role. The agent accumulates permissions it never needed, for tasks nobody planned.
- **Credential spaghetti is the production default.** Teams move fast. Multiple agents end up sharing service accounts because provisioning new ones takes time. By the time the security team audits, there are 47 MCP integrations on 12 service accounts and the org chart for those accounts looks like a bowl of spaghetti.

## The move

Treat every agent as a first-class principal with a lifecycle-managed identity, explicit role, tight permission scope, and a preconfigured tool manifest.

### 1. Unique identity per agent

```python
# ❌ Anti-pattern: shared credential
AGENT_TOKEN = "sk-service-account-all-agents-share"

# ✅ Each agent gets its own identity
agent_registry = {
    "customer-email-agent": {
        "identity": "nhi://corp/customer-email-agent/v2",
        "credentials": "aws-iam-role-arn/agent-customer-email",
        "provisioned_via": "SPIFFE/SPIRE",       # workload identity
        "deprovision_date": "2026-09-01",
        "owner": "growth-eng@corp.com",
    },
    "crm-read-agent": {
        "identity": "nhi://corp/crm-read-agent/v1",
        "credentials": "azure-managed-identity/crm-read-only",
        "provisioned_via": "Microsoft Entra Agent ID",
        "deprovision_date": None,  # no sunset — permanent scope
        "owner": "data-eng@corp.com",
    },
}
```

Use SPIFFE/SPIRE (for workload attestation), Microsoft Entra Agent ID (for Azure-native), or AWS IAM Roles Anywhere. The point is: every agent gets a cryptographic identity that can be independently audited, scoped, and revoked.

### 2. RBAC scope binding at tool level

```python
# Tool manifest: what this specific agent is ALLOWED to do
TOOL_MANIFEST = {
    "customer-email-agent": {
        "allowed_tools": [
            "sendgrid.send_email",      # restricted to transactional template
            "salesforce.read_contact",  # read-only, no write/delete
        ],
        "denied_resources": [
            "salesforce.delete",
            "crm.bulk_export",
            "db.delete_rows",
        ],
        "rate_limit": "100 req/hour",
        "require_approval_for": ["send_email"]  # human-in-loop gate
    },
}
```

The MCP gateway enforces the manifest. Before dispatching any tool call, the gateway checks: is this tool in `allowed_tools`? Is the resource in `denied_resources`? Is the rate limit respected? The agent never sees tools outside its manifest.

### 3. The MCP gateway as permission broker

```python
# MCP gateway: enforces tool-level RBAC before tool dispatch
from mcp_gateway import PermissionBroker

broker = PermissionBroker(agent_registry, tool_manifests)

async def dispatch_tool(agent_id: str, tool_name: str, args: dict) -> dict:
    decision = broker.evaluate(
        agent_id=agent_id,
        tool_name=tool_name,
        args=args,
        context={"session_id": get_session_id(), "purpose": "customer-onboarding"}
    )
    
    if decision.effect == "DENY":
        logger.warning(
            "BLOCKED agent=%s tool=%s reason=%s",
            agent_id, tool_name, decision.reason
        )
        return {"error": "tool_not_permitted", "reason": decision.reason}
    
    # Log with full identity context for audit
    audit_log.record(
        agent=agent_id,
        identity=agent_registry[agent_id]["identity"],
        tool=tool_name,
        args=args,
        decision=decision.effect,
        session=get_session_id(),
    )
    
    return await broker.forward(decision, args)
```

The gateway is the chokepoint. It knows who the agent is, what it's allowed to do, and logs with full identity context for post-incident RCA. This is where you catch scope creep — the agent asks for `db.delete_rows`, the gateway says no, the audit log records the attempt.

### 4. Lifecycle: provision → operate → revoke

```bash
# Provision: agent gets identity + scoped credentials at startup
hermes agent provision \
  --name customer-email-agent \
  --role customer-email \
  --tools sendgrid.send_email,salesforce.read_contact \
  --ttl 90d \
  --owner growth-eng@corp.com

# During operation: audit trail is identity-aware
# Every action = agent_id + identity URI + timestamp + tool + args

# Revoke: one agent, one command, no collateral
hermes agent revoke customer-email-agent --reason "replaced-by-v2"
# Entra/SPIFFE token is invalidated immediately
# MCP gateway rejects any new session for this identity
# Audit log frozen for compliance
```

Revocation must be surgical. You revoke Agent A without touching Agent B, C, or D. With shared credentials, you can't. This is why per-agent identity isn't optional — it's what makes revocation possible.

### 5. Defense-in-depth: layers of the NHI perimeter

| Layer | What it does | Failure mode it closes |
|-------|-------------|----------------------|
| Workload identity (SPIFFE/Entra) | Cryptographic proof of agent identity | Token theft / reuse |
| Tool manifest (MCP gateway) | Pre-approved tool allowlist | Scope creep / lateral movement |
| RBAC role binding | Role-per-tool permission matrix | Privilege accumulation |
| Rate limiting | Quotas per agent per tool | Unintended bulk operations |
| Audit log (identity-attributed) | Full trace of every tool call | Invisible drift / compromise |
| Deprovision SLA | Auto-expiry of temporary agent credentials | Forgotten agents still running |

## Receipt

> Verified 2026-07-21 — Researched from Microsoft Security Blog (Yesenia Yser & Toby Kohlenberg, July 16 2026), Supergood Solutions (March 16 2026), and Kubernetes SIG Apps agent-sandbox controller (kubernetes-sigs/agent-sandbox, Nov 2025). Microsoft Entra Agent ID provides managed NHI lifecycle with per-agent role binding and tool-level scope. Supergood confirms NHIs outnumber human identities 50:1 in average enterprise. The kubernetes-sigs/agent-sandbox controller introduces `Sandbox`, `SandboxProfile`, and `SandboxClaim` K8s resources for lifecycle management of agent workloads — the controller pattern applies to identity governance at scale.

## See also

- [S-1041 · The Agent Shadow IT Stack](s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — discovering agents your security team doesn't know exist
- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — deciding which tools to give an agent and with what permissions
- [S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — multi-agent role isolation
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance that doesn't rely on prompts
