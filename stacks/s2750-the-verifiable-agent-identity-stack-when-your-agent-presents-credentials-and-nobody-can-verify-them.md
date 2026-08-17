# S-2750 · The Verifiable Agent Identity Stack — When Your Agent Presents Credentials and Nobody Can Verify Them

Your agent calls a partner's specialist agent via A2A. It passes an OAuth token. The receiving agent has no way to verify that token's chain of delegation — whether it originated from a human principal, what scopes it carries, whether it has been tampered with mid-flight. Your agent signs an AgentCard. The partner has no mechanism to verify the signature. MCP has no authentication layer at all. The agent ecosystem is held together by trust-but-verify and a prayer.

## Forces

- **MCP has no authentication.** The STDIO transport launches local processes with full host access. The HTTP+SSE transport uses bearer tokens with no standard. Neither the tool-calling agent nor the server knows who — or what — is on the other end.
- **A2A signatures cover the AgentCard, not the delegation.** JWS signatures authenticate the agent card itself but not the chain of principals behind the agent. When a user's agent delegates to a sub-agent, the receiving agent cannot answer: "who authorized this, with what scope, expiring when?"
- **Credential chains break at protocol boundaries.** An agent authenticated via OAuth to your service can spawn 50 sub-agents via A2A. Each sub-agent inherits the same token with the same broad scopes. There is no concept of scoped, narrowing delegation in current stacks.
- **No standard for agent identity.** The W3C has Verifiable Credentials. The IETF has WebAuthn. Neither defines a format or verification mechanism for AI agent identity. Two competing drafts now exist (IETF AIP and OpenA2A AIP), creating a new interoperability challenge.

## The move

**Adopt the Agent Identity Protocol (AIP) as your identity layer, and treat agent credentials as first-class security principals.**

### The core primitives

**ATX (Agent Trust eXtension)** is the credential format proposed by the IETF AIP draft (`draft-prakash-aip-00`) and implemented in Python/Rust (`agent-identity-protocol` on PyPI). It carries:
- Agent's public key (Ed25519 or RSA-PSS)
- Human principal binding (who owns this agent)
- Capability grant (what the agent is allowed to do)
- Delegation chain (who authorized what)
- Expiry timestamp

```
# AIP ATX credential (simplified)
{
  "iss": "agent:alice-planner-v3",
  "sub": "agent:alice-planner-v3",
  "human_principal": "did:web:acme.com/users/alice",
  "capabilities": ["read:orders", "write:tasks"],
  "delegation_chain": [
    {"principal": "did:web:acme.com/users/alice", "role": "owner"},
    {"principal": "agent:alice-planner-v3", "role": "delegate"}
  ],
  "exp": 1755388800,
  "signature": "Ed25519(agent_private_key, payload)"
}
```

**Biscuit tokens** are an alternative: append-only, capability-scoped delegation tokens that narrow permissions at each hop. A Biscuit issued by your auth service can be passed to a sub-agent with only the subset of permissions needed for that task.

### Implementation pattern

```python
from agent_identity_protocol import AgentCredential, verify_credential
from agent_identity_protocol.aip import ATXCredential

def make_agent_credential(
    agent_id: str,
    human_principal: str,
    capabilities: list[str],
    delegator_key: bytes,
) -> ATXCredential:
    """Issue an ATX credential for an agent, bound to its human principal."""
    credential = ATXCredential.issue(
        agent_id=agent_id,
        human_principal=human_principal,
        capabilities=capabilities,
        issuer_private_key=delegator_key,
        ttl_seconds=3600,
    )
    return credential


def verify_incoming_agent(request_credential: str, allowed_capabilities: list[str]) -> bool:
    """Verify an ATX credential and check that all required capabilities are present."""
    try:
        cred = verify_credential(request_credential)
    except Exception as e:
        # Signature invalid, expired, or tampered
        raise PermissionError(f"Agent credential verification failed: {e}")

    # Capability intersection: does the agent have what we need?
    granted = set(cred.capabilities)
    required = set(allowed_capabilities)
    if not required.issubset(granted):
        raise PermissionError(
            f"Agent {cred.agent_id} lacks required capabilities: "
            f"{required - granted}"
        )

    # Verify human principal binding (non-repudiation)
    print(f"Authorized by human: {cred.human_principal} ({cred.agent_id})")
    return True


# In your MCP server or A2A handler:
def handle_agent_request(credential_b64: str, action: str):
    verify_incoming_agent(credential_b64, allowed_capabilities=["read:orders"])
    # proceed with action
```

### The dual-identity pattern

The IETF AIP draft formalizes dual-identity credentials: one identity for the **agent itself** (what it is), one for the **human principal** (who is responsible). This is the key insight that existing stacks miss — an agent needs its own cryptographic identity for delegation, but the human principal needs to remain accountable.

```
Dual identity at the wire:
  [Human] --delegates-with-scope--> [Agent ATX credential]
                                         |
                          [Agent calls partner agent]
                                         |
                          [Passes ATX with narrowed scopes]
                                         |
                          [Partner verifies: who + what + expiry]
```

### Trust scoring (OpenA2A AIP approach)

The OpenA2A AIP draft (July 2026, `draft-fane-opena2a-aip-00`) introduces a **multi-factor behavioral trust score** — a composite of independently verifiable signals:
1. Credential validity (cryptographic)
2. Behavioral history (has this agent been compliant?)
3. Principal attestation (has the human principal vouched for it?)
4. Capability scope (least privilege enforcement)

### What to verify, and when

| Protocol | What to verify | How |
|----------|---------------|-----|
| MCP STDIO | Nothing (local process) | Use process isolation, seccomp, AppArmor |
| MCP HTTP+SSE | Bearer token validity | Standard JWT verification |
| A2A | AgentCard signature + ATX credential | JWS + ATX chain verification |
| Cross-org A2A | ATX + human principal + scope | Full AIP verification |

## Receipt

> Verified 2026-08-16 — Sources: IETF `draft-prakash-aip-00` (GitHub: sunilp/aip, PyPI `agent-identity-protocol`, Apache-2.0, IETF Internet-Draft, under NIST NCCoE evaluation); IETF `draft-fane-opena2a-aip-00` (OpenA2A AIP, July 2026, Standards Track, expires Jan 2027). Both drafts are active — check IETF datatracker for current status before production use. No production deployments confirmed; both are early-stage standardization efforts.

## See also

- [S-2744 · The A2A Trust Vacuum](stacks/s2744-the-a2a-trust-vacuum-stack-when-your-agents-introduce-each-other-without-credentials.md) — covers the A2A authentication gap this entry extends
- [S-1075 · The Ephemeral Delegation Stack](stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — covers credential scoping for sub-agents
- [S-2746 · The MCP Observability Blindspot Stack](stacks/s2746-the-mcp-observability-blindspot-stack-when-your-monitoring-dashboard-is-lying-to-you.md) — covers MCP-layer visibility; identity verification is the complement
