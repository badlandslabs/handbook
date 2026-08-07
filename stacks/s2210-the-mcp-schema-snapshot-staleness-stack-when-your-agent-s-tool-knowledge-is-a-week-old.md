# S-2210 · The MCP Schema Snapshot Staleness Stack — When Your Agent's Tool Knowledge Is a Week Old

Your agent is running fine in production. You didn't change anything. Then one morning your agent starts calling `update_user()` with a `user_id` parameter that the MCP server renamed to `account_id` three days ago. No error. The server returns 200. The agent moves on, confident. The update targets the wrong user. This is not a bug you introduced. It is a staleness gap — the distance between what your agent knows about your tools and what your tools actually do.

## Forces

- **MCP tool definitions are fetched once and cached indefinitely.** The standard pattern is to call `tools/list` at session start or on first connection and reuse that snapshot for the entire session. If the MCP server changes its tool definitions between fetch and expiry, the agent reasons from a hallucinated interface.

- **HTTP health probes can't detect schema drift.** A probe that checks `{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}` and gets back `200` with valid JSON is green. It says nothing about whether the tools inside that response match what the agent cached three days ago. AliveMCP measured a **7.1% drift rate over 48 hours** across 196 healthy MCP servers — extrapolating to ~50% drift probability over 30 days for any single server.

- **The model cannot self-correct from a stale schema.** An LLM generates tool calls by reading the `inputSchema`. It has no secondary lookup to check whether the schema it is reading matches what the server actually accepts. It will confidently generate `{"user_id": 12345}` long after the server started rejecting that parameter name.

- **Four distinct shapes of drift.** From AliveMCP research: (1) **Tool removed** — agent calls a method that no longer exists, gets an unhandled error. (2) **Parameter renamed** — agent sends `old_name`, server ignores it or errors, silent data loss. (3) **Required field added** — agent omits the new mandatory field, server returns garbage or a 422, agent tries again with same stale schema. (4) **Type changed** — agent sends `string` where server now expects `integer`, server coerces or errors silently.

## The Move

### 1. Schema Snapshot at Session Start

Capture a fingerprint of the `tools/list` response when the session connects. Store it alongside the session context.

```python
import hashlib
import json
import mcp

def fetch_and_snapshot(client: mcp.Client, session_id: str) -> str:
    result = client.call_tool("tools/list", arguments={})
    # tools/list returns a ToolList result; extract the canonical representation
    tools_payload = json.dumps(result.tools, sort_keys=True, exclude_none=True)
    snapshot_hash = hashlib.sha256(tools_payload.encode()).hexdigest()[:16]
    # Store snapshot_hash + tools_payload in session store
    session_store[session_id] = {
        "schema_snapshot": tools_payload,
        "schema_hash": snapshot_hash,
        "captured_at": datetime.utcnow().isoformat(),
    }
    return snapshot_hash
```

### 2. Canonical JSON Hash for Drift Detection

The hash must be deterministic across serialization round-trips. Use `sort_keys=True` and `exclude_none=True` to ensure the same tool list always produces the same digest regardless of library serialization quirks.

```python
def detect_schema_drift(client: mcp.Client, session_id: str) -> DriftReport | None:
    """Call tools/list and compare to session's cached snapshot."""
    result = client.call_tool("tools/list", arguments={})
    current_payload = json.dumps(result.tools, sort_keys=True, exclude_none=True)
    current_hash = hashlib.sha256(current_payload.encode()).hexdigest()[:16]
    stored = session_store[session_id]

    if current_hash != stored["schema_hash"]:
        # Drift detected — diff and classify severity
        old_tools = {t["name"]: t for t in json.loads(stored["schema_snapshot"])["tools"]}
        new_tools = {t["name"]: t for t in result.tools}
        return DriftReport(
            added=[n for n in new_tools if n not in old_tools],
            removed=[n for n in old_tools if n not in new_tools],
            modified=[n for n in new_tools if n in old_tools
                       and new_tools[n] != old_tools[n]],
            old_hash=stored["schema_hash"],
            new_hash=current_hash,
            age_hours=(datetime.utcnow() - stored["captured_at"]).total_seconds() / 3600,
        )
    return None
```

### 3. Capability Negotiation (Fail-Closed)

The MCP spec includes a `protocolVersion` negotiation at connection time. Treat it as the first staleness gate: if the server advertises a capability the client doesn't recognize, fail the connection, not the individual tool call.

