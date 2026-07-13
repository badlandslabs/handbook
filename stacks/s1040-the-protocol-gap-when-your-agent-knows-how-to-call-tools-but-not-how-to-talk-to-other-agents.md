# S-1040 · The Protocol Gap — When Your Agent Knows How to Call Tools But Not How to Talk to Other Agents

Your agent can call tools, query databases, and write code. But it can't hand a task off to another agent. It can't discover what capabilities a colleague agent exposes. It can't negotiate a multi-step collaboration with a system it didn't build. You've solved tool use — you haven't solved interoperability. This is the **protocol gap**, and two complementary standards are closing it: MCP (tool access) and A2A (agent collaboration).

## Forces

- Every custom agent-to-agent integration costs 2–4 weeks and dies when either side changes — the integration tax is unsustainable at scale
- MCP and A2A are both real, both backed by major vendors, and both have distinct roles — teams that treat them as interchangeable or ignore one end up with half a solution
- MCP's security model was underspecified at launch (NSA flagged it in late 2025) — blindly exposing MCP servers to agents without auth boundaries is a known production hazard
- Agent-to-agent communication requires sharing state across trust boundaries — you can't just pipe tool calls through a shared channel
- The protocol landscape is still young: tools exist for discovery, capability negotiation, and long-running task handoffs, but teams build bespoke solutions for each because the patterns aren't yet codified

## The move

**Layer MCP for tool access, layer A2A for agent collaboration.** They are not competitors — they solve different communication problems and compose together.

- **Use MCP (Model Context Protocol) for anything your agent needs to _do_: call APIs, query databases, execute code, read files.** MCP is a client-server model where the LLM client calls tools exposed by MCP servers. Think of it as the USB-C port for tool integration — one protocol, any data source. GitHub's MCP server is the world's most-used remote MCP server (built on Go, launched alongside VS Code Agent Mode in 2025, handling millions of daily tool calls).

- **Use A2A (Agent2Agent Protocol) for anything your agents need to _collaborate on_ across organizational or framework boundaries.** A2A handles capability discovery, task negotiation, long-running task handoffs, and rich media exchange between opaque agents. It was co-developed by Google, donated to the Linux Foundation in June 2025 with 50+ partners (Atlassian, Salesforce, SAP, ServiceNow, PayPal, AWS, Microsoft), and has 24K+ GitHub stars as of early 2026.

- **Compose them together: an A2A agent can expose MCP tools as part of its capability set.** The A2A protocol defines a `skills` field where an agent can advertise what it can do — that skill can include an MCP server endpoint. This lets A2A handle the collaboration layer while MCP handles the execution layer.

- **Design MCP servers for AI consumption, not human interaction.** Return structured JSON with typed schemas, not natural language. Validate all inputs with Zod or similar before calling downstream APIs. Return only the fields the LLM needs — extraneous data degrades context efficiency. MotherDuck's team learned this after watching 4,000+ agent queries against their DuckDB MCP server: agents choke on verbose responses.

- **Secure MCP with auth boundaries and schema validation.** The NSA's November 2025 security guidance flagged that MCP's flexible design allows malicious inputs to reach execution environments. Production deployments need: OAuth 2.0 or API key authentication on MCP servers, input schema validation (Zod), least-privilege tool scoping, and audit logging. Remote MCP servers should use SSE (Server-Sent Events) transport for stateless operation behind load balancers.

- **Expose MCP servers through outbound-only tunnels in cloud environments.** GitHub's MCP server team learned that enterprises can't open inbound ports. The pattern: agents connect outbound to an MCP gateway, which proxies to internal services. Claude Managed Agents uses this approach natively — no exposed ports required.

- **Track what tools your agent actually uses.** Fleet management commands (list instances, check health, restart services) account for the majority of MCP tool calls in production. Don't give agents a menu of 200 tools — observe usage patterns and prune aggressively. GitHub's MCP server started with too many tools and had to cut down after users ignored most of them.

## Evidence

- **Engineering blog post (Arcade.dev):** GitHub's engineer Sam Morrow describes building GitHub's MCP server from a volunteer side project to "the most-used remote MCP server in the world" — viral launch alongside VS Code Agent Mode, lessons on tool count, Go SDK migration, and the outbound-tunnel pattern for enterprise deployments — [Arcade.dev Enterprise MCP Lessons](https://www.arcade.dev/blog/enterprise-mcp-lessons-from-githubs-mcp-server-launch)

- **Dev diary (MotherDuck):** After releasing one of the first MCP servers in the ecosystem (November 2024, 370+ GitHub stars), the MotherDuck team learned that agents perform better with narrow, well-typed tool schemas — a hackathon showed agents at 19 correct answers vs. a human analyst at 12, but only after tool output was redesigned for AI consumption — [MotherDuck Dev Diary](https://motherduck.com/blog/dev-diary-building-mcp/)

- **Enterprise adoption report (Ragwalla):** Survey of enterprise MCP deployments found 30% reduction in development overhead and 50–75% time savings on common tasks, with security reviews and MCP server governance identified as the primary barriers to production adoption — [MCP Enterprise Adoption Report 2025](https://ragwalla.com/blog/mcp-enterprise-adoption-report-2025-challenges-best-practices-roi-analysis)

- **Primary source (GitHub A2A repo):** The A2A protocol GitHub (24K+ stars, Linux Foundation, 50+ enterprise partners) defines 6 key capabilities: capability discovery via Agent Cards (JSON), task negotiation and push notifications for long-running tasks, rich media output negotiation, secure fallback to human-in-the-loop, and no shared memory model (agents are opaque to each other) — [A2A Protocol GitHub](https://github.com/a2aproject/A2A)

- **Primary source (Google Developers Blog):** A2A was announced at Google Cloud Next '25 as a complement to MCP — A2A handles "agent-to-agent collaboration" while MCP handles "agent-to-tool" — [Google A2A Announcement](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)

- **Technical blog (iKangai):** A2A uses a Task-centric model where work is structured as a unit with defined lifecycle, while MCP uses a Resource/Tool/Prompt model. The protocols can compose: an A2A agent exposes MCP tools in its skills — [A2A vs MCP Comparison](https://www.ikangai.com/a2a-vs-mcp-ai-standards/)

## Gotchas

- **Don't expose internal MCP servers directly to the public internet.** The NSA flagged that MCP's design reversal (servers can query clients) creates attack paths that traditional API gateways don't cover. Always proxy through an auth layer.
- **Don't confuse A2A with a tool-calling protocol.** A2A is for agent-to-agent negotiation — sharing context, agreeing on who does what, handling multi-step handoffs. It is not a replacement for MCP tool calls.
- **Don't give agents every tool they _might_ need.** GitHub's MCP team started with too many. Monitor which tools are actually called and cut the rest — a smaller, actively-used toolset is easier to secure and less confusing to the LLM.
- **Don't skip the OAuth proxy for remote MCP servers.** Without it, every user needs a direct API token. With it, the proxy mediates authentication and you can audit, rate-limit, and revoke centrally.
- **Don't assume your agent framework handles protocol composition automatically.** LangChain, LangGraph, and CrewAI have varying levels of MCP and A2A support — check the specific version and SDK support before designing around them.
