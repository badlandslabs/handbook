# S-952 · The Tool Verbosity Gap Stack — What You Give Your Agent Determines What It Can Do

You're building an agentic workflow and you wire it to one tool — say, a web search. The agent does fine on demos. In production, users ask it to fill out a form, query a database, and run a calculation. It can only do one of those things. The failure isn't in the orchestration layer or the model — it's in the tools you gave it. This is the **tool verbosity gap**: agents are only as capable as the tool surface you expose, and most teams under-engineer that surface until it's already causing production pain.

## Forces

- **Breadth vs. depth trade-off** — More tools mean more capability but more blast radius to contain, more permission fatigue for users, and harder evaluation.
- **Tool quality compounds agent quality** — Ambiguous parameter names, poor schemas, and missing error handling cause tool-call failures that cascade through the entire workflow. A single bad tool can poison an otherwise well-designed agent.
- **The MCP convergence is real but not complete** — Model Context Protocol has won the registration layer (13,000+ servers, 97M+ monthly SDK downloads as of 2025-2026), but the tool implementations underneath are uneven. Not all MCP servers are production-grade.
- **Containment and capability are in tension** — The same tools that make an agent useful (filesystem access, code execution, browser control) are the ones that cause damage when misbehaving. Anthropic's telemetry shows humans approve 93% of permission prompts — the containment layer has to work even when the human isn't paying attention.

## The move

**Build a minimal, high-quality tool surface instead of a large, shallow one.** The evidence from production agent deployments converges on five tool categories that cover the majority of real-world workflows, and each category has specific implementation choices that separate working from broken.

### The five categories that matter

1. **Information retrieval** — Web search (Firecrawl, Brave Search MCP), knowledge base / RAG retrieval, GitHub API access. These extend the model's knowledge without changing its reasoning. Web retrieval prevents hallucination on time-sensitive facts; RAG retrieval grounds answers in your own data.

2. **Structured data access** — Database tools (Postgres MCP, SQLite MCP) with read-only enforcement, column allowlists, and row/cost limits. The production-grade Postgres MCP servers all enforce these; the archived/community ones frequently don't. If your agent can query your database, it can only do so through tables you've explicitly exposed.

3. **Code execution** — Sandboxed Python/JS execution (E2B, Modal, Docker-based). The key insight from production deployments: agents that execute code need ephemeral, isolated runtimes with task-scoped credentials, network egress allowlists, and action reversibility. The blast radius of a `DELETE FROM users` query is zero if the agent's sandbox can't reach your production database. E2B's process-level isolation in Rust (Daytona) offers sub-10ms cold starts; Docker-based approaches offer stronger isolation at the cost of startup time.

4. **Browser / UI automation** — browser-use (81K GitHub stars, 89.1% WebVoyager benchmark success rate), Skyvern, Anthropic's Computer Use. These fill the gap for vendor portals, government sites, and legacy apps that have no API. The agent reads the DOM, determines action, and drives the browser like a human who understands the page — no CSS selectors to maintain. Heavy anti-bot protection (Cloudflare, DataDome) remains a real blocker for some sites.

5. **Communication / tooling** — Slack/Discord MCP for notifications, GitHub MCP for issue/PR management, filesystem MCP for reading/writing structured files. These close the loop between agent decision and organizational action.

### Design principles for tool schemas

- **Unambiguous parameter names** — `city` not `location`, `max_results` not `limit`. The model must infer intent correctly from the name alone.
- **Descriptive schemas with examples** — MCP's JSON schema format supports descriptions; use them. A tool with a docstring explanation of what `table_name` means in your specific context outperforms one with just a type annotation.
- **Error-first design** — Every tool should return structured error information (not just "failed"), so the agent can decide whether to retry, fall back, or escalate.
- **Cost and rate limits as first-class tool parameters** — Database tools should expose `max_rows`; web scraping tools should expose `timeout_seconds`. Agents that don't know cost bounds will run up bills or hit rate limits in production.

### Containment layer (non-negotiable for production)

Anthropic's Claude Code telemetry: 93% of permission prompts approved by users → approval fatigue is real. Auto mode blocks ~83% of risky behavior before execution. For your own agents:

- Scoped credentials: tools get tokens that can only touch their target system, never a superset.
- Network egress allowlists: a code-execution sandbox should only reach endpoints you've approved.
- Reversible actions: design tools so the worst-case outcome is recoverable (e.g., write to a staging table, not production).
- Full VM isolation for browser agents: browser-use and Skyvern both recommend containerized browser execution where the browser's blast radius is bounded to a workspace directory.

## Evidence

- **Anthropic engineering on containment:** Claude Code users approve ~93% of permission prompts; auto mode blocks ~83% of risky behavior before execution. The blast radius containment model uses six interlocking isolation mechanisms (two survive root-level access inside the VM). — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/how-we-contain-claude) (May 2026)
- **MCP ecosystem scale:** 13,230+ public MCP servers as of March 2026, up from ~100 when Anthropic launched the protocol in November 2024. Official TypeScript SDK: 79K+ GitHub stars, 97M+ monthly downloads. Remote MCP servers grew ~4× since May 2025. — [OpenClaw / MCP Manager](https://openclaw.direct/mcp-guide/model-context-protocol-examples) (March 2026) + [Zylos Research](https://zylos.ai/research/2026-01-10-mcp-servers-ecosystem) (January 2026)
- **Browser-use adoption and benchmarks:** 81,754 GitHub stars, 9,625 forks as of mid-2026. 89.1% success rate on the WebVoyager benchmark. $17M seed funding from Felicis Ventures, Y Combinator, Paul Graham. — [GitHub browser-use](https://github.com/browser-use/browser-use) + [FusionChat](https://fusionchat.ai/news/revolutionizing-web-automation-the-browser-use-story)
- **Postgres MCP production requirements:** Production-grade Postgres MCP servers enforce read-only mode, column allowlists, row limits, and query cost guards. Archived community servers were found to have SQL injection vulnerabilities bypassing read-only protection. — [QueryBear Landscape Review](https://querybear.com/blog/state-of-postgres-mcp-2026) (May 2026)
- **Sandbox infrastructure maturity:** E2B, Modal, and Daytona (process-level Rust isolation) all in production use. Docker + E2B partnership announced 2026. Enterprise governance primitives (OWASP agentic AI policy enforcement) becoming native sandbox features. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/sandboxed-code-execution-ai-agents-e2b-modal-daytona) + [Docker Blog](https://www.docker.com/blog/docker-e2b-building-the-future-of-trusted-ai/) (2026)

## Gotchas

- **Not all MCP servers are production-grade.** The 13,000+ count includes archived repos, proof-of-concept implementations, and servers with known security gaps. Before wiring a community MCP server into a production agent, audit it for the production requirements in your threat model — especially for database and filesystem tools.
- **Browser automation hits anti-bot walls.** Cloudflare, DataDome, and PerimeterX can block agentic browsers. This is not a solvable problem in general — it's a deployment constraint you need to know about before promising browser automation to users. Test against your specific target sites.
- **Tool count scales blast radius.** Every tool you add is a new failure mode and a new attack surface. Teams that start with 20 tools and discover 15 are unused in production end up auditing and removing them anyway. Start with the minimum viable tool surface and add on demand.
- **The LLM can't use a tool it doesn't know exists.** MCP's tool registration solves the discoverability problem — once registered, the model sees all available tools. But you still need to prompt the model to actually call the right tool for the right task. Tool selection is a separate skill from tool availability.
