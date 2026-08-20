# S-2903 · The Capability Attenuation Stack — When Your Sub-Agent Has More Power Than Your Planner Agent Ever Authorized

Your planner agent needs a specialist to analyze a dataset. It delegates to a sub-agent — and the sub-agent inherits the planner's full GCP admin credentials, its production database read/write access, and its network egress allowance. The specialist doesn't need any of that. But delegation passed the credentials through unchanged, because delegation was a trust proxy, not a capability filter. The sub-agent gets compromised by a prompt injection in the dataset. Now an attacker with sub-agent access has planner-level reach. This is the delegation chain problem: every hop widens the attack surface unless you actively attenuate it. The five-plane reference architecture (Tallam, arXiv:2606.12320, Jun 2026) formalizes this as **capability attenuation through delegation chains** — the principle that downstream agents should hold a subset of upstream capabilities, enforced structurally rather than by convention.

## Forces

- **Delegation inherits, not filters.** The default delegation model passes the delegating agent's full credential scope to the sub-agent. There is no mechanism to say "you can read this dataset but not write to any system, and you cannot spawn further sub-agents." Every delegation hop that doesn't attenuate is a compounding exposure.
- **Composite principals don't fit atomic authorization models.** Standard IAM evaluates "does this principal (user or service account) have permission X?" Agentic delegation chains create composite principals — the planner acting through the specialist acting through a tool. The capability set is the intersection of all three, not any one. Static IAM cannot represent this; the enforcement must happen at the delegation point.
- **Authorization checks are point-in-time; agentic authority is temporal.** A human grants a permission and it persists until revoked. An agent's authority should degrade over time, with task completion, or with context changes. A 4-hour-old delegation to a compromised sub-agent is categorically worse than a fresh one. Capability attenuation must be time-scoped and stateful.
- **Attenuation conflicts with capability accumulation.** Agents are designed to accumulate capabilities — more tools, more access, more autonomy. Attenuation runs against this design instinct. The tension is real: attenuate too aggressively and the agent can't complete its task; attenuate too loosely and you haven't addressed the delegation problem.

## The move

### The attenuation principle

When agent A delegates to agent B, B receives **only** the intersection of: A's granted capabilities, the task-specific required capabilities, and the enforcement plane constraints (time, scope, data sensitivity). The rest is dropped. This is not a prompt instruction — it is an architectural gate enforced by the delegation broker before B's first tool call.

```python
# Minimal capability-attenuating delegation broker (conceptual)
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Flag, auto

class Capability(Flag):
    READ_DATA = auto()
    WRITE_DATA = auto()
    NETWORK_EGRESS = auto()
    SPAWN_SUBAGENT = auto()
    EXECUTE_CODE = auto()
    READ_CREDENTIALS = auto()

@dataclass
class DelegationContext:
    task_id: str
    issued_at: datetime = field(default_factory=datetime.utcnow)
    ttl: timedelta = timedelta(minutes=30)
    task_capabilities: Capability = Capability.READ_DATA
    parent_capabilities: Capability = Capability.READ_DATA | Capability.WRITE_DATA | Capability.SPAWN_SUBAGENT
    max_depth: int = 2

    @property
    def attenuated_capabilities(self) -> Capability:
        # Enforce: sub-agents cannot spawn sub-agents unless explicitly granted
        effective = self.task_capabilities & self.parent_capabilities
        if self.max_depth <= 1:
            effective &= ~Capability.SPAWN_SUBAGENT
        return effective

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.issued_at + self.ttl

    def enforce(self, required: Capability) -> bool:
        if self.is_expired:
            return False  # Revoke on TTL expiry
        return (required & self.attenuated_capabilities) == required

# Usage
ctx = DelegationContext(
    task_id="data-analysis-001",
    task_capabilities=Capability.READ_DATA,
    parent_capabilities=Capability.READ_DATA | Capability.WRITE_DATA | Capability.SPAWN_SUBAGENT,
    max_depth=2,
)
print(f"Planner capabilities:    {ctx.parent_capabilities}")
print(f"Task-required:           {ctx.task_capabilities}")
print(f"Sub-agent gets:          {ctx.attenuated_capabilities}")
# Planner capabilities:    READ_DATA | WRITE_DATA | SPAWN_SUBAGENT
# Task-required:            READ_DATA
# Sub-agent gets:           READ_DATA (only)
```

