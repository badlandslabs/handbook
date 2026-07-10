# S-915 · The Tool Surface Stack — When More Tools Make Your Agent Worse

You wire up 200 MCP tools, 15 API integrations, and a custom code execution environment. The agent can technically do anything. In practice, it calls the wrong tool, wastes tokens deciding between similar options, and ignores half your tools entirely. More surface area, less capability. The tool surface stack is the discipline of designing the right tool set — not the maximum one.

## Forces

- **Capability vs. confusion** — Every tool you expose to an agent is a decision it has to make. A 200-tool agent spends significant reasoning budget just choosing. The research is concrete: Cursor caps at 40 MCP tools, GitHub Copilot at 128. Above those thresholds, the LLM ignores or misroutes.
- **Context window as a shared budget** — Tool definitions are not free. Claude Sonnet-4's Playwright MCP server tools alone consume ~22.2% of its 200K-token context window before the agent has said a word. The more tools you expose, the less room remains for the actual task.
- **Richness vs. reliability** — Theoretically, exposing every capability is good. Practically, tools differ wildly in reliability, latency, and output quality. An agent that calls a slow or noisy tool performs worse than one that calls a fast, narrow one — even if the slow tool is more capable.
- **Static exposure vs. dynamic retrieval** — The default MCP pattern loads all tool definitions upfront. The 2025–2026 solution is on-demand tool retrieval: agents query for relevant tools only when needed, rather than carrying the full catalog in context.
- **Security surface grows with tool count** — Every tool is an execution path. The more tools, the larger the blast radius from a misbehaving or hallucinating agent. Least-privilege scoping and human-in-the-loop gates become non-negotiable at scale.

## The Move

Design the tool surface for the agent's decision task, not for the engineer's maximum flexibility.

- **Start with four tools** — pi.dev's minimal harness uses exactly four tools (read, write, edit, bash) and demonstrates that this is sufficient for most coding agent tasks. The tool loop, not the tool count, determines capability. More tools are an engineering convenience, not an agent capability multiplier.
- **Expose tools in context, not all at once** — The code-execution-with-MCP pattern Anthropic published November 2025 solves the token problem by having the agent write TypeScript that imports and calls tools locally, rather than passing all tool definitions through the LLM context on every turn. The model writes a short script, runs it, handles data locally, then calls the next tool.
- **Scope tools to least-privilege** — Each tool should expose only what the agent needs for that specific task. Read-only vs. write permissions, rate limits, and confirmation gates are not paranoia — they are the baseline for any tool an agent can call autonomously.
- **Use RAG-style retrieval for large tool sets** — When you genuinely need dozens or hundreds of tools, retrieve only the relevant subset per task. The MCP-Agent benchmark (2026) specifically targets this gap. Anthropic's own MCP SDK shows on-demand tool retrieval dramatically reducing token consumption.
- **Design tool descriptions for the model, not for humans** — A tool's natural-language description is how the model reasons about when to call it. Vague or generic descriptions cause mis-routing. Specific, action-oriented descriptions with concrete examples of inputs and outputs significantly improve selection accuracy.
- **Measure tool utilization, not tool count** — Track what percentage of your exposed tools are actually called. If 60% of your tools go unused in production, they are pure overhead. Prune them.

## Evidence

- **HN discussion:** Simonw on the Anthropic "Building Effective Agents" thread (June 2025, 543 points) endorsed starting with LLM APIs directly: "It's insane that people use whole frameworks to send what is essentially an array of strings to a web API." The top reply agreed — complexity in tooling does not translate to capability in agents.
  — https://news.ycombinator.com/item?id=44301809
- **Anthropic engineering:** "Code execution with MCP" (November 2025) describes the token consumption problem concretely — a Google Drive + Salesforce workflow that generates a large transcript in the traditional MCP pattern becomes a short local script when the agent writes code that calls those tools. The agent decides what to call, then writes code to call it efficiently, rather than passing all tool definitions through context on every turn.
  — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Cleanlab production survey (2025):** Of 1,837 engineering leaders, only 95 had agents live in production. Among those, top pain points were observability (63% plan to improve it), reliability, and evaluation — not tool count. The teams that succeeded in production had focused, constrained tool surfaces, not expansive ones.
  — https://cleanlab.ai/ai-agents-in-production-2025
- **BenchLM.ai agent benchmarks (July 2026):** 26 benchmarks tracked across terminal, browsing, tool-use, and computer-use. Agentic capability carries 22% weight in the overall model score — the single largest category. Terminal-Bench 2.0, BrowseComp, and OSWorld-Verified form the core weighted benchmarks. Tool selection quality directly determines benchmark performance.
  — https://benchlm.ai/llm-agent-benchmarks

## Gotchas

- **Adding tools feels like progress; it usually isn't** — More tools increase decision complexity for the agent, consume context budget, and introduce more failure modes. The instinct to expose everything is the wrong one.
- **Tool descriptions are often an afterthought** — The schema gets built for the developer; the natural-language description gets copy-pasted from the schema. This is backwards. The description is what the model uses to reason about tool selection.
- **Hard limits are real** — Cursor's 40-tool cap and Copilot's 128-tool cap exist because the LLM degrades above them. If you hit those limits, a proxy layer or on-demand retrieval is not a workaround — it is the correct architecture.
- **Not all tools are created equal in latency** — A tool that takes 5 seconds to respond will dominate your agent's latency budget regardless of how good the rest of your pipeline is. Measure per-tool latency in production, not just in development.
- **MCP tool proliferation creates a false sense of coverage** — 13,000+ public MCP servers exist, but the majority are unmaintained or poorly documented. Connecting to many MCP servers without evaluating their reliability, latency, and output consistency will degrade your agent's quality, not improve it.
