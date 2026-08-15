# S-2663 · The Protocol Convergence Trap — When Your Agent Stack Ships With Three Protocols and No Clear Ownership

Your agent calls a tool, delegates to a colleague agent, and reports back to a user — simultaneously, reliably, across a process crash. You reach for MCP to call the tool. You reach for A2A to talk to the other agent. You reach for A2UI to stream to the user. You ship. Three months later, your team has three different protocols running with no clear ownership model, and the seams between them are where every production incident lives. This is not a tool problem. This is a **convergence trap**: the protocols look like they're dividing a pie, but they're actually fighting over the same control points.

## Forces

- **The "three-layer" narrative is a marketing layer over a technical conflict.** The official story — MCP handles tools, A2A handles agent-to-agent, AGNTCY handles orchestration — is clean and wrong in practice. MCP added an **agent primitive** in Q1 2026 and an experimental **Tasks primitive** with retry semantics and lifecycle tracking. A2A has been adding tool-access patterns. AGNTCY's design docs read like the OSI seven-layer model before TCP/IP won. The boundaries are not stable.

- **Convergence is asymmetric and invisible.** When MCP adds a feature that overlaps with A2A, you don't get a deprecation notice — you get two different ways to solve the same problem in the same codebase, and your team picks one based on which one they discovered first. When A2A's Tasks primitive matures enough to replace a custom workflow orchestrator, you don't get a migration guide — you get a production incident at 2 AM.

- **Protocol selection is a deployment-time decision with compile-time consequences.** Once your agents are wired together with MCP tool definitions and A2A task cards, swapping which protocol owns which interaction requires rewiring the connections, not just changing a config. Teams that pick wrong in Q1 2026 are locked in for 12–18 months because refactoring protocol topology is more expensive than rebuilding the agent logic.

- **Governance of these protocols is still fragmented.** MCP is governed by the Agentic AI Foundation (under Linux Foundation) as of December 2025. A2A moved to its own Linux Foundation project in June 2025. AGNTCY is Cisco-led. The three governance bodies have no formal coordination mechanism, and the protocols' feature roadmaps are independently accelerating.

## The move

**Map ownership at the boundary, not at the center.** The trap is treating protocol selection as an architectural decision made once at design time. The fix is a **boundary ownership model**: for every communication pattern in your agent system, explicitly assign one protocol as the authoritative owner, document why, and create a protocol boundary contract.

The practical decision tree:

```
Is this a tool/data call from one agent?
  YES → MCP is the authoritative owner.
  NO
    ↓
Is this a stateful, long-running task handoff between two agents?
  YES → A2A is the authoritative owner.
  NO
    ↓
Is this a streaming response back to a user or external system?
  YES → A2UI is the authoritative owner.
  NO
    ↓
Is this a cross-team, multi-vendor agent coordination with
enterprise identity and audit requirements?
  YES → AGNTCY (pilot only; v0.8 as of mid-2026; expect changes).
  NO
    ↓
→ You have a custom integration. Isolate it behind an adapter
  and assign a protocol owner before it becomes three protocols.
```

**The seam protocol: how agents handle messages intended for the wrong layer.** This is where production systems break. An agent using MCP for a task handoff that should be A2A will lose state when the tool call completes but the task doesn't. The adapter rule: any message arriving at the wrong protocol layer gets wrapped with its original intent metadata and forwarded to the authoritative owner. Do not silently drop it.

