# S-2911 · The Agent Tool-Use Stack

When your agent can reason but can't act — it can't check a balance, post to Slack, run a query, or browse a page. The question is not whether to give agents tools, but which tools, how many, and how to manage the combinatorial explosion when you have 40 MCP servers and the context window screams.

## Forces

- **The token gravity problem.** Loading all tool definitions into context at once has a cost that compounds fast. Ten tools is manageable. Fifty tools means you're paying token tax on definitions for tools you never use. Anthropic's November 2025 engineering post documented that naive MCP clients that load all tools upfront suffer "excessive token consumption" — a solvable but non-obvious failure mode.
- **Tool discovery vs. tool overload.** MCP has thousands of servers in its registry (89k+ stars on the official `modelcontextprotocol/servers` repo). Teams start with five tools and end up with a sprawling zoo — filesystem access, Stripe, GitHub, Slack, browser automation, vector DB, and three weather APIs. More tools mean more ways to fail, more edge cases, and more attack surface.
- **The write-code-vs-call-tools trade-off.** smolagents (Hugging Face, ~1,000 line core) made the case that code-first agents — where the LLM writes Python that calls tools — are more expressive and cheaper than JSON tool-calling schemas. But code execution requires sandboxing, which adds infra complexity.
- **Browser access is table stakes.** Modern agents need to see the web the way users do. Cloudflare workers block simple HTTP clients. SPAs need real browsers. Headless browser infrastructure (Browserbase, Steel) became the default answer by 2025, but self-hosting headless Chrome is a painful path most teams discover too late.

## The move

**Layer 1 — The protocol: MCP as the standard tool bus.**

Anthropic launched the Model Context Protocol in November 2024. By 2026 it is the connective tissue of the agent ecosystem. The official reference servers repo has 89,704 stars; the community registry at `modelcontextprotocol/registry` catalogs thousands of servers. When a company publishes an MCP server, their APIs become callable by any MCP-compliant agent — no custom glue code per tool.

- Build or consume MCP servers for every external integration (Stripe, GitHub, Postgres, Slack, etc.)
- Use the Host/Client/Server model: the agent is the Host, the tool is the Server, MCP is the transport using JSON-RPC 2.0 over stdio or HTTP+SSE
- Prefer scoped tool sets loaded on demand rather than all-at-once — the Anthropic engineering team recommends loading tool definitions lazily, only when a task domain requires them

**Layer 2 — The efficiency trick: code execution beats direct tool calls.**

When an agent needs to use many tools, write code that calls the tools — don't call tools directly. Anthropic's November 2025 post documents this pattern: instead of the LLM receiving a tool result and deciding the next step, the agent writes a script that orchestrates the tool calls, reducing round-trips and token overhead. This is the core smolagents insight too — a ~1,000 line code-first agent out-performs a 50,000 line orchestration framework on production benchmarks.

- Use smolagents' CodeAgent for code-first tool orchestration (Hugging Face, 2025)
- Sandbox code execution via Modal, E2B, or Docker for production safety
- The agent writes Python that calls tools; the Python executes; the agent interprets the output
- Fewer LLM hops, lower latency, lower token cost

**Layer 3 — The browser tool.**

Headless browser APIs are now a standard agent tool. Steel (open-source, 7.4k GitHub stars) and Browserbase are the two dominant approaches — Steel is self-hostable, Browserbase is managed. Both expose browser sessions via REST API that agents call just like any other tool.

- Give agents Steel or Browserbase for any web interaction beyond simple GET requests
- Handle Cloudflare, CAPTCHAs, authenticated sessions, and SPAs that need JS rendering
- Steel supports session replay for debugging; Browserbase offers stealth browsing with fingerprint rotation

**Layer 4 — The memory tool.**

Without persistent memory, every agent session starts from scratch — it re-solves the same bugs, rediscover the same conventions. Engram (open-source, MIT license) provides a local-first memory layer using SQLite with FTS5 — sub-millisecond recall, works on a Raspberry Pi. OpenClaw (145k GitHub stars, launched November 2025) bundles persistent memory as a core feature via its AgentSkills system.

- Engram for team-wide engineering memory: git history, PR context, incident decisions, architecture rationale
- OpenClaw AgentSkills for personal automation memory: preferences, recurring tasks, session state
- Hybrid search (FTS5 + embeddings) for recall that doesn't require expensive embedding lookups on every query
- Memory is not a feature; it's the foundation — 87% of agent failures from missing context per Engram's internal analysis

## Evidence

- **Engineering blog:** Anthropic documented the token gravity problem with direct MCP tool calls and the code-execution solution — [Code execution with MCP: Building more efficient AI agents](https://www.anthropic.com/engineering/code-execution-with-mcp) (November 4, 2025)
- **Framework analysis:** smolagents' architecture analysis (Statsig Perspectives, October 31, 2025) benchmarks code-first agents against orchestration-heavy stacks, finding "fewer LLM calls, lower latency, lower cost" as the primary wins — [SmoLAgents architecture: Lightweight agent design](https://www.statsig.com/perspectives/smolagents-lightweight-design)
- **Enterprise adoption:** By mid-2026, 28% of Fortune 500 companies have MCP servers in production; Stripe reduced payment issue investigation from 15 minutes to 30 seconds using an MCP server for payment analytics; Cloudflare's MCP server enables natural language infrastructure queries — [10 Real-World MCP Use Cases: How Companies Are Using It in Production](https://reskilll.com/blogs/10-real-world-mcp-use-cases-companies-using-production-2026/) (Reskilll, August 7, 2026)
- **Open-source scale:** MCP official servers repo: 89,704 stars, 11,488 forks; MCP registry: 7,176 stars — [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
- **Local agent framework:** OpenClaw reached 145,000 GitHub stars in under three months (launched November 2025); 100+ community AgentSkills covering browser automation, memory, news aggregation — [OpenClaw AI](https://openclaw-ai.dev/)
- **Browser infrastructure:** Steel: 7.4k stars, open-source headless browser API; Browserbase: managed cloud browser infrastructure with stealth browsing and session replay — [Steel Browser API](https://github.com/steel-dev/steel-browser)
- **Memory infrastructure:** Engram uses SQLite + FTS5 for sub-millisecond recall; memory-grounded answers for engineering teams (git history, PR context, incidents) — [Engram — Memory for AI Agents](https://engram-ai.dev/)

## Gotchas

- **Loading all MCP tools at once is an anti-pattern.** Anthropic's engineering team explicitly calls this out. Lazy-load tools by domain or task phase. The difference between 5 tools and 50 tools in context is not linear token cost — it's also model attention degradation.
- **Code execution sandboxes can be escaped.** smolagents and code-execution approaches are powerful but require proper sandboxing. Modal, E2B, and Docker are the standard options. Never give a code-execution agent access to a privileged environment without one.
- **Browser fingerprinting breaks agents.** Many agents using headless Chrome get blocked by Cloudflare or sites that detect automation. Steel and Browserbase handle fingerprint rotation and stealth; rolling your own headless Chrome without these measures will result in agents that work in testing and fail in production.
- **Memory without schema is just a blob.** Engram's SQLite + FTS5 approach works because it stores structured, tagged memories — not raw conversation logs. Without schema, you have a vector store, not a memory system.
- **MCP server auth is an afterthought in most tutorials.** FastMCP tutorials (Danilchenko, April 2026) note that production MCP servers behind corporate VPNs or requiring OAuth need a proxy layer. The 6-line "hello world" MCP server doesn't teach you how to handle GitHub OAuth, corporate SSO, or secrets management.
