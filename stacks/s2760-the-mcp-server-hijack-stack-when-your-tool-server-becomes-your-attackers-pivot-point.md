# S2760 · The MCP Server Hijack Stack — When Your Tool Server Becomes Your Attacker's Pivot Point

Your agent authenticates to your MCP server. The MCP server can read your filesystem, query your database, send emails, and run code. That MCP server is the attack surface.

## Forces

- MCP gives your agent privileged access to infrastructure — and any compromise of the server pivots that access directly into your environment
- Server-side vulnerabilities in MCP servers bypass every client-side safeguard you deployed
- The protocol's composability means a hijacked server cascades across every agent that chains it
- Transport-layer injection (SSE, WebSocket) operates beneath the tool-calling layer, invisible to traditional defenses

## The move

**The attack surface is the server, not the model.** MCP tool-description poisoning (S-743) corrupts what the model *knows about* its tools. This stack covers what happens when attackers compromise *the server itself* — its code, its transport, or its network path — so the model runs genuinely malicious tooling.

### The six attack vectors

**1. RCE via unsafe eval in the server**
MCP servers written for convenience use `eval()`, `exec()`, or `subprocess` with unsanitized input. The agent never sees the exploit — it sends a legitimate-looking tool call and the server executes arbitrary code.
```
CVE-2026-44717: MCP Calculate Server < 0.1.1 — eval() on math expressions → RCE, CVSS 9.8
CVE-2026-56274: FlowiseAI Custom MCP Server — OS command injection, CVSS 9.9
```
Fix: zero `eval`/`exec` in MCP server code. Use sandboxed expression evaluators (AST-walking parsers, not string execution).

**2. Path traversal in network-facing transports**
When MCP servers run in SSE or Streamable-HTTP mode (the documented remote deployment pattern), server-side input validation often fails to constrain file paths.
```
CVE-2026-40576: excel-mcp server in SSE mode — arbitrary file read/write via unvalidated filepath arguments,
no authentication, binds to 0.0.0.0 by default
CVE-2026-58500: MCP Appium — XSS in UI resource rendering via unescaped locator attributes
```
Fix: strict allowlist for file operations, no path join without canonical resolution, auth on all network transports.

**3. SSE transport injection**
SSE is a unidirectional stream from server to client over HTTP. If an attacker can inject into the SSE stream (via a compromised upstream server, a MITM on the HTTP path, or a malicious HTTP redirect), they can send fake MCP protocol messages that the client renders as legitimate tool responses or prompts.
- Attack: compromise the HTTP path → inject `data: ` lines → client processes as MCP protocol messages
- Defense: TLS on all MCP connections, validate `Content-Type: text/event-stream`, use signed SSE streams

**4. Server supply chain compromise**
An MCP server is just a third-party service your agent calls. If that service is compromised — malicious update, compromised registry, dependency confusion — your agent becomes a vehicle for the attacker's payload, even if your prompt and tool definitions are pristine.
- 313+ MCP-related CVEs indexed in the MCP CVE project (mcp-security-project/mcp-cve-project)
- Attack surface: npm/pypi package typosquatting, compromised CI/CD pipelines, deprecated servers with known CVEs still running
```
GHSA-8rgw-6xp9-2fg3: playwright-mcp — silently patched RCE, no CVE assigned
```
Fix: pin server versions, verify package integrity hashes, run servers in isolated network segments, maintain an MCP server SBOM.

**5. MCP server credential relay**
An MCP server that holds credentials (API keys, database passwords, OAuth tokens) to perform its function is a single point of compromise. If the server is breached, all credentials it held are exposed — and since the server had privileged access to act on behalf of the agent, the attacker inherits that privilege.
- Don't embed long-lived credentials in MCP server environments
- Use short-lived, scoped credential issuance (Vault-style secret broker)
- Audit what credentials each MCP server *actually needs* vs. what it was granted

**6. Agentic browser / UI rendering attacks via MCP resources**
MCP resources are data blobs the agent can read and present. If a server returns HTML or JavaScript content as a resource (e.g., Playwright MCP returning UI snapshots, or any server rendering dynamic content), rendering that content can execute arbitrary JS in the agent's context.
```
CVE-2026-58500: MCP Appium — XSS via unescaped element attributes in generated UI resources
```
Fix: sanitize all resource content before rendering, set CSP headers on any HTTP server component, never render untrusted HTML/JS as a resource.

### Defense posture checklist

```
Network layer:
  □ TLS on all MCP transports (SSE, WebSocket, HTTP)
  □ Auth on all network-facing MCP servers
  □ MCP servers in DMZ, not on internal network
  □ Least-privilege network policy (MCP server → only its target API, nothing else)

Code execution layer:
  □ Zero eval/exec in any MCP server implementation
  □ Input validation with allowlists (not denylists)
  □ gVisor or Firecracker isolation around MCP server processes

Credential layer:
  □ Short-lived scoped credentials per server
  □ Secret broker (Vault, AWS Secrets Manager) — MCP server never holds long-lived secrets
  □ Audit which servers hold which credentials

Supply chain layer:
  □ Pin and hash all MCP server versions
  □ Maintain MCP server SBOM
  □ Monitor for new CVEs against deployed servers (313+ and growing)
  □ Automated CVE alerts for MCP dependencies

Agentic layer:
  □ MCP server runs in its own least-privilege identity
  □ Telemetry on every MCP server response (was the output what you expected?)
  □ Circuit breaker: if a server returns anomalous content, sever the connection
  □ Treat MCP servers as untrusted third parties — the agent can call them, but the agent's security posture must not depend on their integrity
```

## Receipt

> Receipt pending — 2026-08-17

## See also

- [S-743 · MCP Tool Description Poisoning](/stacks/s743-the-mcp-tool-description-poisoning-stack-when-your-schema-is-your-attack-surface) — tool schema poisoning (the knowledge layer)
- [S-2709 · The MCP Schema Inflation Trap](/stacks/s2709-the-mcp-schema-inflation-trap-when-your-protocol-tax-costs-more-than-your-queries.md) — MCP protocol overhead
- [S-2711 · The MCP A2A Protocol Axis Failure](/stacks/s2711-the-mcp-a2a-protocol-axis-failure-stack-when-mcp-works-but-cross-agent-coordination-fails.md) — cross-agent coordination
