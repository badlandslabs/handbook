# [S-1428] · The Agent Secrets Sprawl Stack

> When your AI coding agent committed 3.2% of its sessions with live credentials — and your secrets debt crossed 28 million exposed keys.

Every AI agent that calls an API, pushes a commit, reads an inbox, or queries a database is a non-human identity (NHI). In 2026, that population reached 45–100× the number of human identities in a typical enterprise, with IDC projecting 1.3 billion AI agents in production by 2028. The governance practices meant to control these identities have not kept pace. The result is a secrets sprawl crisis that is structurally worse than anything the human developer population produced.

## Forces

- **Agents generate credentials autonomously** — an agent given write access to a SaaS tool will, given sufficient autonomy, request role escalations, create sub-agents, and chain tool-use across systems whose individual security postures were never designed to be composed by a non-human actor.
- **Detection ≠ governance** — GitGuardian's 2026 report found that 64% of exposed secrets remain valid after disclosure. Most teams can detect sprawl; few can govern it.
- **The coding agent baseline is already 2× worse than humans** — Claude Code commits leak secrets at 3.2% vs. the 1.5% human-only baseline (GitGuardian, 2026). AI-service secret leaks grew 81% YoY in 2025, reaching 28.65 million hardcoded secrets added to public GitHub.
- **Creation velocity outpaces identity maturity** — 78% of organizations lack a formal AI identity creation policy; only 23% have a formal agent identity strategy (CSA, February 2026).
- **The NHI:human ratio is extreme** — SANS Institute (June 2026) estimates 82:1 in typical environments, projected to 400:1 for ephemeral cloud workloads. Every one of those identities is a secret-backed credential that can be leaked, rotated, or compromised.

## The move

### 1. Name every agent's credential identity before it touches production

Every agent needs a workload identity registered in a centralized identity store before it receives its first credential. This is the agent's NHI — its name, version, capability scope, and authorized tool chain. Without this, credentials are issued to unnamed processes and cannot be revoked, audited, or scoped.

The minimum viable registration:

```
AgentID: coding-agent-prod-v3.2
Owner: platform-team
CapabilityScope: [read-repos, write-issues, read-db:reporting]
CredentialType: dynamic  # never static
IssuedBy: vault-prod
TTL: 4h
HandoffAllowed: false
```

### 2. Replace every static credential with a dynamic secret

Gartner's April 2026 Reference Architecture Brief stated it plainly: *"Every new static symmetric string, such as an API key, represents a failure of the IAM program and tooling."*

Static API keys are the dominant credential form for agents today — and they are the root cause of the sprawl. The fix is a dynamic secrets engine: credentials are minted on-demand, short-lived (4–24h), and scoped to the specific resource the agent needs at that moment.

```python
# Agent requests a scoped credential from the secrets vault
credential = vault.issue(
    agent_id="coding-agent-prod-v3.2",
    scope="read-db:reporting",
    ttl="4h",
    purpose="ad-hoc-query-2026-07-21"
)
# Agent uses credential — it expires before the next session
```

This eliminates the "long-lived secret" category entirely, which GitGuardian found accounts for **60%** of all policy breaches.

### 3. Implement per-tool credential egress allowlists

Agents with broad tool access accumulate credentials for every system they touch. The attack surface is the union of all those credentials. The mitigation is an **egress allowlist per tool** — each MCP server or tool endpoint gets its own minimal credential, and the agent cannot call a tool with a credential scoped to a different tool.

```python
# Per-tool credential scopes — agent cannot use db-cred for email API
tool_credentials = {
    "github-repo-reader": github_cred(ttl="2h", scope="read"),
    "db-reporting-query": db_cred(ttl="1h", scope="SELECT-only"),
    "slack-alert-sender": slack_cred(ttl="30m", scope="post:#incidents"),
}
```

If a compromised tool tries to use a credential from a different scope, the vault logs the mismatch and alerts.

### 4. Run secret scanning as a pre-commit gate — and inside the agent loop

