# S-1527 · The Effect Outbox Stack — When Your Agent Acts Before You Approve

Your agent reads a poisoned document, generates a $340,000 wire transfer instruction, and fires it at the payment API. By the time the output reaches the network, it has already happened. The agent didn't "hack" itself — it followed its instructions correctly. The instructions were just wrong, because the data was untrusted. This is the Effect Outbox: the pattern that makes agent effects transactional, auditable, and stoppable *before* they reach the outside world.

## Forces

- **Agents are proposal engines, not execution engines.** An agent generates actions. In stateless RPC agent runtimes, generation and execution are the same call — the moment the LLM produces `POST /transfer`, it fires. But generation includes reasoning about untrusted data, which means the action carries provenance from whatever polluted the context.
- **Multi-step reasoning multiplies the attack surface.** A single poisoned document can shape the entire plan. By step 8 of a 10-step workflow, the agent's goal may have drifted so far from the original intent that the final action is catastrophically wrong but perfectly logical within the agent's (now-corrupted) frame.
- **Trust boundaries live between the agent and the world.** The filesystem, the database, the payment API, the email API — these are all trust boundaries. Traditional guardrails and prompt filters sit *inside* the agent (they filter inputs). They don't sit at the output boundary where the agent's effects actually reach the world.
- **Effect ordering matters for non-idempotent operations.** A read-then-write, or a write-then-transfer, is a trajectory — not a pair of independent events. Stateless RPC treats every call as atomic and independent. The failure of one reveals that the others were contingent.

## The Move

**Split the agent's output into two phases: generation and commitment.** The agent proposes effects; they land in an effect outbox. A reference monitor reviews each effect before it executes, tracing the data lineage back to its origin and classifying the action's risk.

### 1. The Effect Outbox

Every action the agent generates — tool call, API request, file write, state mutation — is intercepted before it fires and placed in a staging outbox as an `EffectRecord`:

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Any

class EffectRisk(Enum):
    READ_ONLY = 0      # No side effects — auto-approve
    LOW = 1            # Read with minor state (cache write, log)
    MEDIUM = 2         # State mutation (DB write, file create)
    HIGH = 3           # External communication (email, payment, API call)
    CRITICAL = 4       # Financial, regulatory, or irreversible

@dataclass
class EffectRecord:
    effect_id: str
    agent_id: str
    proposed_at: datetime
    effect_type: str              # "http_request", "file_write", "db_query"
    target: str                   # URL, file path, table name
    parameters: dict[str, Any]
    risk_level: EffectRisk
    data_provenance: list[str]    # IDs of input artifacts this effect depends on
    status: str = "PENDING"       # PENDING → APPROVED → COMMITTED / REJECTED
    rejection_reason: str | None = None

    def trace_provenance(self) -> dict[str, Any]:
        """Walk the artifact graph back to root sources."""
        provenance = {"effect": self.effect_id, "ancestors": []}
        for artifact_id in self.data_provenance:
            artifact = artifact_registry.get(artifact_id)
            if artifact:
                provenance["ancestors"].append({
                    "artifact_id": artifact_id,
                    "source": artifact.source,
                    "trust_level": artifact.trust_level,
                    "ingested_at": artifact.ingested_at,
                    "parent_artifacts": artifact.parent_ids
                })
        return provenance
