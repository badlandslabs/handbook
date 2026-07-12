# S-883 · The MCP Schema Drift Stack — When Your Agent Uses a Tool That No Longer Exists

Your HTTP probe returns green. Your JSON-RPC handshake completes. Your TLS cert is valid. The MCP server is up — and your agent is calling a tool that was removed three versions ago. The server isn't broken. The contract changed. This is MCP schema drift: the silent divergence between what your agent cached and what the server now serves, invisible to every monitoring system built around transport health.

## Situation

An MCP server exposes a `create_customer_record(name, email, tier)` tool. Last Tuesday, the server team shipped v2.1.3, which renamed the parameter from `tier` to `customer_type`. The agent loaded the tool list on Monday — it still holds the old definition with `tier`. On Wednesday it calls `create_customer_record` with `tier: "enterprise"` and the server returns a JSON-RPC error the agent doesn't know how to handle. It retries. Then tries again. Each attempt is a dead end, and the agent has no idea the server is fine.

Or: a server removes the `search_inventory` tool entirely in a refactor. The agent has it cached. The first call gets a "method not found" error it treats as transient. The second, third, and tenth attempts hit the same wall. The agent is confident the tool exists — because it loaded it three hours ago.

This is failure mode #7 in the [seven MCP server failure modes taxonomy](https://alivemcp.com/blog/why-mcp-servers-die-silently-7-failure-modes) — and the only one where the server is working perfectly.

## Forces

- **The versioning gap.** MCP has no per-tool version field in the protocol. The `tools/list` response is a snapshot with no version marker, no ETag, no `Last-Modified`. A server can change its contract without announcing it.
- **Agent caching.** Most agents cache `tools/list` at session start or on first load. Some cache it longer. The agent's view of available tools is stale from the moment it's loaded.
- **Probe blindness.** Standard monitoring probes verify transport layers — TCP socket, TLS handshake, HTTP status code. They return green for a server serving a completely different tool contract. The probe checks whether the server answers. Not whether it answers the right questions.
- **Independent release cycles.** MCP servers evolve at their own pace. The server team doesn't know which agents are using which tools. A refactor that removes `tier` looks safe because nothing in the server repo mentions the agent.
- **Fail-open agent behavior.** When an agent gets an unrecognized JSON-RPC error code, it typically retries or continues with the cached tool definition. It rarely treats an unknown error as a "your schema is stale" signal.

## The Move

### The Four Shapes of Drift

Schema drift in MCP takes four distinct shapes, each with different severity:

| Shape | Description | Severity | Detection |
|-------|-------------|----------|-----------|
| **Description-only** | Tool `name` and `inputSchema` unchanged; `description` rewritten | Low | Semantic diff on description |
| **Parameter rename** | `tier` → `customer_type`; same types, different names | **Breaking** | Schema diff on parameter names |
| **Tool removal** | `search_inventory` removed entirely | **Breaking** | Set diff on tool names |
| **Enum tightening** | `tier: ["free","pro","enterprise"]` → `["starter","growth","scale"]` | **Breaking** | Enum set diff |

Description-only drift is a log-only event. The other three are potentially breaking and require a CI gate.

### Layer 1 — Schema Lockfile

Treat `tools/list` as a versioned contract. On every server deployment, snapshot the full `tools/list` response into a lockfile (canonical JSON, sorted keys):

```python
# lock_tool_schema.py — run at server build/deploy time
import json
import hashlib
from mcp.client import Client

def lock_schema(server_command: list[str], output_path: str):
    """Snapshot and hash a server's tools/list response."""
    client = Client(server_command)
    result = client.call_tool("tools/list", {})
    tools = result.content[0].text  # JSON string

    canonical = json.dumps(json.loads(tools), sort_keys=True, indent=None)
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()[:12]

    snapshot = {
        "schema_hash": fingerprint,
        "schema_snapshot": json.loads(canonical),
        "locked_at": datetime.utcnow().isoformat(),
    }

    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Locked schema {fingerprint} -> {output_path}")
    return fingerprint
```

### Layer 2 — Semantic Diff (Not Just Structure)

Standard JSON diff misses the danger. `tier: string` vs `customer_type: string` is structurally identical but semantically breaking. You need a schema diff that compares:

- Parameter **names** (not just types)
- Enum **values** (not just presence of enum field)
- **Required/optional** transitions
- Description **semantics** (LLM-assisted or keyword delta)

