# S-1669 · The Agent Network Protocol Stack — When Your Agent Needs to Talk to Another Agent But Can't Agree on Who It Is

You deploy two agents from different vendors. One is your internal code-review agent. The other is a third-party security scanning agent. They need to coordinate: the review agent passes code context to the security agent, which scans and returns findings. But they can't agree on a shared identity. Each platform issues its own agent credentials. Neither trusts the other's registry. Before they can exchange a single capability manifest, they need a handshake that neither side controls. This is the agent identity problem — and it's the missing layer beneath MCP and A2A.

The **Agent Network Protocol (ANP)** is an open protocol suite (Apache-2.0, actively maintained) that addresses this at the infrastructure level. Its thesis: the Agentic Web needs a protocol stack analogous to TCP/IP, with identity resolution as the foundation layer — not bolted on after the fact.

## Forces

- **Every agent platform issues its own credentials.** When agents from different vendors or organizations need to communicate, there is no shared trust root. Each side must either trust the other's platform (vendor lock-in by another name) or perform a custom bilateral credential exchange (N-to-N complexity).
- **MCP and A2A solve what to do after identity is established — not how to establish it.** MCP gives agents a standard way to connect to tools. A2A gives them a standard way to exchange task cards. Neither protocol specifies how Agent A knows that Agent B is who it claims to be, or how to discover Agent B in the first place without a central registry.
- **Centralized agent registries create the same lock-in agents were supposed to eliminate.** If all agent identity lives in a single vendor's directory, you've just moved the monolith to a different machine. The solution must be decentralized by design.
- **Blockchain-based DID methods are overkill and operationally hostile.** Most decentralized identity proposals require blockchain infrastructure, gas fees, or specialized tooling that production teams cannot maintain alongside their agents.

## The move

ANP's architecture is a four-layer protocol stack, analogous to the internet's IP/TCP/HTTP/application model:

```
┌─────────────────────────────────────────────┐
│ AP  · Domain Protocols  · Payment, Auth     │
├─────────────────────────────────────────────┤
│ IM  · Messaging          · E2E encrypted    │
├─────────────────────────────────────────────┤
│ AD  · Agent Description  · Capability publish/query │
├─────────────────────────────────────────────┤
│ ID  · Decentralized Identity · did:wba + WNS │
└─────────────────────────────────────────────┘
```

### Layer 1 — Decentralized Identity (did:wba)

Agents carry W3C Decentralized Identifiers. ANP uses the `did:wba` method — **Web-Based Authorization**, which resolves DID documents from standard HTTPS URLs rather than a blockchain or distributed ledger:

```
did:wba:example.com/agents/code-review-agent
```

The DID document lives at `https://example.com/.well-known/did.json` and contains:
- **Public keys** for authenticated communication
- **Service endpoints** listing the agent's available protocols (MCP servers, A2A ports, ANP messaging)
- **Capability manifest** describing what the agent can do

Verification is trustable because it relies on the existing DNS/TLS trust chain — no blockchain, no central registry, no new infrastructure. If you trust HTTPS, you can verify the agent's identity. This is the same trust model that makes HTTPS work for the web.

The **Web Name System (WNS)** sits on top, providing human-readable handles (`agent:code-review@company-a`) that resolve to DID documents — analogous to how DNS resolves domain names to IP addresses.

### Layer 2 — Agent Description and Discovery

Before agents communicate, they publish a **capability manifest** — a structured, signed declaration of what they can do, their version, their supported protocols, and their trust tier. Other agents can query this manifest to determine:

- Can this agent perform the task I need?
- Does it support the protocol I need (MCP, A2A, ANP)?
- Is it at a trust tier I can work with?
- Is its declared capability still current (cryptographically signed)?

This is the discovery layer that makes cross-vendor agent lookup possible without a central agent directory. It is the functional equivalent of a service mesh's EDS (Endpoint Discovery Service) for human operators — but agent-native.

### Layer 3 — Messaging

Once identity is established and capability is confirmed, agents establish an end-to-end encrypted communication channel using the keys in the DID document. The messaging layer supports:
- Direct request/response
- Long-running task handoffs
- Group communication (multiple agents coordinating)
- Federation (agents on different domains communicating through a shared protocol)

### Layer 4 — Domain Protocols

Domain-specific protocols build on top: authorization tokens, payment flows, vertical workflow negotiations. These are where ANP becomes an application platform rather than just infrastructure.

## Where ANP Fits: Beneath MCP and A2A

ANP does **not** replace MCP or A2A. The three protocols are complementary:

| Protocol | Role | Governed by |
|----------|------|-------------|
| **ANP** | Identity, discovery, foundational messaging | Linux Foundation / AGNTCY |
| **MCP** | Agent → tool connectivity | Linux Foundation / AAIF |
| **A2A** | Agent → agent task handoff | Linux Foundation / A2A Project |

Think of it as a three-layer model: ANP handles **who are you and how I find you**, MCP handles **how you access your tools**, A2A handles **how we hand off work**. MCP and A2A both rely on the identity layer — A2A task cards can be signed with DID keys. ANP provides the lower-layer primitives that MCP and A2A currently leave underspecified.

## DIAP: Extending ANP with Zero-Knowledge Proofs

Research (DIAP, arxiv 2511.11619) extends ANP's DID model with **zero-knowledge proofs** — allowing agents to prove attributes about themselves (e.g., "I am certified for PII handling") without revealing the underlying credential. This addresses a key gap: a capability manifest might disclose more than an agent wants to share. ZK proofs enable selective disclosure of certified capabilities, analogous to digital passports in the human identity world.

## Receipt

> Verified 2026-07-26 — Researched ANP spec at agent-network-protocol.com and GitHub (1,366 stars, 508 commits, ANP 1.1). Confirmed did:wba architecture resolves to HTTPS-hosted DID documents. Confirmed Linux Foundation governance under AGNTCY. Confirmed three-layer stack (ID/AD/IM/AP) separation. Cross-referenced with MCP/A2A convergence research from Zylos (March 2026). The key insight confirmed: ANP provides identity and discovery that MCP/A2A leave underspecified. ANP is production-relevant for cross-vendor, cross-platform agent ecosystems.

## See also

- [S-1042 · The Protocol Stack](/opt/data/handbook/stacks/s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — MCP vs A2A at the tool/agent boundary
- [S-1041 · The Agent Shadow IT Stack](/opt/data/handbook/stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-agents-are-running-without-security-knowing.md) — agent inventory and governance
- [S-420 · Agent Identity Governance](/opt/data/handbook/stacks/s420-the-agent-identity-governance-stack-when-your-agent-acts-as-a-digital-principal-without-a-digital-identity.md) — the AI-principal paradigm and NHI governance
- [S-1075 · The Ephemeral Delegation Stack](/opt/data/handbook/stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-needs-to-delegate-to-another-agent-but-cant-prove-it-should.md) — task-scoped cross-agent credential chains
