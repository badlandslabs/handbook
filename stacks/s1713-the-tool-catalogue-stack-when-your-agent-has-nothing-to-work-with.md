# S-1713 · The Tool Catalogue Stack — When Your Agent Has Nothing to Work With

When an LLM becomes an agent, the difference is tools. Without them, you have a chatbot. With the wrong ones, you have a liability. The challenge is not giving agents *more* tools — it is knowing which tools unlock real leverage and how to design them so agents actually use them correctly.

## Forces

- **Token economics constrain tool budgets** — loading all tool definitions upfront burns context. A GitHub MCP server with 35 tools consumes ~26K tokens before any real work starts. Agents operating with thousands of potential tools need a way to discover only what matters for the current task.
- **Tool count and tool quality are in tension** — teams want broad capability (dozens of tools) but agents degrade when overwhelmed. The literature shows 5–10 well-designed tools outperform 50 poorly-described ones.
- **The MCP ecosystem is exploding but fragmented** — 80K+ GitHub stars on the MCP spec project, 100+ production-ready servers, yet teams still debate whether to build custom tools or wire in existing MCP servers. No clear winner on which tools to give in which order.
- **Browser automation is the most requested and most dangerous tool** — agents need to see the web, but giving them a live browser profile with cookies and credentials is a remote-code-execution risk.
- **Tool design is load-bearing on agent reliability** — the same model swings from 72% to 90% parameter accuracy depending on whether tool descriptions include concrete usage examples. Getting tool design wrong compounds across every agent invocation.

## The Move

The move is **catalogued tool deployment with progressive disclosure**: maintain a curated, categorized tool library and expose tools to agents contextually rather than all-at-once. Three concrete layers:

1. **Three canonical tool tiers** (from Anthropic's production deployments): *(a)* **Knowledge retrieval** — RAG over structured docs, vector search, knowledge graphs; *(b)* **Model-backed tools** — LLM-in-LLM calls for sub-tasks like classification, summarization, routing decisions; *(c)* **External systems** — code execution, filesystem I/O, API calls to GitHub, Slack, Jira, databases, web browsers. Start with tier (a) and only add (b) or (c) when the agent genuinely needs to act, not just reason.

2. **MCP as the universal tool bus** — The Model Context Protocol (80K+ GitHub stars as of early 2026) has become the de facto standard for connecting agents to tools. Rather than writing custom tool wrappers per integration, teams wire MCP servers and let agents discover tools dynamically. Production-ready MCP servers exist for: GitHub (code, PRs, issues), filesystem, Slack, browser automation (Playwright MCP, BrowserUse MCP), HN/news, database connectors, Firebase, CI/CD pipelines. Use the registry at [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) as the starting point.

3. **Tool design minimum viable spec** — Every tool must have: *(a)* a concrete name (verb-noun: `fetch_pr`, not `github_ops`); *(b)* a one-sentence description of what it does and when to call it; *(c)* at least one usage example showing the expected input and output; *(d)* a JSON schema for parameters. Adding usage examples to tool definitions improved parameter accuracy from 72% to 90% in Anthropic's benchmarks (Advanced Tool Use, Nov 2025). Names and descriptions alone are not enough.

4. **Browser tool with strict sandboxing** — For browser automation, use Playwright MCP (34K+ GitHub stars, Microsoft-maintained) which exposes accessibility trees rather than raw screenshots — faster and cheaper. Never give an agent a logged-in browser profile with session cookies. Browser MCP projects like `browser-use-mcp` and Ghost support multi-agent parallel browsing on a shared profile, but require clear isolation boundaries to prevent credential leakage. Microsoft's AutoJack research (Jun 2026) demonstrated RCE through a malicious page abusing localhost trust and unsafe parameter handling — browser tool access must treat the web as untrusted input.

5. **Progressive tool loading** — Instead of loading all tool definitions at session start, use on-demand tool discovery. Anthropic's Tool Search Tool (Nov 2025 beta) reduced token consumption by 85% while preserving 95% of context by only loading relevant tool definitions when the agent signals need. For teams not on the Anthropic platform, a lightweight registry + routing layer achieves similar results without context bloat.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective Agents" (Dec 2024) defines the three tool tiers and recommends simple composable patterns over complex frameworks — widely cited and endorsed on HN (543 points, 88 comments, Jun 2025). — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Engineering blog:** Anthropic's "Introducing Advanced Tool Use" (Nov 2025) quantifies the token cost of tool proliferation (GitHub: 26K tokens for 35 tools) and benchmarks three solutions with concrete improvement metrics (85% token reduction from Tool Search, 37% from Programmatic Tool Calling, 72→90% parameter accuracy from usage examples). — [anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)

- **GitHub/MCP ecosystem:** MCP servers project reached 80K+ GitHub stars by early 2026. The official registry at `modelcontextprotocol/servers` lists production-ready servers for filesystem, GitHub, Slack, PostgreSQL, and more. Playwright MCP has 34K+ stars with active Microsoft maintenance. BrowserUse MCP supports multi-agent parallel browsing. — [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)

- **Show HN:** "Representing Agents as MCP Servers" by LastMile AI (May 2025, 58 points) demonstrates flipping the MCP client/server relationship — agents expose themselves as MCP servers, enabling multi-agent orchestration over a single protocol without custom infrastructure. — [news.ycombinator.com/item?id=44053754](https://news.ycombinator.com/item?id=44053754)

- **Security research:** Microsoft Security Blog documented AutoJack (Jun 2026) — a single malicious webpage achieving RCE against a host running an AI browsing agent via localhost trust abuse and unsafe WebSocket parameter handling in AutoGen Studio's MCP integration. — [microsoft.com/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent](https://www.microsoft.com/security/blog/2026/06/18/autojack-single-page-rce-host-running-ai-agent)

- **AI Lab Notes:** Practical guide to browser automation for agents (Feb 2026) maps the tool landscape: Playwright MCP for accessibility-tree-based browsing, Chrome DevTools MCP for live browser control, Browser MCP for agent access to an existing logged-in profile — each with distinct security tradeoffs. — [codeshrew.github.io/ai-lab-notes/posts/2026-02-08_browser-automation-ai-agents-mcp-playwright](https://codeshrew.github.io/ai-lab-notes/posts/2026-02-08_browser-automation-ai-agents-mcp-playwright)

## Gotchas

- **Loading all tools at startup is a common beginner mistake.** The token cost is non-trivial, and agents spend inference budget on tool *descriptions* they never invoke. Route tools contextually or use a discovery layer.
- **Natural-language tool descriptions are not enough.** Anthropic measured the gap: adding usage examples to the same tool definition pushed parameter accuracy from 72% to 90%. Write tools as if training a new hire — concrete examples of inputs and outputs, not just high-level purpose.
- **Browser tools require a threat model before deployment.** An agent with access to a logged-in browser profile can read your email, access your banking session, and post on your behalf. The AutoJack research confirms real exploitation paths. Sandboxing, separate profiles, and treating browser output as untrusted input are non-optional for production deployments.
- **MCP servers vary wildly in maturity.** The registry has 100+ servers, but some are experimental, unmaintained, or have incomplete parameter schemas. Audit each server's maintenance status, security model, and data handling before giving an agent access in production.
- **Agents as MCP servers is a compelling pattern with a bootstrapping problem.** You need at least one existing MCP client to configure and launch the agent-as-server. Teams report it works well for multi-agent orchestration but adds setup complexity that is not worth it for single-agent workflows.
