# S-2227 · The MCP Schema Drift Stack — When Your MCP Server Changes and Your Agent Silently Hallucinates

Your agent passed every integration test on Monday. By Wednesday it was recommending out-of-stock products, routing tickets to deleted departments, and issuing refunds against closed accounts. No tests failed. No alerts fired. The MCP server was healthy — serving JSON-RPC 200s, responding in under 50ms. The only problem: one field on one tool changed type from `date-time` to `date`, and the agent never noticed. It kept sending the old format, the server started silently coercing it, and the agent downstream got back subtly wrong data it couldn't distinguish from correct data. This is **MCP schema drift** — the silent contract violation that turns a healthy agent into a confident liar.

## Forces

- **MCP tools have no built-in versioning.** The `tools/list` endpoint returns whatever the server currently has. There's no schema version, no changelog, and no deprecation window. A field that was `integer` last week is `string` today, and the agent — which cached the old schema — keeps sending the wrong type.
- **Agents can't detect schema drift.** The agent's schema is embedded in its context at startup or on first tool discovery. Once loaded, it never re-discovers unless you explicitly refresh. The agent has no mechanism to notice that `tools/list` returned a different shape than it expected.
- **Server health checks miss the contract.** Your HTTP probe checks `200 OK` and sub-100ms latency. The MCP server is healthy. The tool contract changed. These are orthogonal signals — the probe tells you the server is up; it tells you nothing about whether the agent's cached schema is still valid.
- **Drift compounds silently across the agent pipeline.** A field rename in one MCP server causes the agent to stop using that tool entirely (it picks the next closest match). The agent starts hallucinating the missing data. No error propagates — the agent just acts on incomplete information and produces plausible but wrong outputs.
- **Schema validation happens at the wrong layer.** The MCP server may validate tool inputs against its live schema, returning an error — or it may be lenient, coercing types silently. Either way, the agent has already committed to a behavior based on stale schema knowledge, and the resulting confusion cascades.

## The Move

### Layer 1 — Schema Snapshotting in CI

Treat `tools/list` as an immutable contract. On every CI run, snapshot the current schema and compare against the committed baseline:

```bash
# snapshot_current.sh
mcp tools list --json | jq -c '.tools[] | {name, description, inputSchema}' \
  | sha256sum > /schemas/baseline.sha256

# check_drift.sh
mcp tools list --json | jq -c '.tools[] | {name, description, inputSchema}' \
  | sha256sum > /schemas/current.sha256

if ! diff /schemas/baseline.sha256 /schemas/current.sha256; then
  echo "MCP schema drift detected — review before deploying"
  diff <(jq -c '.tools[] | .name' /schemas/baseline.json 2>/dev/null || echo "") \
       <(jq -c '.tools[] | .name' /schemas/current.json)
  exit 1
fi
```

Or use `mujin-mcpdrift` (PyPI: `mujin-mcpdrift`) — snapshots `tools/list` in CI, fails the build on any contract change.

### Layer 2 — Live Schema Watching in Production

For production monitoring, poll `tools/list` on a cadence and alert on diffs:

```python
import json, hashlib, httpx, asyncio
from datetime import datetime

async def watch_schema(client, server_url: str, baseline: dict, interval: int = 300):
    """Poll tools/list and alert when the contract changes."""
    seen = {}
    while True:
        resp = await client.post(server_url, json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        resp.raise_for_status()
        result = resp.json()["result"]
        tools = {t["name"]: t for t in result.get("tools", [])}
        
        # Check for added/removed/renamed tools
        for name in set(seen) | set(tools):
            was = seen.get(name)
            is_now = tools.get(name)
            if was and not is_now:
                print(f"[{datetime.utcnow()}] DRIFT: tool removed: {name}")
            elif not was and is_now:
                print(f"[{datetime.utcnow()}] DRIFT: tool added: {name}")
            elif was and is_now:
                # Check if inputSchema changed
                was_sig = hashlib.sha256(json.dumps(was.get("inputSchema", {}), sort_keys=True).encode()).hexdigest()[:16]
                is_sig = hashlib.sha256(json.dumps(is_now.get("inputSchema", {}), sort_keys=True).encode()).hexdigest()[:16]
                if was_sig != is_sig:
                    print(f"[{datetime.utcnow()}] DRIFT: schema changed: {name} ({was_sig} -> {is_sig})")
        seen = tools
        await asyncio.sleep(interval)
```

AliveMCP's Q2 2026 audit measured a **7.1% schema drift rate over 48 hours** across 196 healthy servers — roughly 50% probability of drift within 30 days for any given server.

### Layer 3 — Schema Refresh on Drift Detection

When drift is detected, force the agent to re-discover tools rather than continuing with a stale cache:

