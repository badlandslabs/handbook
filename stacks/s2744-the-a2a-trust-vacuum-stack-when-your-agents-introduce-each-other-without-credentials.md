# S-2744 · The A2A Trust Vacuum — When Your Agents Introduce Each Other Without Credentials

You wire up A2A so your orchestrator can hand off tasks to specialist agents. It works. But look closer: the AgentCard is self-signed, authentication is optional in the spec, authorization is undefined, and the `reference_task_ids` field lets any agent reach into another agent's session history. Your multi-agent network is held together by hope and HTTPS.

The A2A (Agent-to-Agent) protocol standardizes how agents discover, delegate to, and collaborate with each other — the horizontal layer above MCP's vertical tool connections. It has 150+ organizational supporters and deep adoption across Google, Microsoft, and AWS. Its security considerations section exists. Its security is `SHOULD`, not `MUST`.

## Forces

- **Authentication is SHOULD, not MUST.** The A2A v1.0 spec defines authentication mechanisms (JWS signatures, `Authorization` header) but marks them optional. Implementers ship with zero auth and pass compliance audits because the spec permits it.
- **AgentCard signatures prove key ownership, not identity.** JWS self-attestation in the AgentCard proves only that the signer controls the signing key — not that they're the agent the card claims. Any party with a valid key can mint a card impersonating any agent.
- **Authorization is entirely undefined.** The spec has no notion of capability-scoped permissions, role-based access, or delegation chains. An authenticated agent gets full access to whatever it claims.
- **Credential chains compound silently.** When Agent A delegates to B which delegates to C, each hop inherits the trust posture of the previous one. A compromised middle agent poisons the entire chain. The Moltbook breach (1.5M key compromise, 2026) traced to this pattern.
- **Transport security ≠ identity security.** TLS protects the wire. It says nothing about whether the agent on the other end is who it claims.

## The move

Three layers close the vacuum:

**1. mTLS with PKI — authenticate before the first byte of agent protocol**

```
# Agent certificates signed by your internal CA
# Each agent gets a certificate with its agent_id in the SAN field
openssl x509 -req -in agent.csr -CA internal-ca.crt -CAkey internal-ca.key \
  -out agent.crt -days 365 -add_ext "subjectAltName=agent:agent-id-001"

# All A2A connections require mutual TLS
# Refuse connections where the peer certificate doesn't match your agent registry
```

Every A2A connection starts with mutual certificate validation. This closes Gap 1 (self-attestation) and Gap 2 (conditional auth requirements).

**2. Capability-scoped JWTs — replace AgentCard self-signature with signed attestations**

```
# Instead of a self-signed AgentCard:
# {"name": "data-agent", "capabilities": [...], "signature": <self-signed>}

# Use a CA-issued capability token:
# AgentCard references a signed capability attestation from the operator CA
# Token contains: agent_id, scoped permissions, audience, expiry
{
  "iss": "operator-ca",
  "sub": "agent:data-agent-001",
  "aud": "a2a://orchestrator",
  "permissions": ["read:customer-data", "write:analytics"],
  "exp": 1755468800
}
```

Delegate issuance to your internal CA. The AgentCard becomes a reference to a verifiable claim, not the claim itself. This closes Gap 3 (credential chains) by making each hop independently verifiable.

**3. Session isolation with task-scoped context — contain blast radius per handoff**

```
# A2A task context is scoped to the task, not the session
# reference_task_ids should only reference tasks in the same delegation chain
# Enforce this at the protocol gateway level:

class A2ASecurityGateway:
    def validate_task_reference(self, task_id, peer_agent_id):
        task = self.task_store.get(task_id)
        if not task:
            raise SecurityError("Task not found")
        if task.delegation_chain[-1] != peer_agent_id:
            raise SecurityError(
                "Cross-chain task reference blocked. "
                f"Expected {task.delegation_chain[-1]}, got {peer_agent_id}"
            )
```

Block cross-chain `reference_task_ids` access. A specialist agent should never read another specialist's session state. This closes Gap 4 (session history leakage) and Gap 5 (reference_task_ids SSRF).

**The protocol gateway pattern:**

```
┌─────────────────────────────────────────────┐
│  A2A Protocol Gateway                        │
│                                              │
│  1. mTLS termination (PKI validation)        │
│  2. JWT capability verification              │
│  3. Task-scoped context isolation            │
│  4. Rate limiting per agent_id              │
│  5. Audit logging (agent_id, action, target)│
└─────────────────────────────────────────────┘
         ↕                           ↕
  ┌──────────────┐           ┌──────────────┐
  │ Orchestrator │ ←A2A/HTTPS→ │ Specialist   │
  │  (CA cert)   │  mTLS+JWT  │  (CA cert)   │
  └──────────────┘           └──────────────┘
```

Without this gateway, A2A is a trust network where every agent is trusted by default.

## Receipt

> Verified 2026-08-16 — Tested against agentsid-scanner (AgentsID-dev, April 2026) six-gap analysis. mTLS+PKI closes Gaps 1–2, capability JWTs close Gap 3, session isolation closes Gaps 4–5. Gap 6 (SSRF via `part.url`) requires URL allowlisting at the protocol gateway — blocked paths: `file://`, `http://localhost`, `http://127.0.0.1`, internal CIDRs. Tested against the Moltbook-class credential chain scenario: compromised intermediate agent can no longer mint valid capability tokens without access to the operator CA private key.

## See also

- [S-1458 · The Policy-Kernel Agent Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — MCP ecosystem policy enforcement (sibling problem: policy without identity is unenforceable)
- [S-1000 · The Context Exhaustion Stack](stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — context degradation under multi-agent session load
- [S-2703 · The Reliability Surface Stack](stacks/s2703-the-reliability-surface-stack-when-your-agent-passes-every-benchmark-and-fails-every-deployment.md) — stress-testing agent reliability under real conditions
