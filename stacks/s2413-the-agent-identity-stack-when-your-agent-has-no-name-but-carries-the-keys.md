# S-2413 · The Agent Identity Stack — When Your Agent Has No Name But Carries the Keys

Your incident review finds something unsettling: a support agent deleted 847 customer records last week. It had access to a service account with write permissions to the customer database. Every log entry shows the request came from "Claude Code." No one knows which agent, which workflow, or which invocation — because none of your agent runs have a verifiable identity. The agent operated as a first-class actor with real-world consequences and a zero-personality credential. This is the agent identity gap.

## Forces

- **Agents are the only principals without an identity system.** Users have UPNs. Services have service principals. Workloads have managed identities. Agents — autonomous code acting on behalf of all of these — have none of the above. They inherit credentials from wherever they can find them, and logs reflect the inherited identity, not the agent's.
- **Authorization decisions need to know who is asking.** Every RBAC system, every ABAC policy, every audit trail depends on the caller's identity. When the caller is a probabilistic reasoning engine with tool access, the entire authorization model collapses: the credential belongs to a human or a service, not to the agent using it.
- **The audit trail is useless without attribution.** "User X's token called the delete endpoint" is not an audit — it's noise. You need "Agent A running workflow B, acting within policy C, invoked this tool at this time." Without agent identity, you cannot distinguish one agent's authorized actions from another's, or from a compromised credential.
- **Agent lifecycles don't match human or service lifecycles.** Agents are created, cloned, updated, and destroyed dynamically — often within a single session. A human's RBAC role rotates quarterly. An agent's effective permissions may change on every model update. A static identity model breaks immediately.

## The move

**Give every agent a lifecycle-managed identity bound to a capability manifest — not to the credentials it uses.**

### 1. Establish agent identity as a first-class concept

Assign every agent a unique, stable identifier scoped to its deployment context — an `AgentID` — separate from the human or service account that launched it. This is not a process ID (ephemeral) or a model version (changes on upgrade). It is a named principal with its own metadata: owner, purpose, creation time, trust level, and policy constraints.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class TrustLevel(Enum):
    PROOF_OF_BEHAVIOR = "proof_of_behavior"  # PoB receipts verified
    COMPLIANCE_ATTESTED = "compliance_attested"  # Audit-signed manifest
    STANDARD = "standard"  # Manifest + runtime monitoring
    PILOT = "pilot"  # No production data, human-in-loop

@dataclass
class AgentIdentity:
    agent_id: str                    # e.g., "support-agent-prod-v3"
    principal_owner: str              # team or human accountable
    purpose: str                     # "customer support ticket resolution"
    trust_level: TrustLevel
    created_at: datetime
    tool_manifest: list[str]         # approved tool names only
    policy_constraints: dict        # e.g., {"max_refund_usd": 500, "readonly_db": False}
    parent_identity: str | None      # for agent-of-agent hierarchies
    attestation_scheme: str = "none" # "pob", "eat", "agentledger", etc.
```

### 2. Bind capability manifests, not credentials, to authorization

Authorization policies must evaluate the agent's declared and verified capabilities — not the underlying service account's permissions. An agent with `AgentID = support-v3` should be authorized to read the customer database **only** if its manifest includes `read_customer`, regardless of whether the underlying service account has broader access. This is the shift from "what can this token do?" to "what should this agent be allowed to do?"

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class CapabilityBinding:
    agent_id: str
    bound_tools: list[str]       # only these tools are authorized
    bound_resources: list[str]    # only these resources (URIs, tables)
    max_action_value: dict        # monetary, record-count, etc.
    jit_approvals_required: list[str]  # e.g., ["delete_customer", "bulk_refund"]
    verification_required: bool = True  # post-action PoB receipt check

def authorize_agent_action(
    binding: CapabilityBinding,
    requested_tool: str,
    requested_resource: str,
) -> tuple[bool, str]:
    """Check if agent's capability binding covers this action."""
    if requested_tool not in binding.bound_tools:
        return False, f"tool '{requested_tool}' not in {binding.agent_id} manifest"
    if requested_resource not in binding.bound_resources:
        return False, f"resource not in {binding.agent_id} scope"
    return True, "authorized"
```

### 3. Enforce time-boxed, just-in-time elevation (JIT)

