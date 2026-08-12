# S-2549 · The Tool-Access Stack

*When your agent can only talk to you — but you need it to act in the world.*

## Forces

- **The M×N integration problem** — wiring each agent to each tool individually creates O(M×N) bespoke integrations; every new tool or agent is new plumbing.
- **Token gravity** — tool definitions compete for context budget; loading 50 tool schemas can consume 10K+ tokens per call, breaking latency and cost targets.
- **Security vs. capability tension** — the tools powerful enough to be useful (filesystem, browser, code exec) are powerful enough to be dangerous; sandboxes trade safety for overhead.
- **The abstraction gap** — developers think in "give the agent access to GitHub" but the LLM sees 12 API endpoint definitions; matching human intent to tool invocation is non-trivial.

## The move

Build tool access around the **Model Context Protocol (MCP)** as the universal interface layer, then tier your tool portfolio by risk:

### The MCP foundation layer
- Use MCP as the **"USB-C for AI tools"** — one implementation per tool unlocks the entire MCP server ecosystem (10,000+ servers as of 2026).
- Adopt MCP's three primitives: **tools** (actions the agent calls), **resources** (data the agent reads), **prompts** (reusable prompt templates). This gives you a typed, discoverable interface rather than raw function calls.
- Prioritize the official servers for commodity needs: filesystem, GitHub, Slack, PostgreSQL, Redis — don't reinvent these integrations.

### The tool portfolio tiers

| Tier | Tools | Isolation | Use case |
|------|-------|-----------|----------|
| **T1 — Read-only / low-risk** | Web search, file read, vector DB queries | No sandbox needed | Information retrieval |
| **T2 — Stateful write** | Database writes, API calls, Git operations | MCP with permission scoping | Operational tasks |
| **T3 — Code execution** | Python/JS eval, shell commands | Isolated sandbox (container/VM) | Computation, data analysis |
| **T4 — Browser automation** | Web navigation, form filling, scraping | Playwright + browser-use + sandboxed CDP | Multi-step web workflows |

### Manage token budget at the tool level
- Don't pass all tool schemas upfront. Use MCP's **dynamic tool discovery** to load only relevant tools per task phase.
- For agents with hundreds of tools, Anthropic's code-execution-with-MCP pattern (Nov 2025) shows agents writing code that calls tools rather than receiving every tool as a direct function call — this shifts token cost from schema definitions to results.

### Sandbox code execution by risk level
- **Trusted code** (your own agent's generated scripts, internal use): Docker container isolation with resource limits (CPU, memory, network).
- **Untrusted code** (third-party agents, user-submitted scripts): VM-level isolation (Kata Containers, gVisor) or purpose-built services (E2B, Modal).
- The isolation spectrum has five levels from `exec()` (no isolation) through container to micro-VM — match level to actual risk, not to a maximum-safety ceiling.

## Evidence

- **Anthropic Engineering (Nov 2025):** Documented how MCP solves the M×N integration problem and introduced the code-execution-via-MCP pattern where agents write code to call tools, reducing per-call token overhead. Thousands of MCP servers in production, SDKs for all major languages. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **arXiv (cs.CR, April 2025):** First academic survey of the MCP landscape. Confirmed rapid adoption: thousands of community MCP servers for GitHub, Slack, Postgres, filesystem, Blender. Identified the M×N integration problem as the core driver. — [arxiv.org/html/2503.23278v2](https://arxiv.org/html/2503.23278v2)

- **Ecosystem scale (cross-referenced):** MCP reached 97 million monthly SDK downloads by late 2025/early 2026, with 10,000–12,000 public servers. Anthropic donated the protocol to the Linux Foundation's Agentic AI Foundation in December 2025. Fortune 500 companies including Block, Bloomberg, Amazon, and Pinterest have live MCP integrations. — [baeseokjae.github.io](https://baeseokjae.github.io/posts/mcp-ecosystem-2026), [ooty.io](https://ooty.io/blog/state-of-mcp-ecosystem-2026), [neonstack.dev](https://neonstack.dev/blog/mcp-97-million-downloads-ecosystem-2026)

- **Browser automation (Zylos Research, April 2026):** Playwright leads browser automation with 78.6K GitHub stars and 45.1% QA adoption (+235% YoY). browser-use is the dominant AI-native framework at 91K+ stars with 89.1% success on WebVoyager benchmark. Google Project Mariner achieves 83.5% on WebVoyager using Gemini 2.0. — [zylos.ai](https://zylos.ai/en/research/2026-04-05-browser-automation-ai-agents-2026-landscape)

- **Code sandboxing (Tian Pan, March 2026):** Sandboxing exists on a five-level spectrum from `exec()` to micro-VM. Most incidents stem from mismatched isolation level, not from having no sandbox. Container isolation (Docker) is appropriate for trusted code in single-tenant environments; VM-level isolation (Kata, gVisor) for untrusted workloads. — [tianpan.co](https://tianpan.co/blog/2026-03-09-agent-sandboxing-secure-code-execution)

- **Production repo (NirDiamant/agents-towards-production, 21K stars):** Curated tutorials on secure tool calling, external API integration, and observability for agent tool use in production. Maps the full production-grade agent tool stack. — [github.com/NirDiamant/agents-towards-production](https://github.com/NirDiamant/agents-towards-production)

## Gotchas

- **Don't load all tools at once.** Token budget collapses with 50+ tool schemas in context. Load tools dynamically per phase, or use the code-execution pattern to batch tool calls.
- **Container isolation ≠ VM isolation.** Docker shares the host kernel — a kernel CVE breaks all containers. If running untrusted agent-generated code, use micro-VM isolation.
- **MCP server quality is uneven.** The 10,000+ server count includes many unmaintained community servers. Stick to official servers (`modelcontextprotocol/servers`) for production, audit community servers before deploying.
- **Browser agents are stateful and lossy.** Screenshots consume massive tokens and lose DOM structure. WebMCP (shipped Chrome 146, March 2026) reduces token cost 89% vs screenshots — prefer structured DOM access over pixel screenshots.
- **Tool permissions cascade.** A single MCP server with broad filesystem access defeats the purpose of MCP's scoped permission model. Define tool access with least-privilege per-agent, not per-deployment.