The 3.2% leak rate from AI coding agents is not a developer failure — it is a process failure. Pre-commit hooks (TruffleHog, GitGuardian ggshield, Semgrep secrets) catch most of these before they reach version control, but only if they run as non-optional gates.

```yaml
# .github/workflows/agent-guard.yml
- name: Scan for secrets in AI agent commits
  uses: trufflesecurity/trufflehog@main
  with:
    base: ""
    head: ${{ github.ref_name }}
    extra_args: --results=verified
  # FAIL on any verified secret — no allow_failure
```

More critically: agents that generate code should run secret scanning on their own output before committing. The agent is the most efficient remediation agent for its own mistakes.

```python
# Inside the agent's commit tool — scan before push
def safe_commit(file_changes):
    scan_result = trufflehog.scan_bytes(file_changes)
    if scan_result.has_secrets:
        raise AgentSafetyError(
            f"Blocking commit: {len(scan_result.secrets)} secret(s) detected. "
            f"Use vault.fetch_credential() instead of hardcoding."
        )
    git.push(...)
```

### 5. Govern the credential lifecycle — rotation, revocation, and handoff

Long-lived secrets persist because no one owns their rotation. Every agent-issued credential needs an owner, a rotation schedule, and an automated revocation path.

| Credential Type | TTL Target | Rotation Trigger |
|---|---|---|
| Agent workload identity (SPIFFE/SVID) | 1–4h | Automatic via SPIRE |
| Database query | 30m–4h | On task completion |
| Cloud API (dynamic exchange) | 1–4h | Vault lease renewal |
| MCP server auth token | 4–24h | Daily rotation |
| Static API key (legacy) | 90d maximum | Migration to dynamic first |

For handoff between agents (planner → worker, supervisor → specialist), use **capability tokens** — short-lived, scoped JWTs that the receiving agent cannot further delegate. This prevents credential chaining where agent A calls B, which calls C, each accumulating broader access.

### 6. Detect sprawl drift — the 64% problem

64% of exposed secrets remain valid after disclosure (GitGuardian, 2026). Valid after disclosure means your scanning found it, someone acknowledged it, and nothing changed. The stack must include automated:

- **Rotation confirmation**: when a secret is flagged, verify it was actually rotated within 72h
- **Secret health scoring**: number of valid secrets × age × blast radius per agent
- **Commit-level alerting**: flag when any commit authored by an AI agent's identity contains a credential pattern, even if the credential itself isn't valid — the pattern itself is evidence of a process failure

## Receipt

> Verified 2026-07-21 — Primary sources: GitGuardian State of Secrets Sprawl 2026 (28.65M secrets, 3.2% Claude Code leak rate, 64% valid-after-disclosure); CSA Survey Feb 2026 (23% formal strategy, 78% no creation policy); SANS Institute June 2026 (82:1 NHI:human ratio, 400:1 projected); Gartner April 2026 Reference Architecture Brief (static API keys as IAM failure); Zylos Research July 5, 2026 (NHI lifecycle governance for agent fleets); WorkOS June 2026 (API key management for AI agents); LeanOps May 2026 (token cost patterns); Akeyless May 2026 (hardcoded API keys as IAM failure). Deduplication: S-1265 covers kill switch and artifact versioning but not credential lifecycle governance; S-1388 covers NHI identity broadly but not the secrets sprawl failure mode; S-1391 covers MCP gateway and tool registry but not credential scoping per tool. None covers the full five-layer stack from workload identity registration through dynamic secrets, per-tool credential scoping, pre-commit scanning, lifecycle governance, and sprawl drift detection.

## See also

- [S-1265 · The Kill Switch Stack](s1265-the-kill-switch-stack-when-you-need-to-stop-the-agent-right-now.md) — revocation and emergency stop, the complementary half of credential lifecycle
- [S-1266 · The Agent Governance Void Stack](s1266-the-agent-governance-void-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — the governance layer that makes credential policies enforceable
- [S-1388 · The A2A Context Fidelity Stack](s1388-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md) — NHI lifecycle, the identity layer this pattern depends on
