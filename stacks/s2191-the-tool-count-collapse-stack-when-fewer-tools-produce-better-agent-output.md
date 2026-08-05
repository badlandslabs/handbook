# S-2191 · The Tool Count Collapse Stack — When More Tools Make Your Agent Worse

You built 40 tools. Each one maps cleanly to an API endpoint. The agent can do anything. And it keeps picking the wrong tool, hallucinating tool arguments, or calling a tool when bash would have been faster. The fix: collapse the tool surface.

## Forces

- **The completeness trap** — every API resource feels like it needs its own tool. Tool proliferation feels like feature completeness. It isn't.
- **The LLM's attention budget** — tool descriptions compete for the model's context. More tools mean more decisions, more misfires, more wrong tool selections.
- **The tool-per-resource ceiling** — mirroring your API surface as tools is natural, but it treats the agent as an API caller rather than a problem-solver.
- **The bash-shaped escape hatch** — once agents have shell access, they route around most tools anyway. Fighting this makes both the tools and the bash calls worse.
- **The MCP ecosystem cost** — with 10,000+ MCP servers available, the temptation to wire in "just one more" tool is constant. The marginal tool almost always hurts more than it helps.

## The move

Collapse the tool surface to a minimal expressive set. The specific tools don't matter as much as the discipline of keeping the count low and the expressiveness high.

**The "files over tools" inversion.** Instead of one tool per API resource, give the agent a virtual filesystem populated with the account's current state (workflows, templates, configs as files), a bash interpreter to explore and edit, and a single `_back` primitive to persist changes. Knock rebuilt their agent this way after their tool-per-type prototype failed to scale. Their tool surface collapsed from dozens of narrow tools to three: filesystem, bash, and `_back`. The agent composes changes by editing files in place, then pushing via `_back`.

**The interpreter as universal tool.** A sandboxed code interpreter (Python, JavaScript, or both) replaces a wide class of ad-hoc tools. Data analysis, math, string processing, API calls, and file manipulation all route through one tool with a consistent failure mode (bad code) rather than 20 tools with 20 different failure modes. Microsoft, OpenAI, and Anthropic all expose interpreters this way. The tradeoff: cold-start latency (container boot) and resource cost. In-process REPLs (no container) are faster but less secure.

**The filesystem as state oracle.** Rather than giving the agent tools to query current state, populate a virtual filesystem with the state at the start of each session. `ls` and `cat` replace `get_workflows()`, `get_templates()`, `get_audiences()`. The agent's familiar Unix intuitions work. State reads become free. The filesystem can be backed by Postgres (pgvector, full-text search) rather than a real FS for searchability at scale.

**Two to five tools maximum.** Across frameworks — LangGraph, CrewAI, AutoGen, custom builds — production systems that work reliably tend to have 2–5 tools, not 20–40. The lastmile-ai/mcp-agent framework (8.5K GitHub stars) implements MCP tool composability but explicitly notes that simple patterns beat complex architectures.

**Selective browser automation.** For web-facing tasks, browser tools (Playwright/Chromium) are the most capable but slowest. Use them for tasks that genuinely require rendering (SPA interactions, CAPTCHA, visual verification). Use direct HTTP/curl for API-driven tasks. Don't give the agent both unless the task domain requires it — the ambiguity between "should I use the API or browse the site?" becomes an internal routing problem.

## Evidence

- **Engineering blog:** Knock (knock.app) rebuilt their agent from a tool-per-type pattern to a virtual filesystem + bash approach. Tool surface collapsed from "one tool per management API resource" to three: filesystem, bash, and `_back` persistence. Shipped March 2026. — [https://knock.app/blog/how-we-built-the-knock-agent-virtual-filesystem-and-bash](https://knock.app/blog/how-we-built-the-knock-agent-virtual-filesystem-and-bash)
- **HN discussion:** The Show HN post on the Knock approach received focused discussion on the tradeoffs. Vercel's `just-bash` (TypeScript) provides the open-source virtual bash environment that powers this pattern. — [https://news.ycombinator.com/item?id=48845364](https://news.ycombinator.com/item?id=48845364)
- **Framework:** lastmile-ai/mcp-agent explicitly builds on the insight that "simple patterns are more robust than complex architectures for shipping high-quality agents." 8.5K stars, 872 forks. — [https://github.com/lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent)
- **MCP ecosystem scale:** MCP had 10,000+ active servers and 97M monthly SDK downloads as of early 2026 — [https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools](https://learn.microsoft.com/en-us/agent-framework/agents/tools/local-mcp-tools)

## Gotchas

- **Virtual filesystem cold-start** — populating a large account's state as files at session start can be slow. Pre-compute and cache snapshots, or limit the initial state to the most likely working set.
- **Bash is too expressive** — once agents have bash, they can call external APIs, spawn subshells, or hit rate limits on internal services. Rate-limit and timeout bash calls, not just the tools.
- **Tool description bloat** — even with a collapsed tool count, each tool's description competes for the prompt's tool-calling budget. Keep descriptions short and action-oriented ("Execute Python in sandboxed environment" not "This tool allows you to write and execute Python code for data analysis, mathematical computations, string manipulation, and other computational tasks").
- **The persistence primitive is critical** — `_back` or its equivalent must be atomic, idempotent, and validate inputs. A bad persist breaks the entire "edit files, then commit" model.