Agents doing routine work should operate with minimal privileges. For actions that require more — deleting a customer record, approving a large refund — request a short-lived elevated token via a human-in-the-loop approval or an automated policy gate. This is the JIT entitlement model: privilege exists only for the duration of a specific workflow.

```python
import time, secrets, hashlib

@dataclass
class JITSessions:
    active_sessions: dict = field(default_factory=dict)

    def request_elevation(
        self, agent_id: str, required_capability: str, justification: str,
        ttl_seconds: int = 300
    ) -> str | None:
        session_id = hashlib.sha256(
            f"{agent_id}:{required_capability}:{time.time()}:{secrets.token_hex(8)}".encode()
        ).hexdigest()[:16]
        self.active_sessions[session_id] = {
            "agent_id": agent_id,
            "capability": required_capability,
            "justification": justification,
            "expires_at": time.time() + ttl_seconds,
        }
        return session_id

    def use_elevation(self, session_id: str) -> bool:
        session = self.active_sessions.get(session_id)
        if not session or time.time() > session["expires_at"]:
            return False
        del self.active_sessions[session_id]
        return True
```

### 4. Attach PoB receipts to every action

The IETF AgentLedger Proof-of-Behavior (PoB) protocol (draft-dembowski-agentledger-pob, April 2026) defines a signed, tamper-evident receipt format that proves: the agent declared a behavioral rule, policy enforcement occurred before execution, and the action log is unmodified. Every tool invocation should produce a PoB receipt.

```python
import json, hashlib, hmac, time

class PoBReceipt:
    """Simplified Proof-of-Behavior receipt (AgentLedger draft, 2026)."""
    def __init__(self, agent_id: str, private_key: str):
        self.agent_id = agent_id
        self._sign = lambda data: hmac.new(
            private_key.encode(), data.encode(), hashlib.sha256
        ).hexdigest()

    def create_receipt(
        self, action: str, params: dict, policy_hash: str,
        enforcement_point: str, prev_receipt_hash: str = "GENESIS"
    ) -> dict:
        payload = json.dumps({"action": action, "params": params}, sort_keys=True)
        receipt = {
            "agent_id": self.agent_id,
            "timestamp": int(time.time()),
            "policy_hash": policy_hash,
            "enforcement_point": enforcement_point,
            "prev_receipt_hash": prev_receipt_hash,
            "action_digest": hashlib.sha256(payload.encode()).hexdigest(),
            "signature": self._sign(f"{prev_receipt_hash}:{payload}:{policy_hash}"),
        }
        return receipt

    def verify(self, receipt: dict) -> bool:
        expected_sig = self._sign(
            f"{receipt['prev_receipt_hash']}:"
            f"{receipt['action_digest']}:{receipt['policy_hash']}"
        )
        return expected_sig == receipt["signature"]
```

### 5. Integrate with organizational identity infrastructure

Microsoft Entra Agent ID (GA, July 2026), Google Agent Identity, and cloud-native RBAC systems now support agent principals. Map your agent identity scheme to the organization's identity provider so that existing audit pipelines, compliance tools, and SIEM systems consume agent-aware events.

## Receipt

> Verified 2026-08-10 — Microsoft Security Blog (2026-07-16) documents Entra Agent ID GA with lifecycle-managed identity + JIT entitlements. IETF AgentLedger PoB draft (2026-04-20) defines the receipt schema with pre/post hash chain. CSA AI Safety Initiative (2026) documents that 76% of enterprises have CAIOs but only 13% believe they have adequate agent governance. Armalo Labs (2026-05) reports 30 production attestations across behavioral_summary and filesystem_provenance types. OWASP Top 10 for Agentic AI (Dec 2025) designates "Excessive Agency" (ASI03) as a top-tier risk: agents taking more actions than intended. Draft-huang-rats-agentic-eat-cap-attest extends RFC9248 EAT with agent capability claims. Anthropic's agent system prompt guidance (2026) recommends explicit capability declaration per agent instance.

## See also

- [S-2291 · The MCP Supply Chain Stack](s2291-the-mcp-supply-chain-stack-when-your-tool-registry-is-your-attack-surface.md) — supply chain attacks begin where identity ends
- [F-200 · The Permission Guard Stack](forward-deployed/f200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — capability proof without identity is theater
- [S-2406 · The Orchestration Success Signal](stacks/s2406-the-orchestration-success-signal-when-your-sub-agent-returns-but-nothing-happened.md) — sub-agent attribution requires identity before it can require receipts
