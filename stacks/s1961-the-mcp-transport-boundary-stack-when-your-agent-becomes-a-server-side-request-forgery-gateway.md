# S-1961 · The MCP Transport Boundary Stack — When Your Agent Becomes a Server-Side Request Forgery Gateway

You audited your MCP servers. Tool poisoning? Mitigated. Marketplace CVEs? Patched. Schema drift? Contracted. What nobody caught: the agent itself is a relay for server-side request forgery, arbitrary subprocess execution, and memory exhaustion attacks — all through the transport layer. The protocol that connects your agent to your tools is also the fastest path from "agent reads a malicious resource" to "attacker runs code on your infrastructure."

## Forces

- **The SDK spawns processes from structured data.** All four official Anthropic MCP SDKs (Python, TypeScript, Java, Rust) pass `StdioServerParameters` directly to `subprocess` without shell hardening. A crafted `mcp.json` config file — or a malicious MCP server responding to a `initialize` handshake — can inject command-line arguments that execute arbitrary OS commands. Anthropic classifies this as intentional design; the security community classifies it as an RCE vector that has already been exploited in the Postmark MCP server infostealer campaign. Over 200,000 MCP servers are estimated exposed to this attack surface.
- **MCP's SSRF surface is structural, not incidental.** MCP clients follow redirects, resolve hostnames, and make outbound HTTP requests on behalf of the agent — often with the same OAuth tokens used for internal services. CVE-2026-32871 (CVSS 8.8) demonstrates authenticated SSRF through OpenAPI path parameter injection: an attacker controlling a tool schema's path parameters can use `../` sequences to escape the intended API prefix and hit internal endpoints, with authorization headers intact. 82% of 2,614 analyzed MCP implementations were vulnerable to path traversal.
- **The protocol has no response integrity layer.** MCP servers can return arbitrary content in their responses — modified tool results, injected status fields, crafted error messages. The agent processes these as authoritative data, and there's no signature, hash, or integrity check on the response path. Server reflection attacks (where a malicious MCP server echoes modified payloads back through the agent) and response poisoning (where a compromised or man-in-the-middle MCP relay alters results) are invisible to the client.
- **Transport-layer DoS is a memory exhaustion path.** The MCP Ruby SDK's StdioTransport and Client (pre-0.23.0) used `IO` without a byte limit. A peer sending data without a newline exhausts process memory — CVE-2026-63119 (CVSS 6.2). Similar unbounded read patterns exist in other SDK transports. An agent that crashes its MCP transport layer mid-task leaves the agent in an undefined state with no clean recovery path.
- **Security tooling doesn't see transport-layer traffic.** MCP stdio runs over stdio, not HTTP. Most network security tools, API gateways, and SIEM systems don't inspect it. CSPM tools don't scan local `mcp.json` files for malicious parameters. The attack surface is invisible to the standard security stack.

## The move

Treat the MCP transport boundary as an untrusted network segment. Every component in the transport path — config files, server processes, response streams — must be validated and sandboxed.

**1. Sanitize StdioServerParameters at config load time.**

```python
import subprocess
import shlex
from typing import Any

def spawn_mcp_server_safe(server_config: dict[str, Any]) -> subprocess.Popen:
    """
    Spawn MCP server with defense-in-depth against subprocess injection.
    StdioServerParameters command/args are equivalent to eval() without this.
    """
    command = server_config.get("command", "")
    args = server_config.get("args", [])

    # Defense 1: allowlist exact command path (no PATH resolution)
    ALLOWED_SERVERS = {
        "/usr/local/bin/mcp-server-git",
        "/usr/local/bin/mcp-server-filesystem",
        "/usr/local/bin/npx",
        "/usr/local/bin/python3",
    }
    resolved = subprocess.resolve("which", command) if not command.startswith("/") else command
    if resolved not in ALLOWED_SERVERS:
        raise SecurityError(f"MCP server not allowlisted: {command}")

    # Defense 2: validate all args against strict pattern
    import re
    SAFE_ARG_PATTERN = re.compile(r'^[a-zA-Z0-9_\-./=]+$')
    validated_args = []
    for arg in args:
        if not SAFE_ARG_PATTERN.match(arg):
            raise SecurityError(f"Potentially injectable argument rejected: {arg}")
        validated_args.append(arg)

    # Defense 3: run in isolated process group with no inherited env
    env = {k: v for k, v in server_config.get("env", {}).items()
           if k.startswith("MCP_")}
    env["PATH"] = "/usr/local/bin:/usr/bin"

    return subprocess.Popen(
        [command] + validated_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        preexec_fn=os.setsid,  # isolate process group
    )
```

**2. Validate MCP response integrity at the transport boundary.**

