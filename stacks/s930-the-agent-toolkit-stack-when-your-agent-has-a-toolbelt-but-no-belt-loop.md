# S-930 · The Agent Toolkit Stack — When Your Agent Has a Toolbelt But No Belt Loop

You give your agent tools. It can read files, call APIs, browse the web, run code. Technically equipped. But it misuses them — calls a web search when it should use the DB, writes code it could have reasoned through, hands credentials to a compromised prompt. The tools are there. The discipline around them isn't.

Equipping an agent is not the same as enabling it. This stack covers what tools agents actually reach for, which ones work in production, and the patterns that separate a useful toolkit from a dangerous one.

## Forces

- **Browser automation is now the dominant agent tool category.** Playwright holds 45.1% QA framework adoption and 78,600+ GitHub stars (Zylos Research, 2026). AI-native browser agents — Claude Computer Use, OpenAI Operator, Project Mariner — shift from DOM scraping to vision-based reasoning. WebMCP (Chrome 146, Feb 2026) standardizes browser access. The browser has become the universal UI adapter for agents.
- **Code execution is the highest-risk, highest-reward tool.** Every major AI lab now ships a computer use API. Claude runs at $0.24–$0.36 per workflow (WowHow, April 2026). OpenAI's Bedrock AgentCore docs (2026) note: "AI agents have reached a critical inflection point where their ability to generate sophisticated code exceeds the capacity to execute it safely." The sandbox gap is the central problem.
- **MCP has won the protocol layer.** GitHub MCP Server has 15.2k stars. Google, Slack, Postgres, Notion, Sentry all ship official MCP servers. The ecosystem shift is from custom tool integrations to protocol-standardized ones. The parallel with LSP is explicit: "Before LSP every IDE had its own esoteric ways of providing language services. MCP is AI's pre-LSP moment." (saqadri, HN Show HN, Jan 2025).
- **Tool count has a ceiling.** Above ~40–128 tools, LLMs stop routing correctly. Cursor caps at 40 MCP tools, GitHub Copilot at 128 (S-915). But the mistake is not counting — it's giving agents tools without scopes, guardrails, and authentication. Enterprise deployments require OAuth, centralized access controls, and complete audit trails that local MCP servers don't provide (MintMCP, 2026).
- **5-tool categories cover 80% of production use.** Browser automation, code execution, database/RAG, filesystem, and vertical SaaS integrations (GitHub, Slack, Notion). Everything else is noise.

## The move

**Build a scoped, sandboxed, auth-gated tool stack around 5 categories.**

1. **Browser automation** — Use Playwright as the underlying driver (not Selenium — 235% YoY adoption growth, 13.5M weekly npm downloads as of mid-2026). Layer vision-based reasoning on top. For cooperative websites, prefer WebMCP (Chrome 146+). Isolate authenticated sessions carefully — the agent has the same permissions as the logged-in user. Log every action in real time so a human can audit or kill the session.

2. **Code execution** — Never run AI-generated code on the host. Use microVMs (Firecracker, libkrun via Era), gVisor for syscall interception, or hardened containers for trusted code only. The Era project (HN Show HN, 62 points) demonstrated that local parallel agents can "step on each other's toes," delete unintended files, and explore wrong filesystem areas. One agent per microVM is the isolation unit.

3. **Database / RAG** — MCP servers for Postgres, MySQL, and vector stores (Pinecone, ChromaDB) are the standard integration path. Query results should be validated and schema-constrained — don't let the agent receive raw DB dumps. For RAG pipelines: hybrid search + reranking + agentic retrieval (query decomposition, self-routing) covers 90% of knowledge work cases (Jahanzaib.ai, April 2026).

4. **Filesystem** — Give agents read access by default; write access scoped to working directories with explicit blocklists (no `/etc`, no `$HOME`, no `.ssh`). Log all filesystem operations. The agent should never explore the host OS — its workspace is a sandbox directory.

5. **Vertical integrations** — GitHub (15.2k stars MCP), Slack, Notion, Sentry, Jira. These cover the enterprise toolchain. Build custom MCP servers for proprietary internal tools. Each integration gets its own auth scope — a Slack agent shouldn't have write access to GitHub.

## Evidence

- **GitHub MCP Server** (15.2k stars) — Canonical example of standardized tool access. Agents get issues, PRs, discussions, backed by GitHub's identity and permissions model. — [github.com/github-mcp-server](https://github.com/github-mcp-server)
- **Browser Use** (21k+ stars, Jan 2025) — Open-source project showing AI agents autonomously navigating and extracting from websites using Playwright + LLM reasoning. 51 contributors, active production use. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use) / [azalio.io](https://www.azalio.io/browser-use-an-open-source-ai-agent-to-automate-web-based-tasks/)
- **Era microVM sandbox** (HN Show HN, 62 points) — Open-source local sandbox using libkrun microVMs. Demonstrates that parallel local agents need hardware-level isolation. — [github.com/BinSquare/ERA](https://github.com/BinSquare/ERA) / [news.ycombinator.com/item?id=46065997](https://news.ycombinator.com/item?id=46065997)
- **Cleanlab survey** (1,837 respondents, 2025) — Only 95 teams had agents live in production. 70% of regulated enterprises rebuild their AI agent stack every 3 months. < 1 in 3 teams satisfied with observability and guardrail solutions. Tool calling accuracy cited as a concern by only 5% — suggesting most teams haven't hit the problem yet. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Zylos Research browser automation landscape** (April 2026) — Playwright dominates QA (45.1% adoption), WebMCP emerges in Chrome 146, AI-native browser agents from Anthropic/OpenAI/Google now production-grade. — [zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape](https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape)

## Gotchas

- **Don't expose production credentials to the agent.** MCP's optional authentication is a security gap. Use OAuth, short-lived tokens, and per-tool scopes — not a shared API key with full access.
- **Browser sessions are a pivot point for prompt injection.** An agent authenticated to your SaaS and browsing untrusted sites is an exfiltration vector. Scope browser sessions, log actions, and prefer read-only tools where possible.
- **Tool descriptions are part of your agent's system prompt.** Ambiguous or overlapping descriptions cause misrouting. Write tool descriptions as action verbs: "Search the internal knowledge base" not "Knowledge search tool v2."
- **Sandboxing code exec is not optional.** "Standard containers aren't sufficient because they share the host kernel" (Northflank, Feb 2026). A compromised or confused agent with host access is a full system compromise.
