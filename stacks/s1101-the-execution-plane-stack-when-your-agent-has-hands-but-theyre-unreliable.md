# S-1101 · The Execution Plane Stack — When Your Agent Has Hands But They're Unreliable

You've standardized your tool interface with MCP. You have a registry of 40 tools across 6 MCP servers. Your agent can list and describe every tool it has. But when it actually tries to use them — navigate a login-protected website, execute generated code in a sandbox, or read a file from a restricted path — it times out, hits permission errors, enters a loop, or silently produces wrong output that looks right. The execution plane is where agentic systems fail in production, and it's where most tooling documentation simply stops.

This is the stack for closing that gap: concrete execution implementations and the failure handling infrastructure that keeps agents from going off-rails mid-task.

## Forces

- **Browser automation has no selectors left.** The era of XPath and CSS selectors is over for AI agents. Modern browser automation tools accept natural language instructions and navigate websites by reasoning about DOM structure — but the shift creates new failure modes around CAPTCHAs, anti-bot detection, and session state that natural language can't easily express.
- **Sandbox isolation and startup latency are in tension.** WASM sandboxes start in milliseconds but require pre-baked tool sets. Container VMs provide full Linux compatibility but take 5+ seconds to cold-start. The choice fundamentally shapes what tasks an agent can realistically attempt.
- **Tool success is not task success.** A browser can navigate to a URL and extract text. That doesn't mean the agent found the right data, handled a paywall, or completed a multi-step form. Execution layer validation must go beyond "did the tool run" to "did the task succeed."
- **Failure modes differ from traditional software.** Rate limits, hallucinations that return HTTP 200, confident reasoning chains that produce wrong answers, and infinite loops don't map to try/catch. You need a failure taxonomy specific to agents.

## The Move

### 1. Browser automation: natural language + Playwright under the hood

Use a library that accepts natural language instructions and translates them to Playwright calls internally. browser-use (104K GitHub stars) is the canonical example — it provides a Python library where you describe the task in plain language and the agent navigates, clicks, fills forms, and extracts content through Playwright without you writing a single selector.

- **Tool set composition:** Combine BrowserToolSet with WebSearchToolSet and a FileReadTool to build a web research agent that searches, navigates, reads, and synthesizes in one pipeline. OpenHands uses this exact composition.
- **Model choice matters for browser tasks:** browser-use's own AGENTS.md recommends `ChatBrowserUse` as the default model for browser automation — higher accuracy, lower latency than general-purpose models. Don't assume your best general model is best for browser control.
- **AI-native browser agents are arriving:** Chrome 146 (Feb 2026) ships WebMCP, a W3C-standard protocol for cooperative websites that makes DOM scraping and screenshot-based inference obsolete for well-behaved sites. Anthropic, OpenAI, and Google all have browser agents shipping in 2026.

### 2. Sandboxed code execution: WASM over containers for latency-sensitive tasks

For agents that generate and execute code, choose your isolation level based on startup latency tolerance:

- **WASM sandbox (Amla Sandbox):** ~11MB binary, starts in milliseconds, provides bash-like shell with configurable tool constraints. Memory-isolated by design (linear memory with bounds checking). Perfect for short-lived code execution tasks where you need <500ms response time. Trade-off: pre-baked tool set, no dynamic pip install at runtime.
- **Container/VM sandbox (Docker, agentvm):** Full Linux emulation. Cold starts in 1-5 seconds depending on image caching. Allows dynamic tool installation. Better for complex, stateful code tasks. Trade-off: startup latency, larger attack surface, more resource overhead.
- **Build tools at build time, not runtime:** HN discussion on Amla Sandbox surfaced the common mistake of pip-installing dependencies at runtime. Pre-bake a container image with all required tools — the agent's job is to write code, not to set up its own environment.
- **Bake tools into the sandbox, not the agent:** The security model works best when the sandbox exposes only the tools the host explicitly provides, not whatever the agent might request. An agent inside Amla can only call tools configured by the host.

### 3. MCP code execution efficiency: write code to call tools

Anthropic's Nov 2025 engineering post identifies the core efficiency problem with MCP tool execution: loading all tool definitions upfront creates token bloat that degrades performance and increases cost as tool count grows. Their solution: **write code that calls tools, instead of calling tools directly.**