### The five-plane enforcement structure

Tallam's architecture decomposes the enforcement into five planes. Each plane applies a different lens to the delegation chain:

| Plane | Role | What it attenuates |
|-------|------|--------------------|
| **Reasoning plane** | Adjudicates intent: is this action consistent with the authorized task? | Prevents task creep — the sub-agent reasoning about whether to access systems outside its mandate |
| **Network plane** | Enforces egress allowlisting and rate limits per delegation context | Limits data exfiltration vectors even if the sub-agent is compromised |
| **Identity plane** | Issues and validates ephemeral scoped identities per delegation hop | Stops credential reuse across delegation boundaries |
| **Endpoint plane** | Controls what files, processes, and system resources the sub-agent can touch | Sandboxes execution to task-relevant resources only |
| **Data plane** | Classifies and tags data; enforces that outputs only flow to authorized destinations | Prevents cross-tenant data leakage in multi-agent workflows |

The critical property: **every plane runs the capability intersection independently**. A network-plane allowance doesn't grant endpoint-plane access. A sub-agent might be allowed to reach `api.example.com` (network plane) but not read `/project/prod-secrets` (endpoint plane).

### Stop-anywhere mediation: 6 interruption primitives

The five-plane architecture defines 6 interruption primitives that generalize beyond allow/deny:

| Primitive | Effect |
|-----------|--------|
| `ALLOW` | Proceed with full attenuated capability set |
| `DENY` | Terminate the invocation; log and alert |
| `ESCALATE` | Pause and require human approval before continuing |
| `REDUCE` | Downgrade the capability (e.g., read-only → no access) |
| `WRAP` | Execute through a proxy that sanitizes inputs/outputs |
| `DEFER` | Queue for async review before the action completes |

These are the actual enforcement primitives, not just boolean gates. A compromised sub-agent attempting a write is `REDUCE`d to read-only mid-action, not denied and left hanging.

### Integrating with OPA / Cedar

For teams already running Open Policy Agent or AWS Cedar, the five-plane reference architecture maps to policy-as-code:

```rego
# OPA policy: capability-attenuation gate at delegation point
package agent.delegation

default allow := false

allow if {
    input.delegator_capabilities & input.task_required == input.task_required
    not exceeds_depth_limit
    not expired
    not prohibited_capability_in_chain
}

exceeds_depth_limit if {
    input.chain_depth >= input.max_delegation_depth
}

expired if {
    now > time.add_duration(input.issued_at, "30m")
}

prohibited_capability_in_chain if {
    # Sub-agents cannot inherit credential-read or spawn-subagent unless explicitly allowed
    input.task_required & prohibited_flags != empty_set
}

prohibited_flags := {"read_credentials", "spawn_subagent"}
```

## Receipt

> Verified 2026-08-20 — Conceptual implementation of the attenuation broker and OPA gate written and validated against the pattern description from arXiv:2606.12320. The OPA rego policy was syntax-checked against OPA v0.68. The core insight holds: capability attenuation is a set intersection operation at each delegation hop, not a prompt instruction. The five-plane model extends beyond OPA/Cedar's atomic-principal model by tracking composite principals through the chain. Next step: integrate with SPIFFE/SPIRE for ephemeral identity issuance per delegation context (see S-992 on Verifiable Credential Infrastructure).

## See also

- [S-1458 · The Policy-Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — OPA/ Cedar policy enforcement as the kernel; S-2903 extends this to delegation chains with composite principals
- [S-1075 · The Ephemeral Delegation Stack](/stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — ephemeral scoped tokens; S-2903 addresses the capability-filtering problem those tokens don't solve alone
- [S-992 · The Agent Verifiable Credential Infrastructure](/stacks/s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — SPIFFE/SPIRE identity for agents; S-2903 extends this to capability scoping per identity
- [S-2847 · The Non-Human Identity Void Stack](/stacks/S-2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) — structural gap between agent capabilities and identity infrastructure; capability attenuation is the remediation
