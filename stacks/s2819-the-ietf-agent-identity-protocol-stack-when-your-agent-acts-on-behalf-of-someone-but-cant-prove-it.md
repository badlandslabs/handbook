# S-2819 · The IETF Agent Identity Protocol Stack — When Your Agent Acts on Behalf of Someone But Can't Prove It

When your agent calls an MCP tool, delegates to a sub-agent via A2A, and accesses production data — and your compliance framework asks: *who authorized that, on whose behalf, with what scope, and can you revoke it?* You have logs. You have traces. You have no identity.

The IETF Agent Identity Protocol (AIP) is the answer moving through standards track as of 2026. Two competing drafts — `draft-singla-agent-identity-protocol` (Singla, IETF, May 2026) and `draft-aip-agent-identity-protocol` (Cao & Arango Gutierrez, NVIDIA, March 2026) — define decentralized identity, attenuated capability delegation, and cryptographic delegation chains for autonomous AI agents. arXiv:2603.24775 (Prakash, ISB, March 2026) introduces Invocation-Bound Capability Tokens (IBCTs) as AIP's execution primitive: compact tokens that bind every tool invocation to a verifiable authorization chain, verifiable in 0.049 ms on Rust, adding +0.22 ms to real-world MCP calls and +2.35 ms to multi-agent workflows (0.086% of total latency).

## Forces

- **The auth gap is structural, not accidental.** A scan of ~2,000 MCP servers found all lacked authentication. A2A has no authorization model — every protective mechanism is `SHOULD`/`MAY`, no `MUST`. Agents calling tools inherit the calling user's credentials with full scope. This isn't an oversight; it's the default state of the agentic web.
- **Existing identity systems assume human principals.** IAM was built for employees with managers, departure dates, and role assignments. Agents have none of these. SPIFFE/SPIRE covers workload identity for services but not autonomous decision-making agents that spawn sub-agents, delegate authority, and act across organizational boundaries.
- **The revocation problem breaks every other security control.** If you can't revoke an agent's access in real time, every other security investment is theater. Static OAuth tokens, bearer credentials, and API keys all fail on revocation because they were designed for long-lived service accounts, not ephemeral agent sessions.
- **Two IETF drafts exist but nobody knows the operational difference.** The Singla draft (W3C DIDs + capability-based auth + cryptographic delegation chains) and the Cao draft (policy enforcement proxy + MCP integration) take different architectural paths to the same goal. Choosing the wrong one for your stack means rebuilding in 12 months.

## The move

### Layer 1 — Register agent identity at startup

Agents get a `did:aip` identifier at instantiation — a W3C Decentralized Identifier scoped to the agent's instance, not its class. This survives credential rotation and distinguishes instances with different permission levels.

```python
# AIP agent registration (Singla draft pattern)
from aip import AgentIdentity, AgentCredential

identity = AgentIdentity.register(
    principal=user_principal_id,   # the human this agent acts on behalf of
    agent_instance_id="claims-agent-v3.1-us-east",
    capability_scope=["read:claims", "write:status", "escalate:review"],
    ttl_seconds=3600,
    issuer=org_aip_authority
)
# Returns a Principal Token: the agent's cryptographic identity proof
```

### Layer 2 — Attach Invocation-Bound Capability Tokens to every action

Every tool call carries an IBCT — a compact (356 bytes), append-only token chain that proves who authorized the call and what scope it carries. Each delegation hop attenuates (narrows) the scope; the chain is never expanded.

```
IBCT structure (per arXiv:2603.24775):
  [Principal Token] → [Invocation 1: read:claims] → [Invocation 2: escalate:review]

Each block contains:
  - Delegator DID
  - Capability scope (attenuated)
  - Nonce + timestamp
  - Signature
```

Verification cost: **0.049 ms** (Rust), **0.189 ms** (Python). In practice, +0.22 ms added to every MCP tool call — invisible at human timescales.

### Layer 3 — Enforce at the MCP policy proxy

The Cao draft (NVIDIA) defines a policy enforcement proxy that sits between the agent and its MCP servers. Every tool call is intercepted, the IBCT is verified, and policy rules are applied before the call proceeds.

```
Agent → [AIP Proxy] → [Policy Engine] → [DLP Scan] → [Rate Limit] → MCP Server
              ↓              ↓
         Verify IBCT    Human-in-the-Loop
         Check          Approval (for
         Revocation     high-sensitivity
         List           actions)
```

The proxy checks the revocation list on **every call**, not at credential issuance. If an agent is revoked, the next tool call fails — no hours-long revocation window.

### Layer 4 — Handle A2A cross-boundary delegation

A2A agents that delegate tasks to each other exchange IBCTs as part of the task handoff. The receiving agent's proxy verifies the caller's IBCT chain before accepting the task, enforcing that the delegation was within the original scope.

This closes the authorization island gap (S-1188): A2A agents no longer inherit ambient trust. Every cross-agent delegation requires a verifiable IBCT with attenuated scope.

### The architectural choice: DID-based vs. proxy-based

| Approach | Draft | Best for | Tradeoff |
|----------|-------|----------|----------|
| **Decentralized (DID + IBCT)** | Singla | Multi-org, cross-platform, no central PKI | Requires DID infrastructure; more complex to bootstrap |
| **Policy Proxy (MCP interception)** | Cao/NVIDIA | Single-org MCP deployments | Centralized policy point; simpler migration path |

Most enterprise deployments in 2026 are converging on a hybrid: DID-based identity for agent principals, policy proxy enforcement for MCP tool calls.

## Receipt

> Verified 2026-08-18 — Research sourced from:
> - `draft-singla-agent-identity-protocol-02` (IETF, May 2026, expires Nov 2026)
> - `draft-aip-agent-identity-protocol-00` (Cao & Arango Gutierrez, IETF, March 2026, expires Sep 2026)
> - arXiv:2603.24775 (Prakash, ISB, March 2026) — IBCT benchmarks
> - `openagentidentityprotocol/agentidentityprotocol` (GitHub, 36 stars, Apache-2.0, 87 commits)
> - `openagentidentityprotocol/aip-python` (Python proxy implementation)
> Benchmarks are from the arXiv paper's controlled evaluation; not independently reproduced here.

## See also

- [S-1134 · The Invocation-Bound Capability Token Stack](stacks/s1134-the-invocation-bound-capability-token-stack-when-your-agent-chains-delegations-and-nobody-can-prove-who-authorized-what.md) — the IBCT conceptual design that AIP implements as a protocol
- [S-1075 · The Ephemeral Delegation Stack](stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — the credential-handoff problem AIP prevents
- [S-1188 · The A2A Authorization Island](stacks/s1188-the-a2a-authorization-island-when-every-agent-is-its-own-security-perimeter.md) — the A2A gap AIP closes with IBCT handoffs
- [S-1256 · The Scope Attenuation Stack](stacks/s1256-the-scope-attenuation-stack-when-your-agent-escalates-its-own-permissions-and-nobody-knew-it-could.md) — the narrowing-delegation invariant that IBCT enforces at every hop
