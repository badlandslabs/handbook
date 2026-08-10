# S-2440 · The MCP Context Tax — When Your Tool Schemas Consume 72% of Your Context Before the First Word of Work

You adopted MCP because it's the USB-C of AI agents: plug in any server, get any tool. Then you ran three MCP servers in production and watched your 200K-token context window evaporate — 143K tokens consumed by tool schemas and capability manifests before the agent processes a single user word. This is the **MCP context tax**: the protocol overhead that makes interoperability expensive in the dimension you can least afford to waste.

## Forces

- **MCP optimizes for discoverability, not density.** Every tool, resource, and prompt template an MCP server exposes gets injected into the context. A GitHub server with 94 tools, a filesystem server, and a data API — that's 150+ schema definitions competing with your user's actual request.
- **Context windows are finite and expensive.** Even 200K-token windows are not infinite, and the compute cost scales with every token in every call, not just the ones that matter.
- **Interop and efficiency are in direct tension.** MCP's design philosophy — expose everything, let the agent decide — trades per-call bandwidth for cross-ecosystem portability. At scale, this tradeoff breaks.
- **Schema verbosity compounds.** Each tool's JSON schema, description, and parameter documentation adds up. The agent's system prompt, tool definitions, prior conversation history, and tool response payloads all compete for the same window.
- **Tool-overhead happens before the first word of work.** Unlike compute that scales with actual output, schema overhead is paid on every single turn — including the first one.

## The move

The pattern is **selective tool exposure and on-demand schema loading** — replace the "expose everything" philosophy with tight, context-aware tool selection:

- **Server-side filtering at capability manifests.** Don't expose all 94 GitHub tools — expose the top 5 the agent has demonstrated a need for, and expand on demand. Perplexity's own MCP server dropped from 94 tools to a focused set.
- **Semantic tool discovery instead of bulk injection.** Instead of injecting all schemas upfront, maintain a tool index and retrieve only relevant tools based on the current task context — essentially RAG for your tool definitions.
- **Compaction for long sessions.** Claude Code, Codex CLI, and MCP Tasks have converged on file-system memory + periodic context compaction as the primary mechanism for surviving 8-hour sessions. The goal is not to fit everything — it's to compress what matters.
- **Protocol-layer optimization.** Split MCP server responses into capability summaries (lightweight) and full schemas (on demand), reducing per-turn token cost while preserving the ability to expand when needed.
- **Per-turn budget allocation.** Reserve a fixed token budget for tool schemas (e.g., 20% of context), and enforce that budget with truncation or summarization at the gateway level. Let the agent work with what fits, not everything available.
- **Tool grouping and hierarchy.** Instead of flat tool lists, group tools into domains (code, data, search) and let the agent first select a domain, then receive domain-specific schemas — reducing the initial schema load from 150 tools to 15.

## Evidence

- **Engineering blog:** Perplexity CTO Denis Yarats announced at Ask 2026 (March 2026) that three MCP servers consumed 143,000 of 200,000 available tokens — a 72% context tax — before any user message was processed. Perplexity abandoned MCP in favor of traditional APIs and CLI integrations. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/perplexity-mcp-exit-protocol-overhead-vs-interoperability)
- **GitHub MCP reference server:** The official GitHub MCP server alone exposes 94 tools, each with full JSON schema definitions. At 94 tools with verbose schemas, a single server can consume 40K+ tokens on every call. — [modelcontextprotocol.io](https://modelcontextprotocol.io/examples)
- **Three-pillar architecture for long sessions:** Claude Code, Codex CLI, and MCP Tasks have converged independently on file-system memory, periodic compaction, and tool-call provenance tracking as the mechanism to survive 8-hour sessions — replacing the assumption that a large context window is sufficient. — [AgentMarketCap](https://agentmarketcap.ai/blog/tags/context-window)

## Gotchas

- **"MCP is still worth it" for low-volume agents.** If your agent makes 10–20 tool calls per session and uses 3–5 servers, the context tax may be acceptable. The problem surfaces at scale or with verbose servers — don't generalize from a demo.
- **Perplexity's exit is not the final word.** Anthropic donated MCP to the Linux Foundation (December 2025) and major vendors (Google, OpenAI, Microsoft) have adopted it. The protocol is likely to evolve toward addressing overhead. Don't rip it out preemptively — implement selective exposure first.
- **Tool-on-demand adds latency.** Retrieving a tool schema only when needed introduces a round-trip. For latency-sensitive real-time workflows, this tradeoff may not be acceptable — profile before assuming the optimization is free.
- **Compaction can lose nuance.** Summarizing conversation history to save tokens risks losing specific details the agent will need later. Implement compaction with semantic保留了 rather than naive truncation.
