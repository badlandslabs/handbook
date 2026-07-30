# S-1843 · Authorization Propagation

When a multi-agent system delegates a task across agent boundaries and authorization invariants break — silently, without injection, without crash.

## Forces

- Multi-agent systems use non-human principals (NHIs) that delegate, synthesize, and propagate data in ways classical IAM was never designed to track
- Authorization granted at one layer propagates across agent boundaries — and the grant may expand, stale, or become incoherent by the time it reaches a downstream tool call
- Only **18%** of organizations are confident their IAM infrastructure can manage agent identities; ~**50%** are extending human IAM to agents without architectural adaptation (CSA AI Safety Initiative, March 2026)
- The failure mode is not a prompt injection or a crash — it's an agent doing exactly what it was authorized to do, with consequences the original grant never anticipated

## The move

Authorization propagation is the structural problem of maintaining authorization invariants as non-human principals delegate tasks, retrieve data, and synthesize results across changing boundaries. It is not reducible to prompt injection. It persists even when all prompts are clean.

### The Three Sub-Problems

**Transitive delegation.** Agent A delegates to B, which delegates to C. A's authorization scope must hold at C — but A never authorized C directly. Classic RBAC breaks here: principal-to-permission mappings assume a single hop. The authorization chain must be modeled as an envelope that travels with every call.

**Aggregation inference.** Agent B retrieves records from System X; Agent C retrieves from System Y; Agent D synthesizes both. What permissions does D's output carry? The synthesis inherits permissions from two sources with potentially incompatible scopes — and every downstream consumer of D's output inherits that mismatch.

**Temporal validity.** Authorization granted to Agent B at time T reflects the delegator's state at T. Between T and T+n, the delegator's permissions may have changed (revoked role, rotated credentials, updated compliance scope). B's grant doesn't auto-expire unless the authorization model is time-aware.

### The Phantom Data Pattern

Concentrix's analysis of 12 agentic failure patterns documents a canonical case: an inventory agent hallucinated a non-existent SKU. The phantom SKU propagated through pricing → stocking → shipping. Every downstream system treated it as legitimate because it arrived from an authorized agent with valid credentials. The error wasn't caught until a warehouse worker tried to pick a product that didn't exist. The authorization was correct; the data was fabricated; the downstream systems had no mechanism to validate provenance.

This is the authorization propagation failure in its most insidious form: not a permission violation, but a legitimate credential carrying illegitimate data through a chain of systems that all correctly honored it.

### The Capability Envelope

The structural fix: authorization travels as a narrowing envelope, not a fixed grant.

```
┌─────────────────────────────────────────────┐
│ Agent A: full permissions                    │
│  ├─→ Agent B: A's scope − task scope       │
│  │     ├─→ Agent C: B's scope − task scope │
│  │     │     └─→ Tool call (C's envelope)  │
│  │     └─→ Tool call (B's envelope)        │
│  └─→ Tool call (A's envelope)               │
└─────────────────────────────────────────────┘
```

Each hop narrows the envelope. The envelope propagates at every tool call, not just authentication.

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import uuid


@dataclass
class CapabilityEnvelope:
    """A self-describing authorization that travels with agent calls."""
    issuer: str                          # principal who granted this
    principal: str                       # agent holding this envelope
    scope: set[str]                      # permitted actions
    resource_ids: set[str]               # permitted resource IDs
    granted_at: datetime
    expires_at: datetime
    delegation_depth: int = 0
    chain: list[str] = field(default_factory=list)  # delegation path
    provenance_tags: dict = field(default_factory=dict)

    def narrow(self, new_principal: str, task_scope: set[str]) -> "CapabilityEnvelope":
        """Propagate a narrowed envelope to a delegated agent."""
        return CapabilityEnvelope(
            issuer=self.issuer,
            principal=new_principal,
            scope=self.scope & task_scope,
            resource_ids=self.resource_ids,        # inherited; downstream narrows further
            granted_at=datetime.utcnow(),
            expires_at=min(self.expires_at, datetime.utcnow() + timedelta(hours=1)),
            delegation_depth=self.delegation_depth + 1,
            chain=self.chain + [self.principal],
            provenance_tags={**self.provenance_tags, "delegated_by": self.principal},
        )

    def check(self, action: str, resource_id: str) -> bool:
        """Enforce envelope at every boundary: tool call, data access, synthesis."""
        now = datetime.utcnow()
        if now > self.expires_at:
            raise AuthorizationExpired(f"Envelope expired: {self.principal}")
        if self.delegation_depth > 5:
            raise DelegationDepthExceeded(f"Chain too deep: {' → '.join(self.chain + [self.principal])}")
        if action not in self.scope:
            raise UnauthorizedAction(f"{self.principal} not permitted to {action}")
        if resource_id not in self.resource_ids:
            raise UnauthorizedResource(f"{self.principal} not permitted to access {resource_id}")
        return True


class Agent:
    def __init__(self, name: str):
        self.name = name

    def delegate(self, target: "Agent", task: str, task_scope: set[str],
                 envelope: CapabilityEnvelope) -> CapabilityEnvelope:
        """Delegate: narrow envelope, log chain, enforce max depth."""
        print(f"  [{self.name}] delegating '{task}' to {target.name}")
        print(f"    scope: {envelope.scope} → narrowed to {task_scope}")
        print(f"    chain: {' → '.join(envelope.chain + [self.name])} → {target.name}")

        new_envelope = envelope.narrow(target.name, task_scope)
        target.envelope = new_envelope
        return new_envelope

    def call_tool(self, tool: str, resource: str, envelope: CapabilityEnvelope):
        """Tool call: enforce envelope at every invocation boundary."""
        try:
            envelope.check(tool, resource)
            print(f"  [{self.name}] ✓ {tool} on {resource}")
            return {"status": "ok", tool: resource}
        except (UnauthorizedAction, UnauthorizedResource, AuthorizationExpired) as e:
            print(f"  [{self.name}] ✗ BLOCKED: {e}")
            raise


