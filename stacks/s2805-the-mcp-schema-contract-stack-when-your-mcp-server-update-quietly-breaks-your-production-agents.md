# S-2805 · The MCP Schema Contract Stack — When Your MCP Server Update Quietly Breaks Your Production Agents

Your agent ran 8,000 tasks flawlessly last week. This week it returns wrong answers on 30% of calls. No errors. No exceptions. No alerts. The MCP server you depend on shipped a breaking schema change three days ago — a parameter renamed, a return field removed, an enum value added. Your agent's tool schemas are cached in memory. The server's schema evolved. Nobody noticed until users started complaining. This is the MCP schema contract problem: tools that change underneath agents that don't know it happened.

## Forces

- **MCP servers evolve; MCP clients don't.** MCP's `tools/list` call returns the server's current schema on demand — but most clients cache it at startup or on first call. A server-side breaking change propagates to the client only when the client restarts or the cache expires. In long-running agent processes, this can mean days of mismatch.
- **Schema changes are silent failures.** Unlike a type error or a missing field, a renamed parameter or removed enum value doesn't throw. The server either ignores the unexpected field, returns a different structure, or — worst — returns a valid-looking result from a fallback path that was never meant to be taken.
- **The MCP protocol has no schema versioning.** The 2026 MCP spec includes no built-in schema version field, no capability negotiation, and no breaking-change detection. Clients that cache `tools/list` results have no mechanism to know the server changed.
- **Tool descriptions compound the problem.** The model's tool-calling decisions are partly driven by tool descriptions — which are also server-controlled and equally unversioned. When a description changes, the model may stop calling a tool, start calling it incorrectly, or misinterpret its output.

## The move

**Schema fingerprint + drift detection at the gateway layer:**

```python
import hashlib
import httpx
from dataclasses import dataclass, field
from typing import Any
import asyncio

@dataclass
class SchemaFingerprint:
    """Content-addressed schema identity for an MCP server."""
    server_name: str
    schema_hash: str          # SHA-256 of canonicalized tools/list response
    tool_signatures: dict[str, str]  # tool_name → hash of its schema
    version_tag: str = "unknown"
    last_seen: str = ""       # ISO timestamp

    def is_compatible_with(self, other: "SchemaFingerprint") -> bool:
        """True if the two fingerprints represent compatible schemas."""
        # Hash equality = identical schemas
        if self.schema_hash == other.schema_hash:
            return True
        # Check if it's a non-breaking evolution
        return self._check_backward_compat(other)

    def _check_backward_compat(self, newer: "SchemaFingerprint") -> bool:
        """Permissive check: new fields OK, removed fields = breaking."""
        for name, sig in self.tool_signatures.items():
            if name not in newer.tool_signatures:
                return False  # tool removed = breaking
            # New tool added = fine
        return True


class SchemaContractMonitor:
    """
    Watches MCP server schema evolution and gates agents from
    servers that have undergone breaking changes.
    """

    def __init__(self, http_client: httpx.AsyncClient):
        self.client = http_client
        self.fingerprints: dict[str, SchemaFingerprint] = {}
        self._cache: dict[str, Any] = {}

    def _canonicalize(self, schema: dict) -> str:
        """Deterministic schema representation for hashing."""
        import json
        # Sort keys, remove description whitespace variation
        normalized = json.dumps(schema, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _tool_signature(self, tool: dict) -> str:
        """Hash of a single tool's stable interface."""
        stable = {
            "name": tool.get("name"),
            "description": tool.get("description", "")[:200],  # truncate
            "inputSchema": tool.get("inputSchema", {}),
        }
        return self._canonicalize(stable)

    async def fetch_and_fingerprint(self, server_url: str) -> SchemaFingerprint:
        """Poll a server's tools/list and compute its fingerprint."""
        resp = await self.client.post(
            f"{server_url}/mcp/v1/tools/list",
            json={"method": "tools/list", "jsonrpc": "2.0", "id": 1},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        tools = data.get("result", {}).get("tools", [])
        schema_hash = self._canonicalize({"tools": tools})
        signatures = {t["name"]: self._tool_signature(t) for t in tools}

        return SchemaFingerprint(
            server_name=server_url,
            schema_hash=schema_hash,
            tool_signatures=signatures,
        )

    async def check_and_alert(self, server_url: str) -> tuple[bool, SchemaFingerprint]:
        """
        Returns (is_safe, current_fingerprint).
        Compares against stored fingerprint; alerts on breaking drift.
        """
        current = await self.fetch_and_fingerprint(server_url)
        stored = self.fingerprints.get(server_url)

        if stored is None:
            self.fingerprints[server_url] = current
            return True, current

        is_compat = stored.is_compatible_with(current)
        if not is_compat:
            # Breaking change detected — log and alert
            print(f"[SCHEMA DRIFT] Breaking change on {server_url}")
            print(f"  Removed tools: {set(stored.tool_signatures) - set(current.tool_signatures)}")
            print(f"  Changed tools: {self._diff_tools(stored, current)}")
            # Gate: return False to prevent agent from using stale schema
            return False, current

        if current.schema_hash != stored.schema_hash:
            # Non-breaking evolution — update in place, log it
            print(f"[SCHEMA EVOLUTION] Non-breaking update on {server_url}")
            self.fingerprints[server_url] = current
            return True, current

        return True, current

    def _diff_tools(self, old: SchemaFingerprint, new: SchemaFingerprint) -> dict:
        diff = {}
        for name in set(old.tool_signatures) & set(new.tool_signatures):
            if old.tool_signatures[name] != new.tool_signatures[name]:
                diff[name] = "schema_modified"
        return diff


# Usage in an MCP client wrapper
async def safe_mcp_invoke(monitor: SchemaContractMonitor, server_url: str,
                          tool_name: str, arguments: dict):
    is_safe, fp = await monitor.check_and_alert(server_url)
    if not is_safe:
        raise RuntimeError(
            f"Schema contract violation on {server_url}: "
            f"server schema has breaking changes. "
            f"Agent is running with stale cached schema. "
            f"Restart agent to pick up new schema."
        )
    # proceed with the actual tool call...
```

