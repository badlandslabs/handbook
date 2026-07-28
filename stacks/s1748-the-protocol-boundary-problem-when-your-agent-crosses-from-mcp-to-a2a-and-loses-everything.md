# S-1748 · The Protocol Boundary Problem — When Your Agent Crosses from MCP to A2A and Loses Everything It Knew

You built a multi-agent system. Agent A uses MCP to connect to your database, file store, and search index. Agent B lives across a trust boundary and speaks A2A. When Agent A needs Agent B's help, it delegates through A2A — and everything breaks. Credentials don't survive the handoff. Rich context becomes flat text. Streaming responses evaporate. Agent B doesn't know what Agent A already did, what state it left behind, or what permissions it carried across. This is the protocol boundary problem: the seam between MCP and A2A is where agents forget who they are.

## Forces

- **MCP is tight-coupling; A2A is loose-coupling.** MCP shares the agent's full execution context with tools — same process, same memory, same auth context. A2A communicates over HTTP with JSON-RPC messages. Crossing between them means translating rich, stateful execution into a stateless request-and-response. Something always gets lost.
- **Capability semantics don't survive serialization.** In MCP, the agent's session carries a full auth context with fine-grained scopes (read this table, write to that API, no file execution). When you serialize this for A2A delegation, you get a JWT bearer token — and the receiving agent has no idea whether that token grants read-only or admin access. The capability model is fundamentally different on each side.
- **MCP v2 introduced rich streaming and typed payloads.** A2A's artifact model is flat — it handles file and data transfers but has no concept of MCP's server-initiated tool announcements, streaming tool responses, or typed resource subscriptions. A tool that streams a 50MB file result over MCP delivers it inline. Over A2A, that same artifact must be chunked, referenced by URL, or base64-encoded in a message — none of which A2A specifies. Practitioners are inventing workarounds independently.
- **Context doesn't flow across the boundary.** MCP tools can read the agent's current conversation context. A2A delegates a task with a prompt and artifacts — but not the full state of what the delegating agent already did, what it found in the database, or what intermediate results are cached in memory. The receiving agent has to either ask back (adding latency) or guess.
- **The boundary is where security posture collapses.** Every A2A message from a delegating agent carries implicit authority — "I am acting on behalf of this user" — but A2A's trust model is at the agent level, not the action level. The MCP server on the other side of Agent A doesn't know that Agent B's request originated from an authenticated user. It just sees an agent. This is the gap that the OWASP ASI and the Guard0 threat landscape both flag as critical: cross-protocol trust propagation.

## The move

**Acknowledge the boundary and encode what crosses it.**

The protocols are not competitors — they solve different problems. MCP is vertical (agent → tool). A2A is horizontal (agent → agent). The stack is using them together. The failure happens at the seam, and the seam requires explicit design.

```python
# Annotated delegation: what gets lost crossing MCP → A2A
# and how to encode it explicitly

from dataclasses import dataclass, field
from typing import Any
import json

@dataclass
class ProtocolBoundaryManifest:
    """
    Encodes the execution state that must survive the MCP→A2A handoff.
    Without this, the receiving agent has no idea what the delegating
    agent already did or what authority it carried.
    """
    task_id: str
    originating_user_id: str
    capabilities_granted: list[str]  # what Agent A was allowed to do
    capabilities_needed: list[str]  # what Agent B needs to complete the work
    execution_summary: str           # what Agent A already did (not raw logs — a summary)
    partial_results: dict[str, Any]  # intermediate state: search hits, DB reads, etc.
    context_window_bytes: int = 0     # how much context was consumed on the A side
    delegation_depth: int = 1        # how many hops deep; >3 is a red flag

    def encode_for_a2a(self) -> dict[str, Any]:
        """
        Serialize as an A2A TaskInput artifact.
        The receiving agent reads this before acting.
        """
        return {
            "task_id": self.task_id,
            "delegation_manifest": {
                "user_id": self.originating_user_id,
                "capabilities_requested": self.capabilities_needed,
                "capabilities_available": self.capabilities_granted,
                "what_already_happened": self.execution_summary,
                "intermediate_results": self.partial_results,
                "context_pressure": f"{self.context_window_bytes / 1024:.0f}KB",
                "delegation_chain_length": self.delegation_depth,
            },
            "instructions": (
                f"User {self.originating_user_id} requested: [task description]. "
                f"Agent A already did: {self.execution_summary}. "
                f"Results available: {list(self.partial_results.keys())}. "
                f"Request only the capabilities you need: {self.capabilities_needed}. "
                f"If you need more than {self.capabilities_needed}, call back before acting."
            ),
        }


@dataclass
class A2ACapabilityGate:
    """
    Validates that a cross-protocol delegation does not escalate authority.
    MCP scopes are richer than A2A tokens — this gate translates and restricts.
    """
    required_capabilities: list[str]
    max_delegation_depth: int = 3

    def authorize(self, manifest: ProtocolBoundaryManifest) -> bool:
        if manifest.delegation_depth > self.max_delegation_depth:
            return False  # too many hops — break the chain

        # The A2A agent can only use capabilities the MCP side was granted.
        # Any capability not in the manifest's granted set must be denied.
        granted = set(manifest.capabilities_granted)
        needed = set(manifest.capabilities_needed)
        unauthorized = needed - granted

        if unauthorized:
            return False  # A2A agent wants more than MCP agent was allowed

        return True
```

