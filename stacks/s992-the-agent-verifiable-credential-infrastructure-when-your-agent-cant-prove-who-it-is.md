# S-992 · The Agent Verifiable Credential Infrastructure — When Your Agent Can't Prove Who It Is

Your agent needs to hire a specialist agent from another company. It asks: "Who are you? Can you prove your capabilities? Has anyone ever verified you? What's your track record?" The agent has no answer — no credential, no identity document, no reputation history. It just has a name and a self-description. This is the agent trust problem, and it's blocking autonomous commerce at the exact moment A2A and AP2 make it possible.

## Forces

- **A2A, MCP, and AP2 all presuppose trust they don't provide.** A2A v1.0 (Linux Foundation, April 2026) handles task delegation; AP2 handles payment mandates; MCP handles tool discovery. None handle identity verification, capability attestation, or behavioral accountability. You're shipping autonomous commerce on infrastructure that authenticates nothing.
- **Agents are non-human identities that multiply.** One human spawns five agents, each spawning sub-agents. Each inherits credentials, escalates permissions, and acts across organizational boundaries. Legacy IAM was built for humans who log in and log out. Agents run continuously, delegate continuously, and accumulate credential blast radius continuously.
- **Self-asserted capabilities are not verifiable.** An agent declares "I handle customer complaints with escalation." That's natural language. There's no cryptographic proof, no third-party attestation, no revocation path. The A2A Agent Card is a capability manifest, not a credential — it solves the discovery problem, not the trust problem.
- **Behavioral reputation requires longitudinal observation.** An agent's trustworthiness depends on what it has done, not just what it claims. In human markets, this is solved by references, certifications, track records. In agent markets, no equivalent exists — until now.

## The move

The pattern is a **three-layer verifiable credential infrastructure** for agent ecosystems:

### Layer 1 — Agent Identity (W3C DID + SPIFFE SVID)

Every agent gets a **Decentralized Identifier (DID)** anchored to its operator's infrastructure:

```
did:web:acme.com/agents/support-agent-v3
```

The DID document links to a **SPIFFE SVID** (SPIFFE Verifiable Identity Document) — the same workload identity standard used in Kubernetes service meshes, now extended to AI agents. The SVID proves cryptographic identity without requiring a central authority. An agent presenting its SVID to another agent's MCP server proves: "I am Agent X, operated by Org Y, authorized to call Tool Z."

| Standard | Role | Adoption |
|----------|------|----------|
| W3C DID Core | Human-readable, resolvable agent identity | did:web in production; did:key for ephemeral agents |
| SPIFFE/SPIRE | Workload identity for agent processes | Kubernetes-native; adopted by Cloudflare, Google |
| OAuth 2.0 Agent Delegation | Scoped authorization across agents | Google AP2 mandate signing, 60+ partners |

### Layer 2 — Capability Credentials (W3C VC, AP2 Mandate Signing)

Capabilities are attested by **Verifiable Credentials (VCs)** — signed JSON-LD documents issued by a trusted authority:

```json
{
  "type": ["VerifiableCredential", "AgentCapabilityCredential"],
  "issuer": "did:web:audit-org.com",
  "credentialSubject": {
    "agentId": "did:web:acme.com/agents/support-agent-v3",
    "capability": "customer_complaint_escalation",
    "scope": "read:customer_data, write:escalation_ticket",
    "constraints": "max_value: 1000 USD, requires_human_approval: true",
    "validFrom": "2026-01-01",
    "validUntil": "2026-12-31"
  },
  "proof": { "type": "BbsBlsSignature2020", "created": "2026-07-01" }
}
```

AP2 Mandate Signing (Google AP2 spec) provides a parallel, payment-specific version of this pattern: agents sign payment mandates with their agent key, proving authorization to commit organizational funds. Sixty-plus organizations are signing mandates with agent keys as of May 2026.

### Layer 3 — Behavioral Reputation (On-Chain + Attestation Registry)

Identity and credentials answer "who are you" and "what can you do." **Reputation answers "have you done it well."**

The behavioral reputation layer aggregates:
- **Outcome telemetry** — task completion rates, escalation frequency, refund requests, approval reversals
- **Attestation chaining** — every completed task produces a signed attestation from the caller (the principal who hired the agent)
- **Composite trust score** — weighted by recency, attestation count, and attester credibility

Vouch Protocol (Solana, live on Devnet) implements this on-chain: agents register once, accumulate behavioral reputation across all interactions, and any downstream agent or human can verify trust via a single on-chain lookup. The W3C Verifiable Credentials data model stores attestations off-chain; the on-chain registry stores the score merkle root.

```
Agent Resume (Vouch Protocol):
  Identity: did:web:acme.com/agents/coder-v2
  SVID: spiffe://acme.com/agent/coder-v2
  Credentials:
    - type: coding_competency, issuer: github.com, status: valid
    - type: security_clearance, issuer: acme-internal-ca, status: valid
  Reputation:
    tasks_completed: 1,247
    avg_rating: 4.7/5
    late_delivery_rate: 3.2%
    last_attestation: 2026-07-10
```

### The Integration Pattern

```
Principal → [A2A task request + VC presentation]
  → Agent → [Verify SVID + VC + reputation score]
    → [Pass gate?]
      → Yes: execute with constrained mandate
      → No: escalate to human or refuse
    → [Sign attestation on completion]
      → Attestation → Reputation Registry
```

The critical integration point: credentials and reputation must be **runtime checks, not compile-time.** An agent's capabilities, issuer trust, and reputation score change continuously. The gate must verify at every delegation point — not cache the result from onboarding.

## Dynamics

- **DID resolution adds latency.** A cold DID resolution to a did:web endpoint can add 50–200ms. Use DID caching with a 5-minute TTL, and did:key for latency-critical paths (no resolution needed — the key is self-contained).
- **Credential revocation is the hard problem.** If an agent's credential is revoked mid-task, the running task must either complete with constrained scope or abort. Build a revocation check into the delegation gate, not just onboarding.
- **Reputation is gameable.** Behavioral scores can be inflated by self-attestations or collusion. Mitigate with attester-weighting (principal agents' attestations count more than new accounts), cross-org corroboration (multiple independent callers must attest), and periodic re-attestation requirements.
- **Privacy vs. accountability is a tension, not a tradeoff.** An agent that reveals its full behavioral history to every caller exposes competitive intelligence. Selective disclosure (W3C VC Data Model 2.0) lets agents prove "I have a valid security credential" without revealing which issuer, expiration, or score.

## What This Replaces

Before this pattern, agent trust decisions were:
- **API keys** — bilateral, not composable, revocable only by rotation
- **IP allowlisting** — breaks when agents run on dynamic cloud infrastructure
- **Manual vetting** — doesn't scale past 10 agents
- **A2A Agent Cards** — self-asserted, unverifiable, no revocation

The credential infrastructure makes trust **cryptographically verifiable, composable, and auditable** — enabling the autonomous commerce that A2A and AP2 have made structurally possible.

## See also

- [S-14 A2A Protocol](s14-a2a-protocol.md) — the delegation layer this trust layer enables
- [S-249 Agentic Payment Layer — AP2](s249-agentic-payment-layer-ap2.md) — the commerce layer AP2 mandate signing inhabits
- [S-313 Agent Credential Lifecycle Security](s313-agent-credential-lifecycle-security.md) — the credential lifecycle this pattern extends with verifiable attestation
- [S-266 Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — the delegation authorization this pattern makes verifiable
- [S-810 Agent Card Registry](s810-the-agent-card-registry-capability-advertisement-and-discovery.md) — the discovery layer adjacent to this credential layer