```python
async def refresh_agent_tools(agent_id: str, mcp_server_url: str):
    """Invalidate agent's cached schema and trigger re-discovery."""
    # 1. Fetch fresh schema
    resp = httpx.post(mcp_server_url, json={
        "jsonrpc": "2.0", "method": "tools/list", "id": 1
    })
    fresh_tools = resp.json()["result"]["tools"]
    
    # 2. Invalidate agent's schema cache
    await invalidate_tool_cache(agent_id)
    
    # 3. Re-inject fresh schema into agent context
    system_prompt = build_system_prompt_with_tools(fresh_tools)
    await update_agent_context(agent_id, system_prompt)
    
    # 4. Log the event for audit
    await log_schema_refresh(agent_id, len(fresh_tools), fresh_tools)
```

### Layer 4 — Schema-Typed Tool Contracts

Rather than relying on the MCP server's JSON Schema at runtime, define explicit contracts and validate against them:

```python
from pydantic import BaseModel, create_model, ValidationError
from typing import Literal

class ToolContract(BaseModel):
    """Define the expected schema for a tool — independent of MCP server output."""
    tool_name: str
    expected_params: dict
    output_contract: dict | None = None

CONTRACTS = {
    "get_order": ToolContract(
        tool_name="get_order",
        expected_params={
            "order_id": {"type": "string", "pattern": "^[A-Z0-9]{8,}$"},
            "include_items": {"type": "boolean", "default": False},
        },
    ),
}

def validate_tool_call(tool_name: str, params: dict) -> tuple[bool, str | None]:
    """Validate a tool call against its contract before sending to MCP server."""
    contract = CONTRACTS.get(tool_name)
    if not contract:
        return True, None  # No contract defined for this tool
    
    for param_name, spec in contract.expected_params.items():
        if param_name not in params and spec.get("required", False):
            return False, f"Missing required param: {param_name}"
        if param_name in params:
            actual = params[param_name]
            expected_type = spec["type"]
            if expected_type == "string" and not isinstance(actual, str):
                return False, f"Param {param_name} expected string, got {type(actual).__name__}"
            if "pattern" in spec and not re.match(spec["pattern"], actual):
                return False, f"Param {param_name} failed pattern match: {actual}"
    return True, None
```

This would have caught the WooCommerce MCP schema drift issue (GitHub #64195) where the server started returning `null` for a required field, but the agent had already cached the old schema and kept sending the old format.

### Layer 5 — Tool Call Output Validation

Drift doesn't only affect tool call *inputs* — it also affects tool call *outputs*. A changed `outputSchema` means the agent may receive structured data in an unexpected shape:

```python
def validate_tool_output(tool_name: str, raw_output: dict, expected_schema: dict) -> bool:
    """Validate tool output against the expected schema (from agent's cached schema)."""
    try:
        # Check required fields exist
        for field in expected_schema.get("required", []):
            if field not in raw_output:
                # Schema says this field is required but server didn't send it
                # → Possible schema drift or data issue
                return False
        # Check field types match
        for field, spec in expected_schema.get("properties", {}).items():
            if field in raw_output and raw_output[field] is not None:
                expected_type = spec.get("type")
                actual_type = type(raw_output[field]).__name__
                if expected_type == "number" and actual_type not in ("int", "float"):
                    return False  # Type coercion drift
        return True
    except Exception:
        return False  # Validation failed — treat as drift signal
```

## Forces (revisited)

- **Drift is invisible to standard monitoring.** CNCF Annual Survey 2025: 68% of organizations running AI agents in production report silent tool failures as their top observability gap — ranking higher than latency or cost overruns. Your APM dashboard shows green. The agent is producing wrong answers.
- **The fix has to be architectural, not operational.** You cannot rely on humans to notice when `tools/list` returns a different shape. The tooling (CI snapshotting, live watching, typed contracts) must detect and respond automatically.
- **Drift has multiple sources.** An MCP server maintainer bumps a dependency that regenerates the schema. A code-gen step produces different field ordering on every deploy. A team removes a tool nobody had used yet. A REST-to-MCP adapter starts returning `null` instead of `[]` for empty results. All of these are drift, and all are invisible to HTTP probes.

## Receipt

> Verified 2026-08-06 — Research sources: AliveMCP Q2 2026 audit (7.1% drift over 48h, 196 servers), CNCF Annual Survey 2025 (68% cite silent tool failures as top observability gap), CubeAPM MCP debugging guide (July 2026), WooCommerce MCP issue #64195 (schema mismatch from date format divergence, resolved May 2026), Microsoft Copilot IntelliJ issue #1183 (missing `probablyHasMoreMatchingFiles` schema field), `mujin-mcpdrift` (PyPI, MIT, 2026-06-22). Production impact: BIPI study of 1.4M tool invocations across 3 clients found schema mismatches caused 31% of all tool failures.

## See also

- [S-51 · Tool Schema Design](s51-tool-schema-design.md) — designing schemas that don't drift in the first place
- [S-1072 · The Tool Schema Stack](s1072-the-tool-schema-stack-when-agents-get-lost-in-a-hundred-generic-tools.md) — managing schemas at scale
- [S-2199 · The Tool Response Gate Stack](s2199-the-tool-response-gate-stack-when-your-agent-reasons-over-corrupted-output-and-nobody-checks.md) — validating tool outputs, not just inputs
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral drift from environmental change
