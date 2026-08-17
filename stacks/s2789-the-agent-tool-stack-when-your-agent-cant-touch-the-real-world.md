# S-2789 · The Agent Tool Stack — When Your Agent Can't Touch the Real World

Your LLM is fluent. It can reason through a task, outline a plan, and describe what needs to happen. Then it hits the wall: it can't check your GitHub repo, it can't run your test suite, it can't browse the web, and it can't write a Slack message. The gap between "knows what to do" and "can actually do it" is the tool problem. Solving it means choosing the right tools, exposing them correctly, and knowing when a tool's interface is the bottleneck.

## Forces

- **The N×M integration tax** — before MCP, connecting N agents to M tools required N×M custom connectors, each with its own auth, schema, error-handling, and maintenance burden. Every new agent-tool pair was a fresh engineering project.
- **Tool interface fidelity** — giving an agent a REST API client is not the same as giving it a browser. Agents need tools that match how the world actually works: through GUIs, dynamic pages, stateful sessions, and human-oriented interfaces — not through the clean API contracts developers write.
- **The stale-state failure mode** — browser-based tools fail differently than API tools. The agent reasons from a DOM snapshot, takes an action, and the page has already changed. The most common agentic browser failure isn't mis-clicking; it's acting on information that was true three steps ago.
- **Over-abstraction risk** — Anthropic's production research found that "the most successful implementations weren't using complex frameworks or specialized libraries. Instead, they were building with simple, composable tools." Wrapping everything in a framework that hides the tool interface adds a layer of indirection that makes debugging harder without making agents smarter.

## The Move

Build a minimal tool surface with three layers, then expand only when you hit a real gap — not a theoretical one.

**Layer 1 — The MCP Protocol (universal glue)**
- MCP (Model Context Protocol) transformed the N×M integration problem into N+M. Write one MCP server, use it from any MCP-compliant client (Claude Desktop, Cursor, Windsurf, OpenAI Agents SDK, custom).
- As of December 2025: ~97 million monthly SDK downloads, 10,000+ public servers, 41% production adoption among senior AI engineers.
- Use stdio transport for local servers (fast, simple), Streamable HTTP for remote (more complex but production-grade with 2025-11 spec additions).
- Source: *Reactify Solutions — "Model Context Protocol in 2026: building production AI integrations on a real standard"* (June 3, 2026) — https://www.reactify-solutions.com/articles/mcp-production-ai-integrations-2026

**Layer 2 — Browser Tool (the primary real-world interface)**
- The browser is the tool that closes the gap between "knows how" and "does": form filling, data extraction, UI validation, job applications, logged-in session access.
- browser-use (MIT, Magnus Müller & Gregor Žunič) is the dominant open-source choice. Supports multi-step workflows, memory, extraction, DOM abstraction, and multi-model support. 3–5× faster than other models on real-world browser tasks.
- For agent-specific browser control: agent-browser-protocol (theredsix/agent-browser-protocol, 155 HN points) is a forked Chromium that freezes the DOM between action and observation — eliminating the stale-state problem. Benchmark: Mind2Web-online leaderboard.
- ghostd.io is a Show HN entry (heavymemory, 5 months ago) specifically for reusable browser workflows — "describe it in text, execute in the browser, save for reuse." Example: agent reads CV, scans inbox, opens job listings, extracts details, builds a Google Sheet.
- Source: *Hacker News — "Show HN: Open-source browser for AI agents"* (155 points) — https://news.ycombinator.com/item?id=47336171
- Source: *Hacker News — "Show HN: AI agent that runs real browser workflows"* (ghostd.io) — https://news.ycombinator.com/item?id=47322046

**Layer 3 — The Tool Hierarchy (narrow beats wide)**
- **File system** — read/write with explicit path scoping. Never give an agent unbounded fs access in production.
- **Code execution** — sandboxed Python/Node. Critical for data analysis, math, transformation tasks. Microsoft, OpenAI, Anthropic all expose this; the pattern is now table-stakes.
- **GitHub MCP server** — repository access, issue management, PR reviews. The most-used MCP server in enterprise stacks.
- **Slack MCP server** — ftaricano/mcp-slack exposes 37 tools with OAuth 2.0, typed errors, retry/backoff, Prometheus metrics. Production-grade Slack integration without custom API work.
- **Database MCP servers** — PostgreSQL, MySQL, MongoDB via connection strings. Enables agents to query live data for synthesis tasks.
- Narrow, single-responsibility tools outperform general-purpose ones. An agent told "search GitHub issues" performs better than one told "use the GitHub API however you want."
- Source: *Airbyte — "12 MCP Server Examples Every AI Engineer Should Know"* (January 23, 2026) — https://airbyte.com/agentic-data/mcp-server-examples

**Tool Definition Discipline**
- Every tool gets: a name, a one-sentence description, and a JSON-schema input spec. The description is for the LLM — keep it concrete, action-oriented, and unambiguous.
- Limit the tool surface per agent to what it actually needs. A research agent doesn't need a code execution tool; a coding agent doesn't need Slack.

## Evidence

- **Anthropic Engineering post (543 HN points):** Teams achieving the best agent results in production used simple, composable tools rather than complex frameworks. "The most successful implementations weren't using complex frameworks or specialized libraries." — https://news.ycombinator.com/item?id=44301809 (original: https://www.anthropic.com/engineering/building-effective-agents)
- **Browser automation tool comparison (2026):** Nine tools ranked on token cost of the driving interface, login-state access, parallelism, and setup friction. No universal winner — ego (lite) leads for parallel logged-in sessions, browser-use leads for open-source flexibility, Playwright MCP leads for developer-native workflows. — https://lite.ego.app/article/best-browser-automation-agents
- **MCP ecosystem data (December 2025):** 97M monthly SDK downloads, 10K+ public MCP servers, 41% production adoption. Protocol standardized N×M integrations into N+M — same pattern TCP/IP, USB, and LSP solved in their domains. — https://www.reactify-solutions.com/articles/mcp-production-ai-integrations-2026
- **Pragmatic Engineer newsletter on MCP:** "It will likely also boost AI agents' capabilities because they have extra tools for more complex tasks." MCP adoption in four months went from Claude Desktop to all major IDEs. — https://newsletter.pragmaticengineer.com/p/mcp

## Gotchas

- **Don't expose raw REST APIs as tools** — the LLM will use them correctly in demos and incorrectly in production. Wrap them in purpose-built tools with constrained inputs and clear semantics.
- **Browser tools need login-state management** — screenshots and DOM snapshots are useless if the agent can't authenticate. Prioritize tools with cookie/session persistence, or use headless browsers with pre-authenticated contexts.
- **MCP tool proliferation creates a new problem** — having 10K+ MCP servers doesn't mean every agent needs all of them. Tool discovery at runtime is valuable, but a large tool surface creates decision paralysis in the model. Scope per-agent, not per-ecosystem.
- **Code interpreter is powerful but not free** — sandbox escapes are real, resource costs are unbounded on long-running loops, and output serialization limits what the agent can see. Set hard timeouts, memory limits, and always validate code-interpreter output before using it as a decision input.
- **The stale-state problem is architectural, not a bug** — it's inherent to any snapshot-based browser interface. Solutions like ABP's DOM freezing or polling-based re-observation are engineering choices, not features. Budget time to implement one if you're building browser automation.
