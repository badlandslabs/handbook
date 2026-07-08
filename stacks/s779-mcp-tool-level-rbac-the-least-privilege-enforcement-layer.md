# S-779 · MCP Tool-Level RBAC: The Least-Privilege Enforcement Layer

An agent with access to your CRM, email, and cloud console will use all three if the task seems legitimate. Prompt-level restrictions get dropped during context compaction. The only correct answer is infrastructure-level enforcement: each agent gets a named, time-scoped, revokable allow-list of tools — enforced before the model sees the tool, before the server executes it, and logged after.

## Forces

- Default MCP grants every connected client access to every tool the server exposes — a single compromised agent can traverse your entire tool surface
- Agent behavior is probabilistic; permission enforcement must be deterministic — the server must say no regardless of what the model requests or what the prompt contains
- Tool-level permissions must account for context: the same `send_email` tool is legitimate for a support agent but dangerous for a code-review agent, and that distinction lives in session metadata, not in tool schemas
- High-privilege operations (write, delete, execute) need human approval gates — auto-deny with a review queue, not silent allow
- Audit trails must capture the full chain: which agent, which tool, which parameters, which principal authorized the call, and what came back

## The move

### Three enforcement points

MCP RBAC operates at three layers, not one:

**1. Discovery enforcement (server → client → model)**
When an agent connects, the gateway (or MCP server) advertises only the tools that the agent's permission scope allows. The model never sees disallowed tools — they don't appear in the tool list, so the model can't call them.

```python
# Bifrost-style virtual key: permissions enforced at discovery
from mcp_gateway import VirtualKey, ToolPermission

# Each agent gets a scoped key — not a shared API key
analytics_key = VirtualKey(
    consumer_id="agent:support-triage-v3",
    scopes=[
        ToolPermission("read_customer", read_only=True),
        ToolPermission("search_knowledge_base", read_only=True),
        ToolPermission("create_ticket", read_only=False),
    ],
    ttl_seconds=3600,
    parent_principal="user:support-team-lead",
)

# Server-side: filter tool list before sending to client
def filtered_tools_for(consumer: VirtualKey, all_tools: list[Tool]) -> list[Tool]:
    allowed_names = {s.tool_name for s in consumer.scopes}
    return [t for t in all_tools if t.name in allowed_names]
```

**2. Invocation enforcement (model → server)**
When the model calls a tool, the server re-checks the caller's permission before executing. Discovery filtering is advisory; invocation enforcement is the security boundary.

```python
# Server-side: enforce at invoke time (the real boundary)
def invoke_tool(consumer_id: str, tool_name: str, params: dict) -> ToolResult:
    permission = db.get_permission(consumer_id, tool_name)
    if not permission:
        raise PermissionDenied(
            f"Consumer {consumer_id} not authorized for {tool_name}"
        )
    if permission.read_only and _is_mutation(tool_name, params):
        raise PermissionDenied(f"Read-only scope cannot invoke {tool_name}")

    audit_log.write(
        event="tool_invoke",
        consumer=consumer_id,
        tool=tool_name,
        params_hash=sha256(json.dumps(params)),
        authorized_by=permission.parent_principal,
        timestamp=datetime.utcnow().isoformat(),
    )
    return _execute(tool_name, params)
```

**3. Approval workflow for high-risk tools**
Mutating operations (write, delete, send, execute) beyond a defined threshold require a human-in-the-loop approval before the tool call completes. The model receives a `pending_approval` response and waits.

```python
# High-risk tool approval flow
HIGH_RISK_TOOLS = {"send_email", "delete_record", "execute_shell", "deploy_service"}

@app.post("/mcp/approve")
async def request_approval(request: ApprovalRequest) -> ApprovalResponse:
    if request.tool not in HIGH_RISK_TOOLS:
        return ApprovalResponse(action="proceed")

    ticket = approval_ticket(
        tool=request.tool,
        params=request.params,
        requested_by=request.consumer_id,
        principal=request.parent_principal,
    )
    # Returns immediately — model gets pending status, waits for webhook
    return ApprovalResponse(action="pending", ticket_id=ticket.id, timeout_seconds=300)
```

### RBAC role model

Define roles, not individual permissions. Assign roles to agent identities.

| Role | Tools | Example Agent |
|------|-------|--------------|
| `readonly` | All tools, read-only flag enforced | Analytics, reporting |
| `operator` | Read + non-destructive write | Triage, routing |
| `deployer` | CI/CD tools, deployment审批 | Release automation |
| `admin` | Full access + approval queue | Incident response |

### Scope composition

Permissions must compose from the principal's identity downward:

```
Principal (human user) → Role → Agent Identity → Session → Scope
```

A support team lead's agent inherits the lead's identity. The agent's session gets the `operator` role. If the session scopes to a single customer ticket, the tool allow-list narrows further. Each layer is independently auditable.

## Receipt

> Verified 2026-07-07 — Researched Bifrost (Maxim AI) MCP RBAC architecture, systemshardening.com MCP permission patterns, cowork.ink least-privilege guide, and NIST AI RBAC standards. Code examples follow production patterns from Bifrost gateway and Cerbos PBAC enforcement models. Receipt pending — not run against live MCP server.

## See also

- [S-201 · MCP Server Security Hardening](stacks/s201-mcp-server-security-hardening.md) — protocol-level threat model
- [S-217 · Agent Capability Authorization](stacks/s217-agent-capability-authorization.md) — session-scoped trust delegation
- [S-321 · Dynamic Agent Capability Negotiation](stacks/s321-dynamic-agent-capability-negotiation.md) — runtime capability probing
- [S-535 · Agent Audit Trail Engineering](stacks/s535-agent-audit-trail-engineering-eu-ai-act-article-12.md) — logging requirements for EU AI Act compliance
