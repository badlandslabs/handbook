# S-1462 · The Tool-Tax Stack — When Your Agent Spends Half Its Context Reading Tool Definitions

You've built an agent with good tools. GitHub for code, Slack for notifications, Sentry for errors, Grafana for metrics. The agent works. Then you add five more tools and it starts missing instructions, calling the wrong tool, and running out of context window. The tools are fine. The problem is that every tool you give an agent costs context tokens before it reads a single user request — and that cost compounds faster than you think.

## Forces

- **Tool definitions are fixed overhead per call.** A single MCP tool definition with description, parameters, and schema consumes 500–2,000 tokens. A realistic enterprise agent with GitHub, Slack, Sentry, Grafana, Jira, and a database MCP server easily burns 53,000 tokens of context before the user's actual request is read. At $15/M tokens, that's $0.80 per conversation in tool tax alone.
- **Agents can't search what they can't see.** If you hide tools to save tokens, agents can't discover or call them. The classic tradeoff: load everything and bleed context, or load a subset and risk missing the right tool.
- **Tool schemas describe shape, not intent.** JSON schemas tell an agent what parameters exist and their types. They don't tell the agent *when* to call the tool, *what* to pass, or *how* to interpret the result. An agent reading `getDocument(id: string, format?: "json" | "markdown")` learns nothing about when to prefer markdown over JSON.
- **Code execution unlocks capability but creates credential isolation.** Giving agents the ability to run code is the unlock that separates "fancy chatbot" from "actual agent." But running agent-generated code on a host with credentials is the vector for API key theft, data exfiltration, and trusted-host exploits. The sandbox isn't optional — it's load-bearing.
- **Tool design for agents is different from API design for developers.** Developers read documentation. Agents need unambiguous descriptions, constrained parameter surfaces, and predictable failure modes. A tool that works fine for a developer using autocomplete can confuse an agent completely.

## The Move

The tool-tax problem isn't solved by giving the agent fewer tools. It's solved by four architectural moves working together:

- **Tool discovery at request time, not initialization.** Instead of loading all tool definitions upfront, agents discover relevant tools on demand. Anthropic's Tool Search Tool (Nov 2025 beta) indexes tool definitions and retrieves only the relevant subset per request, preserving 95% of context window for actual work. The agent asks "which tools do I need for this request?" rather than being shown everything.

- **Programmatic tool orchestration.** Instead of each tool call consuming a full LLM inference pass, agents write code that orchestrates multiple tool calls. Anthropic's Programmatic Tool Calling (Nov 2025 beta) reduces token consumption 37% by letting the agent output a script that calls tools directly, rather than feeding each result back through the model. The agent decides the tool sequence once, executes it programmatically.

- **Tool use examples over parameter schemas.** Anthropic found that adding example calls to tool definitions improved complex parameter handling accuracy from 72% to 90%. Examples teach agents *how* to use a tool, not just *what* parameters exist. Write tool definitions as you would write a worked example for a new hire, not a reference card for an expert.

- **Credential isolation for code execution.** OpenAI's Agents SDK (Apr 2026) separates the control harness — where API keys live — from the compute layer where model-generated code runs. This prevents injected malicious commands from accessing credentials. Use the same pattern: sandboxed execution environments (microVMs, gVisor, Docker) for any agent-generated code, with zero credential access from the sandbox.

- **Semantic tool naming over technical naming.** Name tools for the *goal* they achieve, not the API endpoint they call. `create_github_issue` is a developer name. `file_a_bug_report` is an agent name. Agents reason about goals, not endpoints.

## Evidence

- **Anthropic Engineering Blog:** Code execution with MCP — demonstrates programmatic tool calling pattern, token reduction metrics, and MCP as the universal protocol for connecting agents to external systems. Documents 53,000+ token tool definitions across GitHub (35 tools), Slack (11 tools), Sentry, and Grafana. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Anthropic Engineering Blog:** Advanced tool use — three beta features (Tool Search Tool, Programmatic Tool Calling, Tool Use Examples) that reduce context overhead and improve parameter accuracy from 72% to 90%. Quantifies the token cost of tool definitions per MCP server. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)
- **Anthropic Engineering Blog:** Writing effective tools for agents — tool design principles including semantic naming, example-based schemas, and the distinction between designing tools for agents vs. developers. — [URL](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Show HN / GitHub:** mcp-agent by lastmile-ai — implements Anthropic's "Building Effective Agents" patterns (Router, Orchestrator-Worker, Evaluator-Optimizer) as a higher-level interface on top of MCP. HN discussion highlights MCP as addressing AI development's "pre-LSP space" fragmentation. — [URL](https://news.ycombinator.com/item?id=42867050) | [URL](https://github.com/lastmile-ai/mcp-agent)
- **TechCrunch:** Browser Use raised $17M seed (YC W25) to convert web pages into "text-like" formats agents can process. Demonstrates the browser-as-tool pattern — agents need structured DOM representations, not raw HTML. — [URL](https://techcrunch.com/2025/03/23/browser-use-the-tool-making-it-easier-for-ai-agents-to-navigate-websites-raises-17m/)
- **ZenML LLMOps Database:** Anthropic Applied AI team lessons from Claude Code and enterprise deployments — tracks architectural evolution from single-turn prompts to multi-agent systems with tool orchestration, with production reliability data from finance, healthcare, legal, and tech sectors. — [URL](https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments)

## Gotchas

- **Adding tool definitions never feels consequential in prototyping — it always becomes a production problem.** A 10-tool agent with 500 tokens of definition overhead seems fine. At 50 tools and 53,000 tokens, you've already spent your 200K context budget before the user's request.
- **Code execution sandboxes fail silently in the common case.** If your sandbox has network access, the agent can still exfiltrate data via DNS rebinding or timing attacks. Check egress, not just ingress.
- **Tool descriptions are prompt-engineered, not just written.** A vague description (`getDocument: Retrieves a document`) makes the agent guess. A specific description with preconditions and postconditions (`getDocument: Fetches a document by ID. Returns markdown. Call this after the user mentions a specific file or doc, not for general knowledge. Returns 404 if the document doesn't exist in the workspace.`) teaches the agent when and how to use it.
- **Programmatic tool calling trades LLM inference cost for code complexity.** The agent outputs a script that calls tools directly — but that script now needs its own error handling, retry logic, and potentially its own sandbox. It's a different failure mode, not a simpler one.
