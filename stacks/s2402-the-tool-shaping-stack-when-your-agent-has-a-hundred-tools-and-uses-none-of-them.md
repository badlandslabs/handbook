# S-2402 · The Tool Shaping Stack — When Your Agent Has a Hundred Tools and Uses None of Them Correctly

You wire up 47 MCP tools. The agent can in theory call a browser, run code, search the web, query your CRM, send emails, and trigger deployments. In practice it picks the wrong tool, hallucinates the wrong arguments, calls a deprecated endpoint, and silently makes a mess your observability stack never catches. The problem isn't the number of tools — it's that you gave the agent raw access to capability without shaping how it reasons about using them. Tool shaping is the discipline that closes that gap.

## Forces

- **Tool abundance induces decision paralysis, not power.** More tools in the prompt mean the model's tool-selection accuracy degrades — it wastes tokens evaluating options and picks suboptimally when the choice is genuinely ambiguous
- **Function calling is a contract, not a capability.** Declaring `tools: [browse, search, email]` in your schema doesn't tell the agent *when* to use each or *what the output contract means* — it only tells it the mechanical interface
- **Tool descriptions are prompts.** A poorly written tool description is a misaligned prompt that silently steers the agent toward incorrect tool usage in production edge cases you never tested
- **The Model Context Protocol (MCP) solved the wiring, not the reasoning.** MCP standardizes how agents discover and call tools across providers — but it is architecturally neutral on how many tools to expose and how to describe them

## The Move

Shape the tool interface before exposing it to the agent. Three concrete moves:

- **Tier tools by decision complexity.** Keep 3–7 high-level tools in the agent's active context that require genuine judgment. Push everything else behind a routing layer or a subordinate agent. Anthropic's research on multi-agent systems (2025) confirms this — the orchestrator holds the goal, workers handle domain-specific tool calls. The agent should not need to decide between `http_get`, `browser_navigate`, and `playwright_click` when `search_web` covers the decision at the right abstraction level.

- **Write tool descriptions as usage guidelines, not API docs.** Include: what the tool returns (and what it *doesn't* return), when to prefer it over alternatives, and common failure modes. Compare: `search(query: str) → list` vs. `search — use for factual lookups only, not opinions. Returns top 10 results with titles and snippets, not full pages. If you need page content, use browse next. Does not follow redirects.` The second version is a tool shaped for agent reasoning.

- **Use MCP servers as tool families, not individual tools.** Group related capabilities behind a single MCP server (e.g., `filesystem` rather than `read_file`, `write_file`, `list_directory`, `make_directory`). This reduces tool count at the interface level while preserving full capability. Dexto (Truffle AI / YC W25) demonstrates this: wrapping OpenCV functions into an MCP server and connecting it to a single tool entry, rather than exposing each OpenCV function individually. This is confirmed in their Show HN launch and MCP world documentation.

- **Add a tool-selection system message.** Explicitly rank tool preferences for the current task. "For this workflow prefer web search over browser navigation — speed matters more than rendered content." This is cheap, deterministic, and overrides model tendency to over-engineer tool chains. Treat it as a first-class configuration parameter, not a comment.

- **Instrument every tool call with structured logging.** Log: tool name, arguments (sanitized), response status, response length, and time. This is the data you need to identify which tools are being misused and which are dead weight. Without it, you are guessing.

## Evidence

- **Show HN / GitHub (Truffle AI, YC W25):** Dexto ships as an agent harness that treats MCP servers as the tool integration surface. The team explicitly identifies tool wiring as repetitive plumbing work — each small project ballooned into weeks of tool-orchestration labor. Dexto's solution: configuration-driven tool definitions that swap models and tools without code changes, and MCP as the standardized interface layer. — [Show HN: Dexto](https://news.ycombinator.com/item?id=45734696), [GitHub: truffle-ai/dexto](https://github.com/truffle-ai/dexto)

- **Engineering blog / ToolKiti (July 2026):** The complete production AI agent stack maps tool categories to specific providers: web search (Tavily, Exa, Brave), code execution (E2B, OpenAI Code Interpreter), browser automation (Browserbase, Playwright), data retrieval (Firecrawl). The post emphasizes that tool selection is a *layered decision* — short-term vs. long-term memory, inference provider vs. tool provider — not a flat list. — [ToolKiti: Building an AI Agent — The Complete API Stack](https://www.toolkiti.org/blog/ai-agent-tool-stack)

- **Multi-agent enterprise architecture (Innoflexion, 2026):** Multi-agent workflow deployments grew 300% year-over-year as of 2026. The architecture pattern that emerged: MCP for tool protocol + A2A (Agent-to-Agent) for coordination + three-layer agentic memory. Enterprises achieving sustained results (28%) are the ones that designed tool interfaces with governance in mind — not just capability. — [Innoflexion: Multi-Agent Orchestration Enterprise GenAI Architecture 2026](https://www.innoflexion.com/blog/multi-agent-orchestration-enterprise-genai-2026)

## Gotchas

- **MCP servers multiply silently.** A single MCP registry entry can surface 40+ tools to the agent. Check your actual tool count at runtime, not just at registration time — the gap between declared and active tools is where silent failures live.
- **Tool descriptions in system prompts drift out of sync with implementation.** A tool that once returned structured JSON now returns raw text. The agent keeps using the old assumption. Version your tool schemas and emit a tool schema hash in logs so you can correlate behavior to version.
- **Over-shaping kills useful tool chains.** If you restrict tools to 3–5, you may block legitimate multi-step workflows the agent was correctly reasoning through. The right count is task-dependent — use a routing agent to dynamically scope the toolset per workflow, not a fixed global limit.
