# S-2657 · The MCP Server Supply Chain Stack — When Your Agent Registers a Server Nobody Vetted

Your agent calls a tool. The tool doesn't exist in your codebase. It exists because the agent asked for it, the MCP client connected to an STDIO server it found on the system PATH, and that server ran with the same OS privileges as everything else. This is not a misconfiguration. It is the intended design. And it is the most dangerous trust assumption your agent stack is making right now.

## Forces

- **MCP's reach is its attack surface.** The Model Context Protocol has become the default way agents connect to tools, data, and enterprise systems. The same property that makes it powerful — runtime server registration and transparent tool discovery — also creates a supply chain that runs entirely outside your infrastructure review process.
- **The STDIO mechanism is intentional and everywhere.** Anthropic confirmed in April 2026 that the STDIO interface — which allows MCP clients to spawn arbitrary processes as servers — is a deliberate design choice, not a bug. It exists in all four official SDKs (Python, TypeScript, Java, Rust). This is the mechanism that makes MCP servers "just work." It is also the mechanism that lets a compromised or malicious server run on your system.
- **Enterprise frameworks add auth gaps on top of the protocol.** CSA research (April 2026, OX Security) documented authentication bypass in LiteLLM, LangChain, and LangFlow's MCP server configuration interfaces — three platforms that underpin the majority of enterprise AI agent deployments. An unauthenticated attacker can register a malicious STDIO server and trigger execution simply by initiating an agent session.
- **CVEs are multiplying in MCP tooling.** The kubectl-mcp-server (CVE-2025-65719), Archon OS MCP (CVE-2025-69443), and MarkItDown MCP — all 2025-2026 disclosures — share the same root cause: MCP server code runs with the trust level of the agent, not the trust level of the tool it exposes. The kubectl CVE allowed arbitrary code execution via a crafted HTML page. The MarkItDown CVE enabled arbitrary file read from the host filesystem.
- **You don't know what's in your agent's server registry.** In multi-agent and LangChain/LangGraph deployments, sub-agents can register MCP servers at runtime. Your CI pipeline reviewed your code. It did not review the servers your agent decided to connect to during execution.

## The move

Treat your MCP server registry as an untrusted supply chain. Every server is a dependency with OS-level access. Apply the same scrutiny you'd apply to a npm install you found on a random GitHub repo.

**1. Trust tiering for MCP servers.** Classify every MCP server into a tier before it touches production:

| Tier | Description | Policy |
|------|-------------|--------|
| T1 | First-party, code-reviewed, same repo | Full access, no restrictions |
| T2 | Third-party, open-source, audited | Read-only by default, explicit write allowlist |
| T3 | Dynamic / user-provided / PATH-discovered | No access, sandboxed execution, egress filtered |

The CSA research showed that T3 is the default for LangChain/LangGraph/LiteLLM deployments where MCP server configs are loaded at runtime from user input or external config. Move everything to T1 or T2.

**2. Deploy an MCP gateway.** Don't connect agents directly to MCP servers. Route through a gateway that enforces: (a) server allowlist before connection, (b) request/response inspection, (c) identity attestation per server, (d) per-server rate limits and cost controls. Microsoft recommended this pattern in their 2026 MCP security overview: self-contained requests allow a gateway to inspect and enforce every call without trusting hidden sessions.

**3. Input validation at the server registration boundary.** The Flowise platform received CVE-2026-40933 (CVSS 10.0) for an MCP adapter input validation bypass — even configurations with nominal input restrictions were exploitable. Validate not just the tool name and parameters, but the server's executable path, environment variables, and network egress at registration time.

**4. Egress filtering and least privilege per server.** Each MCP server process should run with the minimum permissions it actually needs — not the permissions of the agent process. Kubernetes network policies, seccomp profiles, and gVisor-based micro-containers for MCP tool execution limit blast radius when a server is compromised.

**5. Audit the registry continuously.** MCP servers can be registered dynamically at runtime. Your static analysis of the codebase doesn't catch them. Instrument the MCP client to log every server registration event with: server name, executable path, connecting agent session, and timestamp. Treat unregistered servers as incidents.

## Example

```python
# MCP Gateway server allowlist enforcement
from mcp_gateway import Gateway, ServerPolicy

ALLOWED_SERVERS = {
    "file_ops": {
        "executable": "/opt/mcp-servers/file-ops",
        "trust_tier": 1,
        "egress": ["s3.amazonaws.com"],
        "read_only": True,
    },
    "database_proxy": {
        "executable": "/opt/mcp-servers/db-proxy",
        "trust_tier": 2,
        "egress": ["internal-db.company.internal:5432"],
        "read_only": True,
    },
}

gateway = Gateway(policy=ServerPolicy.ALLOWLIST_WITH_LOGGING)

# On agent request to use a server
def on_server_request(server_id: str, agent_session: str) -> bool:
    if server_id not in ALLOWED_SERVERS:
        # Alert: dynamic server registration attempt
        alert_security_team(
            event="mcp_unregistered_server",
            server_id=server_id,
            agent_session=agent_session,
            source="agent_runtime",
        )
        return False  # Blocked

    server = ALLOWED_SERVERS[server_id]
    log_audit(
        event="mcp_server_invoked",
        server_id=server_id,
        trust_tier=server["trust_tier"],
        agent_session=agent_session,
        egress=server["egress"],
    )
    return True

# Enforce egress per server
def enforce_egress(server_id: str, target: str) -> bool:
    allowed = ALLOWED_SERVERS.get(server_id, {}).get("egress", [])
    if not allowed:
        return False  # No network access for this server
    return target in allowed
```

## Receipt

> Verified 2026-08-14 — Sources: CSA Research Note (OX Security, April 20, 2026) — "MCP by Design: RCE Across the AI Agent Ecosystem"; Microsoft Tech Community (2026) — "The State of MCP Security in 2026"; OX Security blog (May 12, 2026) — "MCP Security Alert: kubectl-mcp-server, Archon OS, and MarkItDown Vulnerabilities." Cross-referenced: CVE-2025-65719, CVE-2025-69443, CVE-2026-40933. Code example is illustrative — architectural pattern drawn from gateway pattern described in Microsoft MCP security post. Pattern applies to any LangChain, LangGraph, or LiteLLM deployment with dynamic MCP server registration.

## See also

- [S-2274 · The Isolation Spectrum Stack](/stacks/s2274-the-isolation-spectrum-stack-when-your-agent-runs-code-and-nobody-drew-the-fence.md) — Code execution isolation across the full sandbox spectrum
- [S-2627 · The Kernel Primitive Sandbox Stack](/stacks/s2627-the-kernel-primitive-sandbox-stack-when-shared-containers-cost-too-little-and-microvms-cost-too-much.md) — Container vs. microVM tradeoffs for tool execution
- [S-1000 · The Structural Agent Governance Stack](/stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — Prompt-based vs. structural governance enforcement
