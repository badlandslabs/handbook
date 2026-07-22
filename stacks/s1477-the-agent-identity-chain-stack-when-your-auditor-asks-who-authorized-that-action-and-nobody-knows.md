# S-1477 · The Agent Identity Chain Stack — When Your Auditor Asks "Who Authorized That?" and Nobody Knows

[When an agent acts on behalf of a user — spawning sub-agents, calling APIs, accessing data — but the authorization trail ends at a shared service account, leaving a compliance gap that HIPAA, DORA, and the EU AI Act all demand you close.]

## Forces

- **Agents delegate across boundaries without expanding the identity graph.** A human authorizes an orchestrator → the orchestrator spawns sub-agents → each calls tools with credentials scoped to the original user's session. At the terminal action, no one — not the API, not the audit log, not the auditor — can trace back to the originating human principal. The chain is broken.
- **Existing IAM was built for humans, not autonomous pipelines.** IAM assigns credentials to people with employment records, managers, and departure dates. Agents have none of these. ISACA calls this a "looming authorization crisis." Legacy frameworks rely on pre-established scopes too coarse-grained and too static for dynamic agent operations.
- **Regulatory requirements don't have exceptions for AI.** HIPAA §164.312(a)(2)(i) requires unique user identification for every process accessing ePHI. CMMC AU.2.042 demands that activities of processes acting on authorized users be traceable to those users. SEC Rule 204-2 requires advisory activity records to be attributable. A shared service account credential satisfies none of these.
- **The fan-out multiplies the gap.** One human identity becomes one orchestrator becomes N sub-agents becomes N×M tool calls. Static credentials don't carry delegation depth. A credential scoped to "read user data" has no mechanism to express: "read user data on behalf of alice@corp.com, delegated through orchestrator-42, for task-abc only."

## The Move

Treat agent identity as a first-class NHI (Non-Human Identity) with a three-layer model:

**Layer 1 — Lifecycle governance (program level)**
Define agent identity before deployment: who owns it, what data it can access, what actions it can take, and when it should be retired. This is the policy layer — separate from runtime enforcement and separate from the credential mechanics of authentication. Without program-level governance, runtime enforcement has no foundation.

```
Agent Identity Record:
  agent_id:       nhi://corp/prod/triage-v3
  owner:          platform-team@corp.com
  purpose:        customer support ticket routing
  data scope:     read: customers.tickets, write: tickets.status
  api scope:      read: CRM.accounts, write: CRM.notes
  delegation:     may spawn sub-agents? yes
                  sub-agent scope: inherits parent scope (strict subset)
  attestation:    reviewed quarterly
  sunset:         2026-12-31
  kill_switch:    immediate revocation via Entra ID
```

**Layer 2 — Delegation chain with scoped credentials (runtime level)**
When an agent delegates to a sub-agent or calls a downstream API, carry a delegation token that encodes the full provenance chain. The Human Delegation Provenance (HDP) protocol (IETF draft-helixar-hdp-agentic-delegation-00) provides a cryptographically signed, offline-verifiable chain:

```
HDP Token (simplified):
  principal:    alice@corp.com        # originating human
  chain:        [orchestrator-42, sub-agent-search, tool-webhook]
  scope:        read:CRM.accounts
  expires:      2026-07-22T18:00:00Z
  issued_at:    2026-07-22T17:00:00Z
  sig:          0xa8f3...e2d1        # signed by orchestrator key
```

Each hop appends to the chain and narrows the scope. Downstream services verify the signature and inspect the chain to confirm every delegation was authorized.

Microsoft's Copilot Studio pattern enforces this outside the agent using Entra ID RBAC — the authorization decision is made by the identity system, not the model. Delegated permissions keep execution within the requesting user's identity boundary. Application permissions are reserved for background automation only.

**Layer 3 — Audit trail with provenance queries (observability level)**
Instrument every agent action with the full delegation chain as structured metadata:

```
Trace span attributes:
  agent.principal:     alice@corp.com
  agent.delegation_chain: ["orchestrator-42", "sub-agent-rag"]
  agent.scope:         read:CRM.accounts
  agent.delegation_depth: 2
  action.timestamp:    2026-07-22T17:23:11Z
  action.resource:     CRM.accounts#1234
  action.result:       200 OK
```

This enables provenance queries: "show every action taken by any agent acting on behalf of alice@corp.com in Q2." Without chain metadata at the span level, this query returns nothing.

## Minimal Working Example

```python
from hdp import DelegationToken, sign_chain, verify_scope

# Human principal authorizes the orchestrator
token = DelegationToken(
    principal="alice@corp.com",
    scope={"read": ["CRM.accounts"]},
    chain=[],
    ttl_seconds=3600
)
orch_token = sign_chain(token, issuer_key=orchestrator_key)

# Orchestrator delegates to sub-agent (scope narrows)
sub_token = orch_token.delegate(
    sub_agent_id="sub-agent-rag",
    scope={"read": ["CRM.accounts"]},  # same scope
    ttl_seconds=600
)
sub_signed = sign_chain(sub_token, issuer_key=orchestrator_key)

# Downstream API verifies the full chain
def handle_crm_request(token_bytes, resource):
    token = DelegationToken.parse(token_bytes)
    verify_scope(token, required={"read": [resource]})
    # audit: log principal + full chain
    audit_log.info(f"principal={token.principal} chain={token.chain} action=read:{resource}")
```

## Receipt

> Verified 2026-07-22 — Sources: arXiv:2604.04522 (HDP protocol specification); Microsoft Tech Community authorization guide (Entra ID RBAC + delegated permissions); NHI Governance framework (lifecycle/scope/audit surfaces); ISACA authorization crisis analysis; Strata NHI survey (50:1 NHI ratio, 80% of IT leaders report agents acting outside expected behavior). Code reflects HDP draft specification and Microsoft RBAC integration pattern. No live deployment tested.

## See also

- [S-1075 · The Ephemeral Delegation Stack](s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credential scoping and the risk of handing credentials to untrusted agents
- [S-1041 · The Agent Shadow IT Stack](s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — discovering and governing agents you didn't know existed
- [S-1474 · The MCP Bearer Token Gap](s1474-the-mcp-bearer-token-gap-when-authorization-is-true-but-not-verified.md) — the gap between permission granted and permission verified at the transport layer
