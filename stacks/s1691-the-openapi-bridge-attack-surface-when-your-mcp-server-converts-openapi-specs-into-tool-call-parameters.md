# S-1691 · The OpenAPI-Bridge Attack Surface — When Your MCP Server Converts OpenAPI Specs Into Tool-Call Parameters

Your MCP server looks clean: no direct file access, no raw SQL, no hardcoded secrets. Then you enable the OpenAPI bridge — a feature that converts any internal REST API's OpenAPI spec into MCP tool definitions, so your agent can call internal services through the MCP interface. Within hours, an attacker has pivoted from the agent's tool calls to your internal Kubernetes API, cloud metadata endpoint, and private GitLab instance. The OpenAPI bridge didn't add a vulnerability. It exposed one that was sitting inside your network all along, waiting for a tool interface to activate it.

This is the **OpenAPI-bridge attack surface**: MCP servers that convert OpenAPI specifications into tool schemas inherit not just the API's functionality, but its entire attack surface — including every SSRF vector, every internal endpoint, and every unvalidated path parameter that the API's original design assumed would never be reachable from an external caller.

## Forces

- **OpenAPI bridges are a trust amplifier.** An OpenAPI spec describes every internal endpoint: internal auth services, admin routes, metadata endpoints, debug interfaces. Expose it as MCP tools and every one of those endpoints becomes a tool the agent can call, with whatever credentials the MCP server has.
- **Path parameters are invisible attack vectors.** Standard security audits check for malicious user input. They don't check for malicious *path parameter values* — because in a traditional client-server model, the server controls those values. In an OpenAPI-bridge model, the agent generates them, and agent-generated path traversal sequences are invisible to the original API's input validation.
- **SSRF via path traversal is CVSS 10.0.** CVE-2026-32871 (FastMCP OpenAPIProvider, CVSS 10.0) shows the exact pattern: `_build_url()` substitutes path parameters into a URL template without encoding `../` sequences. `urllib.parse.urljoin()` resolves `../` as directory traversal. An agent calling `GET /api/v1/users/../../../admin/keys` with `{user_id: "../../../admin/keys"}` escapes the intended API boundary entirely.
- **Agent tool calls are opaque to the API.** The internal API receiving the tampered request sees a request from a legitimate MCP server process — same IP, same auth context. It has no way to know the path was constructed by an LLM rather than a typed client. The API's own authorization model was never designed for this threat model.
- **The bridge inherits the API's entire trust model.** If the internal API assumed "only our frontend can call this endpoint," that assumption breaks when the endpoint is also exposed as an MCP tool. The blast radius of every internal API misconfiguration now extends to the agent layer.

## The move

### 1. Map the bridge surface before enabling it

Before connecting an OpenAPI bridge, enumerate every endpoint the spec exposes:

```python
import yaml

with open("internal_api_openapi.yaml") as f:
    spec = yaml.safe_load(f)

# Flag dangerous endpoints before bridging
DANGEROUS_PATTERNS = [
    "/admin", "/debug", "/internal", "/health",
    "/metadata", "/169.254",  # cloud metadata
    "/.well-known", "/actuator",
]

dangerous = []
for path, methods in spec.get("paths", {}).items():
    for method, details in methods.items():
        for pattern in DANGEROUS_PATTERNS:
            if pattern in path.lower():
                dangerous.append(f"{method.upper()} {path}: {details.get('summary', 'no summary')}")

print("DANGEROUS ENDPOINTS IN BRIDGE SURFACE:")
for item in dangerous:
    print(f"  ⚠  {item}")
```

Run this against every OpenAPI spec before it touches your MCP server. Treat the output as a security review gate.

### 2. Validate path parameters at the MCP tool layer

Even if the upstream API has its own validation, validate at the MCP bridge:

