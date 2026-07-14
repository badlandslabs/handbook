# S-1091 · The Tool Surface Problem — When Your Agent Has Hands But No Arms

Your agent can reason across 200,000 tokens, follow a 47-step plan, and recover from its own mistakes. But it needs to check the weather for a customer in Lisbon, and there is no tool for that. The agent is stranded by a hole in its tool surface — a class of capability it needs but cannot reach.

This is the Tool Surface Problem: agents are only as capable as the boundary between "what the model knows" and "what the system does." The tool surface is that boundary, and most agents are under-equipped at it.

## Forces

- **MCP solved the protocol layer but not the coverage layer.** Anthropic shipped the Model Context Protocol in November 2024; by 2025 the community had built 383,000+ MCP servers and tools. But the long tail of useful tools — niche APIs, internal systems, proprietary data — still has no off-the-shelf MCP server.
- **Code execution changed the economics of tool calling.** Anthropic's engineering team showed that batching tool calls through code (writing Python that calls an API, then running it) uses far fewer context tokens than calling the same API directly as a tool on every invocation. But this requires the agent to write code, which is a higher-stakes capability.
- **Browser automation is the gap people notice first.** Web apps without public APIs — enterprise dashboards, legacy systems, authenticated portals — are the most common tool surface failures. A browser gives the agent universal access at the cost of speed and reliability.
- **The "few tool" trap.** Anthropic's enterprise deployments showed that teams starting with a small set of tools (web search, file read) hit the ceiling fast. But adding more tools creates a new problem: context bloat. Loading all tool definitions upfront means processing hundreds of thousands of tokens before the agent even starts reasoning.
- **Regulated industries face a tool surface gap.** Cleanlab's 2025 production survey found 70% of regulated enterprises rebuild their AI agent stack quarterly or faster. Tool surface churn — replacing integrations when internal systems change — is a primary driver.

## The move

Match the tool category to the access pattern. Each tool type has a sweet spot:

**Filesystem tools (Read / Write / Edit / Bash)** — sweet spot is local code and project context. Claude Agent SDK ships battle-tested versions handling binary files, large file streaming, precise text patching, and shell timeout limits. The 20% that breaks production (binary file garbling, incomplete writes, infinite shell loops) is pre-solved. Configure with `allowed_tools` allowlists rather than adding all tools by default.

**Web search** — sweet spot is real-time factual queries where context window freshness matters. OpenAI's Responses API exposes `web_search_preview` as a native tool. Anthropic's MCP servers include a web search server. Use when the task requires information from after the model's training cutoff.

**Code execution sandbox** — sweet spot is any tool call that happens more than a few times per session. Anthropic's engineering post recommends writing code that calls tools in a loop rather than calling tools individually — a single tool invocation vs. N tool invocations. OpenAI Agents SDK (April 2026) supports 8 sandbox providers natively: E2B, Modal, Docker, Vercel, Cloudflare, Daytona, Runloop, and Blaxel. Credentials are isolated from execution environments via session-scoped tokens.

**Browser automation** — sweet spot is web apps without APIs or where the UI is the API. The landscape in 2026: Steel (open-source headless browser, 6k+ stars), Browserbase (cloud-hosted with session management), Agent-Browser (Vercel's CLI, launches fresh Chromium per session), Playwriter (MCP-based, connects to existing Chrome via extension with vimium-style visual labels), and Claude in Chrome (MCP extension). Speed favors Agent-Browser; in-conversation UX favors Playwriter.

**MCP servers** — sweet spot is connecting to data sources, developer tools, and external APIs. The official reference servers include Google Drive, Slack, GitHub, PostgreSQL, and web search. The MCP Registry at registry.modelcontextprotocol.io lists community servers. When no off-the-shelf server exists, the HN pattern that got traction (July 2026) is reverse-engineering web apps into tools by running a browser agent inside an authenticated app, watching API calls, and converting them into MCP tools.

**REPL / code interpreter** — sweet spot is data transformation, analysis, and generation where the agent writes code once and runs it. E2B (400ms cold starts, prebuilt templates, filesystem persistence) is purpose-built for agents. Modal is better for GPU workloads. For general containers, Fly.io offers lowest cost at scale ($0.02/hr).

## Evidence

- **Anthropic Engineering Blog:** Code execution with MCP — documents the token consumption problem of loading all tool definitions upfront, recommends code-based tool batching as the scaling solution, confirms MCP launched November 2024 with thousands of community-built servers by late 2025. — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Cleanlab AI Agents in Production 2025:** Survey of 95 enterprise AI leaders with live agents in production. 70% of regulated enterprises rebuild their AI stack quarterly or faster. <1 in 3 teams satisfied with observability and guardrails. 63% prioritizing observability improvements. — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Show HN — Reverse-engineering web apps into agent tools (89 points, July 2025):** A browser-based agent runs inside an authenticated web app, watches how the app calls its own APIs, and auto-generates agent tools from the observed traffic — functioning as a self-updating MCP server. Addresses the "no API available" gap by making the browser itself the integration layer. — [https://news.ycombinator.com/item?id=48847834](https://news.ycombinator.com/item?id=48847834)
- **OpenAI Agents SDK documentation and April 2026 sandbox announcement:** SDK provides Agent, Runner, Handoff, Guardrail primitives. April 2026 release adds native sandbox execution across 8 providers (E2B, Modal, Docker, Vercel, Cloudflare, Daytona, Runloop, Blaxel) with credential isolation. — [https://openai.github.io/openai-agents-python](https://openai.github.io/openai-agents-python)
- **Glama MCP Registry:** 383,953 total tools/servers indexed as of July 2026. Official modelcontextprotocol/servers repository has 88,422 stars, 11,206 forks. — [https://glama.ai/mcp/tools](https://glama.ai/mcp/tools)

## Gotchas

- **Adding tools without discipline causes context bloat.** MCP's token consumption problem (Anthropic, 2025) kicks in fast — loading all available tool definitions upfront can consume more tokens than the actual task. Use `include_domains` / `exclude_domains` filtering or lazy-loading patterns for MCP servers with large tool counts.
- **Browser tools fail silently on CAPTCHAs, MFA, and dynamic JavaScript.** Cloud browser services (Anchor Browser, Browserbase) handle session management and MFA automatically. Self-hosted headless browsers (Steel, Agent-Browser) require you to handle these edge cases. Match the service level to the task.
- **Code execution sandboxes have blast radius.** If the agent has write access to the filesystem inside a sandbox, it can corrupt its own working state. E2B and Modal isolate credentials from execution environments — but the execution environment itself can still be compromised. Set working directory boundaries explicitly.
- **Tool permission models vary by SDK.** Claude Agent SDK uses `allowed_tools` allowlists (auto-approved tools) vs `permission_mode` for escalation. OpenAI Agents SDK uses Guardrails for input/output validation. These are not equivalent — understand the permission model before treating tools as auto-safe.
- **The "no API" gap has a workaround cost.** Reverse-engineering web apps into tools (REA, browser traffic inspection) works but requires ongoing maintenance as the target app changes. This is not free tooling — it's trading API maintenance for reverse-engineering maintenance.
