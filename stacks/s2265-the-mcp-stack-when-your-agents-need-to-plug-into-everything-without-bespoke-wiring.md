# S-2265 · The MCP Stack

[Your agent needs to query GitHub, post to Slack, search your internal wiki, and invoke a billing API. You could write four custom integrations — or you could describe the problem to an agent and let it figure out which tools to use. MCP is the USB-C of that world.]

## Forces

- Every new tool integration is bespoke: custom auth, custom schemas, custom prompts to describe what the tool does — multiplying the work by the number of connected systems
- Context window bloat is real: defining 35 GitHub tools alone consumes ~26K tokens; Slack, Sentry, Grafana stack on top and you've burned ~55K tokens before the agent does real work
- The LLM can't use tools it hasn't been told about — but loading every possible tool's schema into context is the path to token exhaustion and degraded tool selection
- Agent portability across providers requires re-implementing every integration — a new model provider means starting over
- The protocol problem: when two agents need to coordinate, there's no standard language — each pair needs custom glue code

## The Move

MCP (Model Context Protocol) is the open standard that makes tool definitions declarative, discoverable, and portable. Rather than hand-coding "here is how the agent talks to GitHub," you describe GitHub as an MCP server — a typed endpoint that the agent can query, enumerate, and invoke dynamically.

**The core mechanics:**

- **Resources** — MCP servers expose structured data (file contents, API responses, database rows) that the agent can read. Think of these as read-only surfaces the agent queries for context.
- **Tools** — Invocable actions with typed inputs/outputs. The agent calls a tool; the MCP server executes it and returns structured results.
- **Prompts** — Reusable prompt templates stored server-side that bundle context + instructions for a specific task pattern.
- **Dynamic discovery** — On startup, the agent queries the MCP server's `listTools` endpoint and receives only the schemas for the tools that are actually available. No 55K-token payload. No manual schema injection.
- **Bidirectional: A2A (Agent-to-Agent Protocol)** — The newer sibling standard enabling agents to discover each other and delegate tasks directly, without custom webhook glue.

**The token math shifts dramatically:**

| Scenario | Tokens consumed |
|---|---|
| Static schema injection (5 services) | ~55K+ per session |
| MCP dynamic discovery (same 5) | ~3–5K to discover + ~2K per tool call |
| Savings from tool search beta (Anthropic) | 85% token reduction |

**Real deployment topology at Block (Goose):**

```
Agent (Goose MCP client)
  └── GitHub MCP server         (internal tools, auth-managed)
  └── Slack MCP server         (notifications, search)
  └── Notion MCP server        (internal wiki)
  └── Figma MCP server         (design files)
  └── AWS MCP server           (infrastructure queries)
  └── Datadog MCP server       (observability)
  └── Linear MCP server        (project tracking)
```

All built in-house for security control. Deployed company-wide (not just engineering) in 8 weeks. One engineer (Bradley Axton) → company-wide adoption.

## Evidence

- **Engineering post:** Anthropic published "Building Effective AI Agents" (June 2025) — their canonical production guidance explicitly advocates for simple, composable patterns over complex orchestration frameworks, and highlights MCP as the mechanism for tool interoperability. They measured the token bloat problem and introduced Tool Search beta to address it (85% reduction). — https://www.anthropic.com/engineering/building-effective-agents + https://www.anthropic.com/engineering/advanced-tool-use
- **Enterprise case study:** Block (Square/Cash App) deployed Goose — one of the first MCP clients — connecting to internal systems via MCP servers built in-house. Deployed across engineering, design, product, support, risk, data, and operations. VP Engineering Angie Jones described deploying "company-wide in 2 months" with 8 weeks as the key milestone. All MCP servers built internally for security control. — https://mcp-atls.vercel.app/cases/block/ + https://www.aviator.co/podcast/block--ai-agents-goose
- **Ecosystem adoption:** Microsoft Agent Framework added MCP server support (Microsoft Learn docs). OpenAI integrated MCP into ChatGPT and AgentKit. Cursor, VS Code MCP Jam, and dozens of open-source MCP servers (GitHub, Slack, PagerDuty, Fetch, Filesystem) listed on modelcontextprotocol.io. Block contributed Goose to the AAIF (Agentic AI Foundation) to keep the ecosystem open-standard-driven. — https://modelcontextprotocol.io/docs/getting-started/intro
- **Production ROI data:** 2026 production deployments show 41% achieve positive ROI in year one, 67% by year two, with ROI timelines of 4–9 months. Only ~41% of projects succeed at the "autonomous task completion" level — meaning the tooling choice (and MCP's standardization) directly impacts production viability. — https://grandpasai.com/research/ai-agents-in-production-2026.html
- **Framework landscape:** Awesome AI Agents 2026 lists 340+ resources across 20+ categories — including MCP-compatible tooling for Browser Use, Claude Code, OpenAI Operator, DeerFlow (ByteDance, 25K+ stars), n8n (180K stars), and dedicated agent OS projects like Bernstein (zero LLM tokens on coordination), AgentScope (Alibaba multi-agent), and AXME (durable coordination with crash recovery). — https://github.com/caramaschiHG/awesome-ai-agents-2026

## Gotchas

- **MCP servers are as reliable as their backing services** — a flaky MCP server that wraps a slow API turns your agent's reliability into the reliability of that API. Rate limiting, timeouts, and partial failures still bite you at the underlying service layer.
- **Auth management is non-trivial** — Block built all their MCP servers in-house specifically for security control. Off-the-shelf MCP servers with shared credentials are a blast radius risk if one server is compromised.
- **A2A is still maturing** — Agent-to-Agent protocol is the "MCP for agents talking to each other" but production adoption is early. Don't assume inter-agent delegation is as seamless as tool invocation yet.
- **Tool count still grows** — MCP solves the protocol and context-window problem, but doesn't solve the fundamental: more tools mean more decisions for the agent. Anthropic's own Tool Search beta (dynamic discovery at call-time rather than startup) is a response to agents still struggling with large tool sets.
- **Provider lock-in in practice** — MCP is open, but the tooling ecosystem clusters around Claude and ChatGPT as the primary clients. A different model provider's MCP implementation may differ in subtle ways that break server compatibility.
