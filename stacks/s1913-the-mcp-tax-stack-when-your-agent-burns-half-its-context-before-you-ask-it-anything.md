# S-1913 · The MCP Tax Stack — When Your Agent Burns Half Its Context Before You Ask It Anything

You connect seven MCP servers to give your agent good tool coverage — GitHub, Slack, Sentry, Grafana, your internal APIs. The agent boots. You type your first message. The model returns a polite "I don't have the tools to help with that." It consumed 67,300 tokens — 33.7% of a 200k context window — loading tool definitions before seeing a single word of your question. This is the MCP tax: every tool schema you connect costs tokens upfront, regardless of whether the agent ever uses it.

## Forces

- **The spec has no lazy-loading clause.** The MCP protocol's `tools/list` call returns the full catalog — every tool name, JSON schema, parameter descriptions, and usage instructions — in one response. There's no standard mechanism to say "only load tools 1-10 unless I ask for more." The spec solved connectivity; it didn't solve context economics.
- **Tool schemas are surprisingly expensive.** A single GitHub MCP server with 35 tools consumes ~26k tokens. A Slack server with 11 tools: ~21k. The cumulative effect is multiplicative: a realistic enterprise setup with 7 servers and 50+ tools hits 67k+ tokens before any conversation begins. Measured: 33.7% of a 200k context window gone on tool definitions alone.
- **Per-tool costs are hidden until production.** Most teams discover this problem in production, not in staging. A handful of MCP servers in development feel fine. The breaking point arrives when you add a third integration or when the agent starts handling complex multi-step tasks that need the full tool surface.
- **More tools make agents worse, not better.** Beyond the token cost, showing an LLM 50+ tools at once degrades its selection accuracy. The model considers irrelevant options, picks suboptimal tools, and is more likely to hallucinate a tool call that doesn't exist or misread parameter requirements.

## The move

**Three solutions shipped between November 2025 and February 2026, all implementing progressive disclosure:**

1. **Anthropic Tool Search (Nov 2025)** — Mark tools with `defer_loading: true` in the API. At each step, Claude searches a lightweight tool index and fetches only the definitions it needs. Measured reduction: **85%** of tool-definition tokens eliminated. Anthropic's own example: 58 tools across 6 MCP servers (55k tokens) drops to ~8k tokens. Available on the Claude Developer Platform (Messages API).
2. **Anthropic Programmatic Tool Calling (Nov 2025)** — Instead of describing tools to the model, the agent writes code that calls them directly. The model outputs structured function calls that the client executes; only the results return to context. Reduction: **37%** token savings on tool definitions, plus reduced latency from fewer model round-trips.
3. **Claude Code Tool Search (Feb 2026, v2.1.7)** — Claude Code's internal MCP client now lazily loads tool definitions. A GitHub issue reported ~108k tokens consumed at startup (54% of 200k) across MCP tools, custom agents, system tools, and memory files. The fix shipped as an enabled-by-default feature in Claude Code. A separate community project (Context Mode) achieved **98% context reduction** using SQLite FTS5 + BM25 ranking — full tool output stored in a searchable index, only summaries enter context.
4. **Cloudflare Code Mode** — Replaces MCP tool definitions with TypeScript SDK calls. Agent writes code; the SDK executes. Reduction: **99.9%** — tool definitions replaced entirely by a small TypeScript API surface.

**The architectural principle is progressive disclosure:** don't load what you don't need. At session start, the agent receives only a lightweight index of available tools. It fetches full definitions on demand, uses them, then discards or caches them contextually.

## Evidence

- **Engineering blog:** Anthropic measured 58 MCP tools consuming ~55k tokens across GitHub (35 tools, ~26k), Slack (11 tools, ~21k), Sentry (5), Grafana (5), Splunk (2) — "tool definitions account for the majority of our token usage." Tool Search reduced this to ~8k tokens via lazy loading. — [Anthropic Engineering: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use) (Nov 2025)
- **Benchmark:** MCP.Directory measured 7 MCP servers in Claude Code consuming 67,300 tokens before any user input (33.7% of 200k context). GitHub MCP alone: ~18k tokens for 27 tools. Documented three fixes with verified reduction numbers. — [MCP.Directory: MCP Context Bloat Fix 2026](https://mcp.directory/blog/mcp-context-bloat-fix-2026-tool-search-code-mode-progressive-disclosure) (Feb 2026)
- **Community verification:** OpenCode issue #17482 documented a single MCP server (lark-mcp-docx) consuming 86% of context (147k of 168k tokens) before any user message. Proposed solution: two-step discovery / lazy loading. — [GitHub Issue #17482](https://github.com/anomalyco/opencode/issues/17482) (open, 2025-2026)
- **GitHub:** Claude Code lazy loading shipped as feature request #7336 (closed/completed). User-reported baseline: 108k tokens consumed at startup (39.8k MCP tools + 9.7k custom agents + 22.6k system tools + 36k memory files = 54% of 200k). — [GitHub Issue #7336](https://github.com/anthropics/claude-code/issues/7336) (Sep 2025–Mar 2026)
- **Community tool:** Context Mode MCP server achieves 98% context reduction using SQLite FTS5 with BM25 ranking. Tool outputs stored in full-text search index; summaries enter context; full data retrieved on-demand. — [GitHub: mksglu/claude-context-mode](https://github.com/mksglu/claude-context-mode) + [HN discussion](https://news.ycombinator.com/item?id=47193064) (2026)

## Gotchas

- **The MCP spec doesn't enforce progressive disclosure.** The protocol leaves it to clients. If you're building your own MCP client, you need to implement lazy loading yourself — `tools/list` still returns everything. The ecosystem is converging on the pattern, but it isn't mandatory.
- **Tool Search requires opt-in per tool.** You mark tools `defer_loading: true` individually. If you forget to mark a noisy server, it still floods your context. Audit which servers you've connected and which tools within them are actually needed for the current agent task.
- **Code Mode trades one problem for another.** Writing code to call tools is lean on context, but requires the agent to have working knowledge of SDK interfaces — it needs to know the API surface, not just what tools exist. Fine for developer-facing agents; brittle for agents interacting with unfamiliar APIs.
- **Memory systems compound the tax.** If your agent also loads memory files and system prompts at startup (documented: 36k tokens for memory files in Claude Code), adding MCP tools on top can push you past 50% of context before the first user turn. The fix requires auditing all startup load, not just tools.
- **The 50+ tool threshold is the breaking point.** Below ~30 tools, the problem is manageable. Above it, context burn becomes unavoidable without lazy loading. This means the MCP tax hits hardest when agents are most capable — exactly when they need the most context headroom for complex reasoning.
