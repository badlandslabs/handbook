# S-1159 · The Model Context Protocol Stack — When Every Agent Needs to Talk to Every Tool

[Every team building agents hits the same wall: you have 4 tools, your colleague has 6 more, and nobody can share because everyone's tool interface is a bespoke prompt injection. MCP (Model Context Protocol) solves this by making tools a protocol problem, not a prompting problem. When your agent needs to discover, invoke, and trust external tools at runtime — that's when you reach for MCP.]

## Forces

- **Tool proliferation creates integration debt.** Every new tool requires a new adapter, a new prompt injection, and a new failure mode. Teams report spending more time wiring tools than using them.
- **Hardcoded tool lists break under distribution.** When tools live in prompts, they can't be discovered dynamically, versioned, or shared across agent frameworks.
- **LLMs can't reliably invoke tools from documentation alone.** Tool call accuracy drops significantly when the schema is embedded in context rather than delivered through a structured protocol with validation.
- **Standardization cuts both ways.** A universal protocol enables ecosystem effects but risks over-constrained tool schemas that can't represent domain-specific nuances.

## The move

**Treat your agent's tool interface as a network protocol, not a prompt engineering problem.**

- **Adopt MCP as your tool integration layer.** MCP defines a client-server model where the agent (MCP host) connects to tool providers (MCP servers) over stdio or HTTP. Tools are described by JSON schemas, not embedded instructions. The protocol handles discovery, invocation, and response — the LLM just calls functions.
- **Build MCP servers for your core capabilities.** Expose APIs, databases, internal services, and browser sessions as MCP servers. Each server registers its available tools with typed schemas. The agent queries available tools at runtime rather than receiving a fixed list at context load.
- **Use browser automation (CDP-based) as your universal interface tool.** Browser Use (104K+ GitHub stars) connects agents to any website via Chrome DevTools Protocol. The agent receives a serialized DOM, picks an action from a constrained set, and Browser Use executes it. This is the tool that works when no API exists.
- **Implement confidence gates on tool calls.** Browser Use runs screenshot-based visual verification after each action and reverts if the DOM state doesn't match expectations. Layer similar checkpoints on critical API calls.
- **Distinguish MCP fit from overkill.** MCP adds a client-server hop with JSON-RPC overhead. For tightly coupled, single-provider tool sets, direct function calls remain faster. Adopt MCP when tools span providers, need versioning, or must be shared across agents.

## Evidence

- **GitHub / Blog:** MCP server downloads grew from ~1M (February 2025) to ~8M (April 2025), per MCP community tracking. Anthropic introduced MCP in late 2024; Block, Chrome, and 100+ community-built servers followed within months. — [ArXiv 2601.11595 — Enhancing MCP with Context-Aware Server Collaboration](https://arxiv.org/html/2601.11595v1)
- **GitHub / Launch:** Browser Use (YC W25) achieves browser automation by extracting a structured DOM element list, passing it to an LLM with the task, and receiving typed actions (click, input_text, etc.) that map directly to CDP commands. The loop: extract elements → LLM decides → CDP executes → verify state → repeat. 104,733 stars. — [browser-use GitHub](https://github.com/browser-use/browser-use), [HN Launch Thread](https://news.ycombinator.com/item?id=43173378)
- **HN Discussion:** "LLMs weren't the bottleneck — it was the repetitive orchestration work: wiring LLMs to tools, managing context and persistence, adding memory and approval flows, tailoring behavior per client." Dexto (YC W25) built an open-source runtime to address this, treating tool orchestration as a first-class protocol problem. — [Show HN: Dexto](https://news.ycombinator.com/item?id=45734696)

## Gotchas

- **MCP servers are stateless by default.** Each tool invocation is isolated. Agents that need conversation context across tool calls must manage state externally — in-memory, in a database, or via a shared context store layer.
- **The LLM is still the orchestrator bottleneck.** MCP doesn't eliminate the reasoning loop; it just standardizes the transport. A tool-happy agent will still make excessive sequential calls.
- **Schema mismatch breaks runtime.** If a tool schema changes without versioning, the agent will invoke it with stale parameters. Lock schemas or implement schema compatibility checks.
- **Browser automation is fragile under UI churn.** Sites that change their DOM frequently cause Browser Use agents to fail silently or mis-identify interactive elements. Maintain a fallback to API calls where available.
