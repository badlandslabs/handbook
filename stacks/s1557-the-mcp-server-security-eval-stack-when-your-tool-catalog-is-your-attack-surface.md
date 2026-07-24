# S-1557 · The MCP Server Security Eval Stack — When Your Tool Catalog Is Your Attack Surface

Your agent has 8 MCP servers connected. Three are internal, four are from GitHub, one is a vendor SDK. You know what they do. You do not know what they *could* do — what arguments they accept, what their tool descriptions contain, what their return strings carry, or whether they are isolated from each other's data. You have 200,000 other organizations in the same position. As of July 2026, 14 CVEs have been assigned to MCP implementations, 6,237 security findings have been scored against 800+ servers, and the STDIO transport in Anthropic's official SDKs exposes any server launched via `StdioServerParameters` to command injection. Your agent's tool catalog is not infrastructure. It is an attack surface. And most teams have never evaluated it.

## Forces

- **The tool catalog is LLM input.** Unlike a traditional API client, an agent reads tool names, descriptions, and JSON schemas at runtime and uses them to decide which actions exist and how to invoke them. Every field in `tools/list` is a potential injection vector. Unlike user prompts, you control this input — but most teams never scan it.
- **Tool results flow back into the context window.** MCP's `tool` result format feeds directly into the next LLM turn. A compromised or adversarial MCP server can craft responses that manipulate agent reasoning, trigger cascading tool calls, or exfiltrate session context across the entire conversation window.
- **STDIO command injection is a design flaw, not a misconfiguration.** The root cause of 30+ RCE issues in MCP servers traces to `StdioServerParameters` in Anthropic's official Python, TypeScript, Java, and Rust SDKs accepting `command` and `args` passed directly to the OS. Patching the SDK does not fix servers already deployed; scanning for the pattern does.
- **The protocol lacks standardized auth.** MCP has no built-in permission model. Multi-tenant deployments rely on per-key `AllowedTools` restrictions and gateway-level enforcement — both of which are easy to get wrong and easy to forget.

## The move

Run four concrete eval checks against every MCP server — at registration time, in CI, and at runtime as guardrails. This is not a penetration test. It is a systematic scanner that treats your tool catalog as untrusted input.

### Check 1: Tool-description injection scan

**What it catches:** Malicious or poisoned content in tool names, descriptions, and JSON schemas — including nested `description` fields inside parameter objects and `enum` value labels.

**How it works:** Parse the output of `tools/list` and `tools/call` schema definitions. Scan every string field against a blocklist of injection patterns (CSS/JavaScript injection, credential exfiltration, redirect instructions, role-override directives). Flag any field that exceeds a benign-length threshold with high entropy or contains known payload signatures.

**Where it runs:** At server registration (first `tools/list` call) and on every `tools/list` refresh. In CI as a pre-deploy gate.

```python
from mcp_client import MCPClient
import re

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"<script",
    r"javascript:",
    r"data:text/html",
    r"\\x",
    r"\${.*}",
    r"\[SYSTEM\]",
    r"-->{3,}",
]

def scan_tool_description(tool_schema: dict) -> list[str]:
    """Scan a tool schema for injection patterns. Returns list of violations."""
    violations = []
    text_fields = [
        tool_schema.get("name", ""),
        tool_schema.get("description", ""),
    ]
    for param in tool_schema.get("inputSchema", {}).get("properties", {}).values():
        text_fields.extend([
            param.get("description", ""),
            *param.get("enum", []),
        ])
    for field in text_fields:
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, field, re.IGNORECASE):
                violations.append(f"Pattern '{pattern}' in field: {field[:80]}")
    return violations

async def register_server(url: str, name: str):
    client = MCPClient(url)
    tools = await client.list_tools()
    violations = []
    for tool in tools:
        violations.extend(scan_tool_description(tool))
    if violations:
        raise SecurityViolation(f"MCP server '{name}' failed injection scan: {violations}")
    return client
```

### Check 2: Tool-result tampering

**What it catches:** Malicious content in MCP server responses that could manipulate the next LLM turn — instruction overrides, action directives, or context exfiltration embedded in tool return strings.

**How it works:** Intercept every `tools/call` response with a per-session hook. Scan the return string before it enters the context window. Allowlist non-sensitive structured data; flag free-text responses that contain injection-like patterns or exceed a suspicious length ratio relative to the actual result.

**Where it runs:** Per-call hook in the MCP session. This is the only check that runs at runtime on every tool invocation, not just at registration.

```python
async def safe_tool_call(client: MCPClient, tool_name: str, arguments: dict):
    result = await client.call_tool(tool_name, arguments)

    # Scan result before it enters the context window
    if isinstance(result.content, str):
        scan_results = scan_tool_description({"description": result.content})
        if scan_results:
            # Log + alert, optionally reject
            audit_log.warning(f"Tool-result tampering detected: {scan_results}")
            raise ToolResultSecurityError(f"Tool '{tool_name}' returned suspicious content")

    return result
```

### Check 3: Sandbox and permission-escape attempt

**What it catches:** Tool arguments designed to escape the declared tool scope — path traversal in file operations, command injection in shell tools, network requests to internal IPs, credential patterns in arguments that should not carry secrets.

