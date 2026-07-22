# S-1478 · The MCP Tool Catalog Stack — When Your Agent Has Tools But No Standard

You built three MCP servers for your agent — one for Google Drive, one for Salesforce, one for internal APIs. It works locally. Then your team scales to eight agents, each needing different subsets of tools, and suddenly every agent-to-tool integration is a bespoke one-off. The problem isn't the tools. It's that without a shared protocol, every new tool connection multiplies complexity linearly.

## Forces

- **500+ MCP servers exist, but integration is still bespoke.** The community has built hundreds of Model Context Protocol servers, yet most agent-tool connections are custom glue code that doesn't port.
- **Loading all tool definitions upfront is a token tax.** Anthropic measured that direct tool-calling with full schema definitions burns massive context on every call — their code-execution pattern cut this by 98.7%.
- **Agents need tools they can discover, not tools they're handed.** Static tool lists don't scale; agents that explore a filesystem of available MCP servers adapt to new tool availability without re-prompting.
- **Browser automation is the highest-leverage single tool.** browser-use has 105,931 GitHub stars — the single most-starred AI agent framework — because it gives agents a universal interface (the web) rather than bespoke APIs.
- **Production tools need sandboxing.** Code execution, shell access, and browser automation all carry blast-radius risk that tool wrappers must bound.

## The move

Adopt MCP as your agent-tool protocol layer, then build tool catalogs by category — not by individual integration. The key pattern from production deployments:

**Code execution over direct tool calls.** Instead of passing full tool schemas in context, agents write code that imports and calls MCP server functions directly. The agent discovers available servers by reading a `./servers/` directory — it learns what tools exist at runtime rather than at prompt-build time. This was Anthropic's core engineering insight (Nov 2025).

**Three tool tiers in production:**

| Tier | Tools | Example | Use Case |
|------|-------|---------|----------|
| **Foundation** | Code execution, filesystem, bash | E2B, Judge0, Claude Agent SDK | Sandboxed compute, file ops |
| **Connectivity** | Web browser, search, API calls | browser-use (105K stars), Brave Search MCP, Firecrawl | Web interaction, data ingestion |
| **Domain** | Google Drive, Salesforce, Slack, Jira, Postgres | Community MCP servers (70+ production-ready) | Business data, productivity |

**Browser as universal tool.** Rather than building N custom API integrations, browser-use treats any web UI as a tool interface. An agent that can control a browser can interact with any SaaS product with a web UI — without a dedicated MCP server. This is why it dominates agent framework stars.

**Three-agent tool architecture.** Production browser agents (e.g., TheAgenticBrowser on GitHub) stack a Planner Agent (breaks tasks into steps), a Browser Agent (executes via Playwright), and a Critique Agent (verifies results and decides whether to retry). The critique loop prevents the single most common failure mode: the agent thinks it succeeded but the DOM changed.

## Evidence

- **Engineering Blog:** Anthropic's code-execution-with-MCP post describes the 98.7% token reduction achieved by having agents write code that calls MCP servers rather than receiving tool schemas directly — agents discover servers by listing `./servers/` at runtime. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **GitHub Trending:** browser-use/browser-use has 105,931 stars and 11,661 forks as of 2026, making it the highest-starred open-source agent framework. Its AGENTS.md documents a three-agent architecture (Planner → Browser → Critique). — https://github.com/browser-use/browser-use
- **GitHub Architecture:** TheAgenticBrowser (421 stars) demonstrates the planner/browser/critique feedback loop pattern in production browser automation for form filling, data extraction, and e-commerce scraping. — https://github.com/TheAgenticAI/TheAgenticBrowser
- **MCP Registry:** The modelcontextprotocol/servers GitHub registry lists 500+ community MCP servers; TokenMix maintains a curated directory of 70+ production-ready servers organized by category (developer tools, web scraping, databases, cloud, communications). — https://tokenmix.ai/blog/mcp-servers-list-2026-complete-directory
- **GitHub Framework:** Agentflow (18 stars, 626 commits) implements graph-based multi-agent orchestration with native MCP support, 3-layer memory (Redis cache + Postgres + vector store), and parallel tool execution across OpenAI, Google, and Anthropic models. — https://github.com/10xHub/agentflow
- **Industry Survey:** Reddit discussions across r/vibecoding, r/LocalLLaMA, and r/ChatGPT identify three real agent categories: coding agents, browser/computer-use agents, and research agents — with browser automation cited as the highest-leverage capability for non-technical workflows. — https://www.aitooldiscovery.com/guides/best-ai-agents-reddit

## Gotchas

- **MCP server quality varies wildly.** Of 500+ community servers, only ~70 are production-ready by TokenMix's assessment. Vet servers for active maintenance, sandboxing, and error handling before giving agents access.
- **Browser automation is fragile without a critique loop.** DOM selectors shift, pages load asynchronously, and buttons move. A single-agent browser tool will silently fail in ways a critique loop catches.
- **Token costs compound in long tool chains.** Every intermediate result passed through context adds cost. The code-execution pattern solves this for MCP, but agents chaining multiple tool calls across different servers still accumulate overhead.
- **Sandboxing is non-negotiable for code execution.** E2B and Judge0 are the standard choices — bare shell execution in production is an incident waiting to happen.
- **The MCP registry is fragmented.** There is no single canonical source; the awesome-mcp-servers list, TokenMix catalog, and GitHub topics all overlap but don't agree on what's production-ready.
