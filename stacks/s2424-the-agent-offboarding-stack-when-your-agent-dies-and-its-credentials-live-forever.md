# S-2424 · The Agent Offboarding Stack — When Your Agent Dies and Its Credentials Live Forever

You decommission an agent. The task it was built for shipped. The team moved on. The agent is gone — or so you think. In reality, its credentials are still alive. The OAuth client is still registered. The scoped token minted for a pilot project is still authenticating cleanly, months later. The MCP connection is still open. The login handshake passes every single call, and that's exactly the problem: nobody wrote the offboarding step.

This is the agent orphan credential crisis. Every company can answer "who still has access and why" for human employees in seconds. Ask the same question about an AI agent from a pilot four months ago, and the honest answer is usually a shrug.

## Forces

- **No HR event triggers agent review.** Humans resign, get fired, change roles, go on leave. Agents do none of these — they complete tasks and go silent. The absence of a lifecycle termination event means credentials outlive purpose by default.
- **Ephemeral credentials solve the wrong half of the problem.** Task-scoped tokens (S-1075) are the right answer during operation, but they still need to end. If the credential broker doesn't support fast revocation, even short-lived tokens accumulate into a sprawl of legitimate-but-pointless access grants.
- **Offboarding is a governance and data-ownership problem, not just security hygiene.** EU AI Act Article 9 (risk management) and Article 12 (technical documentation) require organizations to account for every AI system operating on their behalf. Orphaned agents are invisible to this accounting.
- **The credential scope and the agent identity are owned by different systems.** The MCP client registration lives in one place. The OAuth client in another. The per-task scoped token in a third. Closing an agent means closing all three, and nobody owns the coordination.

## The move

**The core principle: treat agent offboarding as a lifecycle event, not a delete key.**

### Layer 1 — Offboarding Triggers (The Missing Events)

Human offboarding has termination events (resignation, firing, role change). Agent offboarding doesn't — you have to define them explicitly.

```
offboarding_triggers = {
    "task_complete": True,        # original task done
    "ttl_expired": True,          # max runtime reached
    "owner_absent": True,         # owning team/org changed
    "model_change": True,         # foundation model switched
    "incident_triggered": True,   # security event
    "policy_violation": True,    # compliance boundary crossed
    "manual_review": True,        # quarterly owner attestation
}
```

Each trigger should fire a revocation sequence, not just stop the agent.

### Layer 2 — Credential Broker as Single Source of Truth

The credential broker (S-1075) is the control plane for agent offboarding. Every credential — OAuth client, scoped token, MCP server registration, platform identity — should be issued through the broker and revocable through it.

```
# Credential broker revocation (pseudocode)
async def offboard_agent(agent_id: str, reason: str) -> OffboardingReceipt:
    receipt = OffboardingReceipt(agent_id=agent_id, reason=reason, ts=now())

    # Revoke all active credentials in parallel
    results = await asyncio.gather(
        broker.revoke_oauth_client(agent_id),
        broker.revoke_all_tokens(agent_id),
        broker.close_mcp_connections(agent_id),
        broker.revoke_platform_identity(agent_id),
    )

    # Verify revocation
    for result in results:
        receipt.add_step(result)
        if not result.success:
            alert_ops(f"Revocation failed for {result.resource}")

    # Mark identity as DEPRECATED (different from REVOKED)
    await agent_registry.update_state(agent_id, state="deprecated")

    return receipt
```

**Key distinction:** `REVOKED` means "stop access now." `DEPRECATED` means "this identity is retired, do not issue new credentials." Both states are needed.

### Layer 3 — Instant Revocation via Token Exchange

The strongest architectural argument for token exchange (STS pattern) over static keys: revocation is a single action. If every credential is a short-lived token minted against a live identity, disabling the identity kills all tokens simultaneously. If credentials are static API keys, revocation requires finding every copy.

```
# Token exchange model — revocation is one action
identity.disabled = True   # All outstanding tokens invalidated instantly
# vs. static key model:
for key in api_key_registry.find_keys_by_agent(agent_id):
    key.revoke()          # Must enumerate every copy
```

Praesidia's analysis (2026) identifies this as the core advantage: ephemeral tokens turn revocation from an enumeration exercise into a single control-plane action.

### Layer 4 — Asset and Data Ownership Transfer

An offboarded agent may have generated outputs, written to shared stores, or created artifacts. The offboarding process must handle:

```
offboarding_artifacts = {
    "memory_state": "archive_or_delete",  # What happens to agent memory?
    "output_ownership": "transfer_to_team", # Who owns what the agent produced?
    "audit_trail": "export_and_retain",    # Retain traces per compliance req
    "derived_resources": "list_and_revoke",# MCP servers, sub-agents, tokens
}
```

This is distinct from revocation: it's the data governance layer underneath.

### Layer 5 — EU AI Act Compliance Anchor

The August 2, 2026 EU AI Act enforcement deadline makes this operational, not theoretical. Article 9 requires documented risk management including post-deployment monitoring. Article 12 requires technical documentation listing every AI system in scope. An agent without an offboarding process is:

1. Invisible to the Article 12 registry (underreporting)
2. Ungoverned by Article 9 risk controls (orphaned risk)
3. Exposed to Article 83 civil liability for incidents from decommissioned agents still accessing data

## Receipt

> Receipt pending — 2026-08-10
> Sources: Fullmakt.ai "AI Agent Offboarding" (2026), AgentID "Agentic Identity Protocol" (Jul 2026), Praesidia.ai "Secure Agent Offboarding" (2026), Microsoft Security "Least Privilege for AI Agents" (Jul 2026), Okta "Least Privilege for AI Agents" (May 2026), CSA "Shadow AI Agent Problem" (Apr 2026). Pattern confirmed: 82% of enterprises discovering unknown agents (CSA, Apr 2026) implies the same orgs have no offboarding process — the agent population can only grow, never shrink.

## See also

- [S-1075 · The Ephemeral Delegation Stack](s1075-the-ephemeral-delegation-stack-task-scoped-tokens-for-cross-agent-credential-chains.md) — task-scoped tokens are the precondition; offboarding is what ends them
- [S-1041 · The Agent Shadow IT Stack](s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — inventory is the precondition; offboarding is what closes the loop
- [S-992 · The Agent Verifiable Credential Infrastructure](s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — credential infrastructure for the start of life; this is the end of life
- [S-1083 · The Platform Credential Boundary](s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — platform identities attached during operation must be revoked at termination
