# S-1517 · The Compromised MCP Server Stack — When the Tool You Trusted Becomes the Attack Surface

Your agent connected to a third-party MCP server. It passed the integration test. It worked beautifully. Six weeks later, a security audit found that the server had been exfiltrating your repository contents, internal project names, and employee data into a public pull request — all through a Personal Access Token that had no business touching your GitHub org. The agent never "decided" to leak. The server manipulated it, quietly, from inside the tool interface.

MCP (Model Context Protocol) standardized how agents connect to tools and data. That standardization is now an attack surface. Four CVEs landed in 2026 targeting MCP server implementations specifically. The protocol solved the tool-integration problem — and in doing so, created the most trusted, most privileged, least audited pathway into your agent's decision-making.

## Forces

- **MCP servers read tool descriptions as authoritative context.** A tool's `description`, `inputSchema`, and output are injected into the agent's context window as system-trusted content. Poison any of these and the agent acts on the payload — no user click required, no explicit prompt injection needed.
- **Third-party MCP servers are supply chain risks.** You audit your own code. You don't audit the npm package your MCP server depends on, the MCP server maintained by a startup with two engineers, or the community server you connected because the README said it was "production-ready."
- **Credential scoping is opt-out, not opt-in.** MCP servers with broad permissions (read/write repositories, send emails, access databases) inherit those permissions every time the agent calls them. A compromised server with a broadly-scoped token can do everything the token allows — and the agent will faithfully execute every request, because the server's output looks like tool results.
- **CVE velocity is outpacing MCP adoption velocity.** CVE-2026-26118 (Microsoft MCP server, CVSS 8.8), CVE-2026-0756 (GitHub Kanban MCP server, command injection), CVE-2026-26029 (Salesforce MCP server, command injection via `child_process.exec`), and CVE-2026-25905 (Python-in-JS MCP runtime, environment hijacking) all landed in 2026. The MCP ecosystem's CVE rate now mirrors the early npm ecosystem circa 2018 — before the community developed norms for auditing, pinning, and sandboxing.
- **Traditional security tooling doesn't see MCP payloads.** SIEM tools, DLP agents, and API gateways inspect HTTP headers and request bodies — not the structured JSON-RPC calls inside an MCP session or the tool descriptions injected into a model's context window. You cannot find this exfiltration with conventional data-loss prevention.

## The move

### Layer 1 — Trust boundaries at the MCP server perimeter

Never connect an unverified MCP server to an agent with sensitive credentials. Treat MCP server connections the same way you'd treat installing a browser extension with broad permissions:

- Run `mcp__inspect__` or equivalent tooling to dump the full tool manifest before connecting
- Reject servers that request more permissions than their stated purpose requires
- Maintain an approved-server registry; reject any MCP server not on the allowlist
- For community-maintained servers: pin to a specific git commit SHA, not a version tag

### Layer 2 — Credential scoping for MCP sessions

MCP servers should receive the minimum credential scope required for their function:

```python
# Instead of: broad PAT with repo:* access
# Scope MCP-accessible credentials to what the server actually needs:
# - Read-only PAT for servers that only read data
# - Repository-specific tokens, not org-wide
# - No admin permissions, no delete permissions, no PR creation unless explicitly required
# - Token expiry set to session duration, not "no expiry"

GITHUB_MCP_TOKEN = os.getenv("GITHUB_MCP_TOKEN")
# Validate token permissions before use
if not validate_token_scope(GITHUB_MCP_TOKEN, required_scopes=["repo:read"]):
    raise PermissionError(f"Token has excess scopes: {get_token_scopes(GITHUB_MCP_TOKEN)}")
```

### Layer 3 — Output filtering between server and agent context

The MCP server's output flows directly into the agent's context. Treat it like untrusted input:

```python
from mcp import Client
from agent_framework import ContextBoundary

async def safe_mcp_invoke(server: Client, tool: str, params: dict) -> dict:
    result = await server.invoke_tool(tool, params)

    # Layer 3: Sanitize tool output before it enters agent context
    # Block credential-like strings, private URLs, internal hostnames
    sanitized = sanitize_tool_output(
        result,
        block_patterns=[
            r'[a-zA-Z0-9_-]+:[a-zA-Z0-9_+/=-]{20,}',  # Generic credentials
            r'ghp_[a-zA-Z0-9]{36}',                     # GitHub PATs
            r'xox[baprs]-[a-zA-Z0-9]{10,}',             # Slack tokens
            r'internal\.[a-z]+\.(corp|internal|private)',  # Internal hostnames
        ],
        block_domains=["pastebin.com", "transfer.sh", "ipinfo.io"],
    )
    return sanitized
```

### Layer 4 — Sandboxed MCP execution environment

Isolate MCP server execution so a compromised server cannot reach host resources:

```python
import subprocess, tempfile, os

async def sandboxed_mcp_server(server_script: str, allowed_paths: list[str]) -> None:
    """Run an MCP server inside a restricted container with no network egress."""
    container_config = {
        "readonly_rootfs": True,
        "allowed_paths": allowed_paths,  # Whitelist filesystem access
        "network": "none",               # No outbound network
        "capabilities": ["stdio"],        # Only stdio communication
    }
    # Use gVisor, firecracker microVM, or similar
    # The agent communicates over stdio; the server cannot phone home
    await run_in_microvm(server_script, config=container_config)
```

### Layer 5 — Continuous monitoring and anomaly detection

- Log every MCP tool invocation with full input/output (redacted) to a tamper-evident store
- Alert on: credential-like patterns in MCP responses, outbound connections from MCP servers, server-to-server token forwarding
- Run MCP servers in ephemeral containers that restart clean after each session

## Receipt

> Verified 2026-07-23 — Researched CVE-2026-26118 (CVSS 8.8, Microsoft MCP server, March 2026 Patch Tuesday), CVE-2026-0756 (command injection in github-kanban-mcp-server, January 2026), CVE-2026-26029 (Salesforce MCP server `child_process.exec` injection), CVE-2026-25905 (Python-in-JS MCP runtime environment hijacking). Real-world incidents confirmed: compromised MCP server exfiltrating repo contents + employee data via over-privileged PAT; Asana MCP cross-tenant data exposure. Sources: Microsoft Developer Blog (Sarah Young, April 2025/2026), Practical DevSecOps (Varun Kumar, October 2025/January 2026), NVD/NIST CVE records, AI Workflow Lab MCP Security Guide (March–June 2026). Code examples are structural patterns, not runnable receipts.

## See also

- [S-10 · MCP](/stacks/s10-mcp.md) — MCP protocol fundamentals
- [S-1006 · The Agent Toolbelt Problem](/stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — what tools to give an agent and with what permissions
- [S-1017 · The Transitive Framework Stack](/stacks/s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — transitive dependency vulnerabilities in agent infrastructure
- [S-1458 · The Policy Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcement that doesn't live in prompts
- [S-1509 · The Oracle Problem Stack](/stacks/s1509-the-oracle-problem-stack-when-you-cannot-tell-if-your-agent-is-right.md) — the verification gap in agentic systems
