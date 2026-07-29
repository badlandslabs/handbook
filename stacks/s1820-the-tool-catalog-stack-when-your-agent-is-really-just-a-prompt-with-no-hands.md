# S-1820 · The Tool Catalog Stack — When Your Agent Is Really Just a Prompt with No Hands

You have a capable model, a good prompt, and a clear task. But the agent reads the web but can't book a flight. It writes code but can't run it. It sends emails but can't verify they arrived. The model is fluent; the agent is crippled. The gap is the tool catalog — what you give the agent to actually act on the world, how you wire it up, and how you prevent it from becoming an attack surface.

## Forces

- **Agents need hands, not just eyes.** A model that can only read produces reports nobody acts on. The moment you add "send email," "write file," or "make API call," the agent becomes an actor — and every actor is a risk.
- **MCP has become the de facto wiring standard but the security surface is underappreciated.** Anthropic released MCP in November 2024; within 18 months it had 9,652 registered servers, 97M+ monthly SDK downloads, and adoption from OpenAI, Google, and Microsoft. OWASP already has a documented "MCP Tool Poisoning" attack. The speed of adoption outran the security thinking.
- **Browser automation is the most powerful and most brittle tool category.** Agents that control real browsers can do anything a human can do on the web — but they fail in ways that are hard to detect, hard to sandbox, and easy to exploit via prompt injection in web content.
- **Tool count is a context-window problem.** A GitHub MCP server with 35 tools consumes ~26K tokens; Slack with 11 tools consumes ~21K. An agent with 58 tools from 6 servers can spend 30–50% of its context on tool definitions before doing any real work. Teams hit this wall fast and have to choose between capability and coherence.

## The Move

### 1. Start with the six-category tool model (Neo4j, 2026)

Most agent tool needs fall into six buckets. Map your use case to the minimal set:

| Category | What it does | Production risk |
|---|---|---|
| **Web search** | Live factual queries, documentation lookup | Low (read-only) |
| **Retrieval** | Vector search, knowledge graphs, internal DBs | Low–medium (read-only or constrained write) |
| **Computation** | Code interpreters, calculators, math | Medium (arbitrary code execution) |
| **Filesystem** | Read/write local or sandboxed files | Medium–high (data exfiltration path) |
| **Browser/UI** | DOM control, form fills, web scraping | High (prompt injection via web content) |
| **External APIs** | CRM, email, Slack, Jira, payment systems | High (destructive, irreversible) |

Start with web search + retrieval. Add computation for code-heavy tasks. Add filesystem via sandbox (never raw filesystem access in production). Add browser only when no API alternative exists. Treat external API tools as the last resort, not the first.

### 2. Use MCP as the wiring standard, but gate it

MCP has won the protocol layer. Rather than custom tool-integration code for every model-tool pair, connect via MCP servers. The practical stack: Anthropic's SDK (TypeScript or Python) + a registry of community servers for common integrations. Enterprise teams should run a private MCP server registry and pin versions — don't pull from the public registry at runtime in production.

**For sandboxed code execution:** AIO Sandbox (agent-infra/sandbox, Apache-2.0, 5.5K stars) packages browser + shell + file + MCP + VSCode into a single Docker container. Tilde.run (from the lakeFS co-creator) adds a transactional, versioned filesystem on lakeFS — agents can modify data directly, and every change is a committed version with a rollback path.

### 3. Define tools with enough specificity to constrain, not enough to limit

Anthropic's "Tool Use Examples" feature (Nov 2025) improved complex-parameter accuracy from 72% to 90% — meaning showing the model *how* to call a tool matters as much as the schema. Practical minimum: tool name (imperative verb, e.g., `fetch_customer_record`), a one-sentence description, typed parameters with defaults, and at least one usage example for non-trivial tools. The docstring is not documentation — it is the agent's operating manual.

### 4. Sandboxing is not optional for write tools

Raw filesystem access, direct API credentials, and browser control with full system permissions are all unacceptable in production agents. The correct pattern: agent runs in a sandboxed environment (container, VM, or purpose-built sandbox service), with the minimum set of capabilities scoped to the current task. Terminal Use (YC W26) positions itself as "Vercel for filesystem-based agents" — providing sandboxed execution + message streaming + state persistence without giving agents raw host access.

