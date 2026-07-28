# S-1758 · The Tool Bloat Stack — When Every Agent Framework Invented Its Own Tool Format

Your agent framework of choice works great — until you need it to book a flight, post to Slack, and query your database. Then you discover that OpenAI, Anthropic, LangChain, and your framework all use different JSON schemas for tool definitions, your OAuth tokens are scattered across four services, and your agent has no idea which of the eleven search tools it has access to it should actually use.

This is **the Tool Bloat Problem**: tool proliferation created a fragmentation crisis worse than the one it was supposed to solve.

## Forces

- Every major agent framework invented its own tool-calling format — OpenAI function calling, Anthropic tool schemas, LangChain tool bindings, and custom formats all differ
- MCP (Model Context Protocol) standardized the *transport layer* for tool delivery but left *discovery* unsolved — an agent still can't find relevant tools without configuration
- Tool descriptions are the primary selection mechanism for autonomous agents, but most developers treat them as boilerplate
- Every tool is a failure surface: schema mismatches, argument validation failures, and unstable side effects compound
- Credential management for agents is unsolved: agents are non-deterministic, prone to prompt injection, and cannot safely hold secrets directly
- Adding more tools increases capability but decreases reliability — the marginal tool often breaks more than it enables

## The Move

The community is converging on a three-layer tool stack:

**Layer 1 — Protocol: MCP as the lingua franca.** Anthropic open-sourced the Model Context Protocol in late 2024. By 2025 it had official servers for the most common tools: GitHub (repo management, issues, PRs), Brave Search (web + local search), Filesystem (sandboxed local files), Postgres, SQLite, Google Drive, and Slack. The official MCP Registry launched September 2025 at registry.modelcontextprotocol.io. Smithery.ai hosts thousands of community servers discoverable via CLI. Tools defined as MCP servers are discovered by any MCP-compatible client — one definition, universal consumption.

**Layer 2 — Translation: Composio as the universal adapter.** Rather than rewriting tool integrations for every framework, Composio (28k+ GitHub stars) maintains a registry of 1000+ pre-built tools and a provider-adapter pattern that translates into OpenAI, Anthropic, or LangChain tool schemas on demand. `OpenAIToolSet.getTools(['slack', 'github'])` and `AnthropicToolSet.getTools(['slack', 'github'])` produce functionally equivalent tool definitions from the same registry — the adapter handles schema translation. Authentication is user-scoped: agents access tools on behalf of users via OAuth connections managed by Composio.

**Layer 3 — Description: tool descriptions are the product.** When agents select tools autonomously, description quality determines behavior. The consensus from HN discussions: **specify when NOT to use a tool** — agents pick confidently when boundaries are explicit, not when capability statements are vague. Overlapping tool descriptions cause agents to hallucinate tool selections. Schema examples (input/output pairs in the tool definition) reduce mis-calls more than prose descriptions.

**Credential security:** Agent Vault (Infisical, Show HN 2025) introduces credential brokering — a proxy layer that attaches secrets to agent requests server-side, preventing credential exfiltration via prompt injection. Agents never hold tokens; the proxy handles egress.

**Tool governance:** Production agents should treat tools as untrusted. Schema-validate all arguments before execution. Time-bound tool calls. Make retry behavior explicit — some tools are safe to retry (read-only queries), others are not (write operations, payments). Observable logging at the tool layer is non-negotiable.

## Evidence

- **GitHub / MCP official servers:** The @modelcontextprotocol/servers repo (and successor official repos) provide canonical implementations for GitHub, Brave Search, Filesystem, Postgres, SQLite, Google Drive, and Slack — all with consistent MCP JSON-RPC interfaces. Brave Search MCP alone has 571 commits and active maintenance. — [modelcontextprotocol.io/specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- **MCP Registry launch:** Official registry launched September 2025, resolving the fragmentation problem of scattered community directories. Servers are now discoverable at registry.modelcontextprotocol.io. Smithery.ai independently maintains thousands of community servers with CLI discoverability. — [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io)
- **Composio adapter pattern:** Composio (28.1k GitHub stars) demonstrates the provider-adapter approach — the same tool registry produces OpenAI, Anthropic, and LangChain schemas via provider subclasses. HN discussion on "how agents choose tools" confirms schema examples and explicit boundaries outperform prose capability statements. — [github.com/composiohq/composio](https://github.com/composiohq/composio), [HN thread](https://news.ycombinator.com/item?id=47127532)
- **Agent Vault:** Infisical's Agent Vault (Show HN, 156 points) directly addresses credential exfiltration — agents cannot safely hold secrets, so credentials are brokered via an egress proxy. — [github.com/Infisical/agent-vault](https://github.com/Infisical/agent-vault)
- **Browser as a tool:** Browser Use (16k+ GitHub stars) and Claude Computer Use both take screenshot-level control of browsers rather than DOM-level automation. This is architecturally different from Selenium/Playwright — the agent operates on visual UI, same as a human. Browser Use is used for form filling, data extraction, QA automation, and multi-step web workflows. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)

## Gotchas

- MCP standardizes tool *transport* but not tool *discovery* — you still need to configure which servers your agent can access; unconfigured agents have zero tools
- Tool overlap is a failure mode, not a safety net: if your agent has three overlapping search tools, it will confidently pick the wrong one and fail silently
- Schema validation must happen server-side, not just in the prompt — agents will pass malformed arguments and the tool must reject them cleanly
- Composio's 1000+ tool registry sounds comprehensive but many tools are thin wrappers with minimal OAuth coverage; validate actual API coverage before depending on it
- Browser-use tools are inherently brittle — website UI changes break agents even when functionality is unchanged; build in screenshot-diff checkpoints for production use
