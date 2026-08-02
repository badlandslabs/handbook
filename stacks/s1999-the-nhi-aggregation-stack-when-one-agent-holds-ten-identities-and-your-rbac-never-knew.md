# S-1999 · The NHI Aggregation Stack — When One Agent Holds Ten Identities and Your RBAC Never Knew

When your agent starts a session, it brings credentials. The GitHub integration needs a token. The database needs a password. The Slack webhook needs a secret. The CRM OAuth flow needs a refresh token. The cloud executor needs an IAM role. The MCP server for file operations needs an API key. Add them up: one agent, ten identities, all active simultaneously, all flowing through the same LLM context window. Each individual credential is correctly scoped. The RBAC is clean. The rotation schedule is enforced. The problem is not any single credential — the problem is what happens when they all meet in one place.

This is NHI Aggregation Risk: the attack surface amplification that occurs when an AI agent collapses multiple independent non-human identities into a single execution context. Traditional applications hold one service account per integration. Agents hold all of them simultaneously — and hand that aggregate to a non-deterministic reasoning system that logs, caches, and can surface any of those identities at any point in the session.

## Forces

- **One execution context, many identities.** Traditional service accounts are scoped by invocation. An agent's context window accumulates credentials across the full session. A compromised context exposes everything at once.
- **Context is not a vault.** Credentials in the context window are not isolated from the LLM's reasoning. They appear in system prompts, tool call logs, memory retrievals, and reasoning traces. Stdout captures, log aggregators, and agent memory systems all inherit the full credential surface.
- **Agents acquire credentials dynamically.** Unlike traditional services with static credential sets, agents request, discover, and use credentials at runtime based on task requirements. You cannot pre-enumerate the full credential surface at deployment time.
- **NHI governance ignores agents.** OWASP NHI Top 10 categories (improper offboarding, secret leakage, excessive permissions, long-lived secrets, insecure auth) all assume human-managed credential lifecycles. None account for an LLM reasoning over a credential store mid-session.
- **The aggregation multiplier makes individual credential hygiene irrelevant.** Even if every individual credential is perfectly rotated, scoped, and audited, the aggregated context is a single point of failure. The chain is as strong as its weakest credential — and in an agent, the weakest credential is the reasoning system that holds all of them.

## The move

### 1. Inventory NHI surface before the session starts

Treat the agent's credential surface as a first-class asset. Before deployment, enumerate every identity the agent will hold, their permission scopes, and their blast radius if exposed simultaneously.

```python
# NHI surface map — capture at agent initialization
NHI_SURFACE = {
    "github_api_token": {
        "scope": ["repo", "workflow"],
        "blast_radius": "Code exfiltration, CI/CD compromise"
    },
    "database_creds": {
        "scope": ["read", "write:orders"],
        "blast_radius": "PII access, data deletion"
    },
    "mcp_file_server_key": {
        "scope": ["read:filesystem", "write:workspace"],
        "blast_radius": "Arbitrary file read/write"
    },
    "slack_webhook_secret": {
        "scope": ["channel:post"],
        "blast_radius": "Social engineering via internal channels"
    },
    "cloud_executor_iam": {
        "scope": ["s3:put", "lambda:invoke"],
        "blast_radius": "Lateral movement, resource creation"
    },
}

def agent_nhi_audit(agent_id: str) -> dict:
    """Calculate aggregate risk score for an agent's NHI portfolio."""
    score = sum(len(info["scope"]) for info in NHI_SURFACE.values())
    cross_service = detect_cross_service_permissions(NHI_SURFACE)
    return {"total_identities": len(NHI_SURFACE),
            "aggregate_risk_score": score,
            "cross_service_exposure": cross_service}
```

### 2. Scope credentials per task, not per session

Instead of loading all NHI credentials at session start, provision credentials at task dispatch. Each task gets exactly the identities it needs, and they are revoked on task completion.

```python
from contextlib import contextmanager

@contextmanager
def ephemeral_nhi_context(task_id: str, required_scopes: list[str]):
    """
    Per-task credential isolation.
    Agent receives credentials only for this task.
    Revoked immediately on task exit.
    """
    creds = credential_broker.provision_for_task(task_id, required_scopes)
    # Inject only these credentials into the task's context
    task_context = {"credentials": creds, "task_id": task_id}
    try:
        yield task_context
    finally:
        credential_broker.revoke_for_task(task_id)
        # NHI is now invalid — even if agent reasoning persists,
        # the credential it held is gone
```

### 3. Inject credentials at call time, not at definition time

Never store credentials in the agent's system prompt or long-term memory. Load them at the tool call boundary and inject as runtime parameters only.

```python
# Bad: credential in system prompt — lives for the full session
SYSTEM_PROMPT_BAD = f"""
You are an order-processing agent.
Use this GitHub token for commits: {GITHUB_TOKEN}
"""

# Good: credential injected at tool-call boundary
def call_mcp_tool(agent_id: str, tool_name: str, params: dict) -> dict:
    creds = credential_broker.get_for_tool(agent_id, tool_name)
    # Credential lives only for this one tool call
    # Not in the context window after the call returns
    return mcp_client.invoke(tool_name, params, credentials=creds)
```

### 4. Enforce NHI partition boundaries in the memory layer

If the agent uses persistent memory, credentials must never enter the memory store. Treat any credential appearing in a memory write as a security event.

```python
def memory_write_guard(memory_entry: dict, agent_nhi_set: set[str]) -> bool:
    """Block credential-like content from entering agent memory."""
    for field in memory_entry.values():
        if any(nhi_sig in str(field) for nhi_sig in ["sk-", "ghp_", "eyJ", "token:", "secret"]):
            security_alert.send(
                event="NHI_IN_MEMORY",
                agent_id=memory_entry.get("agent_id"),
                field_hash=hashlib.sha256(str(field)[:50].encode()).hexdigest()[:8]
            )
            return False  # Block the write
    return True
```

### 5. Monitor the aggregate blast radius, not individual credentials

Set alerts for credential co-occurrence patterns. If an agent simultaneously holds GitHub, database, and cloud IAM credentials, flag that as a high-risk state — even if each individual credential is valid.

## Receipt

> Verified 2026-08-02 — Key sources: Zylos Research (2026-05-07) AI Agent Credential and Secret Management; GitGuardian State of Secrets Sprawl 2026 (28.65M secrets, +34% YoY, 1.2M AI-service); Gravitee 2026 survey (919 orgs, 21.9% NHI-aware, 25.4% hardcoded); OWASP NHI Top 10 (improper offboarding, secret leakage, excessive permissions, long-lived secrets, insecure auth); Mem0 survey 2026 (57-71% cross-user contamination); CSA/CrowdStrike/Cisco NHI acquisitions (Jun 2026); LangGrinch CVE-2025-68664 (ephemeral credentialing paper, SSRN, Devon Artis, April 2026).

## See also

- [S-1083 · The Platform Credential Boundary](/stacks/s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — the platform metadata identity that your RBAC never scopes
- [S-1155 · The Credential Lifetime Gate](/stacks/s1155-the-credential-lifetime-gate-stack-when-your-agent-holds-a-permanent-key-it-should-hold-a-temporary-one.md) — token TTL as a containment boundary
- [S-1127 · The Cross-User Memory Contamination Stack](/stacks/s1127-the-cross-user-memory-contamination-stack-when-user-b-sees-user-as-private-notes.md) — when the memory layer leaks context between users
- [S-1248 · The Token Drift Stack](/stacks/s1248-the-token-drift-stack-when-your-long-running-agent-holds-keys-that-expire-and-nobody-knows.md) — keys that expire while the session is mid-run
