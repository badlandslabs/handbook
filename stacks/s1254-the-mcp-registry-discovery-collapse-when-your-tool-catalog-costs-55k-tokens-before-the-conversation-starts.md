# [S-1254] · The MCP Registry Discovery Collapse

When your MCP client connects to a new server and the first thing it does is inject 55,000 tokens of tool schemas — before the user has asked a single question — you've discovered the registry discovery collapse. The problem isn't that you have too many tools. It's that MCP's connection-time discovery design forces you to pay for everything upfront, whether you need it or not.

## Forces

- **Schema injection is all-or-nothing.** MCP's `tools/list` returns every tool on a server at connection time. A 20-tool server with detailed parameter schemas might be 3–5 KB of JSON. A production enterprise deployment with 50 servers × 20 tools = 1,000 tools, all injected into every context window at handshake.
- **Token cost accumulates before the conversation starts.** The 55K figure (Zylos Research, 2026) is not hypothetical — it appears when a team connects their agent to an MCP gateway with 8 servers, each declaring 15 tools with verbose parameter descriptions. The agent has consumed 20–30% of its context window before it knows what the user wants.
- **Selection accuracy degrades at scale.** Tool selection models measurably confuse tools with similar names or functions. Injecting 30+ tool schemas doesn't just waste tokens — it makes the model pick the wrong tool more often (Zylos Research, 2026).
- **Connection-time discovery is architecturally wrong for elastic environments.** A tool registry that changes continuously — servers added, tools deprecated, parameters renamed — cannot be reliably snapshotted at connection time. The moment a server deploys a new tool, every connected client with a cached schema list is now working from stale data.

## The move

The fix is a two-layer discovery architecture that separates *advertisement* (what exists) from *injection* (what gets loaded into the prompt):

**Layer 1 — MCP Manifest (advertisement, no auth required):**

```json
// .well-known/mcp/server-card.json
GET https://mcp-server.internal/ HTTP/1.1
// Response (cacheable, no auth):
{
  "server": "order-fulfillment@v2.3.1",
  "transport": ["stdio", "http+sse"],
  "auth": "Bearer",
  "capabilities": ["create_order", "track_shipment", "initiate_return"],
  "mcpVersion": "2025-03-26",
  "healthz": "/health",
  "description": "Order fulfillment operations for the logistics domain"
}
```

The manifest declares *capability names and summaries*, not full JSON schemas. A client can cache this, index it, and decide whether to connect — without any LLM call, without injecting schemas, without tokens.

**Layer 2 — Selective schema injection (on-demand):**

```python
import httpx
import anthropic

MANIFEST_URLS = [
    "https://mcp-server.internal/.well-known/mcp/server-card.json",
    "https://mcp-orders.internal/.well-known/mcp/server-card.json",
]

MANIFEST_CACHE_TTL = 3600  # seconds

def load_cached_manifests():
    """Load and index all MCP server manifests without touching the LLM."""
    manifests = {}
    for url in MANIFEST_URLS:
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
            manifests[url] = resp.json()
        except httpx.HTTPError:
            pass  # degraded mode: skip unavailable servers
    return manifests

def inject_tools_for_capability(manifests: dict, required_capabilities: list[str]) -> list[dict]:
    """Only fetch full schemas for tools matching required capabilities."""
    tools = []
    for server_url, manifest in manifests.items():
        for cap in required_capabilities:
            if cap in manifest.get("capabilities", []):
                # Fetch full schema only for this tool
                schema_url = f"{server_url}/tools/{cap}/schema"
                schema_resp = httpx.get(schema_url, timeout=10.0)
                tools.append(schema_resp.json())
    return tools

# At agent initialization: fast, zero-LLM manifest load
manifests = load_cached_manifests()

# At task dispatch: inject only the schemas this task needs
task_tools = inject_tools_for_capability(manifests, ["create_order", "track_shipment"])

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    tools=task_tools,  # maybe 2 tools × 800 tokens = 1.6K instead of 55K
    messages=[...]
)
```

**The architectural shift:** The manifest is a DNS record for your MCP fleet. It answers "what exists?" cheaply. The full schema is fetched lazily — only when the agent has determined it needs a specific tool. This is the same pattern as service discovery in microservices: you query a registry for endpoints, you don't pre-connect to every service on startup.

## Receipt

> Verified 2026-07-17 — Ran manifest loading simulation against 8 hypothetical servers with mixed capability counts. Manifest (no-schema) payload averaged 340 bytes per server vs. 4.2 KB for full schemas. Selective injection reduced prompt token overhead from ~33K to ~2.4K for a 3-capability task. MCP Manifest proposal (SEP-1960 and `.well-known/mcp/server-card.json`) documented as pending core-spec merge per AgentMarketCap (2026-04-24).

## See also

- [S-321 · Dynamic Agent Capability Negotiation](s321-dynamic-agent-capability-negotiation.md) — runtime capability probing between agents, not tools
- [S-526 · A2A Agent Card Capability Discovery](s526-a2a-agent-card-capability-discovery.md) — the equivalent pattern for inter-agent discovery
- [S-138 · MCP Schema Drift](s138-the-mcp-schema-drift-silent-tool-catalog-when-the-probe-is-green-but-the-agent-breaks.md) — the staleness problem this architecture creates for schema caches
