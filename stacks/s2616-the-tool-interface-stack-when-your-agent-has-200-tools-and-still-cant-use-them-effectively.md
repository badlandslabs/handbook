# S-2616 · The Tool Interface Stack — When Your Agent Has 200 Tools and Still Can't Use Them Effectively

You give your agent a web browser, a code executor, a file system, Slack, GitHub, Jira, and 200 MCP servers. The agent starts hallucinating tool names, burning tokens on definitions, and calling the wrong API with the right intent. The problem isn't the number of tools. It's how the agent discovers, selects, and invokes them.

## Forces

- **The token explosion problem**: GitHub's MCP server alone is 35 tools consuming ~26K tokens. Slack adds ~21K more. A fully-loaded tool manifest can consume 30–50% of your context before the agent does any real work. (Anthropic, Nov 2025)
- **Tool selection accuracy degrades with scale**: Anthropic measured 72% tool-use accuracy with standard prompting — and 90% with tool use examples. The delta is enormous and directly affects production reliability. (Anthropic, Nov 2025)
- **The interface-substrate conflation**: Filesystems are natural LLM interfaces (LLMs already know how to use them) but break down as memory substrates under concurrent multi-agent load. Databases handle concurrency and auditability better, but require explicit schema design. Teams pick one and regret it. (Oracle Developers, 2025)
- **Agents write their own tools until they can't**: Superagent documented the shift from manually-built tools to dynamically-evolved ones — which works until the agent needs a tool domain it hasn't encountered before. Then work stops. (Superagent Blog, Jan 2025)
- **DeerFlow's insight**: A single monolithic agent with all tools is fragile. The right architecture is a **harness** that orchestrates specialized sub-agents, each scoped to a tool cluster, sharing memory and a sandbox layer. (ByteDance, DeerFlow README, Feb 2026)

## The Move

Design your tool interface as a **three-layer stack**: a discovery layer that keeps definitions out of context, a invocation layer that parallelizes execution, and a skill layer that bundles tool clusters into task-specific modules.

### 1. On-demand tool discovery (not upfront loading)
Load only the tool manifest — names, not definitions. Let the agent invoke a `search_tools(query)` or `ToolSearch` function to pull definitions when it needs them. Anthropic reports **85% token reduction** using this pattern. GitHub MCP goes from ~26K tokens to a few hundred.

### 2. Programmatic tool calling with parallelization
When the agent identifies needed tools, have it write code that calls them in parallel rather than one-at-a-time tool calls. Anthropic measured **37% token reduction** through programmatic invocation versus direct tool-call-per-action. Combine with sandboxed execution for code-writing agents.

### 3. Tool use examples as first-class prompts
Instead of generic tool descriptions, provide 2–3 concrete examples of the tool being called correctly in context. Anthropic's internal data: this moves accuracy from **72% → 90%**. Examples beat descriptions for complex or non-obvious APIs.

### 4. Skill bundles over flat tool lists
Group related tools into skills — a "browser skill" (navigate, click, extract, fill), a "code skill" (write, execute, test, review). DeerFlow's architecture models this explicitly: extensible skills per sub-agent. This lets the orchestrator route to the right skill bundle rather than the agent selecting from 200 flat options.

### 5. Sandbox isolation for dangerous tools
Code execution, browser automation, and file system access belong in sandboxed environments. DeerFlow uses explicit sandbox layers between sub-agents and host systems. The alternative — letting an agent write and execute code directly — is the fastest path to production incidents.

## Evidence

- **Anthropic Engineering (Nov 2025):** Code execution with MCP achieves **98.7% token reduction** compared to passing tool definitions directly in context. The pattern: agent writes code that calls MCP tools programmatically rather than relying on the model's direct tool-call mechanism. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Anthropic Engineering (Nov 2025):** Three advanced tool-use features (Tool Search Tool, Programmatic Tool Calling, Tool Use Examples) reduced token consumption 85% while improving tool-use accuracy from 72% to 90%. GitHub MCP: 35 tools, ~26K tokens; Slack MCP: 11 tools, ~21K tokens — resolved by on-demand discovery. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)
- **LangChain Case Studies (2024–2025):** AirTop built browser automation for AI agents using natural language APIs (Extract API for structured data from authenticated sites, Act API for UI interactions), replacing CSS selector hacks and Puppeteer scripts. Used in production by LangChain customers across e-commerce, social listening, and travel. — [URL](https://blog.langchain.dev/customers-airtop/)
- **DeerFlow (ByteDance, Feb 2026):** Open-source super-agent harness hitting #1 GitHub Trending. Architecture: orchestrator + sub-agents + skills + memory + sandbox layers. Skills are bundled tool clusters (e.g., research, coding, creation). Recommended for long-horizon tasks spanning minutes to hours. 79,973 GitHub stars. — [URL](https://github.com/bytedance/deer-flow)
- **incident.io production case study (2026):** Running 4–7 concurrent Claude Code agents with git worktree isolation. Custom `w` function creates an isolated worktree per agent, preventing concurrent file writes. Verification loops (build + test after each change) catch errors before the next agent cycle. — [URL](https://blog.starmorph.com/blog/claude-code-production-case-studies)

## Gotchas

- **Don't load all tool definitions at startup.** Even with 10 tools, you're burning context on definitions the agent won't need for this request. The upfront loading pattern was the default in early LangChain and similar frameworks; it's now considered an anti-pattern at scale.
- **Parallel tool calls need result aggregation.** When your agent fires 4 tools simultaneously, the responses return out-of-order and the agent must reconcile them. Without explicit result aggregation in your orchestration layer, the agent gets confused and re-queries tools it's already called.
- **Tool descriptions are not tool use examples.** "Searches the web" is a description. "When the user asks for current news, call search_tools(query='...')" is an example. The accuracy delta (72% → 90%) is entirely in the difference between these two.
- **Sandboxing is load-bearing, not optional.** DeerFlow, Claude Code production teams, and every serious browser automation setup isolate dangerous tool execution. Without a sandbox, a single misfired `rm -rf` or browser exploit is your production incident.
- **Skills bundles need versioning.** As your tools evolve, the skill bundle that was "working" silently breaks. DeerFlow's skill architecture supports versioning; most homegrown systems don't — leading to silent regressions where the agent calls the right tool with the wrong interface.
