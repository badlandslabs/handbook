# S-2251 · The MCP Tool Stack — When Your Agent Has No Hands

When your agent reasons brilliantly but can't actually do anything — it can't read your files, query your database, or trigger your CI pipeline. MCP (Model Context Protocol) is the emerging standard for giving agents working hands.

## Forces

- **Standardization vs. lock-in** — MCP promises model-agnostic tool discovery, but early adoption means committing to an evolving spec with breaking changes
- **Security surface area** — every MCP server is a new attack vector; hundreds of publicly exposed servers lack basic auth
- **Local vs. remote trade-off** — STDIO transport (local) is simpler but doesn't scale; HTTP transport enables production deployment but introduces routing, auth, and session management complexity
- **Protocol maturity vs. ecosystem velocity** — the spec changed substantially in Nov 2025 and again in July 2026 (stateless overhaul); servers built on earlier versions may need rework

## The move

**Give your agent MCP servers, not raw function definitions.**

MCP standardizes three things your agent needs to act in the world: how it discovers tools, how it calls them, and how results come back.

- **Define tools as MCP resources, not in-prompt instructions.** Let the agent read the tool schema from the server rather than inferring API shapes from documentation in the prompt. This eliminates the "hallucinated curl commands" failure mode.
- **Start with in-house servers.** Block built all their MCP servers internally rather than using third-party ones. This gives complete control over security boundaries and tool behavior. Every public MCP server you add is an untrusted code path the model can invoke.
- **Use structured output tools over free-text responses.** The June 2025 MCP spec added structured tool output; use it. JSON blobs the agent can parse are far more reliable than natural language tool descriptions in the response.
- **Route remote MCP with session affinity.** If you're running HTTP-transport MCP servers in production, you need sticky sessions (the `Mcp-Session-Id` header pins the client to one server instance). Can't round-robin these — session state lives server-side.
- **Plan for protocol migration.** MCP 2026-07-28 dropped the session handshake entirely, making MCP servers horizontally scalable for the first time. If you're on older HTTP-transport servers, budget time for migration.

## Evidence

- **GitHub (open source):** Block's Goose agent — deployed company-wide to engineering, design, product, support, risk, and ops teams — connects to 6 MCP servers including GitHub, Notion, Slack, Jira, and internal services. Built entirely in-house for security control. ~52k GitHub stars. — [goose-docs.ai](https://goose-docs.ai/blog/2025/04/21/mcp-in-enterprise) and [github.com/aaif-goose/goose](https://github.com/aaif-goose/goose)
- **GitHub (enterprise sample):** Azure-Samples/azure-ai-travel-agents demonstrates multi-agent travel planning with MCP orchestration connecting Azure OpenAI to flight, hotel, and itinerary services. — [github.com/Azure-Samples/azure-ai-travel-agents](https://github.com/Azure-Samples/azure-ai-travel-agents) via [microsoft/mcp-for-beginners](https://github.com/microsoft/mcp-for-beginners/blob/main/09-CaseStudy/README.md)
- **NSA (government advisory):** May 2026 security guidance documents real MCP deployments in production across business, finance, legal, and software development. Flags session-inversion attacks, prompt injection via tool descriptions, and un-traced data flows as systemic risks. — [nsa.gov — CSI MCP Security](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf)

## Gotchas

- **Don't expose MCP servers publicly without auth.** Data Science Dojo identified 492 publicly accessible MCP servers vulnerable to abuse — no authentication, no encryption. Treat MCP servers like internal services, not public APIs.
- **STDIO transport doesn't survive container restarts.** The default local transport is fine for dev, but session state lives in the server process. Production needs HTTP/Streamable transport with proper lifecycle management.
- **Tool descriptions are prompt-injectable.** Simon Willison documented (April 2025) that MCP tool descriptions visible to the model can carry hidden adversarial instructions that don't appear in the user interface. Never let untrusted sources define tool descriptions your agent ingests.
- **The MCP SDK landscape is fragmenting.** TypeScript, Python, Go, and C# SDKs all track the spec at different speeds. TypeScript split into separate `@modelcontextprotocol/client` and `@modelcontextprotocol/server` packages in the 2.0 release. Pin SDK versions and test after every spec update.
