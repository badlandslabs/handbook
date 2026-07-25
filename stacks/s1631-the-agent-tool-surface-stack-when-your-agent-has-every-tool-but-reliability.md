# S-1631 · The Agent Tool Surface Stack — When Your Agent Has Every Tool but Reliability

When your agent can call 40 tools across 6 MCP servers but a 6.2% tool failure rate is silently breaking 1 in 16 production tasks, and you do not know which tools to trust, which to sandbox, or how wide to make the surface.

## Forces

- **Breadth vs. reliability** — every new tool is a new failure mode; agents with large tool surfaces fail more often but narrow surfaces miss necessary capabilities
- **Flexibility vs. security** — tools that can write files, run code, or call APIs are exactly what makes agents useful and exactly what makes them dangerous
- **Protocol proliferation** — MCP won as the standard (tens of thousands of servers, Anthropic + OpenAI + Google + Microsoft backing, donated to Linux Foundation December 2025), but the ecosystem is young and poorly audited
- **Validation gap** — model-generated tool calls arrive with free-form arguments that must be validated before execution, yet most teams skip this step in production
- **Tool description bloat** — passing all tool definitions through the context window scales poorly; a 50-tool MCP server definition can consume 30%+ of a context window (Anthropic, November 2025)

## The Move

Design a minimal, auditable, sandboxed tool surface. The move has five layers.

**Layer 1 — Shrink the surface before it grows.**
Expose 3–8 narrow, job-specific tools rather than a general-purpose API surface. Each tool does one thing with a tight schema. A tool named `search_web(query, max_results=5)` is better than a tool named `search(query_string, filters, sources, date_range, output_format)`. The goal is tools whose failure modes are predictable and whose outputs are structured.

**Layer 2 — Present MCP as a code API, not a tool list.**
Anthropic's November 2025 engineering post introduced the pattern: instead of loading all 40 tool definitions into context, agents write code that calls MCP servers on demand. The agent receives only the tools it needs for the current step. This reduced token consumption dramatically in their benchmarks. One production implementation reported 98% token reduction with 112 tools by loading selectively.

**Layer 3 — Sandboxing is non-negotiable for any tool that executes.**
Code execution (bash, Python, SQL), file writes, and API calls with credentials must run inside an isolated environment. The current production landscape: Firecracker microVMs (AWS, used by Claude Code) for the gold standard; Docker containers for medium isolation; ephemeral processes with no network for low-risk tasks. Credential separation — the control plane holds API keys, the execution environment does not — prevents injected malicious code from exfiltrating secrets. OpenAI's Agents SDK (2025) enforces this by design: API keys never reach the sandbox.

**Layer 4 — Validate every argument before execution.**
Tool call arguments are untrusted input. Treat them like user-submitted form data: validate type, range, format, and length. Reject rather than execute if schema constraints are violated. Add a human-in-the-loop confirmation step for any tool that writes, deletes, sends, or spends money — even if the agent "confirmed" internally.

**Layer 5 — Instrument and measure tool reliability.**
Track per-tool success/failure rates in production. Thread Transfer's 2025 production data found 6.2% average tool failure rate across agent deployments — most failures are silent (the agent retries internally and continues, masking the issue). Log every tool call: what was called, what arguments were provided, what came back, and how long it took.

## Evidence

- **Anthropic Engineering Blog:** MCP code execution pattern — agents write code to call MCP servers instead of receiving all tool definitions upfront, reducing context overhead and improving scalability. Published November 4, 2025. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **AgentLair Security Research:** MCP security landscape in 2026 — 40+ CVEs filed against MCP servers in the first half of 2026 alone, including CVE-2025-6514 (mcp-remote command injection, CVSS 9.6, 437,000+ downloads affected), CVE-2025-49596 (MCP Inspector RCE, CVSS 9.4), and filesystem MCP sandbox escape vulnerabilities. Anthropic's own mcp-server-git had three vulnerabilities disclosed January 20, 2026. — [URL](https://agentlair.dev/blog/mcp-security-vulnerabilities-2026/)

- **Zylos Research:** MCP ecosystem report — tens of thousands of community-built MCP servers as of 2026, TypeScript SDK at 11,255+ GitHub stars, remote MCP server growth ~4x since May 2025. Anthropic donated MCP to the Agentic AI Foundation under the Linux Foundation in December 2025. Gartner predicts 75% of API gateway vendors and 50% of iPaaS vendors will have MCP features by 2026. — [URL](https://zylos.ai/research/2026-01-10-mcp-servers-ecosystem/)

- **Thread Transfer Field Notes:** Production tool failure rates — 6.2% average tool failure rate across real-world agent deployments; narrow, schema-constrained tools consistently outperform broad surfaces in production reliability. — [URL](https://thread-transfer.com/blog/2025-07-08-tool-use-best-practices/)

- **GitHub Browser Use (YC W25):** Open-source browser automation library — agents extract interactive elements from pages, present them to the LLM as a structured list, then execute the LLM's chosen action. Supports any LLM (Gemini, Sonnet, Qwen, DeepSeek-R1). Launched February 2025, MIT licensed. — [URL](https://news.ycombinator.com/item?id=43173378)

## Gotchas

- **MCP is not inherently secure.** The protocol has no built-in authentication or input sanitization between servers. Every MCP server is an attack surface. Audit servers the same way you'd audit a third-party API: treat their outputs as untrusted input.
- **The "one more tool" trap.** Each new tool adds failure modes, context overhead, and attack surface. A tool that "might be useful" is not worth adding unless it maps to a concrete, measured need.
- **Tool descriptions in the prompt are instruction injection vectors.** An attacker who can influence a tool's description — through a GitHub issue, a Notion page, an email the agent processes — can inject instructions the agent executes. This is indirect prompt injection (OWASP #1 LLM vulnerability), not theoretical.
- **Silent failures are the default.** When a tool call fails, agents often retry or continue without surfacing the failure. You will not know about a 6% tool failure rate unless you log it explicitly. Build telemetry first, tools second.