```python
from urllib.parse import urljoin
import re

def safe_build_url(base_url: str, path_template: str, params: dict) -> str:
    """Build URL with path traversal sanitization before passing to backend."""
    # Encode path parameters to neutralize ../ sequences
    sanitized = {}
    for key, value in params.items():
        # Reject path traversal characters in path parameters
        if isinstance(value, str) and re.search(r'\.\.[/\\]', value):
            raise ValueError(f"Path traversal attempt in parameter '{key}': {value!r}")
        # Reject absolute URLs (prevent redirect to arbitrary hosts)
        if isinstance(value, str) and value.startswith(('http://', 'https://', '//')):
            raise ValueError(f"Absolute URL attempt in parameter '{key}': {value!r}")
        sanitized[key] = value

    # Build URL
    path = path_template
    for key, value in sanitized.items():
        path = path.replace(f"{{{key}}}", str(value), 1)

    # Final validation: resolved URL must stay within allowed prefixes
    resolved = urljoin(base_url.rstrip('/') + '/', path.lstrip('/'))
    allowed_prefixes = [base_url.rstrip('/') + '/']
    if not any(resolved.startswith(p) for p in allowed_prefixes):
        raise ValueError(f"URL escaped allowed prefix: {resolved!r}")

    return resolved
```

This addresses the specific root cause of CVE-2026-32871: `_build_url()` substituted parameters without encoding, and `urljoin()` resolved `../` as traversal.

### 3. Scope MCP server credentials to minimum required

The MCP server process that runs the OpenAPI bridge should have *only* the credentials needed for the endpoints you intentionally exposed — not the credentials of an account that can access all internal APIs:

```python
# Instead of: one MCP server with broad credentials
# Use: per-endpoint-credential scoping via an auth proxy

from fastmcp import FastMCP
import httpx

mcp = FastMCP("scoped-bridge")

# Each tool gets its own scoped HTTP client with minimal credentials
TOOL_CREDENTIALS = {
    "get_user": {"scope": "read:users"},       # limited scope token
    "list_orders": {"scope": "read:orders"},    # different token, different scope
    "admin_health": {"scope": "admin:health"}, # explicitly gated — requires separate approval
}

@mcp.tool()
def get_user(user_id: str) -> dict:
    token = get_scoped_token(TOOL_CREDENTIALS["get_user"]["scope"])
    resp = httpx.get(f"https://internal-api.example.com/users/{user_id}",
                     headers={"Authorization": f"Bearer {token}"})
    return resp.json()
```

### 4. Audit the resulting tool surface as if it's a public API

After bridging, treat the MCP server's tool list as a public attack surface:

```bash
# List all tools the MCP server exposes
mcp tools list | grep -E "admin|debug|internal|meta|key|token|secret"

# For each tool, test boundary conditions
echo 'Testing path traversal in each tool parameter...'
```

The OWASP MCP Top 10 classifies this as part of **MCP06: Unrestricted Resource Consumption** and **MCP04: Excessive Agency** — the bridge gives the agent agency over endpoints that were never meant to be externally reachable.

## Receipt
> Verified 2026-07-26 — CVE-2026-32871 (FastMCP OpenAPIProvider, CVSS 10.0) confirmed via GitHub Advisory GHSA-vv7q-7jx5-f767. Affected: fastmcp < 3.2.0. Root cause confirmed: `_build_url()` in `fastmcp/utilities/openapi/director.py` substitutes path parameters without encoding `../` sequences; `urllib.parse.urljoin()` resolves traversal. Patched version: 3.2.0. The MCP Atlassian SSRF (CVE-2026-27826) and Azure MCP Server SSRF (CVE-2026-26118) confirm this is a pattern, not an instance — SSRF via MCP tool call is the recurring exploit vector.

## See also
- [S-1017 · The Transitive Framework Stack](/stacks/s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — infrastructure CVE inheritance (BadHost/CVE-2026-48710); this entry is the *feature* layer (OpenAPI bridging) vs. that entry's *dependency* layer
- [S-240 · MCP Tool Execution Isolation](/stacks/s240-mcp-tool-execution-isolation.md) — sandboxing MCP tools; OpenAPI bridges need the same isolation discipline
- [S-1188 · A2A Authorization Islands](/stacks/s1188-the-a2a-authorization-islands-six-structural-security-gaps-in-the-a2a-v1-0-protocol-spec.md) — protocol-level authorization gaps; the OpenAPI bridge is the *implementation* analog at the tool layer
