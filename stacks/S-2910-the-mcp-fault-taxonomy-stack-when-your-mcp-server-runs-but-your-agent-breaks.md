# S-2910 · The MCP Fault Taxonomy Stack — When Your MCP Server Runs but Your Agent Breaks

Your agent's trace shows HTTP 200 on every MCP call. The server is live. The tools/list endpoint returns a clean list. Then your agent calls `create_booking` with the exact parameters the schema describes — and gets back an error that never appeared in your tests. Or it gets back silently truncated JSON that your eval suite never checked. Or it gets back the wrong tool entirely, because the server updated its tool names between your last health check and this request. This is not your agent failing. This is the MCP server failing in a way your monitoring never caught — because MCP fault taxonomy lives below the HTTP status code layer, in the runtime behavior of a server that answers every request.

## Forces

- **MCP fault taxonomy lives below the HTTP status code.** A server can return HTTP 200 and still deliver a fault: wrong tool output, schema-mismatched parameters silently coerced, host logging corrupting the JSON-RPC stream, configuration parameters accepted but not enforced. Conventional health probes only check HTTP uptime.
- **MCP server implementation quality varies wildly.** The protocol shipped with SDKs in Python, TypeScript, Java, and Rust — each with different failure modes. Configuration accepted at initialization may not be enforced at runtime. The dominant fault surface (23.2%) is in tool capability execution, not protocol transport.
- **Real fault data is now available.** The first large-scale empirical taxonomy of MCP runtime faults analyzed 837 confirmed fault threads across 473 GitHub repositories, deriving 11 top-level categories, 27 subcategories, and 73 leaf fault types. The distribution is predictable enough to engineer against.
- **MCP fault patterns are protocol-specific.** Unlike general API failures, MCP faults include host-side schema updates that break tools/list compatibility, host logging corrupting the JSON-RPC stream, and server startup failures triggered by dependency mismatches between the host environment and the server's requirements.

## The move

### The 11-category MCP runtime fault taxonomy

Derived from 837 fault threads across 473 repositories, validated by 55 practitioners (Owotogbe et al., arxiv:2606.05339, June 2026):

| Category | Share | What it looks like |
|---|---|---|
| **Tool-related** | 23.2% | Tool executes but returns wrong shape, truncated output, or silently ignores a required parameter. The tool "worked" but broke the agent's expectation. |
| **Data & Schema** | 17.6% | Input/output schema violations not caught at runtime. A parameter type accepted at schema definition but violated at call time. |
| **State & Configuration** | 17.1% | Configuration parameters accepted at initialization but not enforced at runtime. Default values applied silently when expected values aren't present. |
| **Host Logging** | ~9% | Server-side log output corrupts the JSON-RPC response stream. The host's logging interceptor and the MCP JSON-RPC layer share a stream — and the logs win. |
| **Server Startup** | ~9% | Required modules or executables absent or mis-packaged. Host-driven startup fails at import or initialization due to dependency mismatches. |
| **Schema Drift** | ~7% | tools/list response changes between sessions. A tool removed in v0.7, a parameter renamed, a description rewritten — while the agent holds a cached tool list. |
| **Host-side Update** | ~5% | Host-side SDK update introduces breaking changes. A Claude Desktop update broke all tool calls with "this schema is not valid" — union of object types dropped from support. |
| **Transport / Protocol** | residual | HTTP/WebSocket transport failures, timeout mismatches, streaming corruptions. Less common than application-layer faults. |

### The supplementary five-category study

Parallel work (Taraghi, Morovati, Khomh, arxiv:2603.05637v2, March 2026, 3,282 bug issues from 279 repos, 41 practitioners) identifies overlapping categories:

```
Functional Faults        → tool calls return wrong/out-of-format data
Schema Faults            → tools/list schema mismatches between host and server
Configuration Faults     → accepted-but-not-enforced parameters  
Operational Faults       → server startup/initialization failures  
Host Logging Faults      → log output corrupts JSON-RPC stream
```

The convergence across both studies confirms: **the fault surface is predominantly in capability execution and data schema enforcement, not in the transport or protocol layer**.