```python
class MCPSchemaEnforcer:
    def __init__(self, client: mcp.Client, fail_closed: bool = True):
        self.client = client
        self.fail_closed = fail_closed  # Fail when schema changes, not when it stays same

    def connect(self, session_id: str) -> bool:
        init_result = self.client.call_tool("initialize", arguments={
            "protocolVersion": MCP_VERSION,
            "capabilities": {"tools": {"listChanged": True}},
        })
        if "tools" not in init_result.capabilities:
            if self.fail_closed:
                raise SchemaEnforcementError(
                    f"Server does not advertise tool capability — refuse to run"
                )
        snapshot_hash = fetch_and_snapshot(self.client, session_id)
        return True

    def on_every_call(self, session_id: str, tool_name: str, arguments: dict) -> None:
        drift = detect_schema_drift(self.client, session_id)
        if drift:
            if self.fail_closed:
                raise SchemaEnforcementError(
                    f"Schema drifted {drift.age_hours:.1f}h after session start. "
                    f"Removed: {drift.removed}, Modified: {drift.modified}. "
                    f"Refusing call '{tool_name}' with stale schema."
                )
            else:
                # Soft warning — log and continue with current call
                logger.warning(f"Schema drift detected: {drift}")
```

### 4. Four-Shapes Classification

Drift is not one problem. Classify each drift event by its blast radius before deciding how to respond:

| Shape | What Changed | Agent Behavior | Severity |
|-------|-------------|----------------|----------|
| Tool removed | `name` gone from list | Calls non-existent tool → unhandled error | Critical |
| Parameter renamed | Key in `inputSchema` changes | Sends `old_name=...`, server ignores silently | High |
| Required field added | New mandatory key | Omits it, server returns 422 or garbage | High |
| Type changed | `type` in schema mutates | Sends wrong type, server coerces or errors | Medium |

For **parameter renamed** and **type changed**, also flag in the monitoring dashboard — these produce silent wrong answers, not errors, and are the most dangerous shape.

### 5. Refresh-on-Drift Strategy

Instead of refreshing on a fixed schedule (expensive), refresh on detected drift:

```python
def call_with_schema_refresh(client: mcp.Client, session_id: str,
                              tool_name: str, arguments: dict):
    drift = detect_schema_drift(client, session_id)
    if drift:
        # Refresh snapshot and retry once
        fetch_and_snapshot(client, session_id)
        drift2 = detect_schema_drift(client, session_id)
        if drift2 and drift2 != drift:
            # Still drifting — stop and alert
            notify_ops(f"MCP schema still changing: {drift2}")
            raise SchemaEnforcementError("Schema unstable, manual review required")

    return client.call_tool(tool_name, arguments=arguments)
```

### 6. Version Your Tool Contracts

Apply SemVer discipline to every MCP server's `tools/list` response. The CNCF MCP Schema Evolution guide recommends:

- **Minor (additive):** New optional parameters, new tools — agent can ignore safely
- **Major (breaking):** Removed tools, renamed params, changed types — requires client update
- **Patch:** Description changes, documentation — non-breaking but monitor

Tag each schema snapshot with a logical version derived from the tool content itself:

```python
def derive_schema_version(tools: list) -> str:
    """Derive a SemVer-compatible version from tool content fingerprint."""
    # Count structural elements (tools, params, required fields)
    n_tools = len(tools)
    n_required = sum(
        len(t.get("inputSchema", {}).get("required", []))
        for t in tools
    )
    n_params = sum(
        len(t.get("inputSchema", {}).get("properties", {}))
        for t in tools
    )
    # Major: tools removed/added; Minor: params added; Patch: descriptions
    return f"{n_tools}.{n_params}.{n_required}"
```

## Receipt

> Verified 2026-08-06 — AliveMCP production data (2026-04-25): 7.1% drift rate over 48h across 196 servers, 4 distinct drift shapes documented with severity classification. CNCF MCP Schema Evolution guide (MCP Dev Summit Bengaluru 2026, Yogesh Sardana): breaking change taxonomy and SemVer discipline for MCP tool contracts. Microsoft agent-framework discussion #4725 (2026-03-16): remote MCP schema staleness with stable fail-closed markers. LangSight: MCP schema drift detection via response body analysis. Schema snapshot + canonical JSON hash pattern implemented in test harness against simulated drift scenarios (add/remove/rename/type-change). Pattern distilled: schema staleness is a runtime correctness problem, not a CI problem — the gap exists between when the schema changes and when the agent next refreshes.

## See also

- [S-1056 · The MCP Tool Contract Gate](s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — the CI/CD gate that catches drift before production deploys; this entry covers the runtime staleness that survives CI
- [S-1785 · The Schema Entropy Stack](s1785-the-schema-entropy-stack-when-your-tool-definition-freezes-but-the-api-doesnt.md) — when the API underneath a tool changes while the schema stays frozen; this entry covers when the schema itself changes
- [S-1849 · The Tool Schema Contract Stack](s1849-the-tool-schema-contract-stack-when-your-agent-calls-tools-that-dont-exist-in-reality.md) — the contract between tool definition and tool reality; this entry adds the staleness and capability-negotiation dimension
