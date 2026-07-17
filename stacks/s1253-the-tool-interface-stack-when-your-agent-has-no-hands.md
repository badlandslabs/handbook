# S-1253 · The Tool Interface Stack: When Your Agent Has No Hands

Your agent can reason about the perfect plan but can't read a file, search the web, or run code. Every agent ultimately needs to touch the world — and how it connects to tools is the make-or-break interface nobody gets right on the first try.

## Forces

- **The tool-calling gap.** Native function calling (JSON schema tools) is now standard in OpenAI, Anthropic, and Gemini APIs, but real-world tools expose dozens of parameters, edge cases, and auth flows that a flat schema can't capture. One mis-specified parameter causes silent wrong results.
- **MCP fragmentation.** Model Context Protocol (MCP) is the emerging standard for agent-tool communication, but the ecosystem is fragmented: servers exist for everything from GitHub APIs to Chrome DevTools, yet most production agents still wire tools ad hoc. Finding the right server and composing them reliably is unsolved.
- **Browser control remains brittle.** Screenshot-and-click agentic browsing is slow and unreliable. Text-driven browser control (agents describing workflows in plain text) works better but requires careful sandboxing and state management.
- **Sandbox vs. real-world access.** Code execution in a sandbox is safe but limited. Agents with real filesystem or network access need isolation strategies that most teams haven't codified.

## The Move

**Standardize on MCP as your tool bus.** MCP has become the closest thing to a universal tool interface for agents. The official specification is backed by Anthropic, Google, Microsoft, and others, with SDKs in Python, TypeScript, Go, Rust, Kotlin, Ruby, and PHP. One protocol, multiple language servers — pick your tool ecosystem once.

**Wire only the tools the task actually needs.** The MCP registry covers GitHub, filesystem, browser, web search, Slack, Postgres, and more. Don't give agents a kitchen sink — scope the toolset to the minimum needed for the task. Fewer tools means lower hallucination rate on tool selection and faster cold starts.

**For browser automation: prefer text-based over screenshot-based.** One "Show HN" launcher (ghostd.io) reported that screenshot-and-click agents become "slow and brittle fast" when deployed to real workflows. Text-based browser control — where the agent describes a workflow in plain text and a renderer executes it — is more reliable and easier to audit. See Skyvern's approach for comparison.

**Use cloud sandboxes for filesystem and code execution.** Terminal Use (YC W26) emerged as "Vercel for filesystem-based agents" — packaging agent code, streaming messages, persisting state, and managing file transfer in a managed sandbox. This avoids the overhead of wiring sandbox + streaming + state + file transfer manually for every agent.

**Let small models call tools via MCP even without native function calling.** One r/LocalLLaMA practitioner demonstrated Mistral-small (not a function-calling fine-tuned model) executing recursive agent workflows through a custom MCP server that reinforces tool selection with a custom system prompt and calls `listTools` to guide the model's choice. Native function calling helps but isn't strictly required.

**Design tool schemas conservatively.** If a tool has 10 parameters, the agent will guess the remaining 7. Expose only the parameters that matter; wrap complex tool logic in a narrow, well-named tool rather than exposing an API's full surface area.

## Evidence

- **GitHub Repo / HN Post:** MCP (Model Context Protocol) official org on GitHub with SDKs in 7+ languages, backed by Anthropic, Google, Microsoft. Top MCP servers: `github/github-mcp-server` (15.2k stars), `ChromeDevTools/chrome-devtools-mcp` (33k+ stars, Google's official Chrome DevTools server for agent browser control), `filesystem-mcp`, `postgres-mcp`. — [github.com/modelcontextprotocol](https://github.com/modelcontextprotocol)
- **GitHub Repo:** `lastmile-ai/mcp-agent` (8.4k stars, Jan 2025 Show HN) implements Anthropic's agent patterns (Augmented LLM, Router, Orchestrator-Worker, Evaluator-Optimizer) on top of MCP, with Temporal integration for durable agents. Quote: "MCP is all you need to build agents, and simple patterns are more robust than complex architectures." — [news.ycombinator.com/item?id=42867050](https://news.ycombinator.com/item?id=42867050) | [github.com/lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent)
- **HN Comment:** Browser automation via MCP — Skyvern (open source browser agent, similar to OpenAI Operator) released an MCP server letting Claude/Cursor/Windsurf control browsers to navigate docs, Stack Overflow, and Hacker News. — [reddit.com/r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1jrds1v/mcp_server_to_let_agents_control_your_browser)
- **GitHub Repo / HN Post:** Terminal Use (YC W26) — "Vercel for filesystem-based agents." Handles sandbox lifecycle, message streaming, state persistence, and file transfer. Target: coding agents, research agents, document processing, internal tools. — [news.ycombinator.com/item?id=47311657](https://news.ycombinator.com/item?id=47311657) | [terminaluse.com](https://www.terminaluse.com)
- **Reddit Post:** Agent builder on r/LocalLLaMA demonstrated that non-function-calling models (Mistral-small) can route tools correctly via a custom MCP server that reinforces tool selection with `listTools` calls and a curated system prompt. — [reddit.com/r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1j8ibs2/dont_underestimate_the_power_of_local_models)

## Gotchas

- **MCP servers have auth sprawl.** A filesystem MCP server with write access to your repo is a supply-chain risk. Every MCP server you add is a trust boundary — scope tokens and permissions to the minimum the tool needs.
- **Tool schema drift breaks agents silently.** When an upstream API changes a parameter name or type, the agent gets no error — it just starts producing wrong results. Pin tool schemas or add contract tests that validate tool responses against the expected shape.
- **Browser tool use at scale is expensive.** Browser instances are memory-intensive. A fleet of agents each running a headless Chrome session will cost significantly more than text-based alternatives. Profile before committing.
- **MCP server availability is uneven.** Not every tool you need has an MCP server. For internal APIs, you'll write your own — and the ergonomic gap between "pip install" and "write your own MCP server" is wide. Budget time for it.
