# S-826 · The Minimal Tool Stack — When Fewer Tools Beat More

You keep adding tools to your agent and it keeps getting worse. The instinct to specialize is wrong — the evidence says the opposite.

## Forces

- **The specialization trap** — when an agent fails, the instinct is to add a dedicated tool for that failure mode. Each new tool adds to the context window, confuses tool selection, and creates new edge cases.
- **The token budget ceiling** — every tool definition costs tokens upfront, every intermediate result costs tokens to pass through. With dozens of tools, you exhaust the context window before the agent does useful work.
- **The model already knows how** — LLMs were trained on vast amounts of code. They already know how to navigate filesystems, run commands, and interact with the web. Forcing them through specialized tool wrappers often degrades performance.
- **The MCP explosion** — 500+ MCP servers exist. The question is not "what can I connect?" but "what should I connect?"

## The move

The minimal tool stack: give agents fewer, more general tools instead of many narrow ones. Cross-validated across Anthropic engineering, Vercel's production data, and independent research.

### The code-execution-via-MCP pattern (Anthropic, Nov 2025)

Anthropic's engineering team documented a fundamental shift: instead of passing every tool definition directly into context, agents write code that calls MCP servers. The difference:

```
# Traditional: all tool defs in context every request
# Context = System + 50 tool definitions + history
# = 150,000+ tokens per request regardless of what the user needs

# Code execution with MCP: tools as code
# Context = System + ~2 general tool defs + history
# = 2,000–5,000 tokens per request
# Agent writes code, code calls the right tool, returns results
```

They replaced most internal tooling with a **filesystem tool** and a **bash tool**. Sales call summarization dropped from ~$1.00 to ~$0.25 per call on Claude Opus 4.5 — a 75% cost reduction with improved output quality.

### The 80%-tool-deletion case study (Vercel, Dec 2025)

Vercel's internal text-to-SQL agent (d0) started with 16 specialized tools for different SQL operations, schema lookups, and validation steps. 80% success rate. Fragile.

They deleted 80% of the tools, leaving roughly 3: arbitrary command execution, a sandbox, and a SQL execution command. The agent now navigates their Cube semantic layer using standard Unix utilities (`grep`, `cat`, `ls`).

Results:
- **100% success rate** (up from 80%)
- **3.5x faster** execution
- **37% fewer tokens**
- **42% fewer steps**

Andrew Qu (Vercel): "The agent got simpler and better at the same time. All by doing less."

### The browser is the one tool that justifies specialization

The one exception to the "fewer is more" rule: **browser automation**. Browser interaction is the case where general tools (shell commands, filesystem access) genuinely fail and a purpose-built tool is required. Key insight from the Agent Browser Protocol (ABP) project on HN:

> "Most browser-agent failures aren't about the model misunderstanding the page. The model is reasoning from stale state."

The fix: structured accessibility tree snapshots (not raw HTML, not screenshots) + state synchronization after each action. This is what Microsoft's Playwright MCP (31K+ GitHub stars) and Apple Safari's built-in MCP server (Safari Technology Preview 247, Jul 2026) both converged on independently.

### Tool count is not the lever — task-fit is

Research from arXiv (Jun 2026) — "How Many Tools Should an LLM Agent See?" — found that the optimal shortlist size depends on task complexity and model capability. A chance-corrected metric (Bits-over-Random, BoR) reveals that:

- **Small shortlists** (5-10 tools): better for focused, high-stakes tasks where precision matters more than coverage
- **Larger shortlists** (15-30): better for open-ended exploration where missing a tool category is costly
- **Context window size** is the real constraint, not the count itself

## Evidence

- **Anthropic engineering post (Nov 2025):** Documented the code-execution-via-MCP pattern — replacing direct tool calls with code-written MCP invocations, cutting token usage from 150K+ to ~2K per request. Sales summarization: $1.00 → $0.25 per call. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Vercel engineering blog (Dec 2025):** d0 text-to-SQL agent: 16 tools → ~3. 80% → 100% success rate. 3.5x faster, 37% fewer tokens, 42% fewer steps. "The agent got simpler and better. All by doing less." — [vercel.com/blog/we-removed-80-percent-of-our-agents-tools](https://vercel.com/blog/we-removed-80-percent-of-our-agents-tools)

- **arXiv research (Jun 2026):** "How Many Tools Should an LLM Agent See? A Chance-Corrected Answer" — proposes BoR metric showing optimal tool shortlist size is task- and model-dependent; no universal count. — [arxiv.org/abs/2605.24660](https://arxiv.org/abs/2605.24660)

- **Show HN / GitHub (Mar 2026):** Agent Browser Protocol — forked Chromium with state synchronization after each action. 90.5% on Online Mind2Web. Key finding: stale browser state is the primary failure mode, not model misunderstanding. — [news.ycombinator.com/item?id=47336171](https://news.ycombinator.com/item?id=47336171) | [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)

- **Apple Safari MCP server (Jul 2026):** Built-in MCP server in Safari Technology Preview 247 — 16 tools giving agents screenshot, DOM inspection, JS execution, network monitoring, console output. Browser control as platform infrastructure. — [thenewstack.io/safari-mcp-platform-infrastructure](https://thenewstack.io/safari-mcp-platform-infrastructure)

## Gotchas

- **"Fewer tools" does not mean "one tool."** Vercel's success came from ~3 tools (bash, sandbox, SQL exec), not 1. The Anthropic approach uses a filesystem tool + a bash tool. General-purpose, not maximally generic.
- **The browser exception is real.** You cannot replace web interaction with shell commands. Browser automation tools (Playwright MCP, ABP, Safari MCP) are the one category where specialization genuinely wins.
- **Context window size drives the decision, not philosophy.** If your agent has a 200K context window and 8 tools, fewer-tools-is-better may not apply. If it has 32 tools with 4K definitions each, you have a problem regardless of what the literature says.
- **Tool schemas still matter.** Even general tools need good descriptions. "execute bash commands" is too vague. "execute bash commands in an isolated sandbox; stdin/stdout only; no network access; timeout after 30s" gives the model enough to reason about when and how to use it.
- **Code execution tools require sandboxing.** Bash without sandboxing is a security risk. Every production code-execution setup (Anthropic's, Vercel's, OpenAI's Agents SDK) runs in isolated containers or sandboxes with resource limits and no external network access.
