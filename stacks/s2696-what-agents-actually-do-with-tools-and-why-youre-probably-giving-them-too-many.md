# S-2696 · What Agents Actually Do with Tools (and Why You're Probably Giving Them Too Many)

The moment you wire up your first agent and it opens a browser, reads files, and queries an API — you think: "I'll just give it access to everything." That's the mistake that kills agent reliability in production.

## Forces

- **Token gravity** — every tool definition and result lives in the context window. A 5-server setup with GitHub (35 tools, ~26K tokens), Slack (11 tools), and others can consume 50,000+ tokens before the agent even acts. Context window fills fast.
- **Accuracy vs. coverage trade-off** — agents pick wrong tools when the list is long. Anthropic measured accuracy dropping from 90% to 72% when tools lacked usage examples.
- **Static loading vs. dynamic discovery** — preloading all tools upfront is the default but it's the wrong default. Tools should be discovered on-demand.
- **Browser automation is uniquely valuable** — web interaction is the most cited real-world tool across HN launches, YC companies, and enterprise agents. It's also the hardest.

## The Move

The tool stack that actually ships in production follows a layered pattern: MCP as the protocol backbone, on-demand tool discovery, programmatic tool calling (not verbose natural-language calls), and browser automation as the primary interface for web interaction.

**1. Standardize on MCP as your tool protocol.**
MCP (Model Context Protocol, Anthropic, November 2024) gives you a universal interface layer between agents and external systems. Rather than hardcoding integrations for each tool, you implement MCP once and tap into an ecosystem. GitHub's MCP server went from launch to 7 million tool calls per week within months of its April 2025 open-source release. OpenAI, Google DeepMind, and Microsoft all adopted it.

**2. Load tools on-demand, not upfront.**
The default (load all tool definitions at session start) is the anti-pattern. Anthropic's Tool Search Tool discovers tools at request time, keeping the context clean. In production testing, this achieved 85% token reduction and preserved 95% of the context window. GitHub's MCP server validated this: after community contributions expanded to 100+ tools, agents became confused and context windows filled prematurely. Their fix was dynamic loading.

**3. Use programmatic tool calling (code-first) over natural-language tool calls.**
When an agent calls a tool by outputting `search(query="...")`, every invocation and result adds verbose entries to the context. A code-first approach lets the agent write code that calls tools internally — loops, conditionals, and batch operations happen in code, not in the LLM's output. Anthropic documented 37% token reduction and enabled parallel tool execution. A third-party GitHub MCP implementation using this pattern across 112 tools validated a claimed 98% token reduction against the traditional approach.

**4. Give agents browser control as the universal web interface.**
Browser automation is the most universally applicable tool. Browser Use (109K GitHub stars, YC W25 launch) connects any LLM agent to a real browser via Playwright, extracting interactive elements and executing actions. OpenAI's CUA (Computer Use Agent) model works the same way: agent receives screenshots, outputs actions (click, type, scroll). Anthropic's `computer-use-2025-11-24` beta exposes a sandboxed Docker environment with a virtual desktop where Claude controls Firefox or LibreOffice.

**5. Demonstrate correct tool usage with examples, not just schemas.**
Tool schemas describe what a tool does. Usage examples show how it's used correctly. Anthropic found that adding tool use examples improved agent accuracy from 72% to 90% — the single biggest improvement from any single change. Include failure cases too.

**6. Sandbox everything.**
Agents with tool access have broad permissions. NVIDIA documented real attacks leveraging watering-hole techniques to achieve RCE on developer machines via computer-use agents. Every tool execution path — code execution, shell commands, file writes, API calls — should run in a sandbox with minimal permissions. Anthropic's computer-use beta uses Docker + Xvfb for isolation.

## Evidence

- **GitHub MCP Server production metrics:** ~7 million tool calls per week, over 95% success rate, scaling from launch to 100+ tools and back down to optimized subsets based on context window impact. Open-source launch April 2025, most-starred repo during launch week. — [ZenML LLMOps Database / GitHub AI Engineer Europe Talk](https://www.zenml.io/llmops-database/building-and-scaling-a-production-mcp-server-for-developer-tooling)

- **Anthropic code-first MCP pattern:** Tool definitions and results can consume 50,000+ tokens in a 5-server setup. Code-first programmatic tool calling reduces token overhead by 37% and enables parallel execution. On-demand tool discovery reduces context consumption by 85%. Tool use examples improve accuracy from 72% to 90%. — [Anthropic Engineering Blog: Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use) and [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Browser Use production deployment (YC W25):** 109,306 GitHub stars, MIT license, connects any LLM agent to browsers via Playwright. Supported models include Gemini, Sonnet, Qwen, and Llama. Claims 3-4x speed improvement over OpenAI Operator with GPT-4o. — [GitHub: browser-use/browser-use](https://github.com/browser-use/browser-use) and [HN Launch Discussion](https://news.ycombinator.com/item?id=43173378)

- **Third-party MCP code-first implementation:** 112 GitHub tools, code-first pattern validated against Anthropic's 98% token reduction claim. Sandboxed Deno runtime for tool execution. — [GitHub Discussion: MCP Server for GitHub — Code-First Pattern Validation](https://github.com/orgs/modelcontextprotocol/discussions/629)

- **MCP adoption timeline:** Anthropic launched November 2024, donated to Linux Foundation's Agentic AI Foundation, adopted by OpenAI, Google DeepMind, and Microsoft within months. Thousands of MCP servers now exist. — [Blaxel.ai: MCP Use Cases](https://blaxel.ai/blog/mcp-use-cases)

## Gotchas

- **Don't load all tools upfront.** Users rarely customize tool sets, so the system defaults to everything, which bloats context. Set smart defaults and let the agent discover what it needs.
- **Tool schemas alone are insufficient.** Without usage examples, agents guess at correct invocation patterns and fail in non-obvious ways. Pair every tool schema with at least one positive and one negative example.
- **Browser automation requires element stability.** Websites change their DOM constantly. Production browser tools need retry logic and fallback strategies when element IDs shift.
- **Security surface expands with each tool.** Every tool is a potential attack vector. Computer-use agents running with user-level permissions are a documented RCE risk. Audit tool permissions, sandbox execution, and log all tool calls for compliance.
- **The "works in demo, breaks in production" gap.** MCP exists specifically because hardcoded integrations break when APIs change. Prefer protocol-based tool connections over bespoke integrations.
