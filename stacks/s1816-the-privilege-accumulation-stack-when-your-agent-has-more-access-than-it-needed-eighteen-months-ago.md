# S-1816 · The Privilege Accumulation Stack — When Your Agent Has More Access Than It Needed Eighteen Months Ago

Your "Quarterly Audit Agent" launched with read-only access to finance data. Eighteen months later it has admin credentials to three databases, write access to the audit log, and permission to call the payroll export endpoint — because every time a workflow needed something, someone added a permission. Nobody ever subtracted one. The agent has become the most over-provisioned identity in your infrastructure, and it runs unattended.

Agents accumulate permissions the same way humans do: incrementally, defensibly, and never revisited. Unlike human accounts, agents don't push back when over-provisioned, don't notice they're dangerous, and don't request a review when context changes. The least-privilege principle assumes a human who re-evaluates. Your agent doesn't.

## Forces

- **Agents run continuously; humans review periodically.** Privilege reviews happen quarterly or annually. Agent deployments change weekly. An agent that needed admin access for a two-day migration six months ago still has it today — because nobody remembers the migration, and the agent can't ask to be de-provisioned.
- **Aggregate privilege is invisible.** A team might grant "narrow" roles across five systems without realizing the combined effective access is broader than any individual system owner approved. Microsoft Entra Agent ID research (July 2026) found this to be the dominant over-provisioning pattern in enterprise deployments.
- **Tool multiplicity multiplies privilege surface.** An agent connected to 12 MCP servers, each with independent auth, faces combinatorial blast: 12 MCP servers × N tools × per-tool scopes = an effective permission surface nobody has fully mapped.
- **Agents act across systems faster than humans can review.** A human who gets a new permission makes one query per minute. An agent can exercise all its permissions in 30 seconds. Over-provisioned agents are disproportionately dangerous because the blast radius of a workflow bug or prompt injection is larger.

## The Move

**1. Treat agents as lifecycle-managed principals, not configurations.**

Assign every agent a managed identity with an explicit lifecycle: creation → active → review → deprecation. Agents that have been running longer than their review window without a re-certification are treated as expired credentials.

```python
# Agent lifecycle manifest (YAML config that travels with the agent)
agent_manifest = {
    "name": "quarterly-audit-agent",
    "identity": "managed-identity-id-xyz",
    "created_at": "2025-01-15",
    "last_reviewed_at": "2025-07-15",  # 6-month review window
    "permissions": [
        {"resource": "finance-db", "access": "read", "justification": "Q4 audit queries"},
        {"resource": "audit-log", "access": "write", "justification": "Append audit trail"},
        # No payroll-export: removed after migration completed
    ],
    "review_window_months": 6,
}
```

**2. Scope tools to preconfigured manifests, not full MCP server access.**

Don't give agents the full toolset of an MCP server. Build a tool manifest per agent that enumerates exactly which tools it may call, with which scopes, against which resources.

```python
from mcp import ToolPolicy

# A tool manifest for a data-export agent — not "full MCP server access"
tool_policy = ToolPolicy(
    allowed_tools=["salesforce.query", "salesforce.export_csv"],
    denied_tools=["salesforce.delete", "salesforce.bulk_update"],
    resource_filters={
        "salesforce.export_csv": {
            "max_rows": 10_000,
            "allowed_object_types": ["Opportunity", "Account"],
            "excluded_fields": ["SSN", "credit_card"],
        }
    },
)

# Before invoking the MCP client, validate the call against the manifest
def mcp_invoke_guarded(agent_id: str, tool: str, args: dict) -> dict:
    manifest = load_manifest(agent_id)
    policy = tool_policy_from_manifest(manifest)

    if not policy.allows(tool, args):
        log_authorization_denied(agent_id, tool, args)
        raise PermissionError(f"Tool {tool} not in {agent_id} manifest")

    # Tool is allowed — continue
    return mcp_client.invoke(tool, args)
```

**3. Implement just-in-time privilege escalation for one-off high-impact actions.**

For actions that need elevated access (delete operations, bulk exports, cross-tenant reads), don't grant permanent access — implement a just-in-time escalation that:
- Checks the action against the policy kernel (S-1458)
- Issues a short-lived token (TTL: 5–30 minutes)
- Logs the escalation event with the requesting workflow, actor identity, and justification
- Revokes automatically

```python
async def elevated_tool_call(tool: str, args: dict, justification: str):
    """Request just-in-time elevation for a specific high-impact action."""
    agent_id = get_current_agent_id()

    # Log the escalation request (audit trail for Article 12 compliance)
    await audit_log.append({
        "event": "privilege_escalation_request",
        "agent_id": agent_id,
        "tool": tool,
        "justification": justification,
        "timestamp": now(),
    })

    # Issue short-lived elevated token
    token = privilege_broker.request_elevated_access(
        principal=agent_id,
        scope=tool,
        ttl_minutes=15,
        workflow_id=get_current_workflow(),
    )

    try:
        return mcp_invoke_with_token(tool, args, token)
    finally:
        privilege_broker.revoke(token)
```

**4. Run periodic aggregate privilege analysis.**

Individual role grants look fine. The combination across 5 MCP servers and 3 database roles is a data exfiltration path. Run quarterly aggregate analysis:

- Map every tool the agent *can* call
- Trace the data each tool can reach end-to-end
- Flag combinations that create unintended cross-system access
- Produce a human-readable privilege report for security review

## Receipt

> Verified 2026-07-29 — Research from Microsoft Security Blog (July 16, 2026) on least-privilege agent identity and tool binding; OWASP Agentic AI Security cheat sheet on per-tool permission scoping; WorkOS MCP authorization patterns article (July 14, 2026) on least privilege enforcement; CSA NHI governance documentation on AI agent identity proliferation; Obsidian Security privilege drift case study. Tool manifest and JIT escalation patterns derived from published best practices. No real-world run for the code samples — run against your own MCP infrastructure.

## See also

- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool selection and scope
- [S-1458 · The Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy enforcement infrastructure
- [S-768 · When Prompts Become Shells](stacks/s768-when-prompts-become-shells-the-agent-framework-rce-paradigm.md) — framework RCE and privilege escalation via prompt injection
