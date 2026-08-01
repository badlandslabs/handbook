# S-1959 · The Agent Tool Attribution Stack

When you have a long list of tools and the agent still can't figure out what to use, or when tool definition overhead is bloating your context and your token bill.

## Forces

- **Comprehensiveness vs. clarity** — the instinct to give agents every possible capability creates decision paralysis and token overhead that degrades reasoning quality
- **Token economics** — tool definitions consume context before any work starts; GitHub's MCP server alone is ~26K tokens, Jira ~17K, and 58 tools hits ~55K tokens of definition overhead (Anthropic, Nov 2025)
- **Tool reliability vs. model confidence** — a poorly defined or unreliable tool is worse than no tool; a model that trusts a bad tool will confidently produce wrong answers
- **MCP ecosystem explosion** — 13,230+ public MCP servers now exist (OpenClaw, 2026), making it trivial to wire up dozens of tools and making the selection problem worse

## The move

Curate tool sets aggressively. Fewer, well-defined, reliable tools beat a sprawling tool library.

- **Start with one tool** — identify the single tool that covers 80% of your use cases, ship with just that, add tools only when you hit a confirmed gap (Anthropic, "Building Effective AI Agents," Dec 2024)
- **Never preload all tools** — use on-demand tool discovery patterns (e.g., Anthropic's Tool Search Tool) to load only relevant tools per task, not all tools on startup
- **Scope tools narrowly** — one tool that does one thing well beats one tool that does many things poorly; a `search_crdb_invoices` tool beats a generic SQL tool that the model has to prompt-engineer correctly
- **Define tool purpose in plain English** — MCP tool descriptions are the model's only guidance; write them as a human would describe the task, not as a schema
- **Validate tool responses before returning to the model** — tool output can be malformed, partial, or wrong; pipe it through a validation layer that either fixes it or flags it before it hits the LLM (Harness Engineering, 2025)
- **Separate read tools from write tools** — read tools (queries, searches, retrievals) can be auto-executed; write tools (sends, deletes, updates) need explicit user confirmation or human-in-the-loop gates
- **Design for composition** — tools should be composable atoms, not monolithic services; a `get_record` + `update_field` + `send_notification` chain beats a `process_invoice` god tool
- **Budget for tool token overhead** — estimate definition cost before wiring a new MCP server; if a server adds 15K+ tokens of definitions for 3 tools, reconsider whether those tools belong in the same agent

## Evidence

- **Anthropic engineering blog ("Building Effective AI Agents"):** Found that "consistently, the most successful implementations use simple, composable patterns rather than complex frameworks" — teams that resist the impulse to over-tool their agents ship more reliable systems. HN discussion (543 points, June 2025) heavily validated this, with multiple practitioners reporting that removing LangChain/LangGraph simplified their tool orchestration and reduced errors. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Anthropic engineering blog ("Introducing Advanced Tool Use," Nov 2025):** Documented the token overhead problem with MCP at scale — GitHub server: ~26K tokens, Slack: ~21K, Jira: ~17K, Sentry: ~3K, Grafana: ~3K — and introduced Tool Search Tool (on-demand discovery) and Programmatic Tool Calling (code execution instead of LLM inference per call) as fixes. Real-world case: Claude for Excel uses Programmatic Tool Calling to handle spreadsheets with thousands of rows without context overload, cutting token usage by 98%. — [https://www.anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)
- **OpenClaw MCP ecosystem report (2026):** MCP grew from ~100K monthly SDK downloads to 97M+ in just over a year — the fastest-adopted protocol in the AI ecosystem. 13,230+ public MCP servers exist. Claude, ChatGPT, Cursor, Windsurf, Gemini, Microsoft Copilot, and VS Code all support MCP natively. This ubiquity makes the over-tooling problem worse: it's now trivially easy to wire 50+ tools, which is the exact failure mode Anthropic's data predicts. — [https://openclaw.direct/mcp-guide/model-context-protocol-examples](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **Cleanlab production survey (Aug 2025, n=95 engineering leaders with agents in production):** Only 5% of teams cited accurate tool calling as a top challenge — meaning the other 95% are dealing with something harder: reliability, observability, and stack churn. 70% of regulated enterprises rebuild their agent stack every 3 months or faster. This suggests that tool integration complexity — not tool capability — is the actual production problem. — [https://cleanlab.ai/ai-agents-in-production-2025/](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **Adding a tool "just in case"** — every new tool adds definition overhead and error surface; resist until you have a confirmed, repeated need
- **Loading all MCP tools at startup** — the MCP ecosystem makes this trivially easy and trivially expensive; use discovery or filtering to load only relevant tools per session
- **No validation on tool output** — malformed API responses, truncated data, wrong field names — these go directly back to the LLM and produce confidently wrong answers; validate before returning
- **Over-permissioned tools** — a tool with broad write access is a liability; scope to minimum necessary permissions and gate destructive actions
- **Tool descriptions as afterthoughts** — in MCP, the description is the model's entire context for when and how to use the tool; a one-line "calls the API" is not a description, it's a label
