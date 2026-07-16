# S-1209 · The MCP Security Surface Stack — When Your Agent Becomes a Trusted Backend You Never Hardened

Model Context Protocol (MCP) turned AI agents into first-class API clients. You can now give a coding agent — Cursor, Claude Desktop, Windsurf — read/write access to Supabase, Neon, Sentry, GitHub, Hacker News, Slack, and dozens of other services through a single config change. What nobody warned you about: **MCP grants your agent trusted-backend status on systems that were never designed to receive trusted-backend calls from an LLM.** The Supabase MCP leaked entire SQL databases through prompt injection. The Cursor agent ran arbitrary code through a git hook. A browsing agent could be RCE'd by a single malicious web page. These aren't hypotheticals — they're 2025–2026 CVEs. MCP isn't the problem; it's the accelerant.

## Forces

- **MCP is opt-in security, not opt-out.** Supabase chose convenience over security by not enabling Row Level Security by default. Anthropic shipped MCP Desktop Extensions with one-click install and no security review gate. Developers connecting a Cursor agent to Supabase MCP get production database access in two config lines — and most don't realize what they've opened.
- **Agents trust their inputs in a way humans never would.** When a support ticket containing a prompt injection payload flows through an agent into a database query tool, the agent isn't "hacking" anything — it's doing exactly what it was asked. The attack surface is the gap between what the agent *was told to do* and what the attacker *coaxed it into doing*.
- **The protocol matured faster than its threat model.** MCP hit production with 17% of surveyed teams using it live (Zuplo, Nov 2025) while security tooling was still experimental. The Nov 2025 update added server discovery and async operations — good for scale, bad for attack surface visibility.
- **Tool breadth compounds blast radius.** A single agent with 5 MCP tools (database, file system, git, Slack, GitHub) is one prompt injection away from data exfiltration, code injection, and repo sabotage simultaneously. Traditional apps require separate vulnerabilities in each service.

## The Move

Design your MCP tool surface as if your agent is a zero-trust client on an untrusted network — because it is.

**Principle 1: Least-privilege tool scoping.** Never give an agent production database access. Use MCP against dev/staging clones with masked or synthetic data. The Supabase MCP can be leveraged for schema inspection, query previews, and migration planning — not live data. If production access is genuinely required, add a human approval step before the tool executes.

**Principle 2: Input sanitization at the tool boundary, not the prompt layer.** Don't try to "make the prompt injection-resistant." The agent's job is to follow instructions; it will follow malicious ones too. Instead, sanitize every user-controlled input that flows into MCP tool calls — especially strings that originate from documents, emails, tickets, or web content the agent has fetched. Treat MCP tool parameters as untrusted SQL parameters.

**Principle 3: Sandbox MCP servers to their blast radius.** Separate MCP servers by trust domain. A hacker-news MCP reading tool and a database MCP should not share a process or a credential. If the hacker-news MCP gets prompt-injected, it should not have access to your database credentials.

**Principle 4: Audit every MCP tool's access scope before shipping.** For each MCP server: What happens if the agent calls this tool with maximal arguments? What data can it read? What can it write? Can it spawn processes? Connect to the network? Exfiltrate credentials? Map this out before the agent reaches users.

**Principle 5: Monitor for the tell-tale signs.** An agent making unusual MCP calls is a signal — a coding agent suddenly calling a network tool 40 times, or a research agent reading tables it has no business accessing. Log MCP tool invocations with caller identity, tool name, arguments, and response size. Alert on anomalies, not just failures.

**Principle 6: Browser-based agents get an additional attack surface.** AutoJack (Microsoft Research, June 2026) showed that agents with web browsing capabilities can be redirected by malicious pages to call localhost services — turning the agent into a pivot point for host RCE. If your agent browses the web, restrict its ability to call local services, or run it in a sandboxed VM.

## Evidence

- **HN Thread + Security Analysis:** Supabase MCP could leak entire SQL databases through prompt injection in support tickets/documents — agents with the MCP connected would relay malicious instructions directly to the database tool. Community consensus: "You should not use MCP against your production database. MCP is useful during development/testing and it ends there." — @sriramsubram (Twitter/X), July 2025 — https://news.ycombinator.com/item?id=44502318
- **CVE-2026-26268 (NVD):** Cursor AI IDE allowed sandbox escape via git hooks written by a malicious or prompt-injected agent. Versions prior to 2.5 allowed agents to write to improperly protected `.git` settings — no user interaction required. Fixed February 2026. — https://nvd.nist.gov/vuln/detail/CVE-2026-26268
- **AutoJack RCE Chain (CybersecurityNews, June 2026):** Microsoft AutoGen Studio's MCP WebSocket surface contained three chained weaknesses (CWE-1385, CWE-306, CWE-78) enabling a single malicious web page to trigger arbitrary code execution on the host. Requires no user interaction beyond submitting a URL to the browsing agent. — https://cybersecuritynews.com/autojack/
- **Zuplo MCP Survey (Nov–Dec 2025):** 92 technical professionals surveyed. 65% experimenting/piloting MCP non-production, 17% in production, 15% evaluating. The protocol was in production with teams before security governance frameworks existed. — https://byteiota.com/mcp-protocol-november-25-update-production-ready-ai-agent-standard

## Gotchas

- **MCP server discovery is a trust problem.** The November 2025 MCP update added `.well-known` server discovery — meaning agents can now auto-discover and auto-connect to MCP servers. If an attacker can control or spoof a discovery endpoint, they can provision tools your agent has never seen. Verify discovery endpoints the same way you'd verify a TLS certificate.
- **"It's read-only" doesn't mean "it's safe."** A hacker-news MCP that reads HN is low-risk. But a read-only database MCP that returns full user tables to the agent feeds that data into the agent's context window — and from there, an agent can be coaxed to summarize, extract, or forward it. Read-only tools still create data-exfiltration surface.
- **The Cursor git hook CVE shows the temporal problem.** The agent wrote the malicious hook on Monday. The code executed on Tuesday when a human ran `git commit`. Security reviews that look at what the agent *did* miss what the agent *left behind*. Audit not just tool calls, but filesystem state after agent runs.
