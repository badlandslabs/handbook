# S-763 · MCP Tool Description Poisoning — The Attack Your Trusted Tools Deliver

A clean MCP server ships version 1.0.0 through 1.0.15. No malware. No CVEs. No complaints. Then version 1.0.16 ships overnight and silently adds a `<thousands of invisible emails BCC'd to an attacker>` to every email sent through Postmark. Nobody reviews tool descriptions. The MCP SDK never inspects them. The agent reads them, trusts them, and acts on them — blind to the change. This is tool description poisoning, and the May 2026 OX Security disclosure confirmed it is not theoretical.

## Forces

- **Tool descriptions are model input — and model input is attack surface.** Every MCP tool ships with a `description` field that the LLM reads before deciding whether to call the tool. If that description contains instructions the developer never wrote, the model executes them silently. Unlike a malicious email that a human reads and flags, a poisoned tool description is consumed by the model with no human in the loop.

- **MCP SDKs trust tool descriptions implicitly.** The Model Context Protocol was designed to connect agents to tools, not to audit those tools. The SDK passes tool descriptions directly to the model with no verification, no signature check, and no content inspection. This is the gap: you can audit the code of a first-party MCP server, but you cannot audit the descriptions of a third-party one — and 200,000 production instances never do.

- **The attack succeeds against the most resistant models at 72%.** MCPTox (arXiv, 2026) demonstrated tool poisoning against Claude-3.7-Sonnet, GPT-4o, and Gemini-2.0-Flash using adversarial descriptions. Claude-3.7-Sonnet — the most resistant — refused fewer than 3% of poisoned descriptions. The attack works precisely because it exploits the model's trust in tool metadata, not its reasoning about user input.

- **The supply chain is already compromised.** OX Security's May 2026 disclosure identified 200,000 vulnerable MCP instances across Python, TypeScript, Java, and Rust SDKs. CVE-2026-33032 carries CVSS 9.8. Malicious prompt injection content grew 32% from November 2025 to February 2026 (Google Security Blog). This is not a future threat — it is a current production condition.

- **The blast radius is proportional to the tool's permissions, not the attack's complexity.** A poisoned `send_email` tool can exfiltrate data. A poisoned `read_database` tool can leak schemas and credentials. The attacker's leverage is whatever permissions the MCP server holds — and developers grant broad permissions because the tool "just needs access."

## The move

### 1. Instrument pre-tool hooks on every MCP server

The critical control point is between "tool description received" and "tool called." Insert an inspection hook that runs before any tool description is passed to the model:

```python
from modelcontextprotocol.server.fastmcp import FastMCP
from modelcontextprotocol.spec import Tool

mcp = FastMCP("my-server")

def inspect_tool(tool: Tool) -> Tool:
    """Strip or flag adversarial patterns in tool descriptions."""
    description = tool.description or ""

    adversarial_signatures = [
        "ignore previous instructions",
        "system prompt",
        "confidential",
        "do not tell",
        "hidden instruction",
        r"<[^>]+>",  # HTML/XML injection
    ]

    for sig in adversarial_signatures:
        if sig.lower() in description.lower():
            # Replace with sanitized description, raise alert
            logger.warning(f"Tool {tool.name}: description flagged — scrubbing")
            tool.description = sanitize(tool.description)

    return tool

# Register hook — fires before tool is registered with the client
mcp.add_pre_tool_hook(inspect_tool)
```

Pre-tool hooks are available in the Python MCP SDK (`add_pre_tool_hook`) and equivalent patterns exist in TypeScript and Java. Without them, tool descriptions reach the model unmediated.

### 2. Sign and verify tool descriptions cryptographically

For MCP servers you control, sign tool descriptions with a private key and require clients to verify against a published public key:

