# S-2239 · The MCP Stack — When Your Agent Needs to Talk to the Real World

You've built an agent that reasons well. Now it needs to read your codebase, query your database, call your internal APIs, and browse the web. Without a standard way to wire tools to models, every integration is bespoke: custom prompts per tool, brittle function-calling schemas, no reuse across agents or frameworks. Model Context Protocol (MCP) is the answer teams are converging on — an open standard that turns "tools" from prompt engineering into a proper protocol layer.

## Forces

- **Protocol debt vs. flexibility** — Tool integrations accumulate as ad-hoc function definitions scattered across prompts. MCP standardizes them but adds a new layer to learn and operate.
- **Security surface expansion** — Every MCP server is a new attack surface. On-premises hosting solves data residency but multiplies operational burden.
- **Ecosystem fragmentation vs. lock-in** — MCP is open (Linux Foundation, November 2025) and backed by Anthropic, OpenAI, Google, Microsoft, and AWS. But "backed by everyone" can mean "nobody owns it."
- **Latency vs. capability** — Streaming resources and tool invocations add network hops. Remote MCP servers introduce failure modes that don't exist in-process.
- **Discovery problem** — With 5,800+ MCP servers available, finding the right one and vetting its security posture is non-trivial.

## The Move

MCP defines three primitives that turn agents into proper tool-using systems:

**1. Servers expose tools, resources, and prompts as a discoverable interface.**
Instead of hardcoding function signatures in your agent's prompt, you connect to an MCP server that advertises its capabilities. The agent queries the server's manifest at runtime and dynamically invokes whatever tools are available.

**2. Resources stream context without saturating the context window.**
MCP supports streaming resources — paginated database results, file chunks, live API responses — so agents can access large data sources without stuffing everything into the prompt. This is the practical difference between a "chatbot with amnesia" and a stateful agent.

**3. The protocol handles transport, not just schema.**
MCP is transport-agnostic (stdio for local servers, SSE/HTTP for remote). This means the same tool definition works whether it's a local filesystem MCP server or a remote enterprise service behind your VPN.

**Key operational decisions:**
- Prefer local MCP servers (stdio transport) for sensitive data — eliminates network exposure.
- Use the official MCP SDK (Python/TypeScript) to build custom servers rather than wrapping REST APIs with custom glue code.
- Configure explicit allowlists for which servers your agent can invoke — don't rely on the agent to self-restrict.
- Host MCP servers on-premises for enterprise data (salesforce CRM, Oracle DB, internal knowledge bases) rather than routing through third-party clouds.

## Evidence

- **Anthropic engineering blog (June 2025):** Anthropic's own Claude Research multi-agent system uses MCP internally to connect subagents to web search, Google Workspace, and custom integrations. The engineering team identified tool design as the single highest-leverage improvement — a 40% decrease in task completion time from better tool descriptions alone. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Anthropic news release (November 2024):** Block (Square/Cash App) built an internal agent called "Goose" on MCP architecture, giving engineers access to in-house MCP servers for their codebase, internal tools, and company APIs. Block built all servers in-house for security control. Early adopters cited significantly fewer tool-calling errors vs. custom function-calling approaches. — [URL](https://www.anthropic.com/news/model-context-protocol)
- **Market research (Gupta Deepak, 2025):** MCP server downloads grew from ~100,000 in November 2024 to 8+ million by April 2025. Over 5,800 MCP servers and 300+ clients now exist. MCP was donated to the Linux Foundation's Agentic AI Foundation in December 2025, with governance backing from Anthropic, OpenAI, Google, Microsoft, and AWS. Enterprise deployments confirmed at Block, Bloomberg, Amazon, and hundreds of Fortune 500 companies. — [URL](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Hacker News discussion (June 2025):** The Anthropic "Building Effective Agents" article thread (543 points) surfaced strong community consensus that tool design — not model choice — is the primary lever for agent quality. HN commenters consistently cited MCP as the practical implementation of this principle. — [URL](https://news.ycombinator.com/item?id=44301809)
- **GitHub Topics — AI Agents Frameworks:** The `microsoft/mcp-for-beginners` repo (part of Microsoft's official AI agents curriculum) treats MCP as a first-class concept. GitHub's own MCP Registry launched September 2025 to address server discovery. — [URL](https://github.com/microsoft/mcp-for-beginners/blob/main/09-CaseStudy/README.md)

## Gotchas

- **MCP is not authentication.** A server advertising tools doesn't mean the agent is authorized to use them. Wire up your own auth layer — OAuth tokens, API keys, IP allowlists — between your agent and MCP servers.
- **Remote MCP servers introduce latency.** Every tool invocation crosses a network boundary. Profile your agent's end-to-end latency with remote servers before assuming parallel tool calls are still faster than sequential ones.
- **Tool description quality dominates model performance.** Anthropic's own data: 40% of task completion time reduction came from better tool descriptions — not better models or more agents. Invest in writing clear, specific tool schemas.
- **Server discovery is unsolved.** With 5,800+ MCP servers, the ecosystem has a discoverability problem. GitHub's MCP Registry (September 2025) is a start but doesn't solve vetting. Prefer curated, security-audited servers over arbitrary community ones.
- **Context window pollution.** Streaming resources helps, but unbounded resource subscriptions can still saturate context. Set explicit limits on how much data an MCP server can return per invocation.
