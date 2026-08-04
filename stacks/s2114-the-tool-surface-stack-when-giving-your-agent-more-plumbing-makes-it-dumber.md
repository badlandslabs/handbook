# S-2114 · The Tool Surface Stack

When you hand your agent a long list of tools and watch it ignore half of them, hallucinate parameter values, and crash on the one it actually needed — the problem isn't the agent. It's the surface area. Giving agents more tools doesn't reliably make them more capable; it makes them harder to prompt, harder to debug, and more expensive to run. The craft is in designing tool surfaces that agents can actually navigate.

## Forces

- **The context explosion tax**: Loading 50 tool definitions upfront can consume 30–50% of the context window before the agent does any useful work. Anthropic documented agents connecting to hundreds of tools across dozens of MCP servers, with all definitions passed upfront — a tax that compounds on every turn.
- **"Just expose your APIs" doesn't work for agents**: Datadog learned this the hard way. Their first MCP server was a thin API wrapper. Agents choked on raw log records, blew token budgets on oversized responses, and guessed at trends instead of computing them. The problem isn't access; it's ergonomics for a non-deterministic caller.
- **Schema mismatch between developers and agents**: Developers design tool schemas for other programs (typed inputs, error codes, nested objects). Agents need flat, unambiguous schemas with natural-language-friendly names and descriptions — a different design contract entirely.
- **Tool count grows faster than utility**: As teams add tools to solve problems, the agent spends increasing energy on tool selection versus task execution. The marginal tool almost always costs more than it delivers.

## The move

**Right-size the tool surface through three layers: tool design, tool selection, and tool execution — each with its own principle.**

### 1. Design tools for agents, not developers

Anthropic's tool-writing guidance (September 2025) is explicit: "Tools are a new kind of software reflecting a contract between deterministic systems and non-deterministic agents." The practical consequences:

- Use flat, descriptive names (`get_customer_by_email`) over nested namespaces (`gdrive.documents.retrieve`).
- Keep parameter schemas shallow (max 3–4 parameters visible without expansion).
- Return pre-aggregated summaries, not raw data. Datadog found that TSV/CSV formats use roughly half the tokens of equivalent JSON for tabular data — and pre-computing a `error_rate_over_time` summary beats returning raw log lines that the agent has to parse.
- Provide LLM-friendly documentation: Anthropic publishes `llms.txt` versions of their API docs specifically for this.

### 2. Batch tool selection, not tool listing

Don't load all tools into context. Anthropic's code-execution-with-MCP post (November 2025) shows the better pattern: **agents write code that calls tools**, rather than calling tools individually. The agent receives one high-level code-execution tool, and that tool internally calls whatever sub-tools it needs. Token cost per turn drops dramatically because the tool list shrinks to one.

OpenAI's Agents SDK and Computer Use API follow the same principle: instead of routing to individual tools, the agent operates through purpose-built primitives (web search, file search, computer use) that handle their own sub-tool complexity.

### 3. Constrain before expanding

Before adding a new tool, ask: can an existing tool handle this with a parameter change? Anthropic's guidance is blunt: "Start with the simplest solution possible. Only increase complexity when evidence shows complexity is needed." Teams that add tools speculatively end up with surface areas that are wide but shallow — many tools, all mediocre.

### 4. Sandboxing is non-negotiable for execution tools

Codex Agentic Patterns (derived from OpenAI Codex CLI's production Rust codebase) enforces sandbox boundaries for every tool execution: tools operate in restricted environments with explicit permission scopes. Datadog wraps every MCP tool call with authentication and scope checks. The principle: a tool that can read your filesystem or call your APIs needs the same security posture whether a human or an agent is calling it.

### 5. Handle tool failures gracefully at the execution layer

Anthropic's patterns guide (Chapter 4: Tool Use) specifies structured error responses that tell the agent *why* a tool failed and *what to try next* — not just an error code. The Codex codebase implements retry-with-backoff and graceful degradation at the tool execution layer, so the agent doesn't need to know about connection timeouts or rate limits.

## Evidence

- **Engineering blog:** Anthropic documented agents writing code to call tools via MCP rather than individual tool calls — reducing per-turn token cost while enabling access to the same tool ecosystem. Tool definitions are no longer loaded upfront; instead, a single code-execution tool dispatches to MCP servers on demand. — [Code execution with MCP (Anthropic, Nov 2025)](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **Engineering blog:** Datadog's MCP server rearchitecture moved from raw API exposure to pre-aggregated summaries, compressed tabular formats, and natural-language output descriptions. Agents went from drowning in log records to getting actionable summaries. "Just expose your APIs wasn't going to cut it." — [Designing MCP tools for agents (Datadog, March 2026)](https://www.datadoghq.com/blog/engineering/mcp-server-agent-tools)

- **Engineering blog:** Anthropic's foundational guidance distilled from dozens of production deployments: simple composable patterns outperform complex frameworks. Tool design should serve the agent's decision-making process, not mirror human API ergonomics. — [Building Effective AI Agents (Anthropic, December 2024)](https://www.anthropic.com/engineering/building-effective-agents)

- **Production codebase analysis:** Codex Agentic Patterns extracted from OpenAI Codex CLI's 100,000+ lines of production Rust code. Tool use is implemented through a registry with explicit sandboxing, permission scopes, and structured error responses — not raw function calls. — [Chapter 4: Tool Use (artvandelay/codex-agentic-patterns)](https://artvandelay.github.io/codex-agentic-patterns/learning-material/05-tool-use/)

- **Industry analysis:** MCP reached widespread adoption within its first year — Gartner estimated 75% of API gateway vendors would have MCP features by 2026. Smithery.ai's registry lists thousands of MCP servers. The standard solved the fragmentation problem but shifted complexity from per-tool integration to per-tool design quality. — [What is MCP? (Smithery Blog, 2025)](https://smithery.ai/blog/what-is-mcp)

## Gotchas

- **Adding a tool is easier than improving an existing one** — and teams default to easy. Audit your tool list before adding; prune tools that have been called fewer than 10 times in a month of production use.
- **Nested tool namespaces look clean but hurt agents** — `filesystem.read_file` is fine; `org.infra.storage.filesystem.documents.read` is a context-wasting hierarchy the agent doesn't navigate intentionally.
- **Tool descriptions are the most-read part of your schema** — Invest in them. A one-sentence description that says what the tool *accomplishes* (not just what it does) reduces hallucinated parameters more than any schema constraint.
- **The sandbox boundary is your attack surface** — CVE-2025-49596 (critical RCE in Anthropic's MCP Inspector, CVSS 9.4) demonstrated that MCP tool execution in browser contexts exposes new attack classes. Treat every tool as a potential privilege escalation vector.
