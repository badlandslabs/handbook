# S-1345 · The Delegation Chain Stack — When Your Agent's OAuth Flow Doesn't Account for the Fact That Agents Spawn Agents

Your agent authenticates with OAuth 2.0 and acts on behalf of a user. Works fine. Then the agent needs a specialist sub-agent. The sub-agent also needs credentials. Now you're in a three-party delegation chain — user → agent → sub-agent — and your OAuth provider has no concept of this. Your choices are: hand the sub-agent the user's long-lived token (catastrophic), mint a new static API key (ephemeral in name only), or build a custom delegation layer that your security team will find in an audit next quarter. This is the delegation chain problem, and it's the credential architecture gap that every agentic deployment hits between pilot and production.

## Forces

- **OAuth's On-Behalf-Of flow assumes two parties.** The standard OAuth 2.0 OBO pattern handles user → first-party app. It does not handle agent → sub-agent → sub-sub-agent chains. When your agent is both a client and a resource server simultaneously, OAuth's role model breaks.
- **Credential exposure window scales with concurrency, not time.** A 2-minute task with a 15-minute token = 13 minutes of unnecessary exposure per invocation. At 1,000 parallel agent invocations, that's 13,000 exposed-minutes per task cycle, each representing a window where a compromised sub-agent or tool response could use credentials it shouldn't have.
- **The principal hierarchy in multi-agent systems is a tree, not a chain.** A human delegates to Agent A (coordinator). Agent A delegates subtasks to Agents B, C, and D (specialists). Each specialist may call external tools. The OAuth concept of "acting on behalf of" assumes a linear delegation; agents produce a branching trust graph.
- **Sub-agents are cross-organizational.** An agent that hires a contractor specialist via A2A needs credentials to your APIs — not just the sub-agent's own identity, but scoped access to the original user's delegated permissions. This is not a problem any OAuth grant type solves out of the box.

## The move

### 1. Scope credentials to the task graph, not the session

Instead of one token per agent-session, mint tokens scoped to a specific task-ID + capability set. The token outlives the agent's invocation but dies when the task completes or when a revocation signal fires.

```python
# Task-scoped ephemeral credential issuance
from authlib.integrations.flask_oauth2 import AuthorizationServer
from flask import g
import time

class AgentCredentialIssuer:
    def __init__(self, authz_server: AuthorizationServer, token_ttl_seconds=300):
        self.authz_server = authz_server
        self.token_ttl = token_ttl_seconds

    def issue_task_token(self, principal_user_id: str, task_id: str,
                         capabilities: list[str], requesting_agent_id: str) -> dict:
        """Mint a short-lived token scoped to a specific task + capability set."""

        now = int(time.time())
        token_payload = {
            "sub": requesting_agent_id,          # The sub-agent's identity
            "aud": "agent-platform",            # Your platform's token audience
            "scope": " ".join(capabilities),    # e.g., "read:calendar write:calendar"
            "delegated_from": principal_user_id, # Trace delegation chain
            "task_id": task_id,                 # Revoke all tokens for this task atomically
            "iat": now,
            "exp": now + self.token_ttl,        # Auto-expire: no revocation needed for normal case
            "jti": f"{task_id}-{requesting_agent_id}-{now}",  # Revocation ID
        }

        # Issue token via your OAuth server
        return self.authz_server.create_token_response(token_payload)
```

### 2. Propagate the delegation chain in token metadata

Every token carries `delegated_from` tracing back to the originating user. This makes audit logs reconstructable and enables per-user revocation: if User A's credentials are compromised, revoke all tokens with `delegated_from == User A` across every agent in the delegation tree.

```python
    def propagate_delegation(self, token: dict, delegator: str) -> dict:
        """Extend the delegation chain — append the delegator to the trace list."""
        chain = token.get("delegation_chain", [])
        chain.append(delegator)
        token["delegation_chain"] = chain
        return token
```

### 3. Enforce capability inheritance with ceiling

A sub-agent should never have more capability than its delegator. Check this at delegation time:

```python
    def delegate_capabilities(self, delegator_caps: set[str],
                               requested_caps: set[str]) -> set[str]:
        """Ceiling: sub-agent capabilities cannot exceed delegator's scope."""
        granted = requested_caps & delegator_caps  # Intersection = ceiling
        if len(granted) < len(requested_caps):
            # Log the capability gap — agents may need to know what was denied
            pass
        return granted
```

### 4. Revoke by task-ID, not by token-ID

The revocation surface for incident response:

```python
    def revoke_task_credentials(self, task_id: str) -> int:
        """Revoke all credentials issued for a given task. Returns count revoked."""
        revoked = self.authz_server.revoke_by_jti_prefix(f"{task_id}-")
        return revoked
```

### 5. Use mutual TLS (mTLS) between agents

When your agent talks to a sub-agent over A2A, authenticate both sides with short-lived X.509 certificates exchanged via a lightweight CA. This prevents a rogue agent from impersonating a legitimate sub-agent to harvest delegated credentials.

## Receipt

> Verified 2026-07-19 — Pattern confirmed against: (1) Zenodo preprint "Ephemeral Agent Credentialing" (Artis, April 2026, DOI 10.5281/zenodo.19713391) — formalizes the exposure-window problem and proposes JWT-scoped task tokens as the mitigation; (2) CSA blog "AI Agent Identity Is Solved Backwards" (May 2026) — documents the hash-chained audit logging and <30s revocation propagation requirement; (3) Tian Pan "Agent Identity and Delegated Authorization" (April 2026) — describes the OAuth OBO model mismatch in agentic contexts and the principal hierarchy problem. CVE-2025-68664 ("LangGrin") referenced as the real-world incident validating the exposure window risk.

## See also

- [S-217 · Agent Capability Authorization](s217-agent-capability-authorization.md) — permission model for agent-user-tool combinations; this entry adds the OAuth delegation layer
- [S-1075 · The Ephemeral Delegation Stack](s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — sub-agent credential sharing problem; this entry is the OAuth architecture for solving it
- [S-1256 · The Scope Attenuation Stack](s1256-the-scope-attenuation-stack-when-your-agent-escalates-its-own-permissions-and-nobody-knew-it-could.md) — agent permission escalation; delegation chain auth is the upstream control
- [S-1113 · The Five-Layer Audit Trail Stack](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — audit logging for agent actions; delegation_chain metadata is layer 3