### The MCP fault detection stack

```
[Monitor HTTP status]          ← What most teams do. Misses 70%+ of MCP faults.
      ↓
[Monitor tools/list response]  ← Catch schema drift, removed tools, renamed params.
      ↓
[Canonical JSON hash of schema] ← Detect any structural change in the tool surface.
      ↓
[Validate tool call contracts]  ← Check return shapes match expected schemas.
      ↓
[Stream-segregate logging]     ← Isolate MCP JSON-RPC streams from host logs.
      ↓
[Dependency pinning]           ← Lock host SDK and server SDK to known-compatible pairs.
```

### The canonical-JSON hash for schema drift

```python
import json, hashlib, requests

def mcp_schema_hash(server_url: str) -> str:
    """Hash the tools/list response to detect any structural change."""
    resp = requests.get(f"{server_url}/tools/list", timeout=10)
    tools = resp.json()
    canonical = json.dumps(tools, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]

BASELINE = mcp_schema_hash("https://your-mcp-server.com")

# In your health check loop:
current = mcp_schema_hash("https://your-mcp-server.com")
if current != BASELINE:
    alert("MCP schema drift detected — tool surface changed since baseline")
    log(f"Old: {BASELINE}, New: {current}")
```

This catches all four drift shapes: removed tools, renamed parameters, changed descriptions, added breaking optional parameters. It is the only approach that catches drift invisible to HTTP probes.

### Host logging stream isolation

```python
# The bug: host logs and JSON-RPC share stdout
# The fix: redirect MCP server logs to stderr, pipe stdout exclusively to JSON-RPC

# Python MCP server
import sys, logging
mcp_logger = logging.getLogger("mcp_server")
mcp_logger.addHandler(logging.StreamHandler(sys.stderr))  # logs → stderr
# JSON-RPC responses still go to stdout — clean stream for the host

# Host-side: read stdout only for JSON-RPC, never mix with server logs
import subprocess
proc = subprocess.Popen(
    ["python", "mcp_server.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,  # logs captured separately
)
```

### Schema pinning at deploy time

```python
from mcp import ClientSession
import hashlib

KNOWN_SCHEMA = "a3f8b2c1"  # pinned at deploy time
KNOWN_TOOLS = {
    "create_booking": {
        "required": ["tenant_id", "slot_id"],
        "optional": {"notify": True}
    }
}

async def safe_tool_call(session: ClientSession, tool: str, params: dict):
    # Check schema hash before every tool call
    tools = await session.list_tools()
    schema_hash = hashlib.md5(
        json.dumps(tools, sort_keys=True).encode()
    ).hexdigest()[:8]
    
    if schema_hash != KNOWN_SCHEMA:
        raise SchemaDriftError(f"Schema changed: {KNOWN_SCHEMA} → {schema_hash}")
    
    # Validate params against pinned contract
    contract = KNOWN_TOOLS.get(tool, {})
    missing = [k for k in contract.get("required", []) if k not in params]
    if missing:
        raise ParameterMissingError(f"Missing required: {missing}")
    
    return await session.call_tool(tool, params)
```

## Receipt

> Verified 2026-08-20 — arxiv:2606.05339 (837 fault threads, 473 repos, 11 categories, 55 practitioners); arxiv:2603.05637v2 (3,282 bug issues, 279 repos, 41 practitioners). Both studies independently converge on tool-related faults (23.2%) as the dominant category. AliveMCP measured 7.1% drift rate over 48 hours across 196 MCP servers. LangSight and MintMCP blogs document the four drift shapes and mitigation patterns. ai-tool-guard and DriftGuard are open-source tools implementing canonical-JSON-hash detection.

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — CVE landscape and marketplace governance
- [S-1609 · The Dynamic Tool Surface Stack](s1609-the-dynamic-tool-surface-stack-when-your-agents-tools-change-between-requests-and-your-eval-doesnt-know.md) — when tool surface shifts under your eval suite
- [S-1072 · The Tool Schema Stack](s1072-the-tool-schema-stack-when-agents-get-lost-in-a-hundred-generic-tools.md) — tool naming, description design, and schema ergonomics
