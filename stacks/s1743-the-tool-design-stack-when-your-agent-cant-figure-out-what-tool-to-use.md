# S-1743 · The Tool Design Stack — When Your Agent Can't Figure Out What Tool to Use

Anthropic's MCP docs go live. You follow the Quickstart, wire up your API, and give the agent 30 tools. It picks the wrong one. Then it picks the right one but with wrong parameters. Then it exhausts your context window and forgets what it was doing. The tooling ecosystem exists — the problem is that every tool was designed for a human reading a reference page, not a model trying to decide.

## Forces

- **Tool definitions are the context bloat culprit.** MCP servers with 30+ tools can preload 50K–100K tokens before the agent does any real work. Agents then select wrong tools and lose the task in noise — not a prompt problem, a tool design problem.
- **Humans search; models need pipelines.** A human tool user reads a description, clicks around, and mentally assembles a plan. A model needs discrete, deterministic steps with predictable output shapes — and it needs to discover tools on demand, not all at once.
- **Output format is agency.** When a tool returns raw API dumps, the agent must parse, filter, and decide before it can act. When a tool pre-processes that data into structured summaries, the agent's reasoning is faster and more reliable.
- **Schema-only definitions fail at scale.** Two tools with similar names or overlapping purposes confuse model tool selection. Examples of correct usage outperform schema descriptions by 72% → 90% accuracy in Anthropic's benchmarks.

## The Move

Design tools for how agents actually reason, not how humans navigate reference docs.

- **On-demand discovery over upfront loading.** Use a Tool Search Tool (Anthropic's pattern) or filesystem-style tool discovery — agents read tool definitions when they need them, not all at startup. This cut Datadog's context usage dramatically.
- **Filter data before it reaches the model.** A tool that returns 500 raw log records forces the model to waste tokens parsing noise. Pre-aggregate, summarize, or paginate results server-side. Anthropic showed this reduces token usage from ~150K to ~2K for code-execution-heavy tasks.
- **Use CSV for tabular data, structured summaries for logs.** Datadog measured CSV as ~50% fewer tokens than JSON for identical records. The model's context budget is shared — every byte in is a byte that can't hold reasoning.
- **Progressive disclosure of tool capabilities.** Surface the most common tools first. Let agents dig deeper into specialized tools only when needed. Anthropic calls this "presenting tools as code on a filesystem" — the agent navigates rather than absorbs.
- **Add usage examples to every non-trivial tool.** Schema definitions alone don't teach correct invocation patterns. Anthropic's tool use examples feature improved tool selection accuracy from 72% to 90% in benchmarks.
- **Standardize output shapes across related tools.** Agents struggle when similar operations return wildly different shapes. One consistent output schema across a family of tools lets the agent generalize rather than re-learn per call.

## Evidence

- **Engineering blog (Datadog):** "Agents would fill their context windows with log data and lose track of what they were doing. They'd request what seemed like a reasonable number of records, then blow their token budget because a few of those records happened to be huge." — [Datadog Engineering, March 2026](https://datadoghq.com/blog/engineering/mcp-server-agent-tools)
- **Engineering blog (Anthropic):** Tool Search Tool + Programmatic Tool Calling reduced context bloat 85% and intermediate result pollution 37%. Tool use examples improved selection accuracy 72% → 90%. — [Anthropic Advanced Tool Use, November 2025](https://www.anthropic.com/engineering/advanced-tool-use)
- **GitHub repo (Agent Browser Protocol):** ABP — a Chromium fork with MCP baked into the browser engine — freezes JavaScript and virtual time between agent actions, returning deterministic settled page states instead of race-prone callbacks. Scores 90.53% on Online Mind2Web benchmark. — [GitHub theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)

## Gotchas

- **Designing for agents is a different skill than designing for humans.** Most internal API teams design tools for human-readable output. Re-review every tool's output format specifically for agent consumption.
- **Browser automation is the hardest tool category.** ABP exists because Playwright-based MCP tools require agents to manage WebSocket sessions, race conditions, and manual wait heuristics. If your agent does browser work, the tool boundary matters enormously.
- **Tool count grows faster than tool quality.** Each new MCP server added to an agent increases context overhead and tool-selection confusion. New tools need to earn their slot, not just function.
