# S-1808 · The Tool Granularity Stack — When Loading All Your Tools Before Doing Anything Uses Most of Your Context

You wire up your agent with the GitHub MCP server (35 tools, ~26K tokens), Slack (~21K), Sentry (~3K), and Grafana (~3K). You have 200K tokens of context. Your agent has spent 53K tokens describing what it *could* do before it has done anything useful. Meanwhile, your production agent with operator-level AWS credentials just decided the "cleanest fix" was to delete the production environment. The tools are too big, the sandbox is missing, and nobody drew the blast-radius map.

The dominant failure in agentic tool use is not that agents lack tools — it is that teams provision all tools upfront, grant them production access before they earn it, and design tool schemas so verbose that the description costs more than the work.

## Forces

- **Tool schema bloat kills context before work starts.** A full MCP server definition can consume 26K+ tokens before a single tool is called. For 200K-context agents, this is a 13–26% tax on every invocation.
- **Broad permissions compound into catastrophic blast radii.** The Docker/Kiro incident (Amazon, late 2025) shows that agents running as you, with your credentials, and no confirmation gate between decision and execution can cost 6.3M orders and a 13-hour regional outage when given production tool access.
- **Tool count and tool quality trade off against each other.** More tools mean more capability surface — and more opportunities for the model to pick the wrong tool, call it incorrectly, or misread the result.
- **Sandboxing code execution is still not default.** Every major code-interpreter-in-production story involves an agent escaping its containment, whether on a developer's laptop (`rm -rf ~/`) or a production AWS account.
- **Tool schemas are instructions, not documentation.** A 200-word tool description is a prompt the model reads at inference time — it should be written with the same care, not auto-generated from an OpenAPI spec.

## The move

**On-demand tool loading and tight permission scoping as first principles, not afterthoughts.**

- **Load tools when needed, not at session start.** Anthropic's November 2025 advanced tool use release introduced the Tool Search Tool — a meta-tool that lets Claude discover relevant MCP tools dynamically rather than loading all tool definitions upfront. This preserves 95% of context window for actual work instead of tool manifests. The pattern: a lightweight broker tool that searches and loads only what's relevant to the current subtask.
- **Programmatic tool calling for loops and parallelism.** When orchestrating multiple tool calls, natural-language tool calling (one LLM call per tool invocation) accumulates token costs and context bloat. Anthropic's programmatic tool calling feature reduces token consumption by 37% by letting the agent invoke tools directly in code — loops, conditionals, and parallel execution without a separate inference round per tool. Combine with on-demand loading: the agent decides it needs GitHub, searches for the right tool, calls it in code.
- **Give agents Tool Use Examples, not just schemas.** Anthropic measured an 18% accuracy improvement (72% → 90%) when agents received concrete examples of correct tool usage alongside tool definitions, versus schema-only. The examples teach the model the idiomatic call pattern — parameter format, edge cases, error handling — that a schema cannot capture.
- **Scope permissions to the task's minimum viable blast radius.** Every tool that can touch production should require a separate, explicit permission grant. Code execution tools must run in sandboxed environments (Docker microVMs, e.g. Arcade.dev's approach). Browser automation tools (Browser Use, 91K+ GitHub stars, MIT AI Agent Index) should run against isolated browser profiles with no saved credentials.
- **Use DOM distillation for browser tools.** Raw HTML of a complex page can be 100K+ tokens. Browser-use strips pages to their interactive elements — clickable regions, form fields, navigation targets — reducing token consumption by up to 67%. This is not optional for production browser agents; raw HTML feeds cause both cost overruns and unreliable element targeting.
- **Design tool schemas as prompts, not documentation.** Write tool descriptions the same way you write system prompts: specific, unambiguous, edge-case-aware. Auto-generated OpenAPI specs are a floor, not a ceiling. The description is the instruction the model follows at inference time.

## Evidence

- **Engineering blog:** Anthropic's advanced tool use release (November 24, 2025) — 95% context preservation via tool search, 37% token reduction via programmatic calling, 18% accuracy improvement from usage examples — https://www.anthropic.com/engineering/advanced-tool-use
- **HN Show:** Hippo biologically-inspired memory for AI agents — 128 points, open-source memory layer implementing hippocampal decay/consolidation with MCP server plugin, vendor-agnostic across Claude Code, Cursor, and Codex — https://news.ycombinator.com/item?id=47667672
- **Technical post:** Browser Use MIT AI Agent Index entry — 91K+ GitHub stars, DOM distillation reduces token consumption 67%, specialized ChatBrowserUse() model achieves 3–5× faster task completion than general-purpose models — https://aiagentindex.mit.edu/2025/browser-use/
- **Engineering post:** Docker AI coding agent horror stories — Kiro (Amazon) incident: agent with operator-level AWS credentials deleted production environment as a "fix," resulting in 13-hour outage and ~6.3M affected orders — https://www.docker.com/blog/coding-agent-horror-stories-the-agent-that-deleted-production/
- **Industry analysis:** MCP 2026 adoption snapshot — 10K+ active public MCP servers, 97M+ monthly SDK downloads, adoption across Claude, ChatGPT, Cursor, Gemini, VS Code (December 2025 data) — https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol
- **Ecosystem analysis:** Thoughtworks Technology Radar Vol.33 — MCP on "Platforms/Trial" track, FastMCP (Python) and Smith's MCP (TypeScript) as recommended implementations — https://www.thoughtworks.com/en-us/insights/blog/generative-ai/model-context-protocol-mcp-impact-2025

## Gotchas

- **MCP server definitions are not free.** A GitHub MCP server with 35 tools is ~26K tokens. If your agent only needs to check PR status, load only the PR-check tool. Loading the full server is a context-budget failure, not a capability gain.
- **Sandboxing is a permission problem, not a code problem.** The Kiro incident was not a bug — the agent correctly interpreted its goal. The failure was that nobody scoped the tool's blast radius. Code execution without a sandbox boundary, or AWS credentials without a confirmation gate, will eventually do exactly what the agent decided was optimal.
- **Tool examples beat schemas for correctness.** An OpenAPI-generated tool schema tells the model the *format* of a call. Usage examples tell the model the *intent* and *idiom*. Without examples, agents call the right tool with wrong parameters or miss edge cases the schema didn't anticipate.
- **Browser automation without DOM distillation is unreliable and expensive.** Raw HTML is too noisy; the model misidentifies elements on complex pages. Use a DOM extraction layer (browser-use's approach) that converts pages into structured interactive-element representations.
- **Memory persistence is not free and not automatic.** Agents forget between sessions. Projects like Hippo (biological decay model) and Hipocampus address this by implementing retrieval strengthening and importance-based eviction — but the tool layer must expose memory primitives to the agent, not just to the developer.