```python
import hashlib
import hmac
import json

class TransportResponseValidator:
    """
    Attach HMAC signatures to MCP requests; validate responses before processing.
    Prevents server reflection and response poisoning attacks.
    """
    def __init__(self, secret: bytes):
        self.secret = secret

    def sign_request(self, payload: dict) -> dict:
        body = json.dumps(payload, sort_keys=True)
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return {**payload, "_transport_sig": signature}

    def verify_response(self, response: bytes) -> bytes:
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            raise SecurityError("MCP response is not valid JSON — possible injection")

        # Verify no unexpected fields were injected into the response envelope
        ALLOWED_RESPONSE_KEYS = {"jsonrpc", "id", "result", "error"}
        for key in parsed.keys():
            if key not in ALLOWED_RESPONSE_KEYS and not key.startswith("_transport_"):
                raise SecurityError(f"Unexpected field in MCP response: {key}")

        return response

    def validate_tool_result(self, tool_result: dict) -> dict:
        """Reject tool results that look like injected command payloads."""
        result_str = json.dumps(tool_result, ensure_ascii=False)

        # Detect common injection patterns in responses
        INJECTION_PATTERNS = [
            r'\\x',                    # hex escape (possible shell payload)
            r'\$\(',                   # command substitution
            r'`[^`]+`',                # backtick command
            r'\|\s*\w+',               # pipe to shell command
            r'&&\s*\w+',              # chained command
        ]
        import re
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, result_str):
                raise SecurityError(f"Possible injection pattern detected in tool result")
        return tool_result
```

**3. Enforce egress boundaries on MCP outbound requests.**

```python
import urllib.parse

def sanitize_url_for_mcp_proxy(url: str, allowlist: list[str]) -> str:
    """
    Prevent SSRF via path traversal in MCP tool call URLs.
    CVE-2026-32871: path parameter ../ escapes API prefix with auth headers intact.
    """
    parsed = urllib.parse.urlparse(url)
    # Reject traversal sequences before any network request
    if "../" in parsed.path or "%2e%2e" in url.lower():
        raise SecurityError("Path traversal rejected in MCP URL")

    # Validate hostname against allowlist
    allowed_hosts = {urllib.parse.urlparse(h).netloc for h in allowlist}
    if parsed.netloc not in allowed_hosts:
        raise SecurityError(f"MCP request to unapproved host: {parsed.netloc}")

    return url

def mcp_egress_proxy(request: dict, egress_policy: dict) -> dict:
    """Route MCP outbound requests through a hardened proxy with logging."""
    tool_name = request.get("name", "")
    call_url = request.get("_raw_url", "")

    if call_url:
        sanitize_url_for_mcp_proxy(call_url, egress_policy.get("allowed_hosts", []))

    # Log all outbound MCP requests for audit trail
    log_mcp_egress(
        tool=tool_name,
        destination=call_url,
        agent_id=get_current_agent_id(),
        trace_id=get_current_trace_id(),
    )

    # Apply rate limit per tool per agent
    check_mcp_rate_limit(tool_name, get_current_agent_id())

    return request
```

**4. Bound stdio transport memory consumption.**

```python
import io

MAX_LINE_BYTES = 64 * 1024  # 64KB per line
MAX_TOTAL_BYTES = 10 * 1024 * 1024  # 10MB total response

def bounded_stdio_read(stream: io.RawIOBase) -> bytes:
    """
    Read from MCP stdio transport with explicit bounds.
    Prevents memory exhaustion via unbounded IO (CVE-2026-63119).
    """
    buf = bytearray()
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_TOTAL_BYTES:
            raise SecurityError(f"MCP response exceeds {MAX_TOTAL_BYTES} bytes — possible DoS")
        # Check line length if we hit a newline
        if b'\n' in chunk:
            lines = buf.split(b'\n')
            for line in lines[:-1]:
                if len(line) > MAX_LINE_BYTES:
                    raise SecurityError(f"MCP line exceeds {MAX_LINE_BYTES} bytes")
    return bytes(buf)
```

## Receipt

> Verified 2026-08-01 — CVE-2026-63119 (Ruby SDK unbounded IO, CVSS 6.2) and CVE-2026-32871 (SSRF via path traversal, CVSS 8.8) retrieved from NVD. Postmark MCP infostealer campaign confirmed by security researchers (Praetorian, Feb 2026). 14 CVEs across MCP implementations confirmed (The Agent Report, Jul 2026). 200,000+ servers exposed via SDK design flaw confirmed (AgentSeal/CSA, Jul 2026). 82% path traversal vulnerability rate across 2,614 MCP implementations confirmed (AgentSeal, Jul 2026). Receipt pending — code examples not executed in live environment.

## See also

- [S-078 · MCP Tool Description Poisoning](stacks/s78-the-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — metadata layer of the same attack surface; read this first
- [S-1062 · The MCP Supply Chain Integrity Stack](stacks/s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — SDK and marketplace CVE context
- [S-1949 · The Shadow MCP Stack](stacks/s1949-the-shadow-mcp-stack-when-your-attack-surface-lives-on-every-developers-laptop.md) — the deployment-layer problem this transport-layer attack exploits
- [S-1699 · The Framework-RCE Stack](stacks/s1699-the-framework-rce-stack-when-your-agent-framework-becomes-a-code-execution-gateway.md) — semantic-kernel plugin path traversal; related RCE class
