# S-1432 · The Tool Taxonomy Stack · When Your Agent Knows 5,800 Tools and Still Uses None of Them Well

You've got 5,800 MCP servers available. Every framework promises tool-augmented agents. You installed a dozen, wired them up, and watched your agent spend 30 seconds reasoning about which of 47 tools to call next — then call the wrong one. The tool-rich ecosystem is real. The cost of being tool-rich is also real.

## Forces

- **The MCP explosion is genuine but expensive.** MCP SDKs went from ~100K monthly downloads (Nov 2024) to 97M (Dec 2025). Five enterprise-grade servers (GitHub, Slack, Sentry, Grafana, Splunk) already consume ~55K tokens before a single user message arrives (Anthropic, Nov 2025). Load everything and you bleed tokens; load nothing and the agent has no reach.
- **Token overhead compounds per tool call.** Multi-step tool chains generate 3–4× token overhead from LLM reasoning between each step (r/LocalLLaMA, ~Feb 2026). A 4-step pipeline (scrape → extract → transform → save) can consume 3–4K tokens of overhead on top of the actual work.
- **Tool security is underappreciated.** 43% of MCP servers have command injection flaws; chaining 10 plugins exceeds 92% exploit probability (Gupta research, Dec 2025). The "plug in anything" promise has a real attack surface.
- **Computer use changes the tool calculus entirely.** Rather than defining bespoke API tools, agents observe screens and act with mouse/keyboard — meaning any piece of software becomes a tool by default, no custom integration required. This collapses the tool authoring problem but introduces its own failure modes: 3–15 seconds/action, variable reliability, and agents that fail silently.

## The move

**Taxonomy-first tool design: fewer tools, richer descriptions, on-demand discovery.**

The move isn't "give agents more tools" or "give agents fewer tools" — it's **curate a minimal tool surface with enough description richness that the agent self-selects correctly**, then layer in dynamic discovery for edge cases.

Specifically:

- **Flat tool count, deep descriptions.** Anthropic's Tool Use Examples (Nov 2025) showed 72% → 90% accuracy improvement when each tool includes a concrete usage demonstration, not just an API description. A well-described tool with 2–3 examples outperforms 5 minimally-described tools.
- **On-demand tool discovery over bulk loading.** Anthropic's Tool Search Tool reduced token cost by 85% vs. loading all tool definitions upfront, while preserving 95% of context. Instead of loading all 35 GitHub MCP tools, load none — then discover the relevant ones when the agent needs them. This is the single highest-leverage change in the 2025–2026 tool-use literature.
- **Prefer atomic, composable tools over mega-tools.** A `search_github(code:"pattern", repo:"owner/repo")` tool that does one thing beats a `GitHubManager` tool that does everything. Composability keeps each tool call legible and failure-scoped.
- **For browser/UI interaction: use computer use, not bespoke scraping tools.** When a website has no API, computer use (screenshot → action) is now benchmark-competitive: Coasty scores 82% on OSWorld, Claude Computer Use runs at $0.24–$0.36/workflow, and OpenAI Operator hits 87% on complex sites. The tradeoff is latency (3–15s/action vs. milliseconds for API) and reliability variance. For one-off data extraction, form filling, or legacy software, computer use wins. For high-frequency automation at known endpoints, API tools win.
- **Harden MCP security before scaling.** Scan tool definitions for injection-prone patterns. Apply least-privilege scoping (can this tool only write to the intended directory?). Rate-limit tool calls from the agent side, not just the server side. The 43% flaw rate in production MCP servers is not a reason to avoid MCP — it's a reason to treat MCP servers like untrusted code.
- **Evaluate tool selection, not just tool execution.** A correct tool called with wrong parameters is a failure. Test tool selection by presenting the agent with scenarios that require different tools and checking which tool it chooses — this catches the "called the wrong API" failure mode that execution-only evals miss.

## Evidence

- **Anthropic Engineering Blog (Nov 24, 2025):** A 5-server MCP setup (GitHub 35 tools ~26K tokens, Slack 11 ~21K, Sentry 5 ~3K, Grafana 5 ~3K, Splunk 2 ~2K) = ~55K tokens before the conversation starts. Their Tool Search Tool achieves 85% token reduction with 95% context preservation via on-demand discovery. Tool Use Examples (concrete usage demonstrations per tool) improved accuracy from 72% to 90%. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)

- **Wowhow benchmark comparison (Apr 13, 2026):** OpenAI Operator hits 87% on complex sites, Google Mariner scores 83.5% on WebVoyager, Claude Computer Use costs $0.24–$0.36/workflow. Traditional Playwright/Selenium: milliseconds per action but breaks on UI redesigns. Computer use: 3–15 seconds/action but adapts to visual changes without selector maintenance. — [URL](https://wowhow.cloud/blogs/computer-use-ai-agents-browser-desktop-automation-2026)

- **Coasty OSWorld benchmark (May 18, 2026):** Coasty 82%, Anthropic Claude 73%, OpenAI Operator 38% on the OSWorld benchmark (real desktop OS control, not simulated). Gap between best and worst is more than double — computer use quality varies wildly across providers despite similar marketing claims. — [URL](https://coasty.ai/blog/computer-use-ai-use-cases-2026-20260518)

## Gotchas

- **Loading all tools by default creates a discovery problem, not a capability one.** The agent doesn't fail because it lacks tools — it fails because it has too many to reason about correctly. The fix is discovery architecture, not more tools.
- **Computer use is not a replacement for structured tools on high-frequency paths.** If an agent needs to check 1,000 GitHub PRs per hour, a browser-based approach will cost 1,000× more and be 100× slower than a GitHub MCP tool. Computer use wins on breadth; structured tools win on repetition.
- **The 43% MCP security flaw rate means trust-but-verify for any MCP server you didn't audit yourself.** Community-contributed MCP servers can have command injection, overbroad permissions, or data exfiltration. Treat them like npm packages: pin versions, review permissions, monitor for unusual access patterns.
- **Token overhead from tool reasoning is invisible until you measure it.** A "simple" 4-step tool chain can generate 3–4× overhead in reasoning tokens. Profile token usage per step before claiming efficiency. Budget for 2–3× token multiplier on multi-step tool chains.
