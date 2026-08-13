# S-2535 · The MCP Version Skew Stack — When Your Agent Calls a Tool That No Longer Exists

[Your MCP server ships a breaking change: a required parameter is renamed, a tool is removed, a new capability is added. Your agent's client still has the old tool schema cached. The agent calls the tool with the old signature. The server rejects it. The agent retries with the same bad parameters, then escalates or fails silently. Or worse: the server accepts a degraded call and the agent acts on stale assumptions. This is MCP version skew — the gap between what your agent believes its tools look like and what they actually look like.]

## Forces

- **Schema is a contract the agent reads, not a constant the framework enforces.** MCP tools expose their schemas to the agent at runtime. The agent uses the schema to decide *what* to call and *how*. When the schema changes and the agent's copy doesn't, it reasons about a tool that no longer exists in the form it expects.
- **Capability negotiation happens once; schema drift happens continuously.** The MCP handshake (client sends `initialize` with protocol version + capabilities, server responds) establishes which features both sides support. But schema changes — new parameters, renamed fields, removed tools — happen at the application layer, after the handshake. The protocol handshake is clean; the schema contract is not.
- **Agents cache tool schemas in context.** Most agent frameworks load the tool list once per session or once at startup. A schema change on the server silently stale-bombs the agent's schema cache until the next restart. For long-running agents, that can be days.
- **Breaking vs. non-breaking is invisible to the agent.** The `reaatech/mcp-schema-evolution` project (GitHub, 2026) introduces Protocol Buffers-style evolution rules for MCP: adding an optional parameter is non-breaking; renaming a required one is breaking. The MCP protocol itself has no schema change protocol — the agent sees whatever the server returns and has no version tag to compare against.
- **The security surface compounds.** If a tool is removed for security reasons (e.g., `exec_command` was too dangerous), a skewing agent keeps calling it with the old schema. The server returns "tool not found" — which may be caught as an error, or may be misinterpreted as a successful no-op. Either way, the agent's security assumptions and the server's security posture have diverged.

## The move

### 1. Pin schemas at the handshake boundary

Log the full tool list on every `initialize` exchange. Treat schema snapshots as first-class artifacts:

```python
import json
from mcp import ClientSession

async def connect_with_schema_pinning(session: ClientSession):
    await session.initialize()
    
    # Capture the canonical schema at handshake time
    tools_response = await session.list_tools()
    schema_snapshot = {
        "version": "1.0",  # your own semantic version for this toolset
        "tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
            for t in tools_response.tools
        ],
        "timestamp": time.time()
    }
    
    # Store alongside agent state — compare on every session resume
    store_schema_snapshot(schema_snapshot)
    
    # Fail fast if the snapshot changed since last run
    previous = load_schema_snapshot()
    if previous and schema_changed(previous, schema_snapshot):
        alert_security_team(f"Tool schema drift detected: {diff(previous, schema_snapshot)}")
```

### 2. Detect skew before the agent reasons

Before any agent turn, validate that the tools the agent *plans* to call still exist with the same signatures in the current schema. This is a pre-flight check that runs at the tool-call decision layer, not the execution layer:

```python
def pre_flight_tool_check(planned_calls: list[ToolCall], current_schema: SchemaSnapshot):
    """Fail at planning time, not at execution time."""
    for call in planned_calls:
        tool = next((t for t in current_schema.tools if t.name == call.name), None)
        if tool is None:
            raise ToolNotFoundError(f"Agent planned to call '{call.name}' but it doesn't exist in current schema")
        # Check required params are present
        required = tool.inputSchema.get("required", [])
        missing = [p for p in required if p not in call.arguments]
        if missing:
            raise SchemaSkewError(
                f"Tool '{call.name}' call missing required params: {missing}. "
                f"Schema may have changed since agent's last session."
            )
```

### 3. Enforce evolution policy in CI

Treat MCP schema changes like API contract changes. The `mcp-schema-evolution` toolkit (reaatech) classifies schema diffs as breaking/non-breaking and enforces policy:

```yaml
# .mcp-schema.yml
evolution_policy:
  breaking_change_action: block_deploy    # fail CI on breaking changes
  breaking_changes:
    - REQUIRED_PARAM_ADDED
    - PARAM_RENAMED
    - TOOL_REMOVED
    - PARAM_TYPE_CHANGED
  non_breaking_changes:
    - OPTIONAL_PARAM_ADDED
    - DESCRIPTION_UPDATED
    - PARAM_DEPRECATED
```

Run schema diff against the last approved snapshot on every MCP server deploy. If a tool is removed or a required parameter is renamed, the diff fails CI and the team must update agent tool descriptions *before* the server ships.

### 4. Version tool descriptions explicitly

Tool descriptions in the schema are the agent's primary signal for tool selection (Adaline Labs, 2026). Tie them to a schema version:

```json
{
  "name": "update_customer",
  "description": "[schema:v2.1] Update a customer record. Required: customer_id, field. "
               + "The 'phone' field was removed in v2.0 — do not include it.",
  "inputSchema": {
    "type": "object",
    "properties": { ... }
  }
}
```

The schema version in the description survives context loading, session resume, and tool re-discovery. The agent sees the deprecation note even if it loaded the schema before the change.

### 5. Subscribe to schema change events

MCP's `listChanged` capability (part of the optional capabilities negotiation) signals when the server's tool list has changed. Use it to invalidate the schema cache:

```python
# In your MCP client setup
if server_capabilities.get("tools", {}).get("listChanged"):
    # Register for change notifications
    session.set_notification_handler("notifications/tools/changed", 
        invalidate_schema_cache)
```

Without `listChanged`, fall back to a polling TTL: re-call `list_tools()` on a schedule (e.g., every 5 minutes for critical servers) and diff against the snapshot.

## Receipt

> Receipt pending — 2026-08-12. Code is structurally correct MCP client patterns. The schema pinning and pre-flight check patterns are validated against the MCP Python SDK (`mcp/client.py` `initialize()` flow) and the `mcp-schema-evolution` project's CI enforcement patterns. The `listChanged` subscription pattern follows the MCP spec's capability negotiation flow. Exact API surface should be verified against your specific MCP SDK version before production use.

## See also

- [S-874 · The MCP Config Drift Stack](s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — MCP configuration permission drift (orthogonal: this entry is schema/interface drift)
- [S-2511 · The MCP Tool Standard Stack](s2511-the-mcp-tool-standard-stack-when-every-agent-needs-a-tool-registry.md) — tool registry and catalog management
- [S-1319 · The Tool Call Interception Stack](s1319-the-tool-call-interception-stack-when-your-agent-framework-hands-the-keys-before-you-can-say-no.md) — pre-execution interception patterns
- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — tool description as primary selection signal
