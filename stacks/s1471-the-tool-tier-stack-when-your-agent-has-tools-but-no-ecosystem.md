# S-1471 · The Tool Tier Stack — When Your Agent Has Tools But No Ecosystem

The default agent build gives each agent its own custom tool integrations — a web search function here, an API wrapper there, a hardcoded file reader. The problem is that tools built for one agent don't compose, don't share state, and don't survive model swaps. When you add a second agent or change the model, you rebuild everything from scratch. The real unlock is a tool ecosystem: a shared protocol layer where tools are discovered, reused, and composed across agents and models.

## Forces

- **Custom connectors are the custom code of agent building** — every new tool is a bespoke integration that doesn't outlive the current agent or model
- **Tool count and tool quality trade off against each other** — agents with 20+ tools select the wrong one 3× more often than agents with 4 tools (Agentic Stack survey, 2025)
- **Security boundaries differ by tool category** — code execution sandboxes, filesystem permissions, and web browser sessions each require distinct isolation models that can't be collapsed into one approach
- **MCP solved the interoperability problem but created a discovery problem** — 5,800+ servers exist but teams don't know which 5 to start with
- **Browser tools are the most capable and most dangerous** — full-page interaction enables real workflows but opens authenticated session access to injected content

## The move

Map your agent's tools across four tiers. Every tier has distinct security requirements and distinct failure modes. Don't mix them.

**Tier 1 — The Universal Layer (MCP Protocol)**
- Use Model Context Protocol as the tool substrate, not custom wrappers — 97M+ monthly SDK downloads, 300+ client apps, backed by OpenAI, Google, Microsoft, AWS, and Anthropic (MCP Enterprise Guide, Dec 2025)
- Start with the MCP "Essential Trinity": Context7 (library docs, 37K+ downloads), filesystem (secure file operations), and a web fetching server
- MCP gives you tool portability across models — swap Claude for GPT without rebuilding integrations

**Tier 2 — Web Interaction**
- Cloud browsers (Browserbase, Steel, Anchor Browser) for production-grade web scraping and automation — handle sessions, CAPTCHAs, MFA, and proxies automatically
- Standard web search (Bing) for one-shot factual queries with citations
- Agent Mode / full-page interaction for multi-step flows requiring click-throughs and form fills — ChatGPT Plus/Pro only
- Never give a browser tool access to authenticated sessions unless you control the credential injection point

**Tier 3 — Code Execution**
- Use isolated sandbox providers (E2B, Modal, Docker, Cloudflare Workers, Vercel) — OpenAI Agents SDK added first-class support for 8 providers in April 2026
- The critical security property: credential isolation — API keys live in the control harness, not the execution sandbox (CVE-2026-25049 drove this into production focus)
- Persistent containers for multi-step execution chains; ephemeral for single-shot evaluation

**Tier 4 — System APIs and Data**
- Direct API integrations for enterprise systems (Slack, Salesforce, GitHub) via their native MCP servers
- Filesystem access scoped to project directories with explicit read/write boundaries — never agent-wide filesystem access
- Database access through read replicas with write approval workflows for production

## Evidence

- **GitHub readme (wong2/awesome-mcp-servers, 4,217 stars):** Official MCP reference servers cover filesystem, fetch (web content), and everything test server — 474 commits showing active maintenance
- **Research post (MCP Enterprise Guide, Dec 2025):** 97M+ monthly SDK downloads, 5,800+ MCP servers, 300+ client applications, 10,000+ published servers; explosive growth from ~100K downloads (Nov 2024) to 8M+ (Apr 2025) to 97M+ (Dec 2025) — [https://guptadeepak.com/research/mcp-enterprise-guide-2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Enterprise case study (Claude 5 Labs, Feb 2026):** Fortune 500 bank switched 500 developers from Copilot to Claude Code, connected internal compliance tools via MCP, automated security scanning in dev workflow — 40% reduction in compliance review time — [https://claude5.ai/news/claude-code-mcp-integrations-enterprise-adoption](https://claude5.ai/news/claude-code-mcp-integrations-enterprise-adoption)
- **Industry survey (Cxo Techbot, 2025):** 57% of companies already run AI agents; Wells Fargo handling 245M+ interactions without human handovers — [https://cxotechbot.com/public/The-Agentic-Stack-in-2025-10-Tools-Defining-Production-Grade-AI-Agents](https://cxotechbot.com/public/The-Agentic-Stack-in-2025-10-Tools-Defining-Production-Grade-AI-Agents)
- **Reddit community analysis (r/vibecoding, r/LocalLLaMA, 2026):** "Real agents reason, make decisions, use tools, access external data, and complete end-to-end tasks" — tool use is the practical threshold separating agents from chatbots; coding agents (GitHub Copilot, Windsurf, Claude Code) are the most trusted in production — [https://www.aitooldiscovery.com/guides/best-ai-agents-reddit](https://www.aitooldiscovery.com/guides/best-ai-agents-reddit)

## Gotchas

- **43% of MCP servers have command injection flaws** (CSA research, Apr 2026); don't let agents register arbitrary STDIO servers — maintain an explicit allowlist of approved tools and audit all `command` parameters in server definitions
- **Tool count degrades agent performance** — resist the urge to expose all 5,800 MCP servers; start with 2–5 high-signal tools per agent and expand only when a specific gap is demonstrated
- **Browser tool security is the most under-engineered** — injected malicious content in agent-controlled browser sessions can access authenticated sessions; isolate browser contexts from credential stores and enforce session boundaries
- **LangChain v1 changed the tool integration model** — the new `create_agent` + middleware pattern handles tool routing automatically; custom tool wrappers built for pre-v1 LangChain may need migration
- **Sandbox credential isolation is not automatic** — OpenAI's April 2026 SDK update added explicit credential isolation as a first-class feature; older code execution implementations may still route API keys through the execution environment
