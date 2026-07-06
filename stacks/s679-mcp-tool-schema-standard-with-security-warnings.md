# S-679 · MCP: The Interoperability Standard with a 92% Exploit Surface

You need your agent to call tools across multiple vendors. MCP gives you a universal handshake for that. The catches: 43% of published MCP servers have command injection flaws, and composing 10 of them hits a 92% cumulative exploit probability.

## Forces

- **Interoperability vs. trust:** MCP (Model Context Protocol) achieved 8M+ monthly server downloads in 6 months after launch — the fastest AI protocol adoption on record. Every major provider (OpenAI, Google, Microsoft, AWS) has backed it. But the servers are mostly community-authored, and the trust model doesn't scale.
- **Protocol completeness vs. production readiness:** The November 2025 update added async operations, server discovery via .well-known URLs, and improved horizontal scaling. These are real production features. But the default SDK patterns encourage connecting to servers without validation.
- **Capability breadth vs. attack surface:** An agent with access to 10 MCP servers inherits every privilege escalation path those servers open — directly compounding exploit probability.
- **Speed of adoption vs. depth of security review:** By end of 2025, an estimated 90% of organizations will use MCP in some form. Most haven't audited the servers they're connecting.

## The move

**Use MCP as your tool interoperability layer, but treat every server as untrusted by default.**

- **Gate MCP servers the same way you gate npm packages.** Audit the source, check the permissions it requests, review the JSON-RPC handler code before adding it to your agent's tool registry. Don't add servers because they're available — add them because you've reviewed them.
- **Scope server permissions to minimum required.** A file-system MCP server that grants read-write on the entire filesystem is a privilege escalation waiting for a prompt injection. Use sandboxed execution environments (E2B, Modal, Firecracker microVMs) as a containment layer between MCP servers and host systems.
- **Chain MCP with typed tool schemas at the agent boundary.** MCP defines the transport; your agent layer should define the schema contract. Validate inputs and outputs at the boundary regardless of what MCP returns. Command injection via malformed tool responses is a real attack vector.
- **Use server discovery (RFC 8615) for catalog browsing, not blind connection.** The November 2025 update enabled browsing MCP server capabilities via /.well-known/mcp/ endpoints. Use this to audit capabilities before connecting — not to auto-discover and auto-connect at runtime.
- **Prefer MCP servers with versioned schemas and changelogs.** Vendor-neutral governance under the Linux Foundation's Agentic AI Foundation (backed by Anthropic, AWS, Google, Microsoft, OpenAI as of December 2025) means the protocol is stable. Individual servers are not. Prefer servers that version their tool schemas.
- **Instrument MCP call chains end-to-end.** MCP operations span your agent → MCP client → transport (stdio or HTTP/SSE) → MCP server → external resource. Each hop is a failure and attack point. Log and monitor all of them.

## Evidence

- **Research report:** MCP server downloads grew from ~100,000 (November 2024) to 8M+ monthly (April 2025); 5,800+ servers and 300+ clients now published; 43% of servers have command injection vulnerabilities, yielding 92% exploit probability at 10 composed servers — [guptadeepak.com](https://guptadeepak.com/research/mcp-enterprise-guide-2025/)
- **Hacker News discussion:** Agent stack is "stratifying" into specialized layers; sandboxing (E2B, Modal, Firecracker wrappers) is becoming its own discipline — [HN #47114201](https://news.ycombinator.com/item?id=47114201)
- **Protocol update:** November 2025 MCP update adds async operations, server discovery via RFC 8615 .well-known URLs, and horizontal scaling improvements — [byteiota.com](https://byteiota.com/mcp-protocol-november-25-update-production-ready-ai-agent-standard/)

## Gotchas

- **The MCP SDK's default transport (stdio) blocks synchronously.** Long-running MCP tool calls will hang your agent loop. The November 2025 async update helps, but requires migrating to SSE/HTTP transport — not a drop-in change.
- **MCP doesn't solve schema compatibility across servers.** Two MCP servers may both expose a "search" tool with completely different schemas. Your agent still needs to know which to call and how.
- **Sandboxing MCP servers is operationally non-trivial.** Firecracker microVMs, E2B, and Modal each have different cold-start profiles, cost models, and network isolation guarantees. Choose before you need it, not during an incident.
- **Prompt injection via MCP tool responses is underexplored.** A compromised or malicious MCP server can return injection payloads in tool responses. Your output parsing layer needs to treat MCP responses as untrusted input.
