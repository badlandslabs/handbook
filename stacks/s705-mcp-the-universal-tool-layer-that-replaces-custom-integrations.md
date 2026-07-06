# S-705 · MCP: The Universal Tool Layer That Replaces Custom Integrations

[You're stitching together another agent, and you face the same decision: write a custom tool definition, wire it into the agent's schema, repeat for every new agent, every new LLM. The integration work compounds. MCP promises to终结 this — one standard that any agent and any LLM share. But is it real yet, and what's the gotcha?]

## Forces

- **Tool fragmentation is the integration debt of agentic AI.** Every agent-to-tool pairing historically required a custom integration. At 10+ tools across 3+ agents, you have 30+ point-to-point connections to maintain. MCP turns this into one server per tool, consumed by any agent.
- **Loading all tool definitions into context is prohibitively expensive.** Anthropic measured 150,000 tokens for direct tool-call definitions — equivalent to ~$0.60 per request at GPT-4o pricing. The token cost of comprehensive tool access was pricing teams out of rich tool environments.
- **The ecosystem moved faster than the evaluation caught up.** Thousands of MCP servers exist, but teams are still learning which patterns actually hold up in production vs. which ones introduce new failure modes.

## The Move

**Adopt MCP as your tool integration layer — but implement it as code-execution APIs, not direct function calls.**

1. **Treat MCP servers as REST-like APIs, not function definitions.** Instead of embedding every tool's schema directly in the context, give the agent one MCP client tool: "write and execute code to call this MCP server." Anthropic measured this reduces token consumption by 98.7% (150,000 tokens → 2,000 tokens for equivalent capability).
2. **Use MCP as the universal interface layer between agents and external systems.** A single MCP server for your database, CRM, or code execution environment is consumed by any agent — no rewiring when you switch from GPT-4o to Claude 4.
3. **Group tools by domain into MCP servers.** Don't create one MCP server per tool. Create one per system (e.g., `database-mcp`, `github-mcp`, `filesystem-mcp`). An agent's available tools become a list of MCP server names, not 50 individual tool schemas.
4. **Prefer MCP SDKs over hand-rolled schemas.** Official MCP SDKs exist for Python, TypeScript, and other languages. They handle the protocol handshake, streaming, and type safety. Hand-rolled tool definitions work but create maintenance burden as the MCP spec evolves.
5. **Design MCP tools with structured output defaults.** Include response schemas in your tool definitions so agents can parse results programmatically rather than trying to extract information from free-text responses.
6. **Plan for MCP server discovery, not just registration.** MCP's 2026 roadmap adds agent-to-agent communication on top of tool calling. Architecture decisions you make now for tool sharing should anticipate the peer-to-peer handoff patterns coming next.

## Evidence

- **Anthropic Engineering Blog (Nov 2025):** "Present MCP servers as code APIs rather than direct tool calls. Agents write code to interact with MCP servers, reducing token usage dramatically (e.g., 150,000 tokens → 2,000 tokens = **98.7% reduction**)." — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Anthropic Engineering Blog (Nov 2025):** "Since launching MCP in November 2024, adoption has been rapid — the community has built thousands of MCP servers and SDKs are now available for all major programming languages." — https://www.anthropic.com/engineering/code-execution-with-mcp
- **GitHub Decision Guide (benconally, 2025):** "LangGraph: MCP support ★★★★★ — Best-in-class. MCP tools are first-class graph nodes with full streaming." — https://github.com/benconally/ai-agent-framework-decision-guide
- **AI Agent Engineering (2026):** "The 2026 MCP Roadmap: From Tool Integration to Agent-to-Agent Communication" — signaling MCP is evolving beyond tool calling into inter-agent handoff protocols. — https://ai-agent-engineering.org/news/the-2026-mcp-roadmap-from-tool-integration-to-agent-to-agent-communication
- **Cirra.ai/MCP Paper (Aug 2025):** "MCP Servers act as universal connectors between AI models and the world of external systems — eliminating the one-off function calling fragmentation." — https://cirra.ai/articles/pdfs/model-context-protocol-ai-tool-integration.pdf

## Gotchas

- **MCP servers must be secured independently.** A compromised MCP server gives an agent access to whatever permissions the server runs with. Treat MCP server permissions like network access — least-privilege by default, no broad filesystem access.
- **The token-reduction benefit only applies if agents call tools via code execution, not direct invocation.** Simply wiring MCP into your agent framework doesn't automatically reduce token costs — you need the code-execution pattern to see the 98.7% reduction.
- **Not all MCP servers are production-grade.** The ecosystem has thousands of community servers. Vet them for security, maintenance, and error handling before giving agents access — a bad MCP server can silently corrupt agent outputs.
- **Context window management is still your problem.** MCP reduces tool-definition overhead, but the agent's reasoning about which tools to call and how to compose results still burns tokens. Code-execution helps, but you still need guardrails on agent loops.
