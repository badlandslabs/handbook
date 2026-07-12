# S-874 · The MCP Config Drift Stack — When Your Agent Has a Secret Security Hole You Don't Know About

Your agent passed its security review three months ago. Nothing in the codebase changed. The agent still uses the same MCP tools, the same tool schemas, the same auth tokens. But last Tuesday, a configuration update to your internal MCP gateway relaxed a permission scope — a single boolean flipped from `true` to `false`. The agent now has access to read and write your customer database when it should only read. No code changed. No alert fired. This is MCP config drift: the silent, invisible accumulation of configuration changes that silently expand your agent's attack surface between review cycles.

## Situation

MCP config drift is different from code drift because MCP configurations govern **capabilities, not behavior**. When your `github` MCP server's config gains a `write` scope, the agent's threat model changes fundamentally — it can now modify repositories, not just read them. When your `database` MCP server's `max_rows_returned` setting is bumped from `100` to `10000`, the agent's blast radius on a data breach doubles. These changes don't appear in git diffs on your agent code. They live in configuration files, environment variables, IAM policies, and server-side permission matrices that your agent review never touched.

Real pattern from MintMCP's Jun 2026 analysis: organizations deploying agents across Claude, Cursor, ChatGPT, and Copilot each have separate MCP configuration stores. A security-relevant permission change in one store (say, relaxing the `web_search` server's allowed domains from `*.internal.corp` to `*`) silently propagates to all agents consuming that configuration — including the one handling your financial reporting workflow.

Another pattern: MCP servers can be updated independently of agent code. The server team ships a new version that adds optional fields to tool responses. The agent's output parser silently drops those fields. Six weeks later, a downstream system that depends on those fields starts returning partial data. No error, no alert — just quiet wrongness, introduced by a server version bump nobody told the agent team about.

## Forces

- **Configuration lives outside the code review boundary** — your agent's git repo doesn't track MCP server configs, OAuth scopes, or IAM policies, yet they define what the agent can actually do
- **Drift is invisible at runtime** — MCP servers return success on valid requests; they don't tell the agent "by the way, you now have admin write access to this resource"
- **Multi-client complexity** — MCP configs differ per client (Claude Desktop vs. API vs. third-party agents), so a scope change in one context may not propagate to others, creating inconsistent agent behavior across deployment surfaces
- **Review cycles don't sync with config changes** — security reviews happen quarterly on agent code; MCP server configs change weekly; the review boundary never captured config in the first place
- **Credential rotation is ad hoc** — MCP auth tokens expire and get replaced; the new tokens may have different permission scopes than the old ones; the agent team never re-validates after a rotation
- **Shadow MCP servers proliferate** — teams add MCP servers to agent configs to solve short-term problems (a developer adds a `read_customer_data` server "just for this one workflow"); it stays in config long after the workflow ends

## The move

Treat MCP configurations as first-class security artifacts — versioned, reviewed, and diffed alongside agent code.

**1. Configuration audit as a review gate.** Before any agent ships, extract the full effective permission surface from all MCP server configs: tool names, resource URIs, OAuth scopes, rate limits, and allowed operations per server. Store this as a signed snapshot in the agent's git repo under `agent-config/`. Every review compares against the last snapshot. Any delta gets explicit sign-off from a security owner.

```bash
# Extract effective MCP config surface
# Requires MCP client with config inspection (Claude Code, cursor, custom SDK)
mcp config inspect --all-servers \
  --format json \
  --include-scopes \
  --include-resources \
  > agent-config/mcp-permissions-$(date +%Y%m%d).json

# Generate a diff against last approved snapshot
mcp-config-diff \
  agent-config/mcp-permissions-20260601.json \
  agent-config/mcp-permissions-$(date +%Y%m%d).json \
  --format markdown \
  --security-gate
```

**2. Drift detection as a continuous monitor.** Run a daily or per-deployment check that compares the live MCP config against the last-approved snapshot. Flag any change to: OAuth scopes, added/removed servers, changed resource URIs, modified rate limits, or altered tool schemas.

```yaml
# .mcp-config-guardrails.yaml
watch:
  - server: github-production
    scopes:
      - write: false   # must be false; alert if true
    allowed_repos:
      - pattern: "org/agent-.*"
        action: enforce
      - pattern: "*"
        action: alert   # any unconstrained repo access = alert
  - server: database-tool
    max_rows: 100        # must not exceed 100
    write_enabled: false # must be false; alert if true
    audit_log: true      # must be true
  - server: web-search
    allowed_domains:
      - "*.internal.corp"
      - "api.company.com"
    # Any addition to this list = security alert

alerting:
  slack: "#agent-security"
  severity: scope_change == critical, resource_change == high, rate_limit_change == medium
```

**3. Server provenance tracking.** Every MCP server in an agent's config should carry a declared source: who deployed it, what version, and what change log. Reject any server that can't provide a provenance record.

```
# In agent-config/servers.yaml
servers:
  - name: github-production
    version: "2.4.1"          # pinned
    source: "infra/mcp-servers"  # monorepo path
    last_reviewed: "2026-06-15"
    owner: "platform-team"
    changelog_required: true

  - name: database-tool
    version: "1.8.0"          # pinned
    source: "infra/db-mcp"       # monorepo path
    last_reviewed: "2026-06-20"
    owner: "data-team"
    changelog_required: true
```

**4. Config-as-code for MCP.** Store MCP server definitions and configurations in the same version-controlled repo as your agent code. Use a pull-request workflow for any config change. This brings MCP configs into the same review, approval, and rollback infrastructure you use for application code.

**5. Automated schema fingerprinting.** Beyond permissions, track the tool schemas themselves. Any change to a tool's input/output schema — field added, field removed, type changed — should trigger a re-evaluation of agent behavior. S-113 (Reactive Schema Evolution) handles runtime adaptation; this step handles the pre-deployment gate.

## Receipt
> Verified 2026-07-09 — Research sources: MintMCP blog "MCP Config Drift: The Security Risk Hiding in Your Agent Infrastructure" (Jun 2026); BuildMVPFast "MCP Server Quality Crisis: Why Most Servers Should Be Killed" (Apr 2026); cleanlab.ai "AI Agents in Production 2025" survey (only 95/1837 enterprise teams had agents live in production, with control and transparency cited as primary gaps); arxiv 2510.01179 (Toucan 1.5M MCP tool-agentic dataset, Oct 2025). Pattern distilled from cross-referencing MintMCP's MCP config drift taxonomy against the handbook's existing S-261 (MCP security), S-870 (MCP session architecture), S-865 (tool behavior drift), and S-113 (reactive schema evolution).

## See also
[S-261](s261-mcp-security-guardrails-for-production-agents.md) · [S-870](s870-the-mcp-session-architecture-stack-when-the-protocol-was-built-for-demos-and-youre-in-production.md) · [S-865](s865-the-tool-behavior-drift-stack-when-the-schema-holds-but-the-silence-wrong.md) · [S-113](s113-reactive-schema-evolution.md) · [S-10](s10-mcp.md)
