# S-2465 · The Tool Access Stack

You built the perfect agent loop. It reasons beautifully. But it still can't look up a price, read a file, post a comment, or check if a page changed. The gap between what agents can reason about and what they can actually touch is the primary bottleneck in 2025–2026. The question isn't whether to give agents tools — it's which ones, through what interface, and how many at once.

## Forces

- **Context starvation limits reach**: Every tool definition costs tokens. A GitHub MCP server alone ships ~26K tokens of tool schema. Load 5 servers and you've burned 40% of your context before the first real action
- **Tool proliferation outpaces integration bandwidth**: MCP now has thousands of servers across the community registry. Teams default to "expose everything" and pay the token tax
- **The browser is the last great walled garden**: Most real-world systems — dashboards, CRMs, booking flows, internal tools — live behind a GUI that APIs don't reach. Browser agents are the bridge, but they're still unreliable on multi-step flows
- **Context-window inflation vs. cost**: Sending more tools to the agent costs more per turn. Teams need a way to give agents surgical access, not a full armory
- **Security and permission surfaces matter**: Exposing a file system tool to an agent that processes customer data creates a new class of risk that teams didn't model in their threat models

## The Move

Build a **tiered tool access strategy** — a small permanent foundation of tools every agent gets, a dynamic layer activated per-task, and a dedicated browser tool for GUI-bound systems.

### Foundation tools (always loaded)

- **File system** — read, write, list. Universal. The agent's primary scratchpad. Every MCP server tutorial starts here
- **Web search** — Brave Search MCP (or equivalent). Agents that can't look things up hallucinate more. Non-negotiable in production
- **Code execution** — Python or shell via MCP. Anthropic's Nov 2025 post showed code execution reduces token consumption by writing code that calls tools rather than calling tools directly. 37% token reduction in their benchmarks

### Dynamic tools (activated per session/task)

- **GitHub** — PR creation, issue management, repo browsing. The default for developer-facing agents. 35 tools in the official MCP server, but use tool-search (Anthropic's advanced tool use, Nov 2025) to activate only the relevant subset — 85% token reduction
- **Database access** — SQLite, Postgres, or Redis via MCP. Read-heavy for RAG grounding; write access gated behind human-in-the-loop prompts
- **Slack/Teams/Mail** — notification and alerting tools. Rarely give agents the ability to send on behalf of users; usually read + draft only

### GUI-bound systems (dedicated browser tool)

- **Browser Use** (MIT, 109K GitHub stars, #1 on Odysseys leaderboard at 87.4%) — open-source, runs locally, gives agents xPath-level control for deterministic re-runs. ~$0.02–0.05/task
- **Claude Computer Use** (Anthropic, stable as of 2026) — highest task success rate among browser agents. ~$0.08–0.12/task
- **OpenAI Operator** — best consumer UX, now consolidated into ChatGPT agent. $0.15/task via Pro subscription

Use browser tools for: form fills, multi-system workflows (e.g., check this dashboard → update this spreadsheet → post to Slack), scraping where no API exists. All three still fail regularly on multi-tab, CAPTCHA, and OAuth flows.

### The governance layer

- **Always surface a permission prompt** for write operations — even if the agent is "trusted." Anthropic's MCP spec explicitly recommends this
- **Scope tool access to minimum necessary** — if the agent only needs to read a file, don't expose the delete tool
- **Log every tool invocation** with input/output. You can't debug a hallucinated database query if you didn't capture what the agent actually ran

## Evidence

- **Anthropic Engineering:** "Code execution with MCP: Building more efficient agents" (Nov 4, 2025) — Documents token bloat from loading all tool definitions, demonstrates code-execution-as-tool-call pattern achieving 37% token reduction. GitHub MCP server example shows 35 tools consuming ~26K tokens — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Anthropic Engineering:** "Introducing advanced tool use" (Nov 24, 2025) — Tool Search Tool reduces tool-definition token cost by 85% while preserving 95% of relevant context. Three new beta features for scaling to large tool libraries — https://www.anthropic.com/engineering/advanced-tool-use
- **GitHub / MCP Ecosystem:** modelcontextprotocol/servers repo has 89K stars, community MCP registry lists thousands of servers. Official reference servers cover Filesystem, GitHub, Brave Search, Google Drive, Slack, Postgres, and more — https://github.com/modelcontextprotocol/servers
- **GitHub / Hacker News:** Browser Use — open-source web agents, 109K stars, #1 on Odysseys leaderboard (87.4%), YC W25 launch with 259 HN points. HN comment thread documents real production use cases: form filling, QA automation, data extraction, job applications — https://news.ycombinator.com/item?id=43173378
- **Anthropic Engineering:** "Building Effective AI Agents" (Dec 2024, foundational post) — Core thesis: "The most successful implementations use simple, composable patterns rather than complex frameworks." Recommended starting with the simplest tool set and adding complexity only when needed — https://www.anthropic.com/engineering/building-effective-agents
- **GitHub Gist:** "AI Agent Frameworks Comparison 2026" by manduks (updated March 2026) — Independent benchmarking of 9 frameworks across tool use, multi-agent, and production readiness. Shows browser-use and Claude Code leading on tool integration — https://gist.github.com/manduks/bb0a93c1e0eb21bc718a78ffdcefdc95
- **Web3AIBlog:** "Browser Agents 2026: Operator vs Computer Use vs Browser Use" (May 13, 2026) — Comparative benchmark across real task types. All three still fail on multi-tab and OAuth flows. Claude Computer Use leads on reliability; Browser Use leads on cost and developer control — https://www.web3aiblog.com/blog/browser-agents-battle-operator-vs-claude-computer-use-vs-browser-use-may-2026

## Gotchas

- **Don't expose everything "for flexibility"**: Loading all available MCP tools into context is the most common production mistake. The token cost compounds, and the agent wastes turns deciding between irrelevant options. Anthropic's advanced tool use post specifically calls this out as the #1 scaling problem
- **Browser agents aren't reliable enough for unattended critical flows**: CAPTCHAs, multi-tab sequences, and OAuth handshakes still fail regularly across all three major browser agent implementations. Build human-in-the-loop checkpoints for any flow that involves money, credentials, or irreversible state changes
- **Tool schemas drift**: When the upstream API changes, your MCP server definition may still return success while silently returning wrong data. Add schema validation at the MCP server layer, not just at the LLM prompt level
- **Read vs. write is a security boundary, not just a UX choice**: Exposing write tools (file delete, GitHub force-push, database UPDATE) to an agent that processes untrusted input creates injection risk. Treat write tool exposure the same as exposing a privileged service account