For code execution: run in V8 isolates (pablovarela's HN response) or Docker containers with no network access and ephemeral storage. The execution environment should be destroyable and recreateable without consequence.

### 5. Treat tool responses as untrusted input

This is the MCP Tool Poisoning attack (OWASP): a malicious MCP server returns data that looks normal but contains hidden instructions. The agent's LLM processes the full response as trusted context. Defenses: (a) MCP server allowlists — only connect to servers you control or have audited, (b) response validation — schema-check tool outputs before passing to the model, (c) capability scoping — even if poisoned, a tool that can only read a specific DB can't exfiltrate credentials or send emails.

### 6. Track tool usage at the execution layer

The agent's tool-calling decisions (which tool, which parameters, what result) are the most important signals for debugging and evaluation. Instrument every tool call: timestamp, tool name, parameters (without secrets), result status, and latency. This data feeds both failure recovery (S-1818) and evaluation (S-1817). Without it, you cannot distinguish "agent chose wrong tool" from "tool returned unexpected data."

## Evidence

- **Engineering Blog:** Anthropic's advanced tool use post (Nov 2025) describes how MCP tool definitions from 6 servers (58 tools) consume ~55K tokens — and their Tool Search Tool reduces this by 85% while preserving 95% of context. Also documents the Tool Use Examples feature's impact on parameter accuracy (72%→90%) — [https://www.anthropic.com/engineering/advanced-tool-use](https://www.anthropic.com/engineering/advanced-tool-use)

- **Industry Survey:** Digital Applied's MCP adoption analysis (May 2026, updated from verified sources) reports 9,652 MCP servers in the official registry, 15,926 GitHub repos with the `mcp-server` topic, and 97M+ monthly SDK downloads. Enterprise adoption: 41% of surveyed software organizations in limited or broad production (Stacklok, 2026) — the widely-cited "78%" claim was found to be unsourced and replaced. [https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)

- **Hacker News / Primary Source:** Tilde.run (HN "Show HN," 205 points, 133 comments) — an agent sandbox with transactional, versioned filesystem on lakeFS. The creator (ozkatz, lakeFS co-creator) emphasizes: "The filesystem is Fuse-mounted into the sandbox, not copied into it. Agents modify data directly by interacting with 'local' files" and "The repo acts as source of truth for agents — think memory, data lineage, reproducibility." — [https://news.ycombinator.com/item?id=48037724](https://news.ycombinator.com/item?id=48037724)

- **Community Discussion:** Ask HN on multi-agent orchestration (HN, 3 months ago) surfaced real production stacks: custom V8 isolates (pablovarela), LangGraph + Claude Code/Codex/Gemini CLI in git worktrees (Chepko932), AGNO framework (kathir05). One strong opinion: "There's absolute 0 framework out there that's good enough for serious work" — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **Security Reference:** OWASP MCP Tool Poisoning attack definition — root cause is the trust gap between MCP connect-time (tool descriptions reviewed once) and runtime (tool responses go directly into LLM context with no validation). Attacker runs a malicious MCP server, poisons tool responses with hidden instructions — [https://owasp.org/www-community/attacks/MCP_Tool_Poisoning](https://owasp.org/www-community/attacks/MCP_Tool_Poisoning)

## Gotchas

- **Adding a tool is not free.** Every new tool adds a routing decision the agent must make, a failure mode it must handle, and a security surface it can be exploited through. The best tool catalog is the smallest one that solves the problem.
- **Browser automation is the wrong default.** When a task can be done via API, use the API. Browser automation (Playwright, CDP, browser-use frameworks) is for tasks where no API exists and the cost of building one is unjustified. It is slow, brittle, and exposes the agent to every prompt injection payload on every page it visits.
- **MCP servers from the public registry are not audited.** Connecting to an unverified MCP server in production is equivalent to running untrusted code. Pin to audited servers, run your own registry for internal tools, and treat the MCP server implementation as a trust boundary.
- **Token cost of tool definitions is invisible until it isn't.** An agent that spends 40% of its context on tool schemas has 60% left for actual work. Profile this early. Anthropic's Tool Search Tool is one solution; a more pragmatic one is to load only the tools relevant to the current session, not all tools all the time.