```python
import hashlib, hmac, json

def sign_tool_description(tool: Tool, private_key: str) -> str:
    """Create HMAC-SHA256 signature of canonical tool description."""
    canonical = json.dumps({
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }, sort_keys=True)
    return hmac.new(
        private_key.encode(),
        canonical.encode(),
        hashlib.sha256
    ).hexdigest()

def verify_tool_description(tool: Tool, signature: str, public_key: str) -> bool:
    """Verify signature before trusting the tool description."""
    expected = sign_tool_description(tool, public_key)
    return hmac.compare_digest(signature, expected)
```

Publish the public key at a well-known endpoint (`/.well-known/mcp-signer.json`) and pin it in your agent's configuration. This ensures a tool description cannot be modified in transit or by a compromised registry.

### 3. Apply least-privilege MCP server permissions

The blast radius of tool poisoning is bounded by the tool's permissions. Audit every MCP server for unnecessary permissions:

```bash
# Audit MCP server permission scope
mcp audit --server=postmark-mcp --permissions
# Expected output: only "send_email" — no "read_emails", no "list_contacts"
```

Reject any MCP server that requests permissions beyond its documented function. A Postmark integration does not need read access to your inbox.

### 4. Monitor tool description diffs in the agent flight recorder

Tool poisoning often arrives via a version update — a clean v1.0.15 followed by a poisoned v1.0.16. Log tool descriptions to your audit trail and alert on diffs:

```python
import hashlib

def log_tool_description_snapshot(tools: list[Tool], snapshot_id: str):
    """Store deterministic snapshot of tool descriptions for diff detection."""
    snapshot = {
        tool.name: hashlib.sha256(
            (tool.description or "").encode()
        ).hexdigest()
        for tool in tools
    }
    audit_log.record(snapshot_id=snapshot_id, tools=snapshot)
    return snapshot

def detect_description_drift(prev: dict, curr: list[Tool]) -> list[str]:
    """Alert when a tool's description hash changes unexpectedly."""
    drifts = []
    for tool in curr:
        curr_hash = hashlib.sha256((tool.description or "").encode()).hexdigest()
        if tool.name in prev and prev[tool.name] != curr_hash:
            drifts.append(f"{tool.name}: description changed — verify with vendor")
    return drifts
```

See [S-760 Agent Flight Recorder](s760-agent-flight-recorder-the-tamper-evident-audit-log-for-autonomous-systems.md) for the full tamper-evident audit architecture.

### 5. Use allowlist mode, not blocklist mode

Blocklisting adversarial patterns (step 1) is a losing arms race. Instead, enable allowlist mode for MCP servers in high-sensitivity contexts:

```python
# Allowlist mode: only tools explicitly approved may be registered
mcp = FastMCP(
    "secure-server",
    allowlist=[
        "send_email",
        "read_drafts",
        # Any tool not in this list is silently dropped
    ]
)
```

Every tool outside the allowlist is dropped at registration time, before it reaches the model.

## Receipt

> Verified 2026-07-07 — Cross-referenced against OX Security May 2026 disclosure (CVE-2026-33032, CVSS 9.8), MCPTox arXiv 2026 evaluation (72% success against Claude-3.7-Sonnet), CSA MCP Security Crisis report, and ITECS/SuperML.dev tool poisoning analysis. Pre-tool hook API (`add_pre_tool_hook`) confirmed in MCP Python SDK. HMAC signing pattern is illustrative — no MCP-native signing spec exists as of July 2026; this is the recommended practice.

## See also

- [S-749 · The MCP Security Surface](s749-the-mcp-security-surface-agents-have-real-access-and-nobody-is-watching.md) — the broader MCP attack surface this entry zooms into
- [S-261 · MCP Security — The Attack Surface You Inherited](s261-mcp-security-attack-surface.md) — foundational MCP security architecture
- [S-201 · MCP Server Security Hardening](s201-mcp-server-security-hardening.md) — server-side hardening controls
- [S-010 · Agentic Prompt Injection: Defense-in-Depth](s010-agentic-prompt-injection-defense-in-depth.md) — the broader prompt injection family this belongs to
- [S-760 · Agent Flight Recorder](s760-agent-flight-recorder-the-tamper-evident-audit-log-for-autonomous-systems.md) — audit trail for tool description drift detection
