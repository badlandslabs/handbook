# S-1134 · The Invocation-Bound Capability Token Stack — When Your Agent Chains Delegations and Nobody Can Prove Who Authorized What

Agent A delegates to Agent B, which calls Agent C, which invokes an MCP tool that touches production data. At each hop, credentials are passed forward — OAuth tokens with broad scopes, bearer tokens with static permissions, API keys with service-account access. Nobody can prove the human authorized that final tool call. Nobody can revoke just that one delegation. Nobody can trace back which agent introduced the failure.

This is the **multi-hop delegation problem** — and it is the defining security challenge of enterprise agentic AI. A scan of ~2,000 MCP servers found zero with authentication. OAuth has no offline-attenuable delegation. Macaroons lack expressive chained policy. UCANs lack provenance-oriented completion records. The arXiv:2603.24775 paper (Prakash, Indian School of Business, March 2026) introduced Invocation-Bound Capability Tokens (IBCTs) as the first primitive to address all four gaps jointly: public-key verifiable delegation, holder-side attenuation, expressive chained policy, and transport bindings across MCP/A2A/HTTP.

## Forces

- **Agents fan out; credentials don't.** A human credential maps to one identity. An agent spawns N sub-agents, each calling N tools. Static credentials have no concept of this fan-out and carry no provenance about which parent agent authorized each downstream call.
- **Every delegation gap is an attack surface.** Cross-agent privilege escalation (Rehberger, September 2025), agent session smuggling (Palo Alto Unit 42, November 2025), and the March 2026 "BadHost" Starlette CVE all exploited the same root: a downstream actor operating with upstream credentials they were never explicitly granted.
- **Revocation is all-or-nothing by default.** When a sub-agent is compromised or misbehaves, revoking the parent credential also revokes every other legitimate sub-agent using it. There is no per-delegation revocation because there is no per-delegation token.
- **The confused deputy problem is structural, not code.** A traditional confused deputy attack: a privileged program gets tricked into misusing its own authority. An agent confused deputy attack: Agent B receives an instruction from Agent A and cannot verify whether the instruction legitimately traces back to the human principal. The agent isn't malicious; it just can't cryptographically distinguish legitimate delegation from crafted attack.
- **MCP and A2A don't verify agent identity.** MCP's stdio transport has no built-in authentication. A2A handles task delegation but provides no cryptographic chain of custody. This means every MCP server you connect to trusts every agent that connects to it.

## The move

**Invocation-Bound Capability Tokens (IBCTs)** replace bearer credentials with a cryptographic token chain that encodes four things at issuance: the agent's DID key pair, the exact scope of the authorization, the parent chain back to the human principal, and a provenance record for completion.

```
Human (root authority)
  └── grants IBCT-1 to Agent A
        scope: [read:orders, list:inventory]
        parent: human DID
        expires: 1 hour
        └── Agent A delegates IBCT-2 to Agent B
              scope: [read:orders]  ← attenuated
              parent: IBCT-1
              expires: 15 min
              └── Agent B invokes MCP tool
                    presents: IBCT-2
                    tool verifies: IBCT-2 signature against Agent B DID key
                    tool verifies: IBCT-1 signature against Agent A DID key
                    tool verifies: human signature against human DID
                    tool verifies: scope covers [read:orders]
                    tool verifies: not expired
                    → action permitted
```

The token chain is append-only: each delegation creates a new IBCT by attenuating (narrowing) the parent scope. The child cannot escalate its own permissions — the cryptographic chain prevents it.

### Two wire formats

| Format | Use Case | Structure |
|--------|----------|----------|
| Compact | Single-hop, latency-sensitive calls (MCP tool invocation) | Signed JWT with IBCT claims |
| Extended | Multi-hop, audit-required flows (A2A delegation, compliance) | CBOR-encoded with full provenance chain |

### The five IBCT claims

Every IBCT carries five required fields:

```
1. sub        — agent DID (cryptographic identity)
2. scope      — exact permissions (narrowed from parent)
3. deleg      — parent IBCT DID (append-only chain)
4. iat / exp  — issued-at / expiration (per-delegation TTL)
5. prov       — completion record (what happened, for audit)
```

### Scope attenuation at each hop

The key property: child IBCTs can only narrow scope, never widen it. If Agent A holds `[read:orders, write:orders, export:reports]` and delegates to Agent B for a specific task, Agent B can only receive a subset — e.g., `[read:orders]` — never the superset. The cryptographic signature on IBCT-2 is computed by Agent A over the attenuated scope; Agent B cannot forge this signature.

```python
def attenuate(parent_ibct: IBCT, new_scope: list[str]) -> IBCT:
    # Child scope must be subset of parent scope
    assert set(new_scope) <= set(parent_ibct.scope)
    # Child expires before parent
    assert new_expires < parent_ibct.exp
    # Child DID signs, parent DID is referenced (not re-signed)
    return IBCT(
        sub=my_did,
        scope=new_scope,
        deleg=parent_ibct.chain_digest,  # hash of parent's full chain
        exp=new_expires,
        prov=None,
    )
```

### Revocation

Revoke at any node in the chain. Because each IBCT references its parent's chain digest, revoking IBCT-1 invalidates all descendants (IBCT-2, IBCT-3, …) — but only those. Other unrelated delegations from the same human or agent are unaffected. Implement revocation via a short-TTL CRL or OCSP-like protocol checked at each invocation.

### Transport bindings

IBCTs are protocol-agnostic by design:
- **MCP**: Attach IBCT as an MCP `authorization` header on tool invocation
- **A2A**: Include IBCT in the `agent://` URI scheme for task delegation
- **HTTP**: Standard `Authorization: IBCT <token>` header

## Receipt

> Receipt pending — [2026-07-15]

Key sources:
- Prakash (2026), arXiv:2603.24775 — "AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A"
- draft-beyer-agent-identity-problem-statement-00 (Beyer, April 2026, IETF Internet-Draft)
- WorkOS, "AI Agents and the Multi-Hop Delegation Problem" (April 2026)
- docs.adid.dev/agents/ibct — IBCT implementation reference

## See also

- [S-266](s266-inter-agent-trust-delegation.md) — Inter-Agent Trust Delegation: the authorization model foundations above IBCTs
- [S-1075](s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — Ephemeral Delegation: the problem IBCTs solve at the token level
- [S-572](s572-the-context-window-is-not-a-vault-when-credentials-flow-through-llm-memory.md) — Credentials Through LLM Memory: how IBCTs prevent credential leakage via context
- [S-1113](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — Five-Layer Audit Trail: IBCT prov records as the provenance layer
- [S-420](s420-agent-identity-governance-the-AI-principal-paradigm.md) — Agent Identity Governance: the identity layer that IBCTs depend on
