# S-2917 · The Tool Catalog Stack: When Your Agent Has No Hands

Your agent writes fluent plans. It reasons beautifully about what to do. Then it runs — and has nothing to do it with. You gave it a great model and a clever system prompt. You forgot to give it tools. The tool catalog is the set of external capabilities an agent can actually invoke: filesystem access, web search, database queries, code execution, browser control, API integrations. Without them, you have a very expensive autocomplete. With the right set, you have something that can actually work.

## Forces

- **Token overhead scales with tool count.** Every tool definition gets loaded into context. 10 tools might add a few hundred tokens; 500 tools can consume 100K+ tokens and tank inference speed. You want reach, but reach has a cost.
- **Agents can't discover tools they don't have.** An agent trained never to browse the web will not browse the web — no matter how good the model. Capability lives in the tool catalog, not the system prompt.
- **Security and capability are in tension.** Filesystem access enables productivity. It also enables path traversal. Code execution enables agents to run analysis. It also enables sandbox escape. Every tool you add is a new attack surface.
- **Tool quality varies more than tool count.** One well-designed MCP server that wraps a complex API beats ten poorly documented tools that return raw responses. The agent's ability to use a tool depends as much on description quality and error handling as on what the tool actually does.
- **The MCP ecosystem is enormous but uneven.** There are thousands of MCP servers. The top 5 categories cover ~95% of real use cases. The long tail is mostly experiments.

## The Move

Map your tool catalog to five capability tiers. Give every agent at least one tool from each tier it needs. Evaluate tool quality, not just count.

**Tier 1 — World knowledge (web search + retrieval)**
- Web search (Bing, DuckDuckGo, Brave via MCP server) for real-time facts
- Documentation lookup (Context7 — 37K+ downloads, fetches live library docs vs. training cutoff data)
- Hacker News / technical forums (hn-mcp: full comment trees, depth control, Algolia search)
- The rule: agents hallucinate less when they can verify against live sources

**Tier 2 — Code execution (sandboxed compute)**
- Docker-isolated code runner via MCP (Python, Node, Bash) for data processing, calculations, transformations
- Anthropic measured up to 98.7% token reduction vs. loading all tool definitions individually — the agent writes code that calls tools, instead of calling tools directly
- Security baseline: `--network none --read-only --no-mount` plus explicit capability flags
- Use for: parsing large datasets, running transformations, executing scripts, any compute-intensive step

**Tier 3 — Data access (filesystem + databases)**
- Filesystem via MCP: read, write, glob, grep — the minimal set that covers 90% of local agent work
- Database: Google MCP Toolbox (list_tables, execute_sql), or Neo4j for knowledge-graph queries
- Parameterized queries at the driver level — never concatenate LLM-generated strings into SQL
- Path traversal defense: resolve to absolute path, check against allowed-root prefix

**Tier 4 — Web and browser control**
- Browser Use (110K GitHub stars, YC-backed): natural language → browser actions, self-healing when UI changes
- Alternatives: Stagehand, Skyvern, LaVague — all MCP-compatible, different tradeoffs on self-healing vs. determinism
- Computer use (Anthropic/Gemini native): full desktop/mobile control for agents that need to use apps the way humans do
- The emerging pattern: reverse-engineering a web app's own API calls into agent tools (Frigade, auto-generated MCP)

**Tier 5 — API integrations (productivity layer)**
- GitHub MCP (51 tools: issues, PRs, repos, search)
- Linear MCP (issues, projects, cycles — official from Linear)
- Slack/Discord MCP (messaging, notifications)
- Sentry MCP (error triage, rate-limit-aware)
- YC Company Directory MCP (search companies, founder details, job postings)
- The principle: wrap third-party services as tools rather than embedding API keys in prompts

**The token budgeting rule:** If you need >50 tools, present MCP servers as code APIs (Anthropic's pattern). The agent writes code that imports and calls the server — loading the server once, not all tool definitions on every call. This is the 98.7% reduction mechanism.

## Evidence

- **Engineering blog (Anthropic, Nov 2025):** Documented code execution with MCP achieving 98.7% token reduction by treating MCP servers as code APIs rather than direct tool definitions. Showed that "direct tool calling scales poorly — agents scale better by writing code that calls tools on demand." — https://www.anthropic.com/engineering/code-execution-with-mcp

- **GitHub repository (browser-use/browser-use, 110K stars, Oct 2024):** "Make websites accessible for AI agents. Automate tasks online with ease." CLI tool installable via `uv add browser-use` with `browser-use skill install`. Powers production agent deployments for repetitive web tasks. — https://github.com/browser-use/browser-use

- **HN Show HN (saqadri, Jan 2025, 80 points):** mcp-agent framework implements Anthropic's "Building Effective Agents" patterns composably via MCP. The comment thread on HN revealed a key debate: CLI-first developers argue "just use CLI tools with --help mechanics" while MCP advocates argue MCP's discovery and standardization outweigh the overhead. — https://news.ycombinator.com/item?id=42867050

- **Community resource (hireblackout/awesome-mcp-servers, Dec 2025):** Curated list ranked by GitHub downloads and Reddit consensus. Top 3 by downloads: Context7 (37K downloads), filesystem MCP, web search MCP. States "These 3 MCPs cover 95% of use cases." — https://github.com/hireblackout/awesome-mcp-servers

- **Engineering blog (Neo4j, May 2026):** Documents six tool categories: web search (low risk), retrieval (low-medium), computation (medium), interaction (medium), workflow automation (medium-high), and physical/world interaction (high). Notes security risk scales with tier. — https://neo4j.com/blog/agentic-ai/agent-tools/

- **Technical guide (AliveMCP, Jun 2026):** Security patterns for each tool category: filesystem → path traversal defense with allowed-root; web fetch → hostname resolution before request, block RFC 1918 + loopback; code execution → Docker with 6 explicit flags; database → parameterized queries at driver level. — https://alivemcp.com/blog/mcp-server-real-world-tools-guide

## Gotchas

- **Loading all tool definitions on startup is the #1 token waste.** If you have >50 tools, refactor to code-API pattern: one MCP server definition, agent writes code to call specific sub-tools. Saves up to 98.7% on token overhead.
- **Tool descriptions are prompts.** "A tool that searches the database" produces worse results than "A tool that executes parameterized SQL against the orders table, returns JSON rows, and times out after 30s." The description quality directly determines whether the agent selects the right tool.
- **MCP servers can lie about capabilities.** Third-party MCP servers may promise more than they deliver, or may change without notice. Pin to specific versions and validate responses against expected schemas.
- **Browser tools drift.** Web UIs change constantly. Agents using browser automation will encounter broken selectors. Use tools with self-healing (Browser Use, Stagehand) or build recovery loops that re-locate elements on failure.
- **Security is not a later concern.** Each tool category has a canonical attack: path traversal (filesystem), SSRF (web fetch), SQL injection (database), sandbox escape (code exec), credential leakage (API wrappers). Design security before deployment, not after.
