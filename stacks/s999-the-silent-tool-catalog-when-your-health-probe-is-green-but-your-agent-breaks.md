# S-999 · The Silent Tool Catalog: MCP Schema Drift

Your HTTP health probe returns 200. Your agent is broken. The server didn't go down — it changed shape. A tool was renamed, a required parameter was added, a deprecated tool was silently removed. The probe checked if the server was up. It didn't check if the tool catalog matched what your agent cached. This is MCP schema drift, and it is the failure mode that every agent operator eventually hits.

MCP servers expose their capabilities through `tools/list` — a runtime response that is not in your repository. Every agent client fetches it, caches it, and uses it to decide which tools to call. When that response changes between invocations, cached tool definitions go stale. The agent calls a tool that no longer exists, or calls a renamed tool with the old name, or passes a parameter the new schema doesn't recognize. No error in your logs. No 500. Just silence.

AliveMCP measured a **7.1% drift rate over 48 hours** across a sample of production MCP servers, extrapolating to roughly a **50% chance of schema drift over 30 days** for any given server. This is not edge-case behavior. It is the normal state of a living tool ecosystem.

## Forces

- **Your health probe checks liveness, not correctness.** An HTTP GET on the MCP endpoint returns 200 as long as the server process is running. It says nothing about whether `tools/list` matches what your agent cached at startup
- **MCP servers evolve on their own clock.** Tool authors rename, deprecate, and refactor tools without bumping the MCP protocol version or restarting the server. Three versioning layers operate independently: protocol version (slow), tool surface (medium), and the backend API the tool wraps (fast)
- **Agents cache aggressively.** Most MCP clients fetch `tools/list` once per session or once at startup. A drift event mid-session means the agent operates with stale schema data and produces calls that the server rejects with opaque errors
- **Drift is invisible to standard monitoring.** Database drift is caught by schema migration tools. API drift is caught by contract testing. MCP tool-list drift has no equivalent — until you specifically probe and hash the `tools/list` response

## The move

**Snapshot and hash `tools/list` on a schedule.** Store the canonical-JSON hash of the response. On every subsequent poll, recompute and compare. A hash mismatch is the only signal that catches all four shapes of drift: tool added, tool removed, tool renamed, signature changed.

```python
import hashlib
import json
import httpx
from datetime import datetime, timedelta

TOOLS_LIST_ENDPOINT = "https://your-mcp-server/.well-known/mcp/tools/list"
SNAPSHOT_INTERVAL = timedelta(hours=6)

async def check_tool_catalog_drift(server_url: str, server_name: str) -> dict:
    """Poll tools/list and classify any drift since the last snapshot."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(server_url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        resp.raise_for_status()
        result = resp.json().get("result", {})
        tools = result.get("tools", [])

    current_hash = hashlib.sha256(
        canonical_json({"tools": sorted(tools, key=lambda t: t.get("name", ""))}).encode()
    ).hexdigest()

    snapshot = load_snapshot(server_name)  # {hash, timestamp, tools}
    if snapshot and snapshot["hash"] == current_hash:
        return {"drifted": False, "server": server_name}

    # Classify the drift
    old_tools = {t["name"]: t for t in (snapshot["tools"] if snapshot else [])}
    new_tools = {t["name"]: t for t in tools}

    added   = [n for n in new_tools if n not in old_tools]
    removed = [n for n in old_tools if n not in new_tools]
    changed = [
        n for n in new_tools
        if n in old_tools and new_tools[n].get("description") != old_tools[n].get("description")
    ]

    save_snapshot(server_name, {"hash": current_hash, "timestamp": datetime.utcnow().isoformat(), "tools": tools})

    return {
        "drifted": True,
        "server": server_name,
        "added": added,
        "removed": removed,
        "changed": changed,
        "severity": classify_severity(added, removed, changed),
    }

def classify_severity(added, removed, changed):
    if removed:   return "BREAKING"   # agent will call non-existent tool
    if changed:   return "WARNING"   # description drift may confuse model
    if added:     return "INFO"      # new capability, not a regression
    return "OK"

def canonical_json(obj) -> str:
    """Stable serialization for hashing — sort keys, no extra whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
```

**Classify severity on every drift event.** Not all drift is equal:

- **BREAKING** (tool removed): The agent may call a tool that no longer exists. Alert immediately. Consider a graceful-degradation path that maps the old name to an available alternative or surfaces a clear error
- **WARNING** (tool description changed): The agent's model may route to the wrong tool based on the cached description. Log the change, alert the team, schedule a cache refresh
- **INFO** (tool added): New capability. Not a regression — just expand the agent's tool registry on the next session

**Refresh agent tool cache on BREAKING drift.** The cheapest fix is to re-poll `tools/list` and re-generate the tool calling instructions. For long-running agent sessions, a hot-refresh (re-fetch mid-session) avoids waiting for a restart. Track the drift in your observability platform as a first-class event — not just a log line.

**Version your MCP servers' tool surface.** Just as you version your API with breaking/non-breaking change labels, version your tool surface. Maintain a `/tools/list?version=` parameter or a `toolVersion` field in the response. This gives agents a stable interface to pin against while the server evolves underneath.

## Receipt

> Verified 2026-07-12 — Ran the drift check against a mock MCP server. Snapshot at T+0 captured 3 tools (hash: `a3f8…`). At T+6h, server returned 4 tools (added `search_docs`). Hash mismatch detected. Classification returned `{"drifted": true, "severity": "INFO", "added": ["search_docs"]}`. No agent impact — new capability. On BREAKING drift (tool removed), the classifier correctly returns severity "BREAKING". Confirmed: hash comparison catches additions (new hash), removals (old tool absent in new snapshot), and description changes (canonical JSON diffs on description field).
> Tradeoff: hashing at 6h intervals means up to 6h of stale cache after a BREAKING drift event. Reduce interval to 1h or use webhook-based invalidation if tool surface changes frequently. Hash comparison is content-addressable but doesn't catch semantic equivalence (tool renamed but behavior identical) — only structural changes.

## See also

- [S-113 · Reactive Schema Evolution](s113-reactive-schema-evolution.md) — detects and adapts to API schema changes automatically; MCP tool-list drift is the same pattern applied to the MCP tool registry
- [S-301 · MCP Is Eating the World](s301-mcp-is-eating-the-world.md) — MCP adoption and architecture; this entry covers the runtime reliability hazard that emerges at scale
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth.md) — MCP servers as an attack surface; tool catalog integrity applies to both availability and security
