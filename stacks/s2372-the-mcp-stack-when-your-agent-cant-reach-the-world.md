# S-2372 · The MCP Stack

When your agent needs to touch production systems — databases, cloud APIs, GitHub, Azure — and every bespoke tool integration becomes technical debt.

## Forces

- **The M×N integration problem**: With N agents and M tools, bespoke API integrations scale as N×M. Each pair has its own auth scheme, rate limits, error handling, and tool description format.
- **Agents need more than text**: Production agents must read files, call APIs, write to databases, trigger CI pipelines. Without a standard interface to these, every agent build reinvents the same wiring.
- **Credential sprawl kills security**: Ad-hoc tool integrations scatter credentials across agent configs. MCP's remote server pattern centralizes auth behind enterprise identity (Microsoft Entra ID), which ad-hoc approaches can't match.
- **Direct API calls don't work everywhere**: CLI-based tool access requires credentials on disk. That works for local dev; it fails for cloud-hosted agents, mobile, or any environment without filesystem access.
- **MCP isn't just a spec — it's an ecosystem**: The GitHub MCP Registry (Sept 2025), Azure MCP Server, and 1,000+ community servers mean the tool discovery problem is largely solved. The remaining gap is deployment patterns.

## The Move

Standardize on the Model Context Protocol (MCP) as the universal tool interface layer. Build remote MCP servers (not stdio) for production. For each tool domain, deploy a dedicated MCP server that handles auth, rate limiting, and the protocol translation — then any MCP-compatible agent plugs in without custom wiring.

**Specific patterns that hold up:**

- **One MCP server per domain** — Azure DevOps server, GitHub server, Slack server — keeps blast radius contained when a server is compromised or rate-limited. Microsoft's OWASP guidance explicitly recommends remote HTTP MCP over stdio for production precisely because stdio scatters credentials and bypasses enterprise identity controls.
- **Use the GitHub MCP Registry** (registry.modelcontextprotocol.com) to discover pre-built servers before writing custom ones. GitHub launched this in September 2025 specifically to solve MCP server discoverability.
- **Gate remote MCP servers behind Azure API Management or an equivalent gateway** — this enforces auth, adds rate limiting, and provides audit logs. Anthropic's guidance notes that direct API calls create bespoke security per integration; a gateway pattern standardizes it once.
- **Prefer stdio for local prototyping only** — the MCP 2026 roadmap explicitly migrated from a release-oriented spec model to working groups because production deployments surfaced different needs than early experiments. The stdio pattern that worked for local Cursor/Claude Code extensions doesn't transfer to cloud-hosted agents.
- **Design tools with narrow, specific capabilities** rather than one monolithic tool. A `create_github_issue` tool with structured parameters is safer and more predictable than a `run_shell_command` tool that can do anything.

## Evidence

- **Anthropic engineering post:** "Building agents that reach production systems with MCP" — Documents why Anthropic built MCP as an open standard: teams were reimplementing the same tool integrations across coding editors, web interfaces, and services. MCP lets them build once and deploy everywhere. Reports it became the fastest-growing open source protocol in history. — [claude.com/blog](https://claude.com/blog/building-agents-that-reach-production-systems-with-mcp)
- **Microsoft OWASP guidance (enterprise):** The "MCP Top 10 Security Guidance" document outlines production deployment patterns — specifically recommends remote HTTP MCP servers over stdio for enterprise because stdio "creates credential sprawl, bypasses enterprise identity and policy controls, and provides zero visibility." Documents the gateway pattern as the recommended production architecture. — [microsoft.github.io/mcp-azure-security-guide](https://microsoft.github.io/mcp-azure-security-guide/adoption/deployment-architecture/)
- **GitHub MCP Registry (Sept 2025 launch):** GitHub launched a public registry specifically to solve MCP server discovery — the problem that scattered MCP servers across repos and registries made integration slow and error-prone. 1,000+ servers now indexed. — [github.com/mcp](https://github.com/mcp)
- **Azure MCP Server (Microsoft Learn):** Production MCP servers for Azure DevOps, Azure resource deployment, and GitHub Actions are documented on Microsoft Learn with full deployment guides — showing MCP is no longer experimental but production-standard at enterprise scale. — [learn.microsoft.com/azure/developer/azure-mcp-server](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/azure-deploy)
- **MCP 2026 Roadmap:** Lead maintainer David Soria Parra documented that MCP shifted from a release-oriented spec to working groups organized around priority areas — reflecting that production deployments have different needs than the early experiments that launched the protocol. — [blog.modelcontextprotocol.io](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)

## Gotchas

- **Tool description poisoning:** Microsoft published research (June 2026) showing that attackers can poison MCP tool descriptions to make agents silently exfiltrate data — the agent never "breaks a rule," every step looks routine. Default MCP setups may not fire alerts on this. Supply-chain security for MCP servers (verifying server provenance, pinning to known-good versions) is not yet mature.
- **stdio is not production-ready:** The MCP ecosystem grew from local coding tool integrations where stdio was fine. Remote production agents (cloud-hosted, mobile, cross-platform) cannot use stdio — they need HTTP/SSE transport. Teams migrating from Cursor/Claude Code local setups to production deployments hit this wall.
- **Not all MCP servers are equal quality:** The 1,000+ servers in the registry vary wildly in auth implementation, error handling, and rate limiting. A bad MCP server can expose your agent to prompt injection amplification or credential leakage. Audit servers before connecting them, especially for production data access.
