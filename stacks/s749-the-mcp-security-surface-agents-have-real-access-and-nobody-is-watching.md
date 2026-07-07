# S-749 · The MCP Security Surface — Agents Have Real Access and Nobody Is Watching

The Model Context Protocol makes it trivially easy to connect an AI agent to production databases, internal APIs, and sensitive systems. That ease is the threat. By mid-2025, practitioners across multiple independent threads had identified the same gap: agents granted MCP access were operating with real permissions, but the security review that normally gates those permissions — the change control, the least-privilege audit, the blast-radius assessment — was entirely absent.

## Forces

- **MCP reduces friction for developers AND for attackers.** Connecting Claude or Cursor to an internal API via MCP takes minutes. That same speed means security review is often skipped entirely, and exposed credentials or overbroad tool permissions sit undiscovered.
- **The OpenClaw incident proved the gap isn't theoretical.** A 1.5M API key leak in the MCP ecosystem showed exactly what happens when the tooling moves faster than governance. Teams connected agents to systems without understanding the data those systems contained.
- **NSA guidance on MCP landed in May 2026 — late.** Organizations were already in production before authoritative security guidance existed. The community had to bootstrap its own practices.
- **Agents amplify existing permission gaps.** An API with sloppy scoping is a risk. The same API accessed by an autonomous agent that can loop, retry, and chain operations is a compounding risk.

## The Move

Treat MCP configuration as infrastructure access control, not developer convenience.

- **Add an MCP audit pass to your agent deployment checklist.** Tools like APIsec MCP Audit scan MCP configs for exposed credentials, overbroad tool permissions, and cross-tenant data exposure risks. Run this before any agent touches a non-public system.
- **Scope MCP tools to read-only by default.** Restrict write and modify operations explicitly. The Nucleus MCP approach enforces this by requiring explicit write permissions and monitoring network activity at the tool level.
- **Build a trust boundary between agent reasoning and MCP tool execution.** Not every LLM-recommended action should execute against a live system. A human-in-the-loop gate or an audit-before-commit MCP server (e.g., Sentinel) catches high-confidence decisions backed by stale or incomplete evidence.
- **Monitor MCP server network activity in staging.** Use mitmproxy or equivalent to observe exactly what data the MCP server sends and receives during a conversation. This surfaces information leakage that static config review misses.
- **Apply the same change control to MCP configs as to infrastructure-as-code.** MCP server additions and permission changes should require review, not just a config file edit.

## Evidence

- **NSA Security Design Considerations for AI-Driven Automation (May 2026):** First authoritative guidance specifically addressing MCP threat models, published after organizations were already in production. — [nsa.gov](https://www.nsa.gov/Press-Room/Press-Releases)
- **APIsec MCP Audit (GitHub, 2025):** Open source tool that scans MCP configs for exposed credentials and cross-tenant access risks — flags the gap between how developers treat MCP (config) vs how security teams treat infrastructure access. — [github.com/apisec-inc/mcp-audit](https://github.com/apisec-inc/mcp-audit)
- **HN Thread on MCP Agent Security (2025):** Multiple practitioners confirming that MCP connections were deployed without security review — "connecting Claude, Cursor, and other assistants to APIs, databases, and internal systems via MCP. These configs grant agents real permissions, often without security oversight." — [news.ycombinator.com/item?id=46966203](https://news.ycombinator.com/item?id=46966203)
- **Nucleus MCP — Secure Local-First Memory for AI Agents:** Open source MCP server explicitly designed to address the credential-exposure problem surfaced by OpenClaw, enforcing explicit read/write scoping and local-first data handling. — [github.com/eidetic-works/nucleus-mcp](https://github.com/eidetic-works/nucleus-mcp)

## Gotchas

- **Scanning MCP configs once is not enough.** Agents can request tools dynamically; static scan misses runtime permission escalation.
- **Local MCP servers on developer machines are a production risk.** Credentials and permissions from a developer's personal MCP config can end up in shared agent deployments if not explicitly managed.
- **MCP's security model assumes the host is trusted.** If the MCP server itself is compromised or malicious, the agent has no defense. Vet MCP servers with the same rigor as browser extensions.
- **The blast radius of an MCP misconfiguration compounds with agent autonomy.** A single errant tool call in a looping agent can do more damage than the same call from a single-invocation assistant.