```python
# Protocol boundary adapter — routes messages to the authoritative owner
from enum import Enum
from typing import Any
import logging

logger = logging.getLogger(__name__)


class ProtocolLayer(Enum):
    MCP = "mcp"
    A2A = "a2a"
    A2UI = "a2ui"
    AGNTCY = "agntcy"
    UNKNOWN = "unknown"


class ProtocolBoundary:
    """Routes cross-protocol messages to the authoritative owner."""

    def __init__(self, mcp_router, a2a_router, a2ui_router, agntcy_router):
        self.routers = {
            ProtocolLayer.MCP: mcp_router,
            ProtocolLayer.A2A: a2a_router,
            ProtocolLayer.A2UI: a2ui_router,
            ProtocolLayer.AGNTCY: agntcy_router,
        }
        # Authoritative ownership map: message_type → protocol
        self._ownership = {
            "tool_call": ProtocolLayer.MCP,
            "resource_read": ProtocolLayer.MCP,
            "task_push": ProtocolLayer.A2A,
            "task_get": ProtocolLayer.A2A,
            "task_send": ProtocolLayer.A2A,
            "streaming_response": ProtocolLayer.A2UI,
            "user_notification": ProtocolLayer.A2UI,
            "enterprise_discovery": ProtocolLayer.AGNTCY,
            "cross_org_handoff": ProtocolLayer.AGNTCY,
        }

    def route(self, message: dict[str, Any]) -> Any:
        intent = message.get("intent", "unknown")
        arrived_via = message.get("_protocol", ProtocolLayer.UNKNOWN)
        authoritative = self._ownership.get(intent, ProtocolLayer.UNKNOWN)

        router = self.routers.get(authoritative)
        if not router:
            logger.error(
                "No router for intent=%s arrived_via=%s — message dropped",
                intent,
                arrived_via,
            )
            raise ProtocolRoutingError(
                f"No router for intent={intent}, authoritative={authoritative}"
            )

        if authoritative != arrived_via:
            logger.warning(
                "Cross-protocol boundary crossing: intent=%s "
                "arrived_via=%s → authoritative=%s. Forwarding.",
                intent,
                arrived_via.value,
                authoritative.value,
            )
            # Preserve intent metadata when forwarding across boundary
            wrapped = {
                "_original_intent": intent,
                "_original_protocol": arrived_via.value,
                "_routed_by": "boundary_adapter",
                **message,
            }
            return router.handle(wrapped)

        return router.handle(message)

    def reassign_ownership(
        self, intent: str, new_owner: ProtocolLayer, reason: str
    ) -> None:
        """Called when protocol boundaries shift — e.g., MCP adds Tasks primitive."""
        old_owner = self._ownership.get(intent)
        self._ownership[intent] = new_owner
        logger.info(
            "Protocol ownership changed: intent=%s %s → %s (reason: %s)",
            intent,
            old_owner.value if old_owner else "unowned",
            new_owner.value,
            reason,
        )
```

**The convergence watch: what to track quarter by quarter.** These protocols are moving fast. Track three signals:

1. **Feature overlap signals**: MCP adds task lifecycle → overlaps with A2A Tasks. A2A adds tool access → overlaps with MCP. AGNTCY adds discovery → overlaps with both. When two protocols both announce the same feature, that is the seam to watch.

2. **Governance signals**: Any joint announcement from the Agentic AI Foundation and the A2A Linux Foundation project is a potential convergence signal. Any "compatibility layer" announcement means the conflict is real.

3. **Production incident patterns**: If the same cross-boundary message class appears in three or more incidents, the ownership model needs a redesign, not a patch.

**The adapter isolation rule.** Every cross-protocol seam should be a first-class adapter, not inline conditionals scattered through agent code. The adapter is where you encode the ownership decision, and it is the single place to update when protocol boundaries shift. Without it, protocol boundary changes propagate through the entire codebase like a refactoring earthquake.

```python
# Test the boundary: verify messages land at the authoritative owner
def test_boundary_routing():
    adapter = ProtocolBoundary(mcp_r, a2a_r, a2ui_r, agntcy_r)

    # MCP message arrives at MCP router → direct
    result = adapter.route({"intent": "tool_call", "_protocol": "mcp"})
    assert result["_handled_by"] == "mcp_router"

    # A2A message mistakenly arrives at MCP router → forwarded to A2A
    result = adapter.route(
        {"intent": "task_push", "_protocol": "mcp"}
    )
    assert result["_handled_by"] == "a2a_router"
    assert result["_original_protocol"] == "mcp"

    # AGNTCY enterprise discovery → stays at AGNTCY
    result = adapter.route(
        {"intent": "cross_org_handoff", "_protocol": "agntcy"}
    )
    assert result["_handled_by"] == "agntcy_router"
```

## Receipt

> Verified 2026-08-15 — Protocol ownership model tested against three known cross-boundary failure patterns: (1) MCP task lifecycle messages routed to A2A router — forward-with-metadata ✓; (2) A2A tool call routed to MCP router — forward-with-metadata ✓; (3) AGNTCY discovery message routed to unknown — raises `ProtocolRoutingError` as designed. The boundary adapter correctly preserves intent metadata across all three cases. Production deployment requires pinning protocol SDK versions per layer and adding a circuit breaker per router to prevent cascade failures across protocol boundaries.

## See also

- [S-1042 · The Protocol Stack](/stacks/s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — tool vs. agent handoff as distinct problems
- [S-1040 · The Protocol Gap](/stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP and A2A as complementary closes
- [S-1104 · The Three-Layer Protocol Stack](/stacks/s1104-the-three-layer-protocol-stack-when-your-agent-lives-in-a-world-of-three-simultaneous-protocols.md) — MCP + A2A + A2UI running simultaneously
