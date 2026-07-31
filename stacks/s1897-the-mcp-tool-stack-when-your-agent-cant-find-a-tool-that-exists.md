# S-1897 · The MCP Tool Stack: When Your Agent Can't Find a Tool That Exists

When your agent has the right model but can't connect to the tools it needs — your code exec is in one repo, your browser is in another, and every new integration requires a custom handler.

## Forces
- **The N×M integration problem** — before MCP, connecting every LLM client to every tool required custom code per pair. With 5 LLMs and 10 tools, that's 50 integrations.
- **Context window is finite** — loading all tool definitions upfront burns tokens and slows every inference call. A 100-tool manifest is not free.
- **Tool sprawl in production** — as agents scale, teams end up with MCP server sprawl: one per tool, each with its own auth, version, and failure mode.
- **Protocol fragmentation** — MCP won the standard war, but not every client or server implements it uniformly. Remote vs. local, streaming vs. stateless, auth models differ.
- **Security surface expands with every server** — 43% of MCP servers have command injection flaws; 10 plugins push exploit probability past 92% (per Deepak Gupta's security audit, Dec 2025).

## The Move
MCP (Model Context Protocol) is the USB-C of AI tool integration. Build one MCP server per resource, connect it once, use it everywhere.

**The practical stack:**

- **Browser automation:** Playwright MCP server (or Vercel's agent-browser) — agents research, scrape, and interact with web UIs. TheAgenticBrowser (422 stars, Jan 2025) uses a three-agent loop: Planner → Action → Validator.
- **Code execution:** Sandboxed runtime via MCP. Anthropic's Nov 2025 post showed that writing code to call tools (rather than passing tool results directly) reduces token overhead and scales better.
- **Data access:** Postgres, filesystem, and internal APIs as MCP servers. One server per data source.
- **Orchestration layer:** LangGraph or PydanticAI for multi-step agent logic; connect MCP servers as tools. Anthropic recommends keeping orchestration simple and composable rather than relying on heavy frameworks.
- **For local models:** llama.cpp added full MCP support, enabling local agents to call tools without cloud dependency. Ollama can serve as the local LLM runtime with MCP tool bridging.
- **Governance layer:** MCP proxy in front of servers for multi-tenant isolation, rate limiting, and routing. API-key auth at the proxy level is the simplest production pattern.

**Scaling tool count:** Don't load all tools at once. Group tools by phase or task type. Use code-as-tool: agents write code that calls specific MCP servers rather than receiving all definitions upfront.

## Evidence
- **Engineering post:** Anthropic's "Code execution with MCP" (Nov 2025) documents that presenting MCP servers as code APIs (agents write code to call tools) is more token-efficient than passing tool definitions directly through the context window — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Ecosystem data:** MCP SDK downloads grew from ~100K to 97M+ per month in ~1 year. 13,230+ public MCP servers exist. GitHub stars on the official repo: 79,000+. 78% of enterprise AI teams have MCP-backed agents in production as of mid-2026. — [URL](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **HN discussion:** "Building Effective AI Agents" (Anthropic, linked on HN June 2025, 543 points) recommends starting with simple composable patterns, not complex orchestration frameworks. Single LLM calls with retrieval beat agent loops for most tasks. — [URL](https://news.ycombinator.com/item?id=44301809)
- **Real tool:** TheAgenticBrowser repo (Jan 2025) demonstrates a production three-agent pattern: Planner Agent breaks down requests, Action Agent executes, Validator Agent checks output — all coordinated via PydanticAI with browser MCP. — [URL](https://github.com/TheAgenticAI/TheAgenticBrowser)
- **Security data:** 43% of MCP servers have command injection vulnerabilities; 10 server plugins push exploit probability past 92% (security audit, Dec 2025). — [URL](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Local stack:** llama.cpp MCP support enables fully local tool-calling agents. Reddit r/LocalLLaMA threads show teams using Ollama + Playwright MCP for privacy-first browser automation. — [URL](https://www.stuffinsider.com/posts/llamacpp-adds-full-mcp-model-context-protocol-support-bb8716)

## Gotchas
- **Don't load all tools at init** — token cost and latency compound. Load tools on demand or group by task phase.
- **MCP server sprawl is real** — without a proxy or registry, teams end up with ungoverned servers, inconsistent auth, and duplicate tooling. Portkey.ai's enterprise post (2025) flagged this as the hidden adoption challenge.
- **Remote MCP servers add latency** — a server in another region can make tool calls slow enough to break agent loops that expect near-instant responses. Benchmark the roundtrip before assuming it's fine.
- **Security surface grows with every MCP server** — treat each server as a network-exposed service with its own attack surface. The command injection statistics are not edge cases.
- **Context window surprises** — agents silently misbehave when the context fills up, not by crashing loudly. Monitor token counts, not just tool call counts.
