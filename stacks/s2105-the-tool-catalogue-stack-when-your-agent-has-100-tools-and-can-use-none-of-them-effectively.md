# S-2105 · The Tool Catalogue Stack — When Your Agent Has 100 Tools and Can Use None of Them Effectively

You built a production agent. You gave it a rich tool catalogue — filesystem, HTTP, database queries, Slack, Jira, GitHub, code execution, browser automation, and more. In demos, everything works. In production, the agent either ignores most tools, picks the wrong one, calls a tool at the wrong abstraction level, or gets so lost in the tool-selection problem that it never solves the actual task. The catalogue is full. The agent is useless.

## Forces

- **Tool definition overhead scales with the catalogue.** Every tool loaded into context consumes tokens whether it gets used or not. Loading 50 MCP tool definitions can eat 150K+ tokens before the agent begins the actual task — Anthropic measured a 98.7% token reduction (from ~150K to ~2K) by moving tool discovery into code execution rather than loading definitions upfront.
- **Tool selection is a sub-problem that competes with the real task.** A model forced to choose from 100 tools spends cognitive budget on selection before solving the actual problem. The Unix-style counterargument: the shell solved this 50 years ago by providing one tool (`run`) that composes everything, and LLMs happen to meet Unix on the same surface: text.
- **Two dominant tool paradigms are colliding.** Function-calling tools (structured, typed, MCP-native) versus code-execution tools (raw shell, more flexible, higher risk). Teams keep switching between them trying to find the right abstraction level.
- **The sandbox question is non-negotiable in production.** AI-generated code running on production infrastructure without isolation is a security incident waiting to happen. E2B grew from 40K to 15M sandbox executions per month (375x in one year) as teams discovered this the hard way.
- **Browser automation is now a first-class production tool category.** Playwright crossed 78.6K GitHub stars. Anthropic, OpenAI, and Google have all shipped AI-native browser agents. But direct computer-use approaches remain "too brittle, slow, and token-hungry" for production — teams are routing around them via MCP, reverse-engineered APIs, or purpose-built browser agents.

## The Move

The core move: **tool design is architecture, not an afterthought.** The specific approach depends on your tool category, but the principle is the same — match the tool abstraction to the task type, not to a unified vision of what a "tool" should be.

### Code Execution

- **Use a dedicated sandbox (E2B, Modal, Daytona) in production.** E2B uses Firecracker microVMs (~150ms cold start), Modal uses gVisor (sub-second), Daytona uses OCI/Docker (~27–90ms). Sandboxed agents reduce security incidents by ~90% vs. unrestricted host access. Never run AI-generated code directly on shared kernels in production.
- **Consider code-execution-via-MCP over direct tool calls.** Anthropic's approach: instead of loading 150K tokens of tool definitions, the agent writes code that calls the tool internally. Token cost drops to ~2K. The tradeoff: requires a sandbox with the right SDK available.
- **For local-only use cases, llama.cpp's `--tools all` flag** gives GGUF models filesystem and shell access (read_file, write_file, edit_file, exec_shell_command, grep_search, file_glob_search) with no external server. Ships a "do not enable in untrusted environments" warning.

### Browser Automation

- **Prefer MCP-wrapped browser tools over raw computer-use.** Anthropic's Computer Use and OpenAI's Operator work for demos but are described as "too brittle, slow, and token-hungry" for production by teams actually deploying them. browser-use (79K+ GitHub stars, YC W25) wraps Playwright as an MCP-compatible Python library — teams use it with Claude Code, Cursor, Codex, and other agents.
- **Reverse-engineer authenticated web apps into MCP recipes** (Frigade pattern). Instead of letting an agent click through a UI, auto-generate MCP tools from the app's internal API calls — endpoint, auth method, response schema. A browser agent inspects the app once, generates the tool definition, and the agent thereafter calls the API directly.
- **WebMCP** (shipped in Chrome 146, February 2026) is an emerging W3C standard that may make DOM scraping and screenshot-based inference obsolete for AI browser agents.

### MCP-Specific Patterns

- **Use tool search for large tool libraries.** Anthropic's November 2025 advanced tool use beta adds a Tool Search Tool: on-demand discovery without preloading definitions. The agent searches for relevant tools at runtime rather than having all 50 definitions in context.
- **Build MCP servers from OpenAPI specs automatically.** Microsoft's Learn MCP Server was generated from OpenAPI specs, covering full API surface with Pydantic validation and resilience. mcpmarket.com's Registry offers 60+ production-ready MCP servers auto-generated from OpenAPI specs.
- **Distribute MCP servers via npm with the `@modelcontextprotocol` scope** for discoverability, versioning, and dependency management. The official MCP registry has 9,652 servers as of May 2026.

