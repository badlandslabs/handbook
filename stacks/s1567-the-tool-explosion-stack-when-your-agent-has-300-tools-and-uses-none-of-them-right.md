# S-1567 · The Tool Explosion Stack — When Your Agent Has 300 Tools and Uses None of Them Right

Your agent has access to GitHub, Jira, Slack, Linear, Notion, a weather API, and a custom DB query tool. All are registered. All are technically available. But it keeps trying to "browse" to GitHub issues (using a web browser to navigate to a page the GitHub API could fetch in one call), hallucinates API calls to endpoints that don't exist, and ignores the DB tool entirely when queries are the whole point of the session. The tools are there. The agent is blind to them. This is the tool explosion problem — the dominant failure mode of real-world agentic systems as of 2026.

By early 2026, the ecosystem has 177,436 public MCP tools across 19,388 verified servers, a 36x increase from November 2024. Downloads grew from 0.08M to 14M over 16 months. The protocol is proven. The problem is no longer whether tools can be connected — it is whether agents can actually use the right ones under real conditions.

## Forces

- **Token overhead vs. tool discovery** — loading all tool definitions upfront means an agent with 5 popular MCP servers carries ~55,000 tokens of tool schema before the conversation starts (GitHub alone: ~26K tokens for 35 tools). But loading nothing means the agent cannot discover capabilities.
- **General-purpose vs. single-purpose tools** — broad tools (a web browser, a file editor) are flexible but require the agent to figure out how to use them correctly. Narrow tools (create_github_issue, send_slack_dm) are precise but create maintenance burden and increase the probability of the wrong tool being selected.
- **Tool description quality vs. developer time** — the best tool descriptions explicitly state *when not to use* the tool and include inline examples, not links to external docs. Writing this well is non-trivial and often skipped.
- **Action capability vs. risk** — agents are measurably shifting from perception (reading, querying) toward action (writing, editing, sending, deleting). The same flexibility that makes agents useful also makes tool misuse consequential.

## The move

**Tame tool explosion with tiered exposure, structured errors, and agent-native description design.**

- **Organize into toolsets, not flat lists.** Major production MCP servers (GitHub, Stripe, Vercel) all use named tool groups loaded at server startup via configuration. Disabled toolsets do not appear in `tools/list` at all — they consume zero context. Configure which toolsets are active per agent role or session type, not globally.

- **Use on-demand tool discovery.** Anthropic's Tool Search Tool (November 2025) lets agents search for relevant tools at call time rather than loading all definitions upfront. Measured results: 85% token reduction in tool schema overhead and a 25% accuracy boost in correct tool selection. Reach for this when your agent serves multiple use cases with non-overlapping tool needs.

- **Design tool descriptions for machines, not humans.** The top insight from HN discussion on tool selection: agents pick confidently when tool descriptions define clear boundaries — specifically *when not to use* a tool, not just what it does. Inline parameter examples outperform links to external documentation (agents do not browse to your docs at call time). Clean parameter naming and type hints improve schema parsing significantly.

- **Return structured errors, not HTTP messages.** Production MCP servers mark error responses with `isError: true` and include a `retryAfter` hint or an alternate tool suggestion. This lets the agent recover programmatically rather than failing silently or looping on the same bad call. The agent learns the error taxonomy over time.

- **Scope tool permissions by agent identity, not by tool.** Agents with a "code reviewer" persona should have read access to repos but not write access. Agents with a "data analyst" persona should have DB query tools but not file write tools. This separation of concerns — what Anthropic's finance agents reference calls Skills / Agents / MCP Connectors as three distinct layers — prevents a single compromised or confused agent from performing destructive actions across the tool surface.

- **Handle batch operations programmatically.** Anthropic's Programmatic Tool Calling reduces token overhead by 37% for repeated operations by executing them in a code block rather than one tool call at a time. For list operations (fetch all open PRs, sync all modified files), batch through code rather than iterative tool calls.

## Evidence

- **Research paper (Oxford/UK AISI):** Analysis of 177,436 public MCP tools created Nov 2024–Feb 2026 found 36x growth in tool count and 2-order-of-magnitude growth in downloads. Tool categorization by impact: perception tools (read-only), reasoning tools (analyze), and action tools (modify external systems). A measurable shift from perception toward action capability is underway, with early deployment in high-stakes domains. — [arXiv:2603.23802](https://arxiv.org/abs/2603.23802)

- **Hacker News (Show HN, 96 points):** Frigade built a browser-based agent that runs inside authenticated web apps, observes how the app calls its own APIs, and auto-generates MCP tool definitions from live traffic. The insight: even modern SaaS apps have a "spider web of undocumented internal APIs" — reverse-engineering them into typed tools is more reliable than having the agent navigate the UI. — [HN #48847834](https://news.ycombinator.com/item?id=48847834)

- **Engineering blog (Anthropic, November 2025):** GitHub MCP (35 tools, ~26K tokens), Slack (11 tools, ~21K tokens), Sentry, Grafana, and Splunk together consume ~55K tokens of system context before any user message. Three advanced tool use features introduced: Tool Search Tool (85% token reduction, 25% accuracy boost), Programmatic Tool Calling (37% token reduction), and Tool Use Examples (18-point accuracy improvement on similar tool selection). — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)

- **Engineering blog (Anthropic, November 2025):** Code execution via MCP achieves 98.7% context overhead reduction compared to traditional tool calling for equivalent operations. Replaces iterative single-result tool calls with batch computation. — [Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Hacker News (Ask HN, 38 points):** Developer discussion on AI agent tool selection confirms tool description quality is the primary lever for correct tool choice — specifically, explicitly describing when NOT to use a tool outperforms capability-focused descriptions. Schema cleanliness and inline examples outperform documentation links. — [HN #47127532](https://news.ycombinator.com/item?id=47127532)

- **Real-world MCP patterns (Agent Surface, 2026):** Production MCP servers from GitHub (60+ tools), Stripe (composable operations), and Vercel (deployment + analytics) share five patterns: toolset grouping, startup configuration, environment-based feature loading, structured error recovery, and lean response schemas. All three use environment-variable-driven auth with no per-request re-authentication overhead. — [Agent Surface](https://agentsurface.dev/docs/mcp-servers/real-world-examples)

## Gotchas

- **Flat tool lists scale poorly past ~15 tools.** Beyond that threshold, correct tool selection drops significantly without grouping or search-based discovery. The evidence from both Anthropic's benchmarks and practitioner HN discussion converges on this: do not expose a flat namespace of 50 tools to a single agent.
- **A tool that returns too much data pollutes context.** Lean responses — returning only the fields the agent needs for the next decision — outperform comprehensive responses. Profile your tool output sizes and truncate or paginate aggressively.
- **Browser-based tools fill a gap that API tools cannot.** Many real-world web apps have no public API, undocumented internal endpoints, or require authenticated sessions. Browser automation (Browser Use at 79K+ GitHub stars, Stagehand at 21K+ stars, Firecrawl at 88K+ stars) fills this gap but introduces anti-bot, proxy, and fingerprint complexity that API-based tools avoid entirely.
- **Tool descriptions drift as the codebase changes.** A tool added in January with an accurate description may have expanded parameters by March. No common tooling automatically keeps descriptions in sync — this requires a review step in the tool definition lifecycle.
