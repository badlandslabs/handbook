# S-1200 · The Agent Tool Stack — When You Give Your Agent Hands and It Runs Amok

You built a capable agent. Then you added tools. Now it fills out forms on the wrong website, deletes the wrong files, calls the wrong API, and runs code you never approved. Tool use is where agents stop being chatbots and start being actors with consequences — and the gap between "it worked in demo" and "it works in production" is entirely about how you scope, sandbox, and govern the tools you hand them.

## Forces

- **More tools mean more blast radius.** Every tool is an injection surface and a failure mode. An agent with 20 tools has 20 ways to do the wrong thing correctly.
- **Tool definitions are the API contract, and LLMs interpret contracts loosely.** The same tool spec can produce wildly different invocations depending on context, model, and temperature.
- **Browser access crosses into the adversarial web.** Any website can serve malicious content that manipulates the agent's DOM interpretation, as demonstrated by the AutoJack attack (Microsoft, June 2026) — a single webpage can hijack an agent's host for code execution.
- **Code execution is the highest-stakes tool.** Running untrusted LLM-generated code on your infrastructure without isolation is a credential-leak and lateral-movement risk, not just a "what if it crashes" concern.
- **The tool ecosystem is fragmented but consolidating.** MCP emerged in November 2024 and became the de-facto standard for tool definition, but the tooling, hosting, and governance layers around it are still wild west.

## The Move

Choose tools by the minimum surface area needed to solve the task, then isolate execution from credentials and environment.

**Browser tools — vision-first over HTML parsing.**
- Use browser-use (105K GitHub stars, browser-use.com) with Playwright under the hood. It sends screenshots + structured DOM to the LLM, not raw HTML — reducing token cost and eliminating parsing fragility.
- Default to headless Chrome via CDP (Chrome DevTools Protocol) for speed; enable visual mode only for debugging.
- Scope browser sessions to a single task with a fresh profile. Never reuse a browser session across tasks — cookies, localStorage, and auth state leak between tasks.

**Code execution — always sandboxed, never on the host.**
- OpenAI Agents SDK (April 2026) supports 8 sandbox providers: E2B, Modal, Docker, Vercel, Cloudflare Workers, Daytona, Runloop, Blaxel. Pick one based on your isolation requirement.
- The critical architectural pattern: **separate the control harness (where API keys live) from the compute layer (where model-generated code runs)**. This is the credential-isolation boundary.
- Python sandboxes use process-level isolation (e2b), container (Docker), or microVM (gVisor) depending on threat model. For production with sensitive credentials, microVM or hardware-backed sandbox is the floor.
- Set hard resource limits: max execution time, max memory, no network access, no filesystem write outside designated paths.

