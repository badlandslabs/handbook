# S-972 · The Agent Trust Negotiation Stack — When Your Agent Has to Prove Itself to Another Agent

[One agent calls another over A2A. The call succeeds. The receiving agent has no idea if the caller was authorized, if the delegation chain is valid, or if the caller is who it claims to be. A2A shipped task delegation without a trust negotiation layer. This entry covers the stack that closes that gap — the ATN protocol, its four artifacts, and how maturity levels gate what an agent can request vs. present.]

## Forces

- **A2A shipped delegation without a trust model.** The Agent2Agent protocol (v1.0, April 2026, 150+ organizations) enables agents to discover and delegate to each other. It does not verify that delegation is authorized, that the calling agent's credentials are valid, or that the delegation chain hasn't been revoked mid-session. You're running a TLS handshake for identity but nothing equivalent for authorization.
- **Agents are non-deterministic counterparties.** TLS verifies server identity via certificates tied to DNS. Agents have no stable DNS identity, no PKI hierarchy, and no shared identity provider. Trust negotiation for agents must work without a central authority that both parties pre-trust — the way browsers pre-trust CAs.
- **The blast radius of a rogue agent is asymmetric.** A compromised laptop can send email. A compromised agent can modify billing settings, exfiltrate data, or authorize financial transactions (S-962) — and the receiving system has no way to know the action was unauthorized until it's too late. The receiving agent needs evidence before it acts, not forensic logs after.
- **Maturity levels determine what trust claims are believable.** An Intern-level agent claiming authority to approve refunds is not credible. A Principal-level agent claiming the same authority is. Trust negotiation must gate requests against the presenterer's verified maturity level — the way a TLS certificate's organizational unit constrains what domains it can assert.

## The Move

The Agent Trust Negotiation (ATN) protocol (IETF draft-somoza-atn-agent-trust-negotiation-00, May 2026) sits above agent discovery and answers what discovery alone cannot: *what is this agent permitted to do, under whose authority, with what provenance, and how do we reach a verifiable agreement?*

ATN binds **four artifacts** to every agent identity established at discovery time:

### 1. Capability Manifest

The agent declares what it is willing to do, under what conditions, and with what constraints. Unlike an MCP tool schema (S-10), a Capability Manifest describes **authorization boundaries**, not interface signatures:

```json
{
  "agent_id": "svc:crm-agent:v3.2",
  "scope": ["read:customer-profile", "write:support-ticket"],
  "constraints": {
    "max_transaction_value_usd": 0,
    "requires_approval_for": ["refund", "account-close"],
    "data_residency": ["US", "EU"]
  },
  "presented_maturity": "senior",  // ATF Level 3
  "expires": "2026-07-12T00:00:00Z"
}
```

### 2. Delegation Chain

Every agent acts on behalf of a principal — a human user, another agent, or an organization. The Delegation Chain proves the chain of authorization back to the ultimate principal:

```
svc:crm-agent:v3.2
  ← delegated by → us:rental-support-org → via → human:alice@corp
  ← authorized by → org:acme-corp/roles/support-tier-2
  ← issued by → idp:corp-ad  at 2026-06-01T00:00:00Z
  ← revoked_at → null (valid)
```

Revocation paths propagate through the chain. If `corp-ad` revokes `support-tier-2`, the chain is broken for any agent that inherited that role. The receiving agent can check revocation at negotiation time without a centralized CRL lookup — via OCSP-style scoped queries to each delegation issuer.

### 3. Provenance Attestation

The agent presents cryptographic evidence of its build-time and runtime integrity:

```json
{
  "build_attestation": {
    "build_ref": "sha256:abc123...",
    "builder": "sigstore.dev/oidc/github-actions",
    "signer_identity": "org:acme-corp",
    "sbom_ref": "https://acme-corp.io/sboms/crm-agent/v3.2.json"
  },
  "runtime_attestation": {
    "hardware_root": "tee:aws-nitro/instance:i-0abc123",
    "measurement_ref": "sha256:def456...",
    "policy_eval": "pass",
    "evaluated_at": "2026-07-11T09:00:00Z"
  }
}
```

Build-time attestation (Sigstore-based) proves the binary hasn't been tampered with since CI. Runtime attestation (TEE-based) proves the agent is actually running on approved infrastructure — the equivalent of TPM remote attestation for software agents.

