# S-1900 · The Governance Gap Stack — When Your Agent Protocols Coordinate but Can't Govern

Your MCP servers connect to tools. Your A2A agents discover each other's capabilities and exchange tasks. You've checked the governance boxes: you have role definitions, approval policies on sensitive tools, and audit logs. But when two agents from different teams negotiate a shared resource — a budget pool, a customer record, an external API — the protocol handles the handoff and your prose policies handle the rest. Nothing actually enforces that Agent A can't commit Agent B to costs B's team didn't approve. Nothing encodes that a three-agent pipeline requires majority agreement before touching PII. Your protocols coordinate. They don't govern. This is the governance gap — and it is the next systemic failure mode as agent fleets scale.

## Forces

- **MCP, A2A, and ACP solve coordination, not governance.** Every major interoperability protocol handles identity, discovery, capability advertisement, and message exchange. None natively encode collective decision-making, admission policy, delegation constraints, or resource commitment limits. The protocols are communication layers — governance is a layer above that doesn't exist yet.

- **Prose policies fail under multi-agent negotiation.** A policy statement like "agents must get human approval for external API calls" lives in a prompt. When Agent A hands a task to Agent B, Agent B's prompt governs Agent B's behavior — but Agent A's prompt has no way to know whether Agent B will comply. The delegation chain breaks the enforcement boundary.

- **The six-dimension governance gap is systematic.** Kang & Dipenegro (arXiv:2606.31498v1, DoiT International, June 2026) systematically evaluated five prominent agent interoperability protocols (MCP, A2A, ACP, ANP, ERC-8004) against a six-dimension governance taxonomy: membership (G1), deliberation (G2), decision (G3), accountability (G4), enforcement (G5), and recourse (G6). Every protocol scored 0–2 out of 12. Zero protocols support collective decision-making natively. This is not a missing feature — it is a missing architectural layer.

- **Fleet-level governance requires something protocols alone cannot provide.** When you deploy 12 agents across 4 teams, each speaking MCP to tools and A2A to each other, the coordination fabric is fine. But who owns the shared API quota? Who can escalate a sub-agent's privileges? Who resolves a deadlock between two agents that each believe they have authority? These are governance questions, and they sit above the protocol layer entirely.

## The move

### 1. Acknowledge the protocol ceiling

MCP, A2A, and ACP occupy layers 1–3 of a four-layer stack:

```
┌────────────────────────────────────────────┐
│  Layer 4: GOVERNANCE  ← missing             │
├────────────────────────────────────────────┤
│  Layer 3: Trust & Reputation                │
├────────────────────────────────────────────┤
│  Layer 2: Negotiation & Negotiation Outcome │
├────────────────────────────────────────────┤
│  Layer 1: Transport / Messaging / Identity  │
│  (MCP, A2A, ACP, ANP, ERC-8004)            │
└────────────────────────────────────────────┘
```

Deploying agents on Layer 1–2 protocols without a Layer 4 governance architecture is like running microservices on HTTP with no API gateway, no auth, and no rate limiter.

### 2. Build a governance manifest layer above protocols

Encode governance constraints as a first-class artifact — a `requirements.toml` or equivalent — that sits above your protocol implementations:

```toml
# fleet-governance.toml
[members]
[members.agents.trade-agent]
team = "finance"
tier = "production"
max_daily_cost_usd = 500.0
can_delegate = false
requires_approval_for = ["external_api", "database_write"]

[members.agents.analysis-agent]
team = "analytics"
tier = "production"
max_daily_cost_usd = 200.0
can_delegate = true
delegation_targets = ["trade-agent"]  # only to finance
requires_approval_for = ["customer_pii"]

[[policies]]
name = "three-agent-pii-access"
trigger = "any agent accesses customer_pii"
condition = "minimum 2 agents must agree (including human-in-loop)"
action = "block + escalate"

[[policies]]
name = "budget-commitment"
trigger = "agent proposes to spend shared resource"
condition = "cost_estimate <= agent's max_daily_cost_usd AND receiving_agent.team approved"
action = "allow"
fallback = "block + notify team-owners"
```

This manifest is read by a governance proxy — a thin service that intercepts inter-agent messages and evaluates them against the policy layer before the protocol exchange completes. It does not replace MCP or A2A; it wraps them.

### 3. Implement the governance proxy as a protocol interceptor

```
Agent A  →  [Governance Proxy]  →  Agent B
           check: G1–G6 policies
           evaluate: delegation chain
           enforce: cost limits, approval gates
           log: full governance trace
```

The proxy evaluates three governance questions on every inter-agent call:

1. **Authority**: Does the originating agent have the right to make this commitment? (G1 membership + G4 accountability)
2. **Consent**: Have the downstream agents (or their owners) consented to this delegation? (G2 deliberation + G3 decision)
3. **Recourse**: If this goes wrong, who can undo it, and is there a trace? (G5 enforcement + G6 recourse)

### 4. Define delegation chains explicitly

Unconstrained delegation is the governance gap's most dangerous edge case. When Agent A hands off to Agent B, and Agent B delegates further to Agent C, the original authority has no visibility into what Agent C is doing. Explicit delegation chains solve this:

```python
class DelegationChain:
    originating_agent: str
    path: list[str]           # [A, B, C] — must match fleet-governance.toml
    depth_limit: int           # e.g., 3 hops max
    cost_attribution: str      # "A pays" or "split by path"
    revocation_token: str      # A can revoke any time

    def validate(self, proposed_action: Action) -> bool:
        # Each agent in the chain must have approved this action type
        for agent_id in self.path:
            if not self.policy.allows(agent_id, action.type):
                return False
        return True
```

### 5. Add governance observability

Every governance evaluation produces a structured log entry:

```json
{
  "event": "governance_check",
  "timestamp": "2026-07-31T10:00:00Z",
  "origin_agent": "trade-agent",
  "target_agent": "analysis-agent",
  "action": "commit_external_api",
  "estimated_cost": 85.00,
  "governance_result": "BLOCKED",
  "blocking_policy": "budget-commitment",
  "reason": "analysis-agent max_daily_cost_usd exceeded (200.00)",
  "delegation_chain": ["trade-agent", "analysis-agent"],
  "trace_id": "gov-abc123"
}
```

This is not an audit log for post-hoc review — it feeds a live governance dashboard showing which policies are active, which are blocking, and where the most common governance friction points are in your fleet.

## Receipt

> Verified 2026-07-31 — Core finding confirmed via Kang & Dipenegro (arXiv:2606.31498v1, June 2026): five agent interoperability protocols collectively score 0–2/12 on a six-dimension governance taxonomy. Codex CLI's layered architecture (Vaughan, July 2026) provides the implementation pattern for a governance manifest layer above MCP/A2A/ACP. The four-layer stack model (transport → negotiation → trust → governance) is the structural insight that distinguishes this from S-1040 (MCP/A2A mechanics) and S-1458 (MCP policy kernel — single-framework, not cross-protocol fleet governance). No existing entry covers the delegation chain problem or the protocol-layer ceiling.

## See also

- [S-1040 · The Protocol Gap](/stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP and A2A mechanics; this entry is the governance layer above
- [S-1458 · The Policy-Kernel Agent Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — single-framework policy enforcement; this entry is the multi-protocol fleet governance layer
- [S-1004 · The Agent Eval Stack](/stacks/s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — governance checks belong in the eval pipeline; fleet policies need coverage testing