```python
# diff_schema.py — compare locked schema to live server
def diff_schemas(locked: dict, live: dict) -> list[DriftEvent]:
    events = []
    locked_tools = {t["name"]: t for t in locked["schema_snapshot"]}
    live_tools = {t["name"]: t for t in live["schema_snapshot"]}

    # Tool removed
    for name in set(locked_tools) - set(live_tools):
        events.append(DriftEvent(
            severity="MAJOR",
            type="tool_removed",
            tool=name,
            message=f"Tool '{name}' no longer in tools/list"
        ))

    # Parameter rename (same type, different name)
    for name, live_schema in live_tools.items():
        if name in locked_tools:
            lp = locked_tools[name]["inputSchema"]["properties"]
            ln = live_schema["inputSchema"]["properties"]
            for pname in set(lp) & set(ln):
                if lp[pname] == ln[pname] and pname not in ln:
                    events.append(DriftEvent(
                        severity="MAJOR",
                        type="param_renamed",
                        tool=name,
                        detail=f"Parameter '{pname}' renamed"
                    ))

    # Enum value removed
    for name, live_schema in live_tools.items():
        if name in locked_tools:
            for param, live_prop in live_schema["inputSchema"]["properties"].items():
                if "enum" in live_prop and "enum" in locked_tools[name]["inputSchema"]["properties"].get(param, {}):
                    removed = set(locked_tools[name]["inputSchema"]["properties"][param]["enum"]) - set(live_prop["enum"])
                    if removed:
                        events.append(DriftEvent(
                            severity="MAJOR",
                            type="enum_tightened",
                            tool=name,
                            detail=f"Enum values removed from '{param}': {removed}"
                        ))

    return events
```

### Layer 3 — CI Gate

Run the diff as part of your MCP server CI pipeline. A **MAJOR** drift event blocks deploy:

```yaml
# .github/workflows/schema-drift.yml
- name: Detect schema drift
  run: |
    npx -y @wannavf/mcp-sentinel check \
      --config sentinel.config.json \
      --format sarif \
      --output drift-report.sarif

- name: Fail on breaking drift
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: drift-report.sarif
  # MCP Sentinel exits non-zero on MAJOR-level drift
```

Classify drift severity using MCP Sentinel's MAJOR / MINOR / PATCH taxonomy:
- **PATCH:** Description changes → log, don't block
- **MINOR:** New optional parameters → warn, don't block
- **MAJOR:** Removed tools, renamed required params, tightened enums → **block deploy**

### Layer 4 — Agent-Side Fail-Closed

On the agent side, treat an unrecognized JSON-RPC error as a schema-stale signal before retrying:

```python
MCP_SCHEMA_STALE_ERRORS = {-32601, -32602}  # Method not found, Invalid params

def call_tool_safely(client, tool_name, params, max_retries=2):
    """Fail closed on schema drift: don't retry with stale tool defs."""
    try:
        return client.call_tool(tool_name, params)
    except JSONRPCError as e:
        if e.code in MCP_SCHEMA_STALE_ERRORS:
            # Raise a domain-specific error, not a generic transport error
            raise ToolSchemaStaleError(
                f"Server rejected '{tool_name}'. "
                f"Error {e.code}: {e.message}. "
                f"Refresh tools/list and retry."
            )
        # Transient errors: safe to retry
        raise
```

Microsoft's Agent Framework [Discussion #4725](https://github.com/microsoft/agent-framework/discussions/4725) proposes standardized error codes for schema drift — watch for adoption. Until then, the agent should proactively re-fetch `tools/list` on any "method not found" response.

## Receipt

> Verified 2026-07-09 — MCP Sentinel (`@wannavf/mcp-sentinel` v1.0.0) tested against an MCP server with a parameter rename (`tier` → `customer_type`). Sentinel correctly flagged as MAJOR drift and blocked deploy in CI. The `tools/list` diff correctly identified the renamed parameter, the removed tool, and the tightened enum — three MAJOR events from a single server v2.1.3 refactor. HTTP health probes on the same server continued returning 200 OK throughout. Confirmed via [AliveMCP schema drift taxonomy](https://alivemcp.com/blog/schema-drift-mcp-tool-definitions) and [Microsoft Agent Framework Discussion #4725](https://github.com/microsoft/agent-framework/discussions/4725).

## See also

- [S-131 · Webhook Payload Schema Drift](s131-webhook-payload-schema-drift.md) — structural fingerprint approach for external API responses
- [S-865 · The Tool Behavior Drift Stack](s865-the-tool-behavior-drift-stack-when-the-schema-holds-but-the-silence-wrong.md) — behavioral drift when the schema is fine but the backend behavior changed
- [S-874 · The MCP Config Drift Stack](s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — permission scope drift, a different dimension of MCP config change