```

### 2. The Reference Monitor

The reference monitor inspects each `PENDING` effect before commitment. It has two jobs: trace provenance and enforce policy.

```python
@dataclass
class ReferenceMonitor:
    outbox: list[EffectRecord]
    policy_engine: PolicyEngine
    artifact_registry: ArtifactRegistry

    async def review(self, effect: EffectRecord) -> EffectRecord:
        # Step 1: Classify risk from the artifact graph
        provenance = effect.trace_provenance()
        untrusted_inputs = [
            a for a in provenance["ancestors"]
            if a.get("trust_level", "trusted") == "untrusted"
        ]

        # Step 2: Escalate risk if untrusted data flows to sensitive operations
        if untrusted_inputs and effect.risk_level.value >= EffectRisk.MEDIUM.value:
            effect.risk_level = EffectRisk.CRITICAL

        # Step 3: Enforce policy
        verdict = self.policy_engine.should_commit(effect, provenance)

        if verdict.approved:
            effect.status = "APPROVED"
        else:
            effect.status = "REJECTED"
            effect.rejection_reason = verdict.reason
            # Notify human reviewer if HIGH/CRITICAL
            if effect.risk_level.value >= EffectRisk.HIGH.value:
                await alert_human_review(effect, provenance)

        return effect

    async def commit_approved(self) -> list[EffectRecord]:
        """Commit all APPROVED effects in topological order."""
        committed = []
        for effect in self.outbox:
            if effect.status == "APPROVED":
                try:
                    await self.execute_effect(effect)
                    effect.status = "COMMITTED"
                except Exception as exc:
                    # Rollback siblings — effects are transactional as a set
                    await self.rollback_group(effect)
                    effect.status = "REJECTED"
                    effect.rejection_reason = f"commit failed: {exc}"
                committed.append(effect)
        return committed
```

### 3. Provenance-Aware Tool Wrappers

Wrap every outbound tool call to route through the outbox instead of executing directly:

```python
from functools import wraps

def outboxed_tool(tool_name: str, base_risk: EffectRisk = EffectRisk.MEDIUM):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, context: AgentContext, **kwargs):
            effect = EffectRecord(
                effect_id=uuid4(),
                agent_id=context.agent_id,
                proposed_at=datetime.utcnow(),
                effect_type=tool_name,
                target=kwargs.get("url") or kwargs.get("path") or "memory",
                parameters={"args": args, "kwargs": kwargs},
                risk_level=base_risk,
                data_provenance=context.active_provenance_ids
            )
            # Always go through the reference monitor
            monitor = context.reference_monitor
            reviewed = await monitor.review(effect)

            if reviewed.status == "REJECTED":
                return {"error": "effect_blocked", "reason": reviewed.rejection_reason}

            # Approved — execute
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Usage: replace direct API calls
@outboxed_tool("payment_api", base_risk=EffectRisk.CRITICAL)
async def send_wire_transfer(account: str, amount: float, routing: str):
    """Now requires reference monitor approval before firing."""
    ...

@outboxed_tool("email_send", base_risk=EffectRisk.HIGH)
async def send_email(to: str, subject: str, body: str):
    ...
```

## Receipt

> Receipt pending — 2026-07-23

Pattern synthesized from Latent Dynamics "Semantic Transactions" (effect outbox + reference monitor at OS runtime boundary), arXiv:2602.10465 "Authenticated Workflows" (four boundary model: prompts, tools, data, context with authenticity + integrity at each crossing), and CSA Cloud Navigator / CloudSAFE research on agent execution boundary enforcement. The $340,000 transfer stop is documented by Latent Dynamics. Reference implementation is architectural pattern guidance; individual components (outbox, monitor, provenance tracker) have production implementations at multiple organizations.

## See also

- [S-1013 · Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — the coordination problem; S-1527 is the security sibling
- [S-1075 · Ephemeral Delegation Stack](/stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credentials should never leave the outbox's trust boundary
- [S-1238 · Authorization Gap](/stacks/s1238-the-authorization-gap-when-your-ai-agent-holds-keys-it-shouldnt-use.md) — the authorization gap is wider when there is no outbox to close it
- [S-1006 · Agent Toolbelt Problem](/stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — every tool is a potential effect target; wrap them all
- [S-1181 · Agentic Gateway Stack](/stacks/s1181-the-agentic-gateway-stack-when-your-fleet-runs-but-nobody-owns-the-flow.md) — the outbox can live in the gateway layer as a fleet-wide enforcement point
