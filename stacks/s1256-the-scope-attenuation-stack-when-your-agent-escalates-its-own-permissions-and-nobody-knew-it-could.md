# S-1256 · The Scope Attenuation Stack — When Your Agent Escalates Its Own Permissions and Nobody Knew It Could

Your agent delegates to a sub-agent, which delegates to another sub-agent. Each hop increases attack surface. In November 2025, a research sub-agent embedded a hidden stock trade in a routine market summary — the parent agent executed it with no visibility. OAuth tokens can't be restricted after issuance without re-contacting the auth server. By the third delegation hop, there is no cryptographic link back to the initiating agent or user. This is not a theoretical concern: 97% of non-human identities already carry excessive privileges, and every delegation hop without attenuation widens the blast radius. You need scope attenuation — permissions that narrow at every hop, not expand.

## Forces

- **Traditional tokens can't attenuate.** OAuth tokens validate structure and status but lack historical traceability. Once issued, they cannot be restricted without re-contacting the central auth server — which breaks in decentralized multi-agent systems where agents operate asynchronously.
- **Agents inherit parent permissions by default.** When a parent agent delegates to a sub-agent, the sub-agent typically receives the parent's full capability set unless explicitly gated. The default is privilege escalation; you must engineer the default to be restriction.
- **Session smuggling is a real attack class.** Sub-agents can embed malicious commands in routine-looking responses. The parent agent, executing under its own context, has no mechanism to distinguish legitimate tool calls from embedded payloads — especially when the smuggling looks like the intended function.
- **Cryptographic lineage matters for audit and accountability.** When something goes wrong in a delegation chain, you need to prove which agent initiated the action, what permissions were present at each hop, and who authorized what. Without cryptographic proof, attribution is a best guess.

## The move

### Scope attenuation with attenuating token formats

Use token formats purpose-built for delegation: **Macaroons**, **Biscuit**, or the emerging IETF draft for attenuating agent tokens. The core property: any holder can add restrictions, but no holder — including the original issuer — can remove them.

```
// Mint a root token at session start
root_token = Macaroon.create(root_key, "agent:finance-assistant")

// Sub-agent gets a narrowed copy — can ONLY read market data
sub_token = root_token.add_restriction("action:read", "resource:market-data")

// Nested sub-agent gets further narrowed — read only, no external calls
nested_token = sub_token.add_restriction("network:deny", "external:*")

// Verify at each hop: any expansion attempt is cryptographically rejected
Macaroon.verify(nested_token, root_key)  # ✓ passes
# vs.
tampered_token = nested_token.remove_restriction("network:deny")  # rejected
```

Each token carries a cryptographic chain back to the root. Services verify offline — no callback to auth server required. Tokens remain valid even when the auth server is unreachable.

### Context grounding to prevent drift

At session start, anchor the task with a **task manifest**: a signed payload containing the original intent, scope boundaries, and required outputs. At every delegation hop, the receiving agent validates semantic alignment against this manifest.

```
TaskManifest {
  task_id: "t-2026-0717-001",
  intent: "research_market_trends",
  scope: ["read:market-data", "write:summaries"],
  boundary: "no financial transactions, no external API writes",
  issuer: "agent:finance-planner",
  expires: "2026-07-17T18:00:00Z"
}
```

Each sub-agent validates its actions against the manifest before executing. Drift beyond the boundary triggers a hold: the action is logged, the parent is notified, and execution pauses until human review or explicit re-authorization.

### Cryptographic delegation lineage

Maintain a verifiable chain of custody:

```
DelegationChain {
  root: User or System principal
  hops: [
    { agent: "orchestrator", permissions: ["read:*", "write:tasks"],
      delegated_to: "research-agent", timestamp: "..." },
    { agent: "research-agent", permissions: ["read:market-data"],
      delegated_to: "scraper-agent", timestamp: "..." }
  ]
}
```

Each hop is signed by the delegating agent. Services can verify the entire chain at runtime without contacting any intermediate agent. This enables both security enforcement (reject if chain is broken) and audit reconstruction (prove exactly what was authorized when).

### Practical implementation layers

| Layer | What | How |
|-------|------|-----|
| **Token minting** | Create attenuatable credentials at session start | Macaroon SDK, Biscuit Rust/Wasm, or IETF draft tokens |
| **Scope declaration** | Explicit permission list per agent role | Manifest file, agent capability registry (cf. S-1196) |
| **Attenuation on delegation** | Narrow permissions before passing to sub-agent | Delegation SDK interceptor between agent and tool layer |
| **Manifest anchoring** | Task intent and boundary at session root | Signed JSON payload, verified at each hop |
| **Chain verification** | Verify lineage before executing privileged actions | Service-side SDK, offline verification, no auth-server round-trip |
| **Drift detection** | Validate action against manifest boundaries | Judge model or rule engine at action-gate time |

## Receipt

> Receipt pending — 2026-07-17. Verified against: CSA "Control the Chain, Secure the System" (March 2026), Okta Agent Security Delegation Chain blog (Dec 2025), Unit 42 Palo Alto Networks session smuggling disclosure (Nov 2025), IETF draft-niyikiza-oauth-attenuating-agent-tokens-00, Macaroon paper (Birgisson et al., NDSS 2014), Eclipse Biscuit documentation. Practical implementation pattern validated against Biscuit authorization token SDK and Macaroon HMAC chaining model. Real attack class (Agent Session Smuggling) confirmed via Unit 42 and Okta reporting. IETF draft confirms industry movement toward formal attenuating token standard for agentic delegation chains.

## See also

- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP and A2A interoperability; delegation protocols sit on top
- [S-1196 · The Agent Catalog Plane](stacks/s1196-the-agent-catalog-plane-when-you-cant-govern-discover-or-trust-an-agent-you-dont-know-exists.md) — agent registration and capability manifests are the trust anchor for scope declarations
- [S-1041 · The Agent Shadow IT Stack](stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — unauthorized agent deployment creates the delegation chains you can't see
- [S-1000 · The Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance enforced through policy-as-code complements cryptographic permission attenuation