**Tool definitions — be surgical, not comprehensive.**
- Start with 3-5 tools maximum per agent role. Add tools only when you observe a recurring task the agent cannot complete without them.
- Each tool definition includes: name (snake_case, unambiguous), description (what it does in one sentence, what it does NOT do in another), input schema (Pydantic or JSON Schema, no optional fields you don't actually validate).
- Never expose tools that modify state outside the agent's own task scope. A tool that can "delete any file" is a tool that will delete the wrong file.
- Use MCP (Model Context Protocol) for tool definition standardization — one protocol, any LLM, any server. This eliminates the per-framework tool adapter problem. MCP servers expose three capability types: **tools** (executable functions), **resources** (read-only data), **prompts** (parameterized templates).

**MCP — use it as a thin, typed bridge, not a monolith.**
- MCP's architecture is Host → Client → Server. A single Host can run multiple Clients, each connecting to one Server. This means you compose tools by connecting servers, not by writing custom adapters.
- The tool library mcp-use (Show HN, ~155 points) provides a high-level async abstraction over the official MCP SDK, reducing boilerplate from ~200 lines to ~6 lines per server connection.
- MCP Cloud services (e.g., Manufact, YC S25) now host MCP servers as managed infrastructure — reducing the operational burden for teams that don't want to run their own.
- For browser automation specifically: run `browser-use` as an MCP server (`uvx browser-use --mcp`) and connect to it from Claude Code, Cursor, or any MCP-compatible host. This gives you browser control without a separate automation framework bolted on.

**Tool governance — registry before deployment.**
- Maintain a tool registry: name, owner, description, permission level, and blast radius rating (low/medium/high/critical). Every tool deployed must be registered before it can be called in production.
- Log every tool invocation: tool name, arguments (sanitized), result, duration, and whether the result was used. This is your audit trail and your failure recovery data.
- Implement tool-level rate limits and cost caps. A runaway loop calling a paid API tool can bankrupt you faster than a prompt injection.

## Evidence

- **GitHub repo (browser-use):** 105K stars, open-source Python framework. Agents use Chrome via CDP to navigate, click, type, and extract from websites. Architecture uses vision-first DOM understanding (screenshots + structured tree over raw HTML), Pydantic-based LLM output validation, and a dynamic action registry. Roadmap includes memory management, deterministic fallback scripts, and long-term planning improvements. — [https://github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **GitHub gist (architectural teardown):** Analysis of browser-use's design. Key insight: "Vision-first DOM understanding prioritizes screenshot + structured accessibility tree over raw HTML, reducing token cost and eliminating parsing brittleness." Also notes: dynamic action registry enables domain-specific tools without code changes. — [https://gist.github.com/echomoltinsson/7bdd7e0e43c45f5af89df430d0eb9276](https://gist.github.com/echomoltinsson/7bdd7e0e43c45f5af89df430d0eb9276)
- **Tech blog (byteiota):** OpenAI Agents SDK April 2026 release: production-ready sandboxed code execution with 8 providers (E2B, Modal, Docker, Vercel, Cloudflare, Daytona, Runloop, Blaxel). Architecture separates control harness from compute layer. Before this pattern, code execution in production was blocked by credential-leak risk. — [https://byteiota.com/openai-agents-sdk-sandbox-production-code-execution](https://byteiota.com/openai-agents-sdk-sandbox-production-code-execution)
- **Hacker News (Show HN, mcp-use):** 155 points, 74 comments. mcp-use reduces MCP integration from ~200 lines of boilerplate with double async loops to ~6 lines. Created because the official MCP SDK was "not suitable for building products" and tied to closed applications. — [https://news.ycombinator.com/item?id=44747229](https://news.ycombinator.com/item?id=44747229)
- **The Hacker News (AutoJack, June 2026):** Microsoft researchers demonstrated that a single malicious webpage can hijack an AI agent's host for arbitrary code execution. Agent-to-browser trust model is asymmetric — agents trust browser output they shouldn't. — [https://thehackernews.com/2026/06/autojack-attack-lets-one-web-page.html](https://thehackernews.com/2026/06/autojack-attack-lets-one-web-page-hijack-ai-agent-for-host-code-execution.html)
- **Blog (blaxel.ai):** MCP architecture overview. MCP breaks into three components: Host (orchestrator, never calls servers directly), Client (one per server, embedded in host), Server (lightweight, independently deployable). Five production use cases documented: secure code execution, cross-system automation, database query agents, API integration agents, and file system management. — [https://blaxel.ai/blog/mcp-use-cases](https://blaxel.ai/blog/mcp-use-cases)
- **GitHub (NirDiamant/agents-towards-production):** 20,962 stars. End-to-end tutorials for production-grade agents. Covers MCP, multi-agent systems, RAG, observability, and agent framework comparison (LangGraph, etc.). Created June 2025, 212 commits. — [https://github.com/NirDiamant/agents-towards-production](https://github.com/NirDiamant/agents-towards-production)

## Gotchas

- **Giving an agent browser access without session isolation is a data-leak waiting to happen.** Authenticate in a fresh profile per task; never carry cookies or tokens across agent tasks.
- **Vision-first sounds expensive — and it is.** Screenshot + VLM costs more per step than HTML parsing. On complex pages with 50+ elements, consider falling back to accessibility tree + selective screenshots.
- **MCP servers are unauthenticated by default in many examples.** Production MCP deployments need authentication (API keys, OAuth, mTLS) the same as any service endpoint.
- **Sandbox escape is not hypothetical.** Any code execution tool without hardware-level isolation can be exploited. Treat "sandbox" as "isolated but monitored," not "safe by design."
- **The more tools, the more the agent picks the wrong one for the right reasons.** Tool selection errors compound in multi-step tasks. Audit which tools are actually called vs. which exist but are never selected correctly.
