# S-2006 · The Agent Toolset Stack — When Your Agent Has No Hands

An agent without tools is a very expensive autocomplete. The moment you give an agent a browser, a shell, and a file system, it stops being a chatbot and starts being a worker. But the toolset you choose — how you define, expose, discover, and constrain tools — determines whether your agent is a precision instrument or a chaos vector. Teams underestimate how much the quality of their tool definitions matters. A poorly described tool wastes more tokens than a missing tool.

## Forces

- **Tool bloat burns context.** MCP servers can consume 20–26K tokens before work begins. An agent with 30 tools defined is already starting the conversation exhausted.
- **Scope vs. reliability is a real trade-off.** Vision-based computer use (screenshots) works on any UI but is slow and brittle. DOM-based browser automation is fast and reliable but blind to rendering bugs.
- **Security and capability are in tension.** A sandboxed agent that can't write files or execute code can't get much done. An agent with unrestricted access to a browser session is an OWASP LLM08 Excessive Agency nightmare.
- **Tool quality beats tool quantity.** Anthropic's internal testing showed 72% → 90% accuracy improvement just by adding correct tool-use examples to definitions — no new tools, no model change.
- **The ecosystem is consolidating around MCP.** GitHub Copilot, Claude, LangChain, and Browser Use all support it. But the tool registry is still fragmented and versioning is unsolved.

## The move

**Define tools with rich schemas, not just descriptions.** Each tool needs: a precise name, a description that tells the agent *when* to use it (not just what it does), a parameter schema with types and constraints, and at least one usage example. A tool named `search` with no example is useless. A tool named `search` with `{"query": "site:github.com langchain", "limit": 5}` succeeds far more often.

**Scope tools to the minimum viable surface area.** A support triage agent needs retrieval, CRM writes, and ticket creation. It does not need code execution or browser access. The more precise the toolset, the more reliable the agent becomes. Tools that do too much are harder to describe accurately and harder to test in isolation.

**Use MCP for dynamic discovery, not static registration.** MCP's core value is runtime discovery — the agent queries the server to find what tools exist, rather than hard-coding every tool at startup. Pair this with Anthropic's Tool Search Tool (85% token reduction on large tool sets) for production systems where tool count grows.

**Separate browser automation into its own sub-agent.** TheAgenticBrowser (421 GitHub stars) uses a three-agent loop: a Planner breaks down the task, a Browser Agent executes via Playwright, and a Verifier checks the result. Don't let the main agent directly drive pixel-level clicks — sub-agents with narrow scope are easier to debug and recover.

**Prefer text/DOM-based browser control over vision-based for reliability.** Browser Use (107K GitHub stars) extracts interactive elements as structured data, presents them to the LLM as annotated options, and executes via Playwright. Claude Computer Use takes screenshots and reasons at the pixel level — broader scope, but 5–10x slower per action and fragile on dynamic UIs.

**Add a code execution tool for compute-bound tasks.** Claude Code uses containerized code execution with `container_upload` for data files — the agent gets a sandboxed environment that can process CSVs, run calculations, or generate files without touching the host. This is the highest-leverage single tool addition for research and data agents.

**Constrain write tools with guardrails, not trust.** Any tool that can send email, write files, or modify state needs an approval workflow or a dry-run mode. Browser Use implements `before_agent_action` hooks for this. Claude Managed Agents wraps stateful operations in a permissioning layer. Never give an agent write access without a rollback path.

**Use programmatic tool calling for bulk operations.** Anthropic's Programmatic Tool Calling feature lets an agent invoke tools from within a code execution environment — useful for iterating over a list of URLs or processing a data frame row by row without round-tripping through the LLM each time. Reduces token cost by ~37% on repetitive tool-call patterns.

## Evidence

- **GitHub repo (107K stars):** Browser Use connects AI agents to browsers via Playwright by extracting interactive elements as structured data, letting LLMs output actions like `input_text(id=3, "Hello")`. The founders (Gregor & Magnus, YC W25) explicitly note that avoiding screenshot-based control was a deliberate reliability choice — "Once you're taking screenshots, guessing what to click, moving the mouse, and repeating, it gets slow and brittle fast." — [browser-use/browser-use](https://github.com/browser-use/browser-use)

- **Engineering blog:** Anthropic's November 2025 advanced tool use post shows concrete token savings from better tool engineering: Tool Search Tool reduces MCP tool context by 85% while preserving ~95% of tool utility. Programmatic Tool Calling cuts token cost 37% by executing tool calls from code rather than inference round-trips. Tool Use Examples boosted correct usage from 72% to 90% accuracy in internal testing. — [Anthropic Engineering: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

- **HN discussion (96 points, 40 comments):** Frigade's "reverse-engineering web apps into agent tools" shows agents inside authenticated web apps watching API calls and auto-generating MCP tool definitions ("recipes") — endpoint, auth method, response schema, input schema, and human-readable description. Self-updates as the host app changes. Demonstrated on Jira, Spotify, and Hacker News. — [HN: Reverse-engineering web apps into agent tools](https://news.ycombinator.com/item?id=48847834)

## Gotchas

- **Adding tools without testing them in isolation causes cascading failures.** A tool that returns an unexpected schema silently breaks every downstream step. Test each tool definition with a fixed input and verify the output shape before the agent can call it.
- **Tool permission boundaries are often an afterthought.** An agent with browser access can read your email, access your banking session, and post to social media if cookies are persisted. Browser Use implements `before_agent_action` hooks specifically to gate dangerous actions — don't skip this.
- **MCP server versioning is a silent breaker.** When a SaaS updates their API, your MCP server definition may drift. Auto-generated tools (like Frigade's API reverse-engineering) handle this better than hand-written definitions. Schedule periodic re-verification of tool definitions against live API responses.
- **Token budget for tools competes with context for the task.** A 200K-token context window sounds large until you register 10 MCP servers. Use on-demand tool discovery (Anthropic's Tool Search Tool or MCP's runtime query) instead of registering everything at startup.
- **Vision-based computer use fails silently on complex UIs.** If a dropdown renders asynchronously, the screenshot may capture the wrong state. DOM-based tools see the actual rendered state at extraction time. For production reliability, prefer DOM/text-based tools and use vision only as a fallback for opaque UIs.
