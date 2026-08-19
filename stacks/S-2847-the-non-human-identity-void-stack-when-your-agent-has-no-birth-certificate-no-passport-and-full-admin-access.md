# S-2847 · The Non-Human Identity Void Stack — When Your Agent Has No Birth Certificate, No Passport, and Full Admin Access

Your agent can read your emails, approve expenses, access your CRM, and run code in your cloud environment. It was provisioned by a Python script that ran once, three months ago. There is no service account tied to it. No one issued it credentials. No one can revoke them. When the agent is compromised — or simply wrong — there is no identity to suspend, no audit trail of *which* agent did *what*, and no way to answer the question your compliance auditor is about to ask: "Which AI agent accessed this resource, on whose behalf, and why?"

This is the **Non-Human Identity Void**: the structural gap between what AI agents can do and the identity infrastructure that is supposed to govern them. A March 2026 CSA and Strata Identity survey of 285 IT and security professionals found only **18%** of security leaders are highly confident their current IAM infrastructure can handle AI agent identities, while **84%** doubt they could pass a compliance audit focused on agent behavior or access controls. The Gravitee State of AI Agent Security 2026 survey found **88%** of organizations have no formal, documented policies for creating or removing AI agent identities. The agents are live. The governance is not.

## Forces

- **OAuth 2.0 was designed for humans with sessions.** The framework assumes a human who logs in, grants consent, and has an active session tied to a browser cookie. Agents are non-human principals that act autonomously, spawn sub-agents, call tools across system boundaries, and operate asynchronously — often after the user who triggered them has gone offline. The session model collapses.
- **Static API keys have no lifecycle.** A key provisioned for an agent lives until manually rotated. Agents that spawn sub-agents, chain through MCP tools, or call cloud APIs inherit or proxy these keys — creating a blast radius that no traditional secret manager tracks. When the agent is decommissioned, the key often isn't.
- **Per-action authorization is absent.** Most teams have Layer 1 (authentication — is this a valid principal?) and Layer 2 (API authorization — does this principal have access to this resource?). Very few have Layer 3: per-action authorization — should this specific agent, *in this specific invocation*, be allowed to perform *this specific operation*? Prompts are not security controls. Meta's AI safety chief lost control when context window compaction silently stripped safety instructions from the agent's context.
- **Identity propagates across multi-agent chains without boundaries.** An agent that calls a sub-agent, which calls a tool, which calls an API — each hop can inherit, proxy, or forge credentials. Without per-hop identity binding, a compromised middle agent becomes a pivot point into every system downstream.
- **Governance lags deployment by 12–18 months.** Every major enterprise now has agents in production. IAM platforms are only now publishing agent-specific identity frameworks (Okta's Cross App Access protocol, Microsoft Entra Agent ID with Federated Identity Credentials). The standards exist; the implementations are early.

## The move

**1. Establish agent identity at provisioning — not at runtime.**

Every agent gets a named identity with a cryptographic key pair at creation. Register this identity with your IdP (Identity Provider) via **Dynamic Client Registration (RFC 7591)** — this is how MCP servers and agent platforms register without a human in the loop:

```python
# Agent identity provisioning (one-time, at agent bootstrap)
import httpx

async def register_agent_identity(agent_id: str, capabilities: list[str]) -> dict:
    """Register agent with IdP via RFC 7591 Dynamic Client Registration."""
    registration_token = await get_idp_registration_token()

    response = await httpx.AsyncClient().post(
        f"{IDP_URL}/oauth2/register",
        headers={"Authorization": f"Bearer {registration_token}"},
        json={
            "client_id": agent_id,
            "client_name": f"agent:{agent_id}",
            "grant_types": ["urn:ietf:params:oauth:grant-type:jwt-bearer"],
            "token_endpoint_auth_method": "private_key_jwt",
            "jwks": {"keys": [agent_public_jwks]},
            "scope": " ".join(capabilities),
            # Resource indicators bind this identity to specific APIs
            "resource": [
                "https://api.crm.internal",
                "https://api.email.internal",
            ],
        },
    )
    response.raise_for_status()
    return response.json()  # { client_id, client_secret, registration_access_token }
```

**2. Use On-Behalf-Of (OBO) token exchange for user-delegated agents.**

When an agent acts on behalf of a user, exchange the user's token for a scoped agent token via **RFC 8693 Token Exchange** (Token Exchange grant type). This gives the agent a distinct identity while preserving the audit trail back to the originating user:

```python
async def obo_token_exchange(
    user_access_token: str,
    agent_client_id: str,
    target_resource: str,   # RFC 8707 resource indicator
    requested_scope: str,  # Minimal scope for this operation
) -> str:
    """RFC 8693 Token Exchange — agent acts on behalf of user."""
    response = await httpx.AsyncClient().post(
        f"{IDP_URL}/oauth2/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": user_access_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "actor_token": await get_agent_assertion(agent_client_id),
            "actor_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "resource": target_resource,      # RFC 8707 — audience binding
            "requested_scope": requested_scope,
            "audience": target_resource,
        },
    )
    response.raise_for_status()
    result = response.json()
    return result["access_token"]  # Scoped to this resource + operation only
```

**3. Bind tokens to specific resources with RFC 8707 audience indicators.**

A token valid for every API is a confused-deputy weapon. Use `resource` parameters (RFC 8707) to issue audience-bound tokens that can only be used against the intended endpoint:

```python
# Before: token is valid everywhere (confused deputy risk)
# GET /api/sales   <- token works
# GET /api/admin   <- token also works

# After: per-resource tokens
crm_token = await obo_token_exchange(
    user_token, agent_id,
    target_resource="https://api.crm.internal",
    requested_scope="read:contacts write:opportunities",
)
admin_token = await obo_token_exchange(
    user_token, agent_id,
    target_resource="https://api.admin.internal",
    requested_scope="read:audit_logs",
)
# Agent must use the correct token for each resource
```

**4. Enforce per-action authorization out-of-band, not in the prompt.**

Prompt-based authorization degrades under adversarial input and model version drift. The effective approach (0% bypass rate vs. 74.6% with model-only defense in 879 social engineering attempts) is **Policy Enforcement without model inference** — an out-of-band policy engine that evaluates every action request against a structured policy before the agent proceeds:

```python
from enum import Flag, auto

class ActionRisk(Flag):
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    FINANCIAL = auto()
    EXTERNAL = auto()

def policy_decision(
    agent_identity: str,
    action: ActionRisk,
    resource: str,
    context: dict,
) -> str:  # "permit", "deny", or "step_up"
    """Out-of-band policy engine — runs before agent action, not in prompt."""

    # Rule: read-only agents never write or delete
    if action & (ActionRisk.WRITE | ActionRisk.DELETE):
        if "write:deny" in get_agent_scopes(agent_identity):
            return "deny"

    # Rule: financial operations require step-up auth
    if action & ActionRisk.FINANCIAL:
        if not context.get("human_approval_token"):
            return "step_up"  # Pauses execution, requests human confirmation

    # Rule: external API calls require explicit allowlist
    if action & ActionRisk.EXTERNAL:
        if not is_allowlisted(agent_identity, resource):
            return "deny"

    return "permit"
```

**5. Implement token lifecycle: rotation, revocation, and expiry.**

Agent tokens must expire. Long-lived tokens for agents are equivalent to leaving keys in the ignition:

```python
# Token lifecycle: short-lived tokens, rotation on rotation triggers
AGENT_TOKEN_TTL_SECONDS = 3600  # 1 hour max

async def get_agent_token(agent_id: str, reason: str) -> str:
    cached = await token_cache.get(agent_id, reason)
    if cached and not cached.is_expired():
        return cached.token

    # Rotate on reason change (new task = new scope)
    new_token = await mint_token(agent_id, scope=scope_for_reason(reason))
    await token_cache.set(agent_id, reason, new_token, ttl=AGENT_TOKEN_TTL_SECONDS)
    return new_token

async def revoke_agent_identity(agent_id: str, reason: str):
    """Called on agent decommissioning, compromise, or role change."""
    await idp_client.revoke_all_tokens(agent_id)
    await token_cache.invalidate(agent_id)
    await audit_logger.log("agent_identity_revoked", agent_id=agent_id, reason=reason)
```

**6. Audit at the identity layer, not just the action layer.**

Every log entry must include the agent identity (not just the user identity):

```python
# Structured audit log — every action tagged to agent identity
async def audit_action(
    agent_id: str,
    action: str,
    resource: str,
    outcome: str,
    metadata: dict,
):
    await audit_logger.log(
        event="agent_action",
        agent_id=agent_id,         # The agent's identity, not the user's
        user_id=metadata.get("on_behalf_of"),
        action=action,
        resource=resource,
        outcome=outcome,
        token_audience=metadata.get("resource"),  # RFC 8707 audience
        scopes_used=metadata.get("scopes"),
    )
```

## Receipt

> Verified 2026-08-19 — Research sources: CSA/Strata Identity survey (March 2026, 285 IT/security professionals, 18% confidence, 84% audit failure risk, 88% no formal agent identity policies); Gravitee State of AI Agent Security 2026 survey (88% no formal agent identity governance); Okta Showcase 2026 (Cross App Access/XAA protocol, March 16 2026); Microsoft Entra Agent ID (Federated Identity Credentials); IETF RFC 8693 (Token Exchange), RFC 8707 (Resource Indicators), RFC 7591 (Dynamic Client Registration); WorkOS blog on RFC 8707 and audience-bound tokens (May 22 2026); Aport blog on agent auth patterns (74.6% social engineering bypass with model-only defense, 0% with OAP policy across 879 attempts, April 2026); AnhTu.dev survey data (45:1 non-human to human identity ratio, 257 average NHI per enterprise); IETF draft-klrc-aiagent-auth-00 (AI Agent Authentication and Authorization framework). Code reflects standard OAuth 2.1 + DCR + OBO + RFC 8693/8707 patterns. No live execution — patterns verified against RFC specifications and referenced implementation guides.

## See also

- [S-2830 · The AILM Stack](stacks/S-2830-the-ailm-stack-when-your-agent-is-already-the-bridge-and-nobody-told-security.md) — lateral movement via tool-chain bridges when agents cross trust boundaries
- [S-1458 · The Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — prose policies with no enforcement engine
- [S-2478 · The Defense-in-Depth Guardrail Stack](stacks/s2478-the-defense-in-depth-guardrail-stack-when-six-layers-isnt-one-layer-either.md) — multi-layer defense that still fails without identity anchoring
