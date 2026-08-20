# S-2904 · The MCP Tool-Abstraction Stack — When Every Agent Needs the Same Integration Wired Differently

Every team that ships a second agent discovers the same problem: the GitHub integration you wrote for agent A isn't reusable for agent B, because the tool-calling conventions, auth headers, and response parsing all live in agent-specific code. You end up with N agents × M integrations — each wiring subtly different, each breaking in different ways when the upstream API changes. MCP (Model Context Protocol) solves this by making the tool interface the artifact, not the agent code.

## Forces

- **N×M wiring tax.** Without a shared protocol, every agent-tool pair requires custom code. Two agents connecting to the same Slack instance = two separate integrations to maintain, test, and debug.
- **Vendor lock-in hidden in the tool layer.** Agents built on Claude-specific tool schemas don't port to OpenAI or Gemini. The tool adapter becomes the lock-in vector — not the model.
- **Enterprise governance requires a contract.** Legal and security teams can't audit agent behavior if the tool logic lives embedded in agent prompts. MCP lets permissions, audit logs, and access controls live at the integration layer.
- **Schema diversity at scale breaks prompts.** An agent with 20 tools described in its system prompt degrades — each tool schema burns 2,000–5,000 tokens of context before the model even acts.
- **Not all servers are equal.** The MCP catalog grew from ~50 servers at launch (November 2024) to 10,000+ by 2026 — most of the growth is noise. Teams need a curated subset.

## The move

MCP (Model Context Protocol) establishes a standardized interface between AI agents and external tools. Build one MCP server per resource; any compliant agent can use it without custom wiring. Think USB-C for AI tool integration.

**The three-server starter pack (install every time):**
- **GitHub MCP** — PR reviews, issue triage, code search, repo management
- **Context7** — answers questions about recently edited files with full accuracy
- **Playwright MCP** — gives agents a real browser with snapshot diffing instead of raw HTML

**Architecture pattern:**
- MCP server = the integration contract (auth, permissions, audit, schema)
- Agent client (Claude Code, Cursor, Windsurf, OpenAI Agents SDK, custom) = consumer
- One server, any client — no per-agent rewiring
- Remote MCP servers (stdio → SSE) enable team-scoped shared tool instances
- Layer A2A (Agent-to-Agent Protocol) on top for multi-agent coordination; MCP handles the tool layer, A2A handles agent handoffs

**Scope rules:**
- One MCP server per domain boundary, not per database or table
- Put permissions, audit logging, and rate-limiting in the server — the agent can't bypass them
- Limit active servers per agent to 5–8 to avoid token bloat from schema injection
- Start in a low-stakes domain: a research workflow, a code-review pipeline

**Enterprise-specific pattern:**
- Block built an internal agent called "Goose" on MCP architecture — entirely in-house MCP servers for complete security control over data residency and audit trails
- Governance model: if permissions and audit logs live in the MCP server, agents become governable services that can clear legal and security review

## Evidence

- **Primary research — MCP ecosystem stats (May 2026):** 97M+ monthly SDK downloads, 10,000+ public MCP servers, 8,000–12,000 distinct servers by Q2 2026. 78% of enterprise AI teams have MCP-backed agents in production. Supported natively by Anthropic Claude Desktop/Code, OpenAI, Google, Microsoft. Spec donated to Linux Foundation's Agentic AI Foundation (December 2025). — [Presenc AI Research](https://presenc.ai/research/mcp-server-ecosystem-statistics-2026) + [andrew.ooo](https://andrew.ooo/answers/mcp-model-context-protocol-enterprise-adoption-july-2026/)

- **Enterprise adoption reality check (April 2026):** Fortune 500 AI agent deployment time reduced 40–60% on multi-service workflows using MCP. 400% growth in remote MCP server deployments since May 2025. Major caveat: Perplexity's CTO publicly departed from MCP, illustrating that protocol maturity doesn't guarantee universal adoption. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/09/mcp-enterprise-adoption-reality-check-2026)

- **Real-world production use:** Block (Square/Cash App) built internal AI agent "Goose" on MCP — both desktop app and CLI — using entirely in-house MCP servers for security and workflow customization. The agent accesses various internal MCP servers without third-party dependencies. — [Wasyra](https://wasyra.com/en/blog/mcp-enterprise-ai-protocol-2026)

- **Open-source tooling (Jan 2025):** `mcp-agent` by LastMile AI (8,500+ stars, Apache 2.0) implements MCP with established agent patterns from Anthropic's "Building Effective Agents" — augmented LLM, routing, and parallel execution. Supports both stdio and SSE transports. — [GitHub/lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent) + [HN Show HN](https://news.ycombinator.com/item?id=42867050)

- **Browser-as-tool pattern:** Libretto Browser Tools SDK (OSS) provides six Playwright-based tools for agents — compact page snapshots with stable refs and diff-based change reporting. Reports 55% lower cost than alternatives. Supports LocalBrowserProvider, Browserbase, Kernel, Steel. — [libretto.sh](https://libretto.sh/browser-tools)

## Gotchas

- **Schema injection token cost.** Each connected MCP server burns 2,000–5,000 tokens of context on schema injection alone. A 20-server agent is already half-full before the first user message.
- **Anthropic archived 13 of 20 reference MCP servers** by late 2025 — only 7 remain active. Don't depend on the official catalog staying current; audit which servers are actually maintained.
- **The "ask the AI anything" trap.** Wiring an MCP server over an entire database and promising natural-language queries against it guarantees an incident. Scope servers to specific domains where mistakes are low-stakes.
- **Remote vs. local transport has security implications.** stdio is simple but runs the server locally; SSE enables centralized managed servers but requires network access and auth configuration. Enterprise teams favor remote for auditability.
- **Perplexity CTO's departure is a signal, not noise.** The protocol has structural weaknesses in multi-turn state management and server-to-server authentication that some teams are solving with homegrown alternatives. Track the Linux Foundation governance process for resolution.