### 4. Session Receipt

When two agents reach an agreement, the negotiation produces a **Session Receipt**: a signed record of what was agreed, by whom, with what constraints. Unlike a TLS session ticket, a Session Receipt is an auditable artifact:

```json
{
  "receipt_id": "atn:receipt:7f3a9b2c",
  "caller": {
    "agent_id": "svc:crm-agent:v3.2",
    "presented_maturity": "senior",
    "presented_scope": ["read:customer-profile"],
    "presented_constraints": {"max_transaction_value_usd": 0}
  },
  "callee": {
    "agent_id": "svc:payment-agent:v1.4",
    "accepted_scope": ["read:customer-profile"],
    "granted_scope": ["read:customer-profile:limited"]
  },
  "negotiated_terms": {
    "scope": ["read:customer-profile:limited"],
    "delegation_chain_validated": true,
    "provenance_check": "pass",
    "maturity_gate": "passed"
  },
  "signature_caller": "base64:sig...",
  "signature_callee": "base64:sig...",
  "created_at": "2026-07-11T09:00:15Z"
}
```

Both agents sign the receipt. The callee keeps it for auditing. The caller keeps it as proof of authorized delegation — critical for downstream liability when the action has financial consequences (S-962).

### The Maturity Gate

ATN enforces that requests are **credible for the presenter's maturity level** (ATF/CSA, February 2026):

| Presenter Maturity | Can Request | Cannot Request |
|---|---|---|
| Intern (L1) | Read-only data access | Any write action |
| Junior (L2) | Read + recommend | Autonomous write |
| Senior (L3) | Write + act, notify after | Modify governance policies |
| Principal (L4) | Full autonomous within bounds | Break microsegmentation |

A Senior-level agent requesting `write:refund` with `max_value: 5000` passes the gate. The same request from an Intern agent fails — the receiving agent rejects it with `MaturityGateError: presenter_level_insufficient`.

### Negotiation Flow

```
Agent Alpha (caller)          Agent Beta (callee)
      |                              |
      |  1. Discovery (A2A DNS-AID)  |
      |------------------------------>|
      |                              |
      |  2. ATN Initiation           |
      |  { capability_manifest,      |
      |    delegation_chain,         |
      |    provenance_attestation }  |
      |------------------------------>|
      |                              | 3. Validate delegation chain
      |                              |    - Check each hop's issuer
      |                              |    - Verify revocation status
      |                              | 4. Verify provenance
      |                              |    - Validate build attestation
      |                              |    - Check runtime measurement
      |                              | 5. Apply maturity gate
      |                              |    - Map presented_maturity to ATF level
      |                              |    - Filter scope to allowed actions
      |                              |
      |  6. Scope Offer              |
      |<------------------------------|
      |  { granted_scope: [...],      |
      |    constraints: {...},        |
      |    session_receipt }         |
      |                              |
      |  7. Accept (sign receipt)    |
      |------------------------------>|
      |                              |
      |  8. Proceed with action      |
      |  (within granted_scope)       |
```

## Receipt

> Verified 2026-07-11 — IETF draft-somoza-atn-agent-trust-negotiation-00 (May 2026), CSA Agentic Trust Framework (Feb 2026, Cloud Security Alliance, Josh Woodruff), AWS Agentic AI Security Scoping Matrix (Nov 2025), GitHub: massivescale-ai/agentic-trust-framework (65 stars, 11 forks). No live implementation available for live test. Code examples are struct-accurate to the draft spec.

## See also

- [S-266 · Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — A2A delegation without ATN; the problem this entry solves
- [S-420 · Agent Identity Governance](s420-agent-identity-governance-the-AI-principal-paradigm.md) — AI principals as the authority ATN chains delegate from
- [S-968 · MCP Server Attestation](s968-the-mcp-server-attestation-stack-when-you-dont-know-if-your-server-is-who-it-claims.md) — Provenance attestation for MCP servers; complementary to ATN provenance for agent→agent calls
- [S-962 · Autonomous Commerce Stack](s962-the-autonomous-commerce-stack-when-your-agent-needs-to-pay-for-things.md) — Financial consequences of failed trust negotiation