**The enforcement points:**

1. **Startup lock**: On agent boot, record the schema fingerprint for every MCP server. Store it alongside the agent's session state so it persists across restarts.
2. **Pre-call gate**: Before each `tools/call`, run `check_and_alert`. If the fingerprint has a breaking change, raise a `SchemaContractViolation` — don't invoke, don't use cached output.
3. **Non-breaking evolution auto-update**: New optional fields, new enum values, new tool additions are auto-accepted and the fingerprint is updated. This avoids alert fatigue for the common case.
4. **Schema diff on alert**: When a breaking change is detected, log exactly what changed — removed tools, modified schemas — so the on-call engineer knows whether to update the agent's schema cache, fix the tool invocation logic, or roll back the server.

## Receipt

> Receipt pending — 2026-08-17. Pattern identified from: LangSight blog on MCP schema drift (June 2026), Waxell MCP Gateway documentation on fingerprint-based drift detection, TechTimes report on silent schema drift between MCP server versions, OWASP ASI Top 10 (ASI05) covering unexpected code execution surface including tool schema manipulation. Production evidence from Waxell's "Fingerprints" feature showing real-world drift events on GitHub, Slack, and Linear MCP servers. Verified against existing entries: S-3355 covers transport lifecycle (server process death), S-1056 covers tool contract health probes (schema present vs. schema correct), S-1022 covers tool catalog vocabulary — none cover schema version mismatch between client cache and server state.

## See also

- [S-1056 · The MCP Tool Contract Gate](stacks/s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — tool contract health probes, complementary to schema fingerprinting
- [S-2090 · The MCP Gateway Token Stack](stacks/s2090-the-mcp-gateway-token-stack-when-your-mcp-fleet-burns-tokens-faster-than-it-serves-requests.md) — MCP gateway patterns for multi-server fleets
- [S-1022 · The MCP Tool Catalog](stacks/s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — shared vocabulary for tool naming, reduces schema misinterpretation
