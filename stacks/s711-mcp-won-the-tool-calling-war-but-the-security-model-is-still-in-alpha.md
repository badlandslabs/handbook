# S-711 · MCP Won the Tool-Calling War — But the Security Model Is Still in Alpha

[Your agents need to call tools: search, write to a database, trigger a Slack message, query the internal knowledge base. You've standardized on MCP because that's what everyone else uses. But the protocol's authorization model is underspecified, 40+ CVEs landed against MCP implementations in four months, and command injection is a live vulnerability class in many popular servers. The ecosystem is real; the production-readiness bar is not uniformly met. You need to know which parts of MCP are solid and which are liability until the spec matures.]

## Forces

- **The network effect is decisive.** MCP crossed 10,000 active public servers, 15,926 GitHub repos, and 97M+ monthly SDK downloads (Anthropic, Dec 2025) in under a year. When every AI app ships an MCP client and every tool provider exposes an MCP server, the protocol wins by default — even if it's not the cleanest design.
- **Security was an afterthought, not a foundation.** MCP was released with a flexible, underspecified design. Between January and April 2026, researchers filed 40+ CVEs against MCP implementations across every SDK language Anthropic ships: Python, TypeScript, Java, Rust. The protocol reverses a familiar interaction pattern — servers can query and execute actions for clients — creating attack paths that most teams haven't mapped.
- **Authorization is the biggest gap.** The MCP spec's authorization layer is documented but inconsistently implemented. Remote MCP servers (80% of top servers support remote deployment) are particularly exposed: an unauthenticated server accepting connections from an agent is a live intrusion vector. Most teams don't have a threat model for "malicious MCP server" versus "malicious input to an MCP server."
- **Command injection is a live vulnerability class.** Local MCP servers may execute arbitrary commands. Poorly implemented servers pass unsanitized data directly into shell calls. The NSA flagged it explicitly: verify server integrity, scan dependencies, sanitize every argument before it reaches a command that executes.
- **The protocol inversion is the root risk.** Traditional systems: clients request data from servers. MCP: servers often query and act for clients. This means the agent's attack surface expands to every MCP server it trusts — and 9 out of 11 MCP marketplaces accepted poisoned proof-of-concept submissions without detection (Red Hat, 2025).

## The move

**Adopt MCP as your tool-calling substrate — but wrap it with a security posture that assumes the spec hasn't caught up to production yet.**

- **Treat every MCP server as a third-party dependency with the authority of a system call.** Vet server provenance. Pin versions. Subscribe to security advisories for servers you depend on. A server that can trigger a Slack message can also trigger `rm -rf /` if the implementation has a command injection gap.
- **Scope server permissions like a least-privilege OS.** Give each server only the tools it needs, nothing more. Separate your "read-only knowledge base" server from your "write to database" server. A monolithic "admin" MCP server that your agent trusts is an incident waiting to happen.
- **Implement authorization on remote MCP servers before production traffic.** Don't rely on the protocol's flexibility — add explicit authentication (API keys, OAuth tokens) on any server exposed over the network. The default is permissive.
- **Sanitize every input at the client boundary.** Even from servers you wrote yourself. The attack pattern is: malicious data flows into a server, the server passes it to the client, the client passes it to the LLM, the LLM instructs the server to execute. Treat every tool response as untrusted input.
- **Add human-in-the-loop gates before irreversible MCP calls.** Sending emails, writing to databases, triggering payments — any tool with side effects should require an explicit approval step. MCP makes calling tools easy; it doesn't make them safe.
- **Evaluate your MCP security posture at the same cadence as your dependency audit.** MCP is infrastructure, not application code. Monitor CVE feeds for `modelcontextprotocol` and every server package you run.

## Evidence

- **Anthropic ecosystem announcement (Dec 2025):** MCP reached 10,000+ active public servers, 97M+ monthly SDK downloads, and 86,148 GitHub stars on `modelcontextprotocol/servers`. The adoption curve is vertical. — [Anthropic AAIF, Dec 2025](https://www.anthropic.com/news/aaif-2025)
- **NSA security guidance (2026):** The NSA/CISA published MCP security design considerations documenting the protocol's underspecified authorization model, command injection risks, and the 40+ CVEs filed against MCP implementations Jan–Apr 2026 across Python, TypeScript, Java, and Rust SDKs. — [NSA CSI: MCP Security (PDF)](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf)
- **Red Hat security analysis (Jul 2025):** MCP's architecture inverts the traditional client-server trust model. The protocol gives servers the ability to execute actions on behalf of clients — the same authority as an authenticated OS call. 80% of top servers support remote deployment, expanding the attack surface beyond localhost. — [Red Hat: MCP Security Risks and Controls](https://www.redhat.com/en/blog/model-context-protocol-mcp-understanding-security-risks-and-controls)
- **Block enterprise data (Apr 2025):** Employees using MCP-powered tooling (specifically GitHub's Goose agent) report 50–75% time savings on common tasks. Security remains the primary barrier to broader deployment, with 50% citing security complexity as the top challenge (Stacklok 2026 survey). — [Block Blog: MCP in Enterprise](https://block.github.io/goose/blog/2025/04/21/mcp-in-enterprise/)

## Gotchas

- **MCP's authorization spec exists but isn't enforced.** The protocol defines how authorization should work; the SDK implementations vary. Check your specific SDK's auth support before assuming it's covered.
- **Remote servers break the localhost trust assumption.** The protocol was designed with local servers in mind. Exposing a server over the network without adding auth is equivalent to leaving a privileged API unauthenticated.
- **A poisoned MCP server can persist across sessions.** If a malicious server is installed before you catch it, it may retain access to historical context and tool state. Vet servers on install, not just on first use.
- **Tool schema enumeration leaks intent.** An attacker who can observe what tools an MCP server exposes (even without calling them) learns what your agent is designed to do. Minimize the number of servers visible to untrusted contexts.
- **The 40+ CVEs are real, not theoretical.** The CVE timeline (Jan–Apr 2026) shows active exploitation research, not just security researchers filing reports. Patch your SDKs. Monitor your servers.
