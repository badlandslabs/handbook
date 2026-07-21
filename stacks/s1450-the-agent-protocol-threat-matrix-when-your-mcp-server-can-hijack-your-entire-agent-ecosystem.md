# S-1450 · The Agent Protocol Threat Matrix — When Your MCP Server Can Hijack Your Entire Agent Ecosystem

You built a clean agent stack. MCP for tools, A2A for agent coordination, ANP for discovery. Each protocol has its own security model — or so you thought. Then you discover that a malicious MCP server can exfiltrate context from every agent that connects to it, that a compromised A2A peer can inject task directives into a trusted agent's planning layer, and that ANP's registry can be poisoned to redirect agent discovery to hostile endpoints. Four protocols, four lifecycle phases, four independent threat surfaces. You secured one. The others are open.

## Forces

- **Protocol adoption outpaces threat modeling by years.** MCP has 97M+ monthly SDK downloads, 5,800+ servers. A2A is in production at hundreds of enterprises. ANP is maturing rapidly. Each protocol was designed for a function, not for an adversarial ecosystem. Security analysis lags implementation by default.
- **No protocol is uniformly secure across its lifecycle.** The same protocol can be safe at creation, dangerous at operation, and vulnerable at update. A threat model that evaluates only the "happy path" operational phase misses the phases where compromise actually happens.
- **Each protocol serves a different attack surface.** MCP is about tool trust. A2A is about delegation trust. ANP is about discovery trust. Agora is about capability negotiation. Attacking a multi-agent system doesn't require breaking the model — it requires breaking the protocol layer that connects agents to each other or to tools.
- **The protocols are converging into a stack, but the threat model is siloed.** MCP, A2A, ANP, and Agora are complementary layers in a production agent architecture. Threat modeling them in isolation produces a false sense of security. The cross-protocol handoff is where agents are most vulnerable.

## The move

### Build the lifecycle-phase threat matrix

The foundational finding from comparative protocol security analysis (arxiv:2602.11327, 2026) is that each protocol's vulnerabilities concentrate in different lifecycle phases. Treat threat modeling as a two-axis matrix: protocol × lifecycle phase.

| Phase | MCP | A2A | ANP | Agora |
|-------|-----|-----|-----|-------|
| **Creation** | Malicious server registration, capability injection | Agent identity spoofing, role claim forgery | Registry poisoning, capability inflation | Negotiation replay, intent interception |
| **Operation** | Tool-call intercept, context exfiltration, ambient authority | Authorization island, delegation hijack, state inference | Discovery redirection, endpoint impersonation | Capability overgrant, intent manipulation |
| **Update** | Schema drift, manifest poisoning | Protocol version downgrade, capability regression | Registry staleness, capability revocation bypass | Negotiation state corruption |

### Enforce protocol-specific trust boundaries

Each protocol requires a distinct trust enforcement strategy:

- **MCP: Zero-trust tool registration.** Treat every MCP server as a potential adversary. Sign and verify server manifests (description-hash from S-889). Scope connections to minimum required tools. Never grant a server access to credentials it doesn't need for its declared function. The 43% command injection flaw rate in MCP servers is not a bug in your MCP client — it's a structural risk in the protocol's trust model.
- **A2A: Authorization at every handoff.** The A2A v1.0 spec has no authorization model — every protective mechanism is `MAY`/`SHOULD`. Wrap A2A with an explicit capability contract at every agent boundary: what is Agent A authorized to delegate to Agent B, what data can cross that boundary, and what is the revocation window if B is compromised. See S-1188 for the authorization island pattern.
- **ANP: Registry provenance and freshness.** Agent discovery via ANP assumes the registry reflects ground truth. Poison the registry and you redirect agents. Require registry entries to carry cryptographic provenance (who registered this agent, when, with what attested capabilities) and enforce TTL with freshness checks. Treat stale registry entries as compromised until proven otherwise.
- **Agora: Negotiated capability boundaries, not ambient trust.** Agora agents negotiate capabilities at connection time. The negotiation can be manipulated to over-grant permissions that the receiving agent accepts because it trusts the sender. Enforce that negotiated capabilities are explicitly checked against the calling agent's declared role before any action is taken.

### Close the cross-protocol handoff gap

The most dangerous attack surface is the boundary between protocols — where an agent transitions from MCP tool access to A2A delegation to ANP discovery. At each transition:

1. **Re-validate identity at the boundary.** A trusted MCP tool result should not automatically carry the trust of the calling agent when that result enters A2A delegation. The protocol transition is a trust boundary that must be explicitly enforced.
2. **Propagate provenance tags across protocol transitions.** The MCP server that produced a tool result should be tagged in the artifact that enters the A2A layer. If that artifact is later used for a downstream delegation, the chain of provenance is visible to the receiving agent.
3. **Instrument protocol-level telemetry.** Most agent observability (S-1438) traces tool calls and LLM invocations. Add a protocol-layer trace that records which MCP servers were contacted, which A2A agents were invoked, and which ANP registry entries were resolved — for every agent run.

### Run protocol-specific adversarial tests in CI

Threat modeling without automated verification is documentation. For each protocol:

- **MCP:** Test that a server declaring capability X cannot access tool Y it wasn't granted. Test that a server cannot exfiltrate context from other connected agents. Use the OWASP ASI MCP Top 10 as the test taxonomy.
- **A2A:** Test that an unauthorized agent cannot invoke another agent's exposed task. Test that delegation carries explicit capability constraints, not ambient trust.
- **ANP:** Test that a poisoned registry entry redirects to a fallback discovery mechanism. Test that capability attestations are cryptographically verifiable and not self-signed.
- **Cross-protocol:** Test that a malicious MCP server cannot use a legitimate A2A delegation chain to reach agents it was never connected to. See S-276 for CI-gated adversarial testing patterns.

## Receipt

> Verified 2026-07-21 — Research: arxiv:2602.11327 (Security Threat Modeling for Emerging AI-Agent Protocols, 2026) — comparative lifecycle-phase threat analysis of MCP, A2A, ANP, and Agora across creation/operation/update phases. Key finding: all four protocols exhibit medium-to-high risk; no protocol provides complete protection across all phases. MCP: 43%+ servers with command injection flaws, exploit probability >92% with 10 plugins. A2A: all security mechanisms advisory (MAY/SHOULD). ANP: registry poisoning and discovery redirection not mitigated by protocol design. Agora: capability overgrant via negotiation manipulation. BlueHeadline (2026): "Most AI agent failures in production are not model failures. They are protocol failures." Cross-reference: S-889 (MCP ambient authority), S-1188 (A2A authorization island), S-359 (MCP security and protocol convergence), S-1438 (execution-reasoning correlation stack — protocol-layer telemetry gap).

## See also

- [S-1188 · The A2A Authorization Island](s1188-the-a2a-authorization-island-when-every-agent-is-its-own-security-perimeter.md) — authorization island problem; this entry extends it to the full protocol ecosystem
- [S-359 · MCP Security and the Agent Protocol Convergence](s359-mcp-security-and-agent-protocol-convergence.md) — MCP-specific security; this entry provides the comparative framework across all four protocols
- [S-889 · MCP Ambient Authority](s889-mcp-ambient-authority-capability-bucketing-against-session-scoped-token-chains.md) — capability scoping; complements the threat matrix with specific mitigation patterns