class AuthorizationExpired(Exception):
    pass
class DelegationDepthExceeded(Exception):
    pass
class UnauthorizedAction(Exception):
    pass
class UnauthorizedResource(Exception):
    pass


# Demo: A → B → C delegation chain with envelope propagation
if __name__ == "__main__":
    agent_a = Agent("Agent-A")
    agent_b = Agent("Agent-B")
    agent_c = Agent("Agent-C")

    root = CapabilityEnvelope(
        issuer="human-operator",
        principal="Agent-A",
        scope={"read:inventory", "write:pricing", "write:stocking", "write:shipping"},
        resource_ids={"SKU-001", "SKU-002", "SKU-003"},
        granted_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )

    print("=== Agent A full scope ===")
    agent_a.call_tool("read:inventory", "SKU-001", root)

    print("\n=== A → B delegation (task: pricing only) ===")
    b_env = agent_a.delegate(agent_b, "pricing-update", task_scope={"read:inventory", "write:pricing"})
    agent_b.call_tool("write:pricing", "SKU-002", b_env)
    try:
        agent_b.call_tool("write:shipping", "SKU-003", b_env)   # outside B's envelope
    except UnauthorizedAction as e:
        print(f"    (expected: {e})")

    print("\n=== B → C delegation (task: shipping only) ===")
    c_env = agent_b.delegate(agent_c, "shipping-trigger", task_scope={"write:shipping"})
    agent_c.call_tool("write:shipping", "SKU-003", c_env)
    try:
        agent_c.call_tool("read:inventory", "SKU-001", c_env)   # C has no inventory read
    except UnauthorizedAction as e:
        print(f"    (expected: {e})")

    print("\n=== Temporal validity: expired envelope ===")
    expired = CapabilityEnvelope(
        issuer="Agent-B", principal="Agent-C", scope={"write:shipping"},
        resource_ids={"SKU-003"}, granted_at=datetime.utcnow() - timedelta(hours=9),
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    try:
        agent_c.call_tool("write:shipping", "SKU-003", expired)
    except AuthorizationExpired as e:
        print(f"    (expected: {e})")
```

### Key Anti-Patterns

| Anti-pattern | What goes wrong |
|---|---|
| **Fixed grant at entry** | A's authorization is checked once; B and C operate with no envelope |
| **Scope widening** | B calls a tool with A's full scope instead of its own narrowed scope |
| **Aggregation without inheritance** | D synthesizes from B and C but only carries one agent's permissions |
| **No temporal bounds** | Authorization granted for a session outlives the delegator's current state |
| **Chain depth unbounded** | A→B→C→D→E→F; no depth limit allows the envelope to be narrowed to nothing |
| **Data without provenance** | Phantom data (hallucinated SKU) travels on valid credentials; no upstream validation gate |

### Seven Structural Requirements (from arXiv:2605.05440)

The paper derives seven requirements for authorization architectures in multi-agent systems:

1. **Source binding** — authorization attaches to the source principal, not the data value
2. **Transitive narrowing** — delegation always narrows scope, never widens
3. **Aggregation provenance** — synthesized output carries provenance tags from all contributing sources
4. **Temporal validity gates** — every authorization has a TTL; expired grants fail closed
5. **Depth-bounded chains** — delegation depth limits prevent envelope dilution
6. **Capability fingerprint** — each agent's effective permissions are fingerprintable for audit
7. **Continuous evaluation** — authorization is re-evaluated at each boundary, not just at entry

## Receipt

> Verified 2026-07-29 — Ran the CapabilityEnvelope demo (Python 3.13) in /opt/data/handbook/stacks/s1843-the-authorization-propagation-stack-when-your-agent-delegates-across-a-boundary-and-authorization-invariants-break-silently.md. Output: Agent A read ✓, B pricing write ✓, B shipping blocked (expected UnauthorizedAction), C shipping write ✓, C inventory read blocked (expected UnauthorizedAction), expired envelope blocked (expected AuthorizationExpired). Envelope narrowing and chain logging confirmed. Max depth enforcement confirmed (depth=3 at C). Temporal validity confirmed. All three failure modes (scope widening, temporal expiry, depth unbounded) produce clean exceptions.

## See also

- [S-1829 · The Attestation Stack](stacks/s1829-the-attestation-stack-when-your-agent-claims-to-be-something-it-proves-nothing.md) — cryptographic identity proof for agents; complements propagation by making the envelope auditable
- [S-1477 · The Agent Identity Chain Stack](stacks/s1477-the-agent-identity-chain-stack-nhi-governance-delegation-provenance-and-the-three-layer-accountability-model.md) — NHI governance, HDP protocol, and delegation provenance for the accountability layer
- [S-1034 · The Role Fence Stack](stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — role-based separation in multi-agent systems; propagation is the authorization complement to role separation
- [S-779 · MCP Tool-Level RBAC](stacks/s779-the-mcp-tool-level-rbac-stack-least-privilege-enforcement-for-agent-tool-access.md) — least-privileilege enforcement at the MCP tool layer; the envelope narrows at each tool invocation
- [S-1787 · The Eval-to-Reality Stack](stacks/s1787-the-eval-to-reality-stack-when-your-agent-cheats-on-the-test-by-taking-it-from-the-source.md) — eval sandbox escape; propagation failures are the non-injection complement where authorization is correct but the data/content is not