### Tool Architecture Debate: Function Calling vs. Shell

- **Function calling** (typed, structured, MCP-native): better for precise operations where the model must pick the right tool. Scales poorly past ~20 tools. Anthropic notes that even 10–15 tools create a non-trivial selection problem for the model.
- **Unix-style `run(command="...")`** (single shell tool): better for flexible, composable tasks where the model generates its own subcommands. Popular in the LocalLLaMA community (1,800+ upvote post from a former Manus backend lead). Works because both Unix and LLMs operate on text.
- **The pragmatic take**: use typed function calls for operations where wrong = expensive (delete, charge, deploy) and shell for exploratory/inquiry tasks where wrong = retryable.

## Evidence

- **Engineering post (Anthropic):** Anthropic's November 2025 advanced tool use documentation — code execution via MCP reduced tool-definition tokens from ~150,000 to ~2,000 (98.7% reduction). Introduced Tool Search Tool for on-demand discovery. Tool Use Examples as a universal standard. — [anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)
- **Benchmark/Blog (AgentMarketCap / Northflank):** E2B grew from 40,000 to 15 million sandbox executions per month between March 2024 and March 2025 — a 375x increase. Security research (early 2026) found sandboxed agents reduce security incidents by ~90% vs. unrestricted host access. Firecracker microVMs (E2B), gVisor (Modal), and OCI/Docker (Daytona) are the three isolation technologies in production use. — [agentmarketcap.ai/blog/2026/04/10/sandboxed-code-execution-ai-agents-e2b-modal-daytona](https://agentmarketcap.ai/blog/2026/04/10/sandboxed-code-execution-ai-agents-e2b-modal-daytona/)
- **Community post (Reddit r/LocalLLaMA, 1,800+ upvotes):** Former Manus backend lead argues for Unix-style single-tool pattern over function calling. After 2 years building agents at Manus, abandoned function calling entirely in favor of `run(command="...")`. Cites tool-selection overhead competing with the actual task, and the natural text-composition match between Unix CLI and LLM text generation. Repo: [github.com/epiral/pinix](https://github.com/epiral/pinix) — [reddit.com/r/LocalLLaMA/comments/1rrisqn](https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn/i_was_backend_lead_at_manus_after_building_agents/)
- **Show HN (March 2025, 389 points):** OpenAI's Responses API and Agents SDK announcement — 157 comments debating vendor lock-in, pricing, and the merit of higher-level abstractions vs. simple API calls. — [news.ycombinator.com/item?id=43334644](https://news.ycombinator.com/item?id=43334644)
- **Show HN (2025–2026):** Browser-use launched YC W25, reached 79K+ GitHub stars as a Python library for AI browser automation. Frigade demonstrated reverse-engineering authenticated web apps into MCP recipes — solving the "too brittle, slow, token-hungry" problem of direct computer-use approaches. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use), [news.ycombinator.com/item?id=48847834](https://news.ycombinator.com/item?id=48847834)
- **GitHub (official):** MCP official registry at [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) — 9,652 servers as of May 2026. Official SDKs for Python, TypeScript, Go, C#, Ruby. — [modelcontextprotocol](https://github.com/modelcontextprotocol)

## Gotchas

- **Loading all tool definitions upfront is the default and the trap.** Every MCP client does this, and it works fine at 5–10 tools. At 50+, it becomes a token and latency problem. Fix it with code execution, tool search, or a two-tier system (core tools always loaded, discovery tools on demand).
- **"Works in demos" is not validation for browser automation.** Anthropic Computer Use and OpenAI Operator demo well. In production, teams report brittleness with anti-bot detection, page layout changes, and token cost. Build a fallback — MCP-wrapped API calls or browser-use with Playwright — before you commit to a computer-use-only approach.
- **Unrestricted code execution in a shared environment is a data breach risk, not just a technical debt item.** Even a single misconfigured prompt or a prompt injection in a retrieved document can exfiltrate secrets if the agent has host-level access. E2B's 375x growth reflects teams discovering this in production, not in planning.
- **Tool quality matters more than tool quantity.** Anthropic's own research and community discussions agree: 5 well-designed, composable tools beat a 100-tool catalogue that nobody can navigate. Invest in the design of each tool's interface — its description, parameter schema, error behavior, and what it returns — as much as you invest in the underlying implementation.
- **MCP server versioning and compatibility is a real operational burden.** The protocol is young (launched November 2024), SDKs are still evolving, and breaking changes happen. Pin versions in production and test against MCP SDK updates before upgrading.