**Enforce the gate at the delegation point, not in either protocol.**

The MCP server doesn't know about A2A. The A2A client doesn't know about MCP scopes. The boundary enforcement lives at the orchestrator that sits between them. This is the same pattern as a network firewall — it doesn't live inside either network, it lives at the interface.

```python
# Orchestrator-side enforcement at the MCP ↔ A2A boundary
# (lives in your agent harness, not in either protocol)

async def delegate_across_boundary(
    agent_a_context: dict,    # MCP-side state
    task: str,
    target_agent_card: dict, # A2A agent card from /.well-known/agent.json
    max_depth: int = 3,
) -> dict[str, Any]:
    manifest = ProtocolBoundaryManifest(
        task_id=agent_a_context["task_id"],
        originating_user_id=agent_a_context["user_id"],
        capabilities_granted=agent_a_context["mcp_scopes"],
        capabilities_needed=infer_required_capabilities(target_agent_card, task),
        execution_summary=summarize_mcp_execution(agent_a_context),
        partial_results=extract_partial_results(agent_a_context),
        context_window_bytes=estimate_context_pressure(agent_a_context),
        delegation_depth=agent_a_context.get("a2a_depth", 0) + 1,
    )

    gate = A2ACapabilityGate(
        required_capabilities=manifest.capabilities_needed,
        max_delegation_depth=max_depth,
    )

    if not gate.authorize(manifest):
        raise PermissionError(
            f"A2A delegation would escalate: needs {manifest.capabilities_needed}, "
            f"has {manifest.capabilities_granted}"
        )

    # Serialize and send via A2A
    a2a_message = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "taskId": manifest.task_id,
            "input": manifest.encode_for_a2a(),
        },
    }
    return await send_a2a_message(target_agent_card, a2a_message)
```

**Key principles:**
- **Capability translation is not 1:1.** MCP's resource-scoped tokens cannot be naively mapped to A2A bearer tokens. Encode the scope difference explicitly in the manifest.
- **Context summaries, not full logs.** Don't stream raw MCP execution logs across A2A — the receiving agent can't parse them. Use a summarizer to produce a two-sentence execution summary.
- **Chain-length tracking.** Every A2A hop increases the blast radius of a credential leak. Track delegation depth and hard-cap it at 3.
- **Callback instead of trust.** If the A2A agent needs a capability the delegating agent didn't carry, it should return a `input-required` status rather than silently acting with implied permissions.
- **MCP v2 workarounds.** MCP v2's server-initiated tool announcements and streaming responses have no A2A equivalent. Until the protocol specs converge, encode streaming results as artifact URLs with TTLs — not as inline payloads.

## See also

- [S-14 · A2A Protocol](s14-a2a-protocol.md) — A2A basics and the three-layer agentic stack
- [S-972 · The Agent Trust Negotiation Stack](stacks/s972-the-agent-trust-negotiation-stack-when-your-agent-has-to-prove-itself-to-another-agent.md) — cross-agent authentication
- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — deterministic enforcement at the MCP/A2A gateway
- [S-1746 · The Non-Human Identity Governance Stack](stacks/s1746-the-non-human-identity-governance-stack-when-your-agent-fleet-has-no-identity-no-credentials-and-no-audit-trail.md) — credential scoping for agent fleets
- [S-1747 · The Hierarchical Orchestration Stack](stacks/s1747-the-hierarchical-orchestration-stack-when-your-agent-fleet-lacks-a-coordinator.md) — coordinator patterns for multi-agent fleets
