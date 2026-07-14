# S-1120 · The Tool Wiring Stack — Connecting Agents to the World with MCP

When your agent can only reason in a vacuum — no files, no browsers, no APIs — it generates text forever and changes nothing. Tool wiring is what gives an agent hands. The dominant pattern for doing this in 2025-2026 is Anthropic's Model Context Protocol (MCP).

## Forces

- **Every agent framework had its own tool abstraction.** LangChain tools, OpenAI function calling, custom tool schemas — none of them were portable. A tool written for one agent didn't work in another. Teams rewrote the same integrations over and over.
- **Tool sprawl makes agents brittle.** The more tools an agent has access to, the more likely it calls the wrong one, calls it in the wrong order, or fails silently when a tool is unavailable. Tool discovery and scoping matter as much as the tools themselves.
- **Browser automation is the hardest tool problem.** Agents race against dynamic, async web pages — modals appear after screenshots, dropdowns cover elements, downloads trigger silently. Traditional Playwright-based approaches require the agent to reason about stale state.

## The Move

MCP (Model Context Protocol) by Anthropic has become the de facto tool-wiring standard for AI agents. The core insight: instead of hardcoding tool integrations per-framework, expose every tool as an MCP server with a consistent interface. Agents discover and call tools through a protocol, not custom code.

**Key architectural components:**

- **MCP clients** sit inside agents (Claude Code, Cursor, custom agents) and negotiate available tools at runtime via the protocol handshake.
- **MCP servers** wrap external capabilities — filesystems, browsers, databases, APIs — and expose them as typed tools with schemas.
- **Tool discovery is dynamic.** The agent queries what tools exist rather than having them baked in at prompt-time. This makes the same agent work against different tool sets without code changes.
- **The agent loop is surprisingly thin.** Julien Chaumond (HuggingFace co-founder) demonstrated this with "Tiny Agents" — a fully functional MCP-powered agent in ~50 lines of JavaScript. The loop: connect MCP client → while response has tool calls → execute → append result → repeat.
- **Browser automation gets deterministic.** The Agent Browser Protocol (ABP) forks Chromium and injects MCP directly into the browser engine. Rather than racing against a live browser, the agent gets a "step machine" — each action waits for the engine to reach a defined "settled" boundary before the next step begins. This eliminates modal/race-condition failures that plague Playwright-based approaches.
- **Remote MCP servers are emerging.** AWS and Azure have launched MCP workflow services, enabling agents to connect to cloud-hosted tool servers rather than only local processes.

## Evidence

- **GitHub / Blog Post:** MCP SDKs hit 97M monthly downloads by end of 2025. The Python SDK has 9M+ downloads, TypeScript SDK has 6.7M weekly downloads. 1,100+ GitHub repos tagged `model-context-protocol`, 16k+ active MCP servers. — [xenoss.io](https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges)
- **GitHub / Blog Post:** "Once you have an MCP Client, an Agent is literally just a `while` loop on top of it." — Tiny Agents demo by Julien Chaumond, April 2025, with File System + Playwright MCP servers connected to Qwen2.5-72B — [huggingface.co/blog/tiny-agents](https://huggingface.co/blog/tiny-agents)
- **GitHub / HN:** Agent Browser Protocol (ABP) achieves 90.53% on Online Mind2Web benchmark — 2x faster, 2x lower token usage, 2x fewer tool calls vs. Playwright MCP. BSD-3 licensed. — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)
- **GitHub:** browser-use has 104k+ stars, 11k+ forks. Makes websites accessible to AI agents via Playwright with form-filling, data extraction, and QA automation examples. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **HN / Blog:** OpenClaw's agent architecture uses MCP servers as the primary integration point — RAG pipelines feed context, MCP servers provide tool execution. Infrastructure management commands (list instances, check health) account for the majority of MCP tool calls in production. — [creativeminds.dev](https://creativeminds.dev/blog/openclaw-architecture-mcp-rag/)
- **NSA:** MCP's rapid proliferation has outpaced security model development. The protocol's server-to-client action pattern creates new attack paths largely not well-traced. — [nsa.gov](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf)

## Gotchas

- **MCP security is underspecified.** The NSA published a concrete security analysis (2026) flagging that MCP allows servers to execute actions for clients — reversing the familiar request/response pattern. Public vulnerable MCP server implementations have been released demonstrating real exploit paths. Treat MCP servers as potentially adversarial; scope permissions narrowly.
- **Not all MCP servers are equal quality.** The 16k+ servers range from production-grade to proof-of-concept. Version skew between SDK versions causes tool schema mismatches. Pin server versions in production.
- **Browser automation still needs human oversight.** Even ABP at 90%+ accuracy on benchmarks fails on captchas, anti-bot protections, and novel UI patterns. Budget for a human fallback, not just an error message.
- **Token cost scales with tool schema.** Every MCP server advertises its full tool list on connection. Large tool sets inflate the system prompt on every call. Scope MCP server connections per-task, not globally.
