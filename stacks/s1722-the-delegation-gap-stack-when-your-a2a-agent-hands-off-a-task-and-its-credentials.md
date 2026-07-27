# S-1722 · The Delegation Gap Stack — When Your A2A Agent Hands Off a Task and Its Credentials

You've connected your agent to the A2A network. It discovers other agents, negotiates tasks, sends context across frameworks. The protocol handles transport security (HTTPS, auth headers). What it doesn't handle is the question every production deployment needs to answer: **should this agent delegate this task to that specific agent with those specific permissions?** A2A v1.0.0 was deliberately scoped to omit built-in authorization — the protocol gives you the plumbing, not the trust model. This is the delegation gap.

## Forces

- A2A enables agent interoperability across vendors and frameworks — which is also exactly what makes agent-to-agent credential delegation the highest-stakes trust boundary in your architecture
- A2A's design (agents are opaque to each other, shared memory model intentionally absent) makes it architecturally clean — and makes delegation authorization harder because the calling agent has no visibility into what the receiving agent will do with the credentials it receives
- GitHub Discussion #284 (A2A repo, JKHeadley, Feb 2026) identifies the core problem: nested delegation chains (agent 5 levels deep requesting PII) mean transport-layer security alone is insufficient — you need a trust signal that propagates through the delegation chain
- A2A protocol v1.0.0 explicitly omits built-in authorization by design (Arnav Sharma, Microsoft MVP, Jul 2026) — the security gap is structural, not accidental
- The proliferation of agent credential tokens (17:1 non-human to human identities, Veza 2026; +81% AI-service credential leaks YoY, GitGuardian 2026) means each delegation handoff potentially amplifies your credential attack surface

## The move

### 1. Establish agent identity before delegation

Every A2A agent must have a cryptographically verifiable identity — not just an authenticated connection, but a **capability contract**. Agent Cards (the A2A discovery primitive) gained cryptographic signatures for domain verification at Google I/O 2026, closing the primary enterprise security gap. Before delegating, verify the Agent Card signature and check the agent's declared capability scope against what the task requires.

```
Before delegation:
  1. Fetch Agent Card from well-known URL
  2. Verify card signature (domain-key verification)
  3. Check: requested_scope ⊆ declared_capabilities?
  4. Check: caller_delegation_chain ⊆ caller_own_capabilities?
  5. Block if any check fails — log the attempted delegation
```

### 2. Scope tokens at the delegation boundary

A2A agents typically receive bearer tokens to complete tasks. Without DPoP (Proof of Possession), a stolen token works anywhere. Add DPoP binding: cryptographically tie the access token to the delegating agent's keypair so intercepted tokens can't be replayed by a downstream compromised agent or external actor (GitHub #284, bgauryy). For nested delegation chains, enforce the **required ⊆ supported** invariant: each agent in the chain can only delegate permissions it itself holds.

```
Token scope enforcement:
  - Delegating agent's effective_scope = min(own_scope, task_requirement)
  - Nested delegation: downstream_agent_scope = min(parent_scope, task_requirement)
  - Log every delegation event: caller → recipient → scope_transferred → chain_depth
```

### 3. Build a behavioral trust score for delegation routing

Authentication answers "is this agent who it claims?" Trust answers "has this agent reliably completed this class of task before?" MoltBridge (SageMind AI, 2026) proposes behavioral trust scores that propagate through the delegation chain — not just binary pass/fail but a graded signal. Route high-stakes tasks (PII access, financial operations, external egress) to agents with established trust scores above your threshold.

```
Trust score dimensions:
  - Task completion rate for this task type
  - Scope adherence (did agent stay within declared boundaries?)
  - Recency (when was last successful delegation?)
  - Chain depth penalty (each hop in a delegation chain reduces trust score)
```

### 4. Apply MCP's least-agency principle to A2A delegation

MCP (Model Context Protocol) governs agent-to-tool access with fine-grained, least-privilege scoping. A2A delegation should follow the same principle: an agent requesting a task handoff should declare the minimum credential scope required, and receiving agents should refuse to accept scopes beyond what they need for the declared task. Block scope upgrades mid-delegation — if an agent's task changes and requires broader access, it must re-authenticate at the higher scope rather than receiving an automatic upgrade.

```
Scope upgrade protocol:
  - Agent declares task_requirement at delegation request time
  - Receiving agent grants exactly: task_requirement ∩ declared_capabilities
  - Any mid-task scope increase → full re-authentication, new delegation record
  - Policy kernel (see S-1458) intercepts delegation for enforcement
```

### 5. Instrument the delegation chain with audit trail

Every A2A delegation is a potential breach vector. Log: caller identity, recipient identity, task description, scope transferred, chain depth, timestamp, outcome. This serves both security audit (post-incident reconstruction of what data flowed where) and operational observability (detecting abnormal delegation patterns — an agent suddenly delegating to unfamiliar agents, or delegating more than usual).

```
Delegation audit log entry:
  {
    "event": "A2A_DELEGATION",
    "chain_depth": 2,
    "caller": "agent:crm-enrichment-v3",
    "recipient": "agent:external-verification",
    "scope": ["read:customer_email", "read:phone"],
    "task_type": "identity_verification",
    "outcome": "SUCCESS",
    "trust_score": 0.87
  }
```

### The protocol-layer pattern

For teams integrating A2A into existing infrastructure, the cleanest deployment pattern is a **delegation proxy** — a policy enforcement point that sits between your agent and the A2A network, intercepts delegation requests, applies the checks above (identity verification, scope comparison, trust scoring, audit logging), and either permits or blocks the delegation. This keeps your agent code clean while centralizing the trust logic.

## Receipt

> Receipt pending — 2026-07-27. Pattern synthesized from: A2A Protocol GitHub Discussion #284 (JKHeadley, bgauryy, Feb–Jul 2026), Arnav Sharma (Microsoft MVP, Jul 2026, "Securing Agent-to-Agent A2A Communication"), Zylos Research (Mar 2026, "Agent Interoperability Protocols 2026"), Microsoft/Okta/AWS agent-governance product announcements (2026). Deduplication: S-1040 (Protocol Gap) covers MCP↔A2A interoperability; S-1458 (Policy Kernel) covers MCP/A2A gateway enforcement; neither covers A2A delegation authorization — the trust model for agent-to-agent credential handover. This entry addresses the structural authorization gap that neither protocol spec resolves by design.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP↔A2A interoperability fundamentals; this entry extends the A2A layer into production authorization
- [S-1458 · The Policy Kernel Stack](S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — MCP/A2A gateway enforcement; the delegation proxy in this entry is a specialization of the policy kernel pattern for A2A
- [S-10 · MCP](s10-mcp.md) — MCP's least-agency principle for tool access; the same principle applied to A2A delegation is the core move here
