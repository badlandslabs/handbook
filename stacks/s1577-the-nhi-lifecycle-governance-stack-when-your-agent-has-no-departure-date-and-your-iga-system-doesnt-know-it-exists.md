# S-1577 · The NHI Lifecycle Governance Stack: When Your Agent Has No Departure Date and Your IGA System Doesn't Know It Exists

Your agent has been running for 8 months. It has a valid API key, access to 14 internal services, and credentials stored in 3 different secret managers. Nobody created a ticket for it. Nobody approved its access grants. Your IGA system has no record it exists. When the project it was built for ended, nobody decommissioned it. Now it has a valid credential and nobody's watching. This is the NHI lifecycle governance problem — and traditional identity tools were not built for it.

## Forces

- Traditional IGA systems are event-driven around HR transitions (joiner/mover/leaver). Agents have no employment record, no manager, and no departure date.
- Agents proliferate faster than any human onboarding process can track — IDC projects 1.3 billion AI agents in operation by 2028, while only 23% of organizations have a formal agent identity strategy.
- Credential sprawl is compounding: GitGuardian's 2026 report found 28.65M secrets leaked to GitHub in 2025 (+34% YoY), with AI-service secrets growing 81% YoY and Claude Code commits leaking secrets at 3.2% vs 1.5% for human-only commits.
- When an agent's task ends, its credentials persist unless someone actively revokes them — the inverse of human offboarding where HR-triggered events drive deprovisioning.
- Agents can spawn sub-agents or replicate credentials autonomously, creating identity populations that no single registration system can track.

## The move

The NHI lifecycle governance stack operates in five phases, independent of HR events:

### Phase 1 — Intentional Registration (Provisioning)

Every agent gets a registered identity *before* it receives credentials. Registration captures:

```
AgentRegistration {
  agent_id: uuid,          // globally unique
  capability_manifest: [], // what this agent can do
  purpose_scope: string,   // bounded business purpose
  owner: human_principal,  // accountable human
  trust_tier: 1-5,         // capability risk tier
  ttl: duration,           // auto-expiry (no agent is permanent)
  renewal_approver: human_principal
}
```

Purpose-bound credentials (per CSA MAESTRO framework, 2025) encode the agent's authorized scope directly into the credential — not just "can call the CRM API" but "can call CRM contacts-read for customer-IDs-matching-query X for 30 days."

### Phase 2 — Workload Identity Authentication

Agents authenticate as workloads, not users. This uses workload identity federation (WIF) — the agent presents a dynamically-issued, short-lived token rather than a static API key. This eliminates the secret-sprawl problem: no long-lived credential to rotate, revoke, or leak.

```python
# Workload identity token issuance (simplified)
import time

def issue_agent_token(agent_id: str, capabilities: list[str], ttl_seconds: int = 3600) -> dict:
    """Issue a short-lived workload identity token to a registered agent.
    Token encodes: agent_id, authorized capabilities, issued_at, expires_at, audience.
    No static secret stored. No rotation needed. Revocation = deny issuance."""
    now = int(time.time())
    return {
        "token_type": "NHI-WIF-v1",
        "sub": agent_id,
        "scope": " ".join(capabilities),
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": "https://identity.internal/agent-issuer",
        "aud": "agent-gateway",
        # The credential encodes PURPOSE, not just identity
        "purpose": capabilities[0] if capabilities else "unknown",
        "purpose_ttl": ttl_seconds,
    }

# Gateway validates token and enforces capability envelope
def validate_and_dispatch(token: dict, requested_capability: str) -> bool:
    if token.get("exp", 0) < int(time.time()):
        return False  # Expired — must re-issue
    authorized = set(token.get("scope", "").split())
    return requested_capability in authorized
```

### Phase 3 — Continuous Behavioral Authorization

Static ACLs say what the agent *can* do. Behavioral authorization monitors what it *does*. A shadow-mode period runs new agents with logged-but-not-enforced access for a calibration window — establishing a behavioral baseline. Post-calibration, deviations from the baseline trigger a capability audit.

Key signals: unusual API call volume, access to previously-unseen resources, outbound data transfers, cross-tenant operations, or execution frequency above established norms.

### Phase 4 — Lifecycle Transitions (Mover)

When an agent's purpose changes — new tools, expanded scope, new owner — the transition is treated as a new provisioning event. Old credentials are invalidated. New capability manifest is registered. Purpose scope is re-established. This prevents capability creep from accumulating silently across updates.

### Phase 5 — Intentional Decommissioning (Leaver)

Agents must have a TTL. When the TTL triggers or the task completes:

1. Revoke all active credentials immediately
2. Invalidate workload identity tokens (deny re-issuance)
3. Drain pending operations with a graceful-wind-down window
4. Archive audit log for compliance retention period
5. Release allocated resources (secret manager entries, quota allocations, tool permissions)

For agents without a defined end date, the TTL serves as the departure event. No TTL = no deployment. This architectural constraint is the single most effective NHI governance measure.

## Receipt

> Verified 2026-07-24 — Research synthesized from Zylos Research (Jul 2026), The Hacker News (Jul 2026), CSA Agent Identity Governance Framework (Dec 2025), GitGuardian State of Secrets Sprawl 2026, Okta AI Agent Lifecycle Management. No live execution. Pattern validated against enterprise NHI governance best practices documented across sources. Receipt pending — live implementation demo.

## See also

- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](s420-agent-identity-governance-the-ai-principal-paradigm.md) — the structural IAM gap that makes this necessary
- [S-444 · The 97/12 Gap: Agent Governance Discovery](s444-the-97-12-gap-agent-governance-discovery.md) — finding the agents your IGA system doesn't know about
- [S-1552 · The AI-BOM Stack: When Your Agent Supply Chain Has No Ingredient Label](s1552-the-ai-bom-stack-when-your-agent-supply-chain-has-no-ingredient-label.md) — the inventory system that feeds into NHI registration
