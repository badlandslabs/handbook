# S-2411 · The Tool Glut Stack — When Your Agent Has Tools But Can't Pick the Right One

You've given your agent a browser, a REPL, file I/O, API clients, and a search function. It has everything it needs. It still fails. Not because tools are missing — because the agent can't reliably choose between them, describe them accurately, or chain them correctly. The problem isn't the toolbox. It's the interface between the agent and the tools: tool descriptions, tool selection, and tool composition. This stack is about designing that interface.

## Forces

- **More tools ≠ better performance.** Giving an agent 40 tools degrades selection accuracy faster than it expands capability. The model spends tokens evaluating which tool to call, or picks the wrong one and spirals.
- **Tool descriptions are prompts.** The words you write to describe a tool become part of the context injected on every call. Vague descriptions cause mis-selection; verbose ones consume context budget.
- **Token cost vs. capability.** Anthropic showed 98.7% token reduction for a Google Drive → Salesforce workflow by replacing sequential API calls with a single code-execution tool. The right tool is the one that compresses the work, not the one that matches the task most literally.
- **Browser automation went from niche to default.** browser-use hit 50k GitHub stars in 3 months. Every major provider — Anthropic, OpenAI, Google, Amazon, Microsoft — now ships a "computer use" or browser-control capability. Teams building web agents no longer need to roll their own DOM parsing.
- **The MCP ecosystem solved integration, not design.** MCP (Model Context Protocol) gave vendors a shared standard — 13,230+ public servers, 97M+ monthly SDK downloads as of early 2026. But standardizing how you *connect* a tool doesn't standardize how you *design* one.

## The Move

Design tools as compression devices, not feature mirrors. Each tool should replace a class of decisions, not expose a class of API endpoints.

**1. Audit tool count by failure mode, not feature list.** If 3 tools cover 80% of use cases and the other 12 cover 20%, the 12 are noise. Run a tool-selection audit: log every tool the agent *attempted* vs. *correctly selected* over 100 runs. Cut or merge the bottom quartile.

**2. Write tool descriptions as decision guides, not API docs.** Describe *when* to use the tool, not just *what* it does. Compare:
   - Bad: `"search_web(query: str)` — Search the web for information."
   - Good: `"search_web(query: str)` — Use when you need current facts, prices, news, or real-time data that you cannot infer. Do NOT use for code, documentation, or known information."

**3. Use MCP for external services, CLI for local dev, code execution for multi-step composition.** The Slava Dubrov analysis of 2025–2026 tool patterns identifies five useful interface patterns: Skills (instruction carriers), CLI (local execution), MCP (shared external services), code execution (sandboxed composition), and JSON function calling (structured actions). Match the pattern to the use case — don't force everything into function calls.

**4. Replace sequential tool chains with code execution when the loop exceeds 3 steps.** The CodeAct paper showed up to 20% task success improvement when agents compose small programs instead of issuing repeated JSON calls. If your agent needs Google Drive → transform → Salesforce, a code-execution tool that does all three in one sandboxed run beats three sequential tool calls on token cost, latency, and error surface.

**5. Treat browser automation as a first-class tool, not a last resort.** browser-use (YC W25) became the reference implementation for web agents by parsing HTML into clickable elements + screenshots and exposing them as structured function calls. If your agent needs to interact with the web, don't build a scraper — wire in an MCP browser-use server. The maintainers are already handling DOM edge cases you don't want to own.

**6. Keep tool schemas stable.** Breaking changes to tool interfaces silently corrupt agent behavior. The agent learned which tool to call for which situation — when the schema changes, that learned mapping breaks without an error. Version your tools and inject migration notes into the description during transition windows.

## Evidence

- **GitHub repo / YC company:** browser-use (gregpr07/browser-use) — open-source web agent library, 50k+ stars in 3 months, Y Combinator W25. Reaches 40k stars as of March 2025. Used as MCP server in production stacks (mcp-browser-use, JovaniPink). — [https://github.com/gregpr07/browser-use](https://github.com/gregpr07/browser-use), [https://www.ycombinator.com/companies/browser-use](https://www.ycombinator.com/companies/browser-use)

- **Engineering blog (primary source):** "AI Agent Tool Use: MCP, CLI, Skills, and Code Execution" — Edge of Context / Slava Dubrov, March 2026. Documents the five interface patterns for agent tool use, Anthropic's 98.7% token reduction case study (Drive → Salesforce via code execution), and the CodeAct paper's 20% improvement finding. — [https://slavadubrov.github.io/blog/2026/03/24/ai-agent-tool-use](https://slavadubrov.github.io/blog/2026/03/24/ai-agent-tool-use)

- **HN community data:** OpenAI "New tools for building agents" thread (389 points, 157 comments, March 2025). Developers reported agent frameworks adding complexity; multiple commenters (bob1029, segmondy) described rolling custom orchestration around chat completion API instead. Intuned HN launch (117 points, 58 comments, ~61 days ago) surfaced the maintenance burden of browser automation — selectors break as sites change, making AI-generated-and-maintained automation code more reliable than runtime AI control. — [https://news.ycombinator.com/item?id=43334644](https://news.ycombinator.com/item?id=43334644), [https://news.ycombinator.com/item?id=48445171](https://news.ycombinator.com/item?id=48445171)

## Gotchas

- **Over-instrumenting tools with permissions and guardrails defeats the purpose.** If every tool call requires human approval or rate limiting that introduces 5-second delays, agents time out or switch strategies mid-task. Set boundaries at the harness level, not per-tool.
- **Tool descriptions drift out of sync with actual behavior.** API changes, server-side updates, auth scope changes — the description stays frozen in the last commit. Automate description validation as part of your CI: if the tool signature changes, fail the build until descriptions are updated.
- **Code execution tools require sandbox discipline.** Giving an agent `eval()` or subprocess access is powerful but dangerous. Isolate execution in a container with no network access, no filesystem write outside `/tmp`, and no secret env vars. The tool's power is proportional to the blast radius if it goes wrong.
