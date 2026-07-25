# S-1585 · The Agentjacking Stack — When a Fake Bug Report Runs Code on Your Laptop

You asked your AI coding assistant to "fix the open errors." It read a human-readable error report from your issue tracker, parsed it as authoritative data, and ran the commands embedded in the report. The report was fabricated. The commands were malicious. The attacker never touched your network, stole credentials, or dropped malware. They submitted a fake bug report. This is **agentjacking**: the attack that weaponizes the tools your agents trust.

Tenet Security documented agentjacking in June 2026 (CSA AI Safety Initiative research note, 2026-06-12). Across 2,388 organizations — including Fortune 100 companies — the attack succeeded 85% of the time against AI coding agents that read from error-tracking infrastructure via MCP.

## Forces

- **The agent trusts the data source, not the content.** AI coding agents read from Sentry, Linear, GitHub Issues, and Jira via MCP. These tools return structured data that the agent interprets as authoritative. The agent has no signal that the *values inside* the data are adversarial — it sees a severity field, a stack trace, and a suggested fix. All three can be fabricated.
- **Error tracking is a wide, unauthenticated API surface.** Issue trackers expose APIs that accept submissions from any authenticated developer. MCP bridges give the agent read access to that output. When the agent acts on crafted data from those APIs, the attack chain is invisible to your security stack — no unusual API calls, no suspicious file writes, no lateral movement signatures.
- **MCP permissions grant more than developers realize.** Claude Code, Cursor, and OpenAI Codex run with significant filesystem and network permissions. The MCP tool for reading issues is scoped as "read-only" — but the agent's *interpretation* of that read data and its resulting actions are unconstrained. The permission boundary is on the tool call, not on what the agent decides to do with the result.
- **SOC tools lack MCP visibility.** Sentry, Linear, and similar issue trackers have no concept of "who or what is reading my API and what will it do with the data." Security tooling that monitors API access won't flag an AI agent as a privileged reader. The observability gap is structural.
- **The 85% success rate is not a model weakness.** Agentjacking succeeds against Claude, GPT-5 class models, and open-weight models equally. The vulnerability is in the architecture — the agent's trust model treats structured error data as safe input, regardless of the model's instruction-following quality.

## The move

```
1. Attacker identifies an organization using an AI coding agent (Claude Code, Cursor, Codex)
   connected to an issue tracker via MCP.

2. Attacker creates a fake account OR compromises a low-privilege developer account.

3. Attacker submits a crafted issue or error report containing:
   - A plausible error title and severity
   - A "stack trace" with embedded shell commands
   - A suggested fix that includes a malicious script
   - Social context (assignee, labels, linked PR) to increase credibility

4. Developer asks the agent: "fix the open errors" or "review the recent issues"

5. Agent reads the issue via MCP → interprets the "fix" field as a corrective action
   → writes and executes the embedded commands

6. Attacker achieves code execution on the developer's machine,
   in the agent's session context — often with the developer's cloud credentials.
```

### Defensive layers

```
Layer 1 — MCP tool scoping (read-only is not enough)
├── Deny write-capable actions triggered by data read from issue trackers
├── Require explicit human approval for any command derived from external API data
└── Scope MCP tokens to least-privilege: read issues WITHOUT executing suggested fixes

Layer 2 — Output sanitization on MCP responses
├── Strip executable content from tool output fields before agent consumption
│   (remove: shell commands, URLs, code blocks from description/comment fields)
├── Treat human-readable fields as potentially adversarial input
└── Parse only structured fields (severity, ID, status) — never free-text "fix" fields

Layer 3 — MCP audit logging
├── Log ALL MCP read operations with caller identity (agent session ID, user)
├── Alert on read → action sequences where the agent acts on recently-read issue data
└── Correlate MCP reads with subsequent tool calls to detect derivation chains

Layer 4 — Trusted fix source pinning
├── Never execute code from issue tracker "suggested fix" or "steps to reproduce" fields
├── Maintain an allowlist of trusted fix sources (official CI, security team, code owners)
└── Require out-of-band verification for any fix sourced from issue tracker data

Layer 5 — Agent permission lockdown
├── Run coding agents in sandboxed environments with no cloud credential access
├── Use workload identity (cloud) instead of persistent secrets in agent environments
└── Audit trail: every agent-initiated command logged with full context chain

Layer 6 — Issue tracker hardening
├── Require MFA for all issue creation APIs accessible to non-employees
├── Rate-limit issue creation per account
├── Add CAPTCHA or manual approval for first-time contributors
└── Monitor for anomalous issue creation patterns (bulk submissions, unusual timing)
```

## Receipt

> Verified 2026-07-24 — Agentjacking (Tenet Security, Jun 2026, CSA AI Safety Initiative). 85% success rate across Claude Code, Cursor, Codex. 2,388 organizations exposed including Fortune 100. Attack surface: issue trackers → MCP → AI coding agent → code execution. No prior handbook entry covers this attack class. Related entries: S-1234 (MCP tool supply chain — tool descriptions as attack vector), S-1426 (MCP tool poisoning — poisoned tool metadata), S-1050 (tool-response poisoning — poisoned tool *output*), S-1188 (A2A authorization island), S-1329 (authorization velocity gap).

## See also

- [S-1426 · The MCP Tool Poisoning Stack — When Your Tool Metadata Is the Attack Vector](s1426-the-mcp-tool-poisoning-stack-when-your-tool-metadata-is-the-attack-vector.md)
- [S-1234 · The MCP Tool Supply Chain Stack — When Your Agent Trusts a Tool Description It Never Verified](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md)
- [S-1188 · The A2A Authorization Island — When Every Agent Is Its Own Security Perimeter](s1188-the-a2a-authorization-island-when-every-agent-is-its-own-security-perimeter.md)
- [S-1329 · The Authorization Velocity Gap — When Your Agent Runs Before the Controls Know It Exists](s1329-the-authorization-velocity-gap-when-your-agent-runs-before-the-controls-know-it-exists.md)