**How it works:** Before invoking any tool, validate arguments against the tool's declared capability scope. For file tools: check for `../`, absolute paths outside the sandbox, and glob patterns that match credential files. For network tools: resolve hostnames, reject internal IP ranges. For shell tools: validate against an allowlist of safe commands.

**Where it runs:** Per-call hook on arguments, before the MCP session forwards them to the server.

```python
import ipaddress
import re

INTERNAL_IP_RANGES = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]
ALLOWLISTED_COMMANDS = {"curl", "wget", "git", "ls", "cat", "grep"}

def check_file_args(tool_name: str, args: dict) -> None:
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        if re.search(r"\.\.\/|/\.\./|\~/\.\.|%2e%2e", value, re.IGNORECASE):
            raise PermissionEscapeError(f"Path traversal in '{tool_name}' arg '{key}': {value}")
        if re.search(r"(aws_|AZURE_|GCP_|sk-)[a-zA-Z0-9]{16,}", value):
            raise PermissionEscapeError(f"Credential-like value in '{tool_name}' arg '{key}'")

def check_network_args(tool_name: str, args: dict) -> None:
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        try:
            host = extract_host(value)  # parse URL or host:port
            ip = ipaddress.ip_address(host)
            for cidr in INTERNAL_IP_RANGES:
                if ip in ipaddress.ip_network(cidr):
                    raise PermissionEscapeError(
                        f"Internal IP access in '{tool_name}' arg '{key}': {ip}"
                    )
        except ValueError:
            pass  # not an IP, skip
```

### Check 4: Cross-tenant data isolation

**What it catches:** Requests from one tenant reaching another tenant's data through shared MCP server state, missing trace context propagation, and over-permissioned tool access.

**How it works:** Validate per-key `AllowedTools` restrictions are enforced at the gateway layer. Ensure trace IDs are namespaced per tenant. Verify server-scoped logs do not expose cross-tenant data. Check that MCP server state (sessions, caches, tool results) is not shared across tenant boundaries.

**Where it runs:** Gateway auth layer and audit pipeline. This check operates on the deployment configuration, not the server code.

```yaml
# Example: Tenant-scoped MCP gateway config
tenants:
  - id: tenant_acme
    allowed_tools:
      - search_docs
      - update_ticket
      - read_customer_record
    trace_namespace: acme-{run_id}
    rate_limit: 120/min
  - id: tenant_beta
    allowed_tools:
      - search_docs
      - read_public_record
    trace_namespace: beta-{run_id}
    rate_limit: 60/min

# Cross-tenant isolation checks:
# 1. No shared session store across tenant IDs
# 2. MCP server state (file caches, memory) scoped to trace_namespace
# 3. Audit logs namespaced — tenant_beta cannot see tenant_acme traces
```

### The eval loop: CI gate to production guardrail

Each check has two layers: a **CI gate** (runs before deploy) and a **runtime guardrail** (runs on every invocation). The CI gate catches known-bad servers. The runtime guardrail catches drift — a server that was clean at registration but returned poisoned results under specific inputs.

```
CI Pipeline:
  1. mcp-server-scan --server-url https://github.com/org/mcp-server
     → Check 1 (tool-description scan) → BLOCK or WARN
  2. mcp-server-fuzz --server-url --tool-list
     → Check 3 (sandbox/escape fuzzing) → BLOCK
  3. mcp-server-audit --config tenant-config.yaml
     → Check 4 (cross-tenant isolation) → BLOCK
  4. Deploy to staging
     → Runtime hooks active (Checks 2, 3)

Production:
  → Runtime hooks on every tool call (Checks 2, 3)
  → Periodic re-scan of tools/list on a cron (Check 1 refresh)
  → Audit log review for Check 4 violations
```

## Receipt

> Verified 2026-07-23 — Research sourced from: The Agent Report (Jul 22, 2026) citing 14 CVEs, 200,000+ exposed servers, 6,237 findings across 800+ servers; FutureAGI MCP Server Security Evaluation (May 10, updated May 20, 2026) with the 4-check framework; OWASP ASI Top 10 (2026). CVE data: CVE-2025-6572 (GPT Researcher), CVE-2026-30623 (LiteLLM), CVE-2026-30615 (Windsurf zero-click), CVE-2026-26015 (DocsGPT), CVE-2026-33224 (Bisheng), CVE-2026-30624 (Agent Zero). STDIO root cause: `StdioServerParameters` in Anthropic MCP SDKs (Python/TS/Java/Rust). Framework available: `agent-audit` on GitHub (51 rules, OWASP ASI Top 10 mapped, LangChain/CrewAI/AutoGen).

## See also

- [S-261 · MCP Security — The Attack Surface You Inherited](stacks/s261-mcp-security-attack-surface.md) — the inherited trust problem when connecting to third-party MCP servers
- [S-743 · MCP Tool Description Poisoning](stacks/s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — the schema injection threat in depth
- [S-1555 · The MCP DevSecOps Shift-Left Stack](stacks/s1555-the-mcp-devsecops-shift-left-stack-when-your-mcp-server-ships-with-a-cve-your-linter-never-caught.md) — moving MCP security into CI
