# S-1359 · The Tool Selection Stack — When Giving Your Agent More Tools Makes It Worse

When you reach for it: You have an agent that works beautifully with 3 tools. Then you add 10 more for production coverage, and it starts picking the wrong tool, calling tools with hallucinated parameters, and ignoring the one it actually needs. You didn't break anything — you just hit the tool explosion cliff.

## Forces

- **More tools ≠ better agents.** Berkeley Function Calling Leaderboard shows individual tool-calling accuracy reaches 96% in isolation but drops below 15% in large-toolset, multi-turn scenarios. Adding tools beyond ~30 creates a cliff, not a slope.
- **Tool definitions are tokens before your query.** A simple single-parameter tool costs ~96 tokens in context. A complex 28-parameter tool costs ~1,633 tokens. With 37 tools, you spend 6,000+ tokens just listing what the agent *can* do — before it sees the actual question.
- **Discovery and execution are different problems.** The tool that searches your codebase is different from the tool that edits it. Treating them as the same problem leads to bloated schemas where the agent can't distinguish intent.
- **Security and capability are in tension.** The tools powerful enough to be useful (file system, database, code execution, browser) are also powerful enough to cause damage. Sandboxed agents reduce security incidents by ~90% vs. unrestricted access, but sandboxing adds engineering complexity.

## The move

- **Design tool schemas like APIs, not prompts.** Use structured JSON Schema with clear descriptions, constrained parameter types, and explicit error states. The agent reads the schema — make it precise. AppScale's 2026 production pattern recommends error envelopes, idempotency keys, and schema versioning from day one.
- **Start with 5 tools, grow surgically.** A HN commenter on the "Building Effective AI Agents" thread put it plainly: "A few clearly defined LLM calls with some light glue logic usually leads to something more stable, easier to debug, and much cheaper to run." Add a tool only when a failure mode recurs in production.
- **Use lazy loading for large tool sets.** Rather than dumping 50+ tool definitions into every prompt, implement retrieval-based tool selection — the agent sees only the top-k relevant tools for the current intent. The tool explosion problem is fundamentally a context management problem.
- **Pick your five from this validated set.** Across MCP server directories (MCP.so, Toolradar's 2026 guide), Hacker News discussions, and Y Combinator 2025 batch patterns, the most production-validated tool categories are: filesystem, Git/GitHub, a database (Postgres/Supabase), browser automation (Playwright/Puppeteer), and Slack or a messaging channel. These cover the broadest class of real tasks.
- **Scope each tool to one action.** A `search_emails(query, from, date_range)` tool beats a generic `run_query(sql)` tool that the agent then has to construct SQL for. The closer the tool is to the user's intent, the fewer decisions the LLM has to make.
- **Sandbox everything that touches execution.** For code interpreters and terminal access, use isolation primitives: Kubernetes pods (Agent Sandbox), microVMs for strongest isolation, gVisor for user-space syscall interception, or at minimum a low-privilege account. The HN "Ask: How are you sandboxing coding agents?" thread surfaced real patterns including SandVault (macOS low-priv account) and bubblewrap on Linux. Sandboxed agents show ~90% fewer security incidents.
- **Govern with hierarchical tool routing past 50 tools.** Above 50 tools, flat tool lists need organizational structure: grouping by domain (code, data, comms), access control per tool, audit logging of invocations, and rate limiting on expensive tools. The agents that work in production aren't the ones with the most tools — they're the ones where each tool is discoverable, well-described, and scoped.

## Evidence

- **Research report:** The Tool Explosion Problem — accuracy drops from 95% at 5 tools to under 30% at 100 tools; Berkeley Function Calling Leaderboard shows 96% individual accuracy collapsing below 15% in multi-tool scenarios — [tianpan.co](https://tianpan.co/blog/2026-04-13-tool-explosion-problem-agent-tool-selection-at-scale)
- **HN discussion:** "Ask HN: How are you sandboxing coding agents?" — bubblewrap on Linux, SandVault/ClodPod on macOS, Kubernetes pods; "remote code execution as a service has caught on as much as it has" — [news.ycombinator.com/item?id=46400129](https://news.ycombinator.com/item?id=46400129)
- **MCP ecosystem analysis:** Most useful MCP servers are filesystem, GitHub, Postgres, browser automation (Puppeteer), Slack; major frameworks (Claude Agent SDK, LangGraph, CrewAI, PydanticAI) have native MCP support — [thoughtworks.com](https://www.thoughtworks.com/en-us/insights/blog/generative-ai/model-context-protocol-mcp-impact-2025), [toolradar.com](https://toolradar.com/guides/best-mcp-servers)
- **Benchmark:** Agent Browser Protocol (ABP) scores 90.5% on the Online Mind2Web benchmark using Opus 4.6; handles dynamic DOM failures (modals, autocomplete dropdowns, downloads) that break standard Playwright-based agents — [news.ycombinator.com/item?id=47336171](https://news.ycombinator.com/item?id=47336171)
- **Production guide:** Tool-calling schema design best practices: error envelopes, schema versioning, idempotency keys, lazy tool loading — [appscale.blog](https://appscale.blog/en/blog/ai-service-pattern-tool-calling-schema-design-llm-agents-2026)

## Gotchas

- **"We'll add tools as needed" is a trap.** Tool explosion is easier to prevent than to cure. Design for tool governance *before* you hit 30.
- **Tool descriptions are prompts too.** A vague description like `search_database(query)` makes the LLM guess intent. A precise description with example inputs and output shapes dramatically improves selection accuracy.
- **MCP solved integration but not governance.** The Model Context Protocol gives you a standard interface, but it doesn't give you per-tool access control, rate limiting, or audit trails — you still need those layers.
- **Browser automation tools fail silently in ways file tools don't.** Modals, autocomplete dropdowns, dynamic reflow, and download confirmation dialogs block agents mid-step. Tools like Agent Browser Protocol specifically target these failure modes, which standard screenshot-then-click approaches miss.
- **Sandbox isolation reduces capability.** A sandboxed agent can't access your git credentials, SSH keys, or network resources. Know which tools need which privilege levels before you scope the sandbox.
