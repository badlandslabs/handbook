# S-1932 · The Tool Surface Stack — When Your Agent Has No Hands

You have a model that reasons. It cannot look up today's weather, write a file, send an email, or query your database. Without tools, it's a fluent writer with no hands — impressive prose, zero impact.

## Forces

- **Breadth vs. depth trade-off** — More tools mean more capabilities, but every tool is attack surface, token overhead, and failure point. The wrong tool set is worse than none.
- **Sandboxing vs. capability tension** — Giving agents real power (filesystem, network, code execution) means accepting that a misbehaving or prompt-injected agent can cause real damage. Isolated execution is safe but limited.
- **Tool definition overhead** — As agents scale to dozens or hundreds of tools, loading all definitions upfront creates massive token costs. Anthropic documented up to 98.7% token reduction possible by restructuring how tools are presented.
- **Brittleness vs. flexibility** — Rigid tool definitions break on layout changes; flexible (vision-based) tools are powerful but unreliable and expensive.
- **Agentic vs. deterministic mismatch** — Traditional software tools assume deterministic inputs and outputs. Agent tools must handle non-deterministic callers that may misunderstand, hallucinate usage, or pass wrong parameters.

## The Move

Give your agent exactly the tools it needs for its domain, scoped to the minimum privilege it requires, with self-contained error handling at every tool boundary.

**Tool selection — the six categories that cover most real-world agents:**

1. **Web search** — Lowest risk. Read-only access to current facts, documentation, pricing. Almost no failure surface beyond stale results.
2. **Retrieval** — Vector or keyword search over domain-specific knowledge. Low-medium risk; the main failure mode is returning irrelevant context.
3. **Computation / code execution** — The highest-leverage and highest-risk tool. A code interpreter lets the agent run calculations, transform data, and automate workflows. Sandbox it (WASM or Docker), never run untrusted LLM-generated code with host access.
4. **File operations** — Read/write files, logs, configs. Scope tightly — read-only for most agents, write-only directories for outputs.
5. **Browser / web automation** — Lets the agent navigate real sites, fill forms, scrape content. Built on Playwright or Puppeteer. The leading open-source implementation, Browser Use, reached 72k+ GitHub stars. Brittle (layout changes break selectors) — prefer API access over browser automation when available.
6. **Communication** — Email, Slack, webhooks. The only tool category that has irreversible external consequences. Require explicit confirmation before any send operation.

**Tool design — how Anthropic recommends you build them:**

- Design tools as contracts between deterministic systems and non-deterministic agents. Unlike `getWeather("NYC")` which behaves identically every time, agents may call tools, refuse to call them, hallucinate usage, or pass wrong parameters.
- **Build a prototype first.** Stand up quick tool implementations, then use the LLM itself to optimize the tool definitions and parameters. This is what Anthropic calls "writing effective tools for agents — with agents."
- **Self-correction loops.** Give tools structured error types (not just generic failures) so the agent can retry, try alternatives, or escalate. A `FileNotFoundError` tells the agent to create the file; a generic `Error` tells it nothing.
- **Tools as code APIs, not direct tool calls.** At scale (hundreds of tools), present MCP servers as code the agent writes to call them — rather than passing all tool definitions into context upfront. Anthropic showed this achieves 98.7% token reduction vs. naive upfront loading.
- **Tool descriptions must be LLM-friendly.** Use plain language descriptions, not implementation jargon. The agent reads these descriptions to decide when to call a tool.

**Sandboxing strategy:**

- Use WASM-based sandboxes (e.g., Amla Sandbox, 146 HN points) for code execution — no Docker overhead, capability-based syscall interface, memory bounds-checked by the runtime.
- Use MCP's permission model as your access control layer — don't add a second layer of permissions on top.
- Never give an agent tools that modify production systems without a human-in-the-loop confirmation gate.

## Evidence

- **Anthropic Engineering:** "Agents are only as effective as the tools we give them." Tools are a new kind of software contract — between deterministic systems and non-deterministic agents. The post covers self-correction loops, prototype-first tool building, and having the LLM optimize its own tool definitions. — [https://www.anthropic.com/engineering/writing-tools-for-agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Anthropic Engineering:** Presenting MCP servers as code APIs rather than direct tool calls reduces token consumption by up to 98.7%. Two problems addressed: tool definitions overload the context window, and intermediate results pass too much data through context. — [https://www.anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Browser Use (GitHub 72k+ stars):** Leading open-source browser agent framework. Built on Playwright, supports Claude/GPT-4o/Gemini. Production use cases: web scraping, form filling, RPA workflows, automated testing. Grew from 0 to 72k stars in under a year. — [https://github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Amla Sandbox (146 HN points):** WASM-based bash shell sandbox for AI agents. No Docker, no subprocess, no SaaS dependency. Every tool call passes through host-side capability enforcement. Design draws from seL4's capability-based security model. — [https://github.com/amlalabs/amla-sandbox](https://github.com/amlalabs/amla-sandbox)
- **Hannes Hapke (AI in Production 2025):** "Open source frameworks like LangChain and CrewAI are great for prototyping but bring too many dependencies for production." Recommends implementing your own core agent loop. Uses Go's reflection to dynamically generate JSON schemas from existing APIs — letting existing access controls handle security automatically. — [https://digits.com/blog/ai-in-production-2025-slides](https://digits.com/blog/ai-in-production-2025-slides)
- **Neo4j (May 2026):** Six tool categories with security risk ratings. Web search (low), retrieval (low-medium), computation (medium-high), file operations (medium-high), browser automation (medium-high), communication (highest — irreversible consequences). — [https://neo4j.com/blog/agentic-ai/agent-tools/](https://neo4j.com/blog/agentic-ai/agent-tools/)

## Gotchas

- **Don't give agents more tools than they need.** Every tool is attack surface and context overhead. Start with the minimum viable set; add tools only when the agent demonstrably needs them.
- **Browser automation breaks on layout changes.** Element selectors (CSS selectors, XPath) are brittle. Prefer API access when available; use Playwright MCP or Browser Use only when no API exists. Budget for maintenance.
- **Prompt injection via untrusted web content is real.** A browser tool that reads arbitrary web pages can be steered by malicious page content. BioShocking (June 2026, LayerX Security) demonstrated credential theft through indirect prompt injection against OpenAI, Anthropic, and Perplexity browsers. Sanitize or summarize web content before it reaches the agent.
- **Generic error messages are useless for agents.** A tool that returns `"Error"` tells the agent nothing. Return structured, typed errors (`FileNotFoundError`, `PermissionDenied`, `TimeoutError`) so the agent can recover intelligently.
- **Code execution without sandboxing is a security incident waiting to happen.** A prompt-injected agent with `subprocess.run` access can exfiltrate data, delete files, or mine cryptocurrency. Always sandbox — WASM, Docker, or seccomp profiles.