Instead of the agent receiving tool results interleaved with reasoning, the agent writes a Python script that internally calls the necessary MCP tools in sequence, then executes the script in a code interpreter. This collapses N tool definitions + N reasoning steps into 1 tool definition + 1 execution pass. The token savings are significant when you have dozens of MCP servers with hundreds of tools.

### 4. Layered failure handling with a specific taxonomy

Don't treat all failures the same. The agentic failure taxonomy has 6 categories that require different responses:

| Failure type | Example | Response |
|---|---|---|
| Rate limit (429) | Too many API requests | Retry with exponential backoff + jitter |
| Server error (500/503) | Provider outage | Fallback to another model or MCP server |
| Timeout | Reasoning takes too long | Increase timeout or simplify task decomposition |
| Invalid output | Agent returns malformed JSON | Retry with stricter output schema prompt |
| Hallucination | Agent calls a tool that doesn't exist | Validate tool existence before execution |
| Infinite loop | Agent enters a tool-call cycle | Step count guard with hard abort |

### 5. Validation beyond tool success

Tool execution returning successfully doesn't mean the task succeeded. Implement a validation layer that:

- Checks whether the extracted data matches the expected schema or range before returning it to the agent
- Compares tool output against a checkpoint of what was expected at this step
- Flags semantic failures (right tool, wrong result) for separate handling from technical failures (wrong tool, right result)

## Evidence

- **GitHub README:** browser-use has 104,498 stars and 11,521 forks, ships with a cloud offering featuring stealth browsers and proxy rotation, and integrates with OpenHands as BrowserToolSet. The README explicitly recommends `ChatBrowserUse` model for production browser tasks. — [https://github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Engineering blog:** Anthropic's Nov 2025 post documents the token consumption problem of loading all MCP tool definitions upfront and presents code-execution-as-tool-call as the solution. Published with full code examples and benchmarks showing reduced context usage for multi-tool tasks. — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Show HN (146 points, 73 comments):** Amla Sandbox (WASM bash shell) demonstrates that WASM-based sandboxing achieves sub-second startup with full syscall isolation, vs. the 5+ second cold-start of container VMs. HN commenters validated the approach but flagged that dynamic pip install at runtime is a common anti-pattern to avoid. — [https://news.ycombinator.com/item?id=46824877](https://news.ycombinator.com/item?id=46824877)
- **Research report:** Zylos Research (Apr 2026) documents that Playwright has overtaken Selenium with 78,600 stars and 45.1% QA adoption, and that WebMCP in Chrome 146 (Feb 2026) is the emerging standard for cooperative website automation. CDP remains the richer protocol for Chrome-specific agent infrastructure despite BiDi migration. — [https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape](https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape)
- **Engineering guide:** Google's production-ready AI agents guide (Feb 2026) catalogs the gap between prototype and production for agents: single failure tolerance becomes multi-step reliability, and manual testing becomes automated evaluation pipelines. — [https://cloud.google.com/blog/products/ai-machine-learning/a-devs-guide-to-production-ready-ai-agents/](https://cloud.google.com/blog/products/ai-machine-learning/a-devs-guide-to-production-ready-ai-agents/)

## Gotchas

- **Anti-bot detection breaks browser agents silently.** browser-use and Playwright-based agents are detected by most enterprise sites. Stealth browser proxies help but aren't foolproof. Budget time for this — it's the most common reason browser agents work in demos and fail in production.
- **WASM sandbox startup is fast but tool-limited.** You can't pip install inside Amla at runtime. If your agent needs a tool you didn't bake in, the whole execution fails. Audit your tool set before deployment, not after.
- **Container cold-starts are a user experience killer.** If your agentic workflow requires a Docker container per task and users are waiting synchronously, 5-second cold starts will get you support tickets. Pre-warm pools or switch to WASM for latency-sensitive paths.
- **Step count guards are not optional.** Without a hard abort on step count (e.g., 100 tool calls max), a confused agent will loop indefinitely and rack up significant API costs. Set this before you ship, not after you get the first bill.
- **Output validation catches semantic failures that tool success doesn't.** A file read that returns empty is a tool success. A file read that returns stale data is a semantic failure. Both look like success at the execution layer — you need validation that checks whether the content makes sense in context.
