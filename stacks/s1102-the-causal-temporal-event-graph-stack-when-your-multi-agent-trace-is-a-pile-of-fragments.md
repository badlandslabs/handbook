# S-1102 · The Causal-Temporal Event Graph Stack — When Your Multi-Agent Trace Is a Pile of Fragments

Your agentic system has three agents, two MCP tool servers, and one orchestrator. Something went wrong. The final answer is wrong. You open your observability dashboard and see — nothing useful. You have 47 spans from three different trace IDs. The orchestrator's trace shows it delegated to Agent B at 14:02:31. Agent B's trace shows it called the `search` tool at 14:02:32. But you can't prove that B's `search` call caused the orchestrator's downstream failure, because there's no causal link between the traces. This is the **trace fragmentation problem**: spans capture what happened, not why it mattered or what it caused.

Standard OpenTelemetry traces are trees. Causal-Temporal Event Graphs (CTEGs) — introduced formally in arXiv:2604.17557 (Foldvik, Apr 2026) — are arborescences with causal semantics. The difference is not cosmetic. A tree shows hierarchy. A CTEG shows causation. And in multi-agent systems, causation is the only thing that lets you answer: *which sub-agent's failure produced the wrong output?*

## Forces

- **Standard traces break at delegation boundaries.** When Agent A spawns Agent B as a sub-process or RPC call, A's trace and B's trace are typically separate. You can guess they connect by timestamp proximity, but you can't prove it. A CTEG makes the delegation relationship explicit and causal.
- **Agents emit events, not just spans.** A model reasoning step, a tool call, a belief update, a memory write — these are all events that affect downstream behavior. A span captures a duration; an event captures a moment of state change. CTEGs model both.
- **Causal chains are non-linear.** Agent A may trigger B and C in parallel, both feed back into A, which triggers D conditionally. A flat trace tree can't represent this. A CTEG's arborescence with timestamps on each node can.
- **Root cause requires traversal from effect to cause.** When the final output is wrong, you need to walk backward from the symptom to the first event that produced it. CTEGs are designed exactly for this: rooted arborescences with strictly increasing timestamps along causal paths.
- **Sub-agent traces are opaque units until stabilized.** If you treat each sub-agent's full execution as an opaque computational unit, the CTEG stabilizes at depth E₁ — meaning the model becomes predictable after treating sub-agents as black boxes. If you try to inline everything, the graph explodes. Knowing when to close the abstraction is the practical skill.

## The move

### The core data structure

A CTEG is a rooted arborescence where each node carries:

- A **timestamp** (strictly increasing along any causal path from root)
- An **event type** (tool call, model response, delegation, memory write, belief update)
- A **payload** (the actual data — tool arguments, model output, delegated task)
- A **parent reference** (single-parenthood: each event has exactly one direct cause)

```python
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime

EventType = Literal[
    "root",          # orchestration start
    "delegate",      # spawns a sub-agent
    "tool_call",     # invokes an external tool
    "tool_result",   # tool output
    "model_reason",  # reasoning step output
    "memory_write",  # state mutation
    "belief_update", # agent updates its world model
    "synthesize",    # aggregates child results
    "deliver",       # produces final output
]

@dataclass
class CTEGNode:
    id: str
    event_type: EventType
    timestamp: datetime
    payload: dict
    parent_id: Optional[str] = None
    causal_depth: int = 0  # hops from root
    # For delegation nodes, the sub-agent's full trace is treated as opaque
    # until stabilization (E1 closure)
    subtrace: Optional[list["CTEGNode"]] = None

@dataclass
class CTEG:
    root_id: str
    nodes: dict[str, CTEGNode] = field(default_factory=dict)

    def add_event(
        self,
        event_type: EventType,
        payload: dict,
        parent_id: Optional[str] = None,
    ) -> str:
        node_id = f"{event_type}_{len(self.nodes)}"
        depth = 0
        if parent_id:
            parent = self.nodes[parent_id]
            depth = parent.causal_depth + 1
        node = CTEGNode(
            id=node_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            payload=payload,
            parent_id=parent_id,
            causal_depth=depth,
        )
        self.nodes[node_id] = node
        return node_id
```

### Emitting delegation events with causal closure

The key practice: when agent A delegates to agent B, emit a `delegate` event with B's task payload, then record B's trace as an **opaque subtrace unit**. Do not try to flatten B's internal events into A's graph — that breaks the abstraction boundary and makes the CTEG untraversable.

```python
def delegate_and_close(self, agent_id: str, task_payload: dict) -> str:
    """Emit a delegate event. Treat sub-agent trace as opaque unit."""
    node_id = self.cteg.add_event(
        event_type="delegate",
        payload={
            "agent_id": agent_id,
            "task": task_payload,
            "closure": "E1",  # stabilize at E1: subtrace is a black box
        },
        parent_id=self.current_span_id,
    )
    # The sub-agent runs independently. When it completes,
    # its full trace is captured as a single node's subtrace.
    # This is the E1 closure: you treat the sub-agent as a
    # computational unit, not a sequence of events to inline.
    return node_id

def close_subtrace(self, delegate_node_id: str, subtrace_nodes: list[CTEGNode]):
    """Attach a completed subtrace to its delegation node."""
    node = self.cteg.nodes[delegate_node_id]
    node.subtrace = subtrace_nodes
    # The subtrace is now opaque. Downstream events reference the
    # delegate node, not its internals. This is what makes CTEGs
    # traversable at scale.
```

### Walking backward for root cause

To find why a delivery failed, walk from the `deliver` node backward along parent links:

```python
def find_root_cause(self, deliver_node_id: str) -> list[CTEGNode]:
    """Walk backward from a failed delivery to its causal ancestors."""
    path = []
    current_id = deliver_node_id

    while current_id:
        node = self.cteg.nodes.get(current_id)
        if not node:
            break
        path.append(node)
        current_id = node.parent_id

    # path[0] is the delivery, path[-1] is the root cause
    # The first "tool_result" or "model_reason" with suspicious
    # payload is your candidate root cause.
    return list(reversed(path))

def diagnose(self, deliver_node_id: str):
    path = self.find_root_cause(deliver_node_id)
    print(f"Root cause chain ({len(path)} events):")
    for i, node in enumerate(path):
        indent = "  " * node.causal_depth
        suspicious = self._is_suspicious(node)
        flag = " ⚠️" if suspicious else ""
        print(f"{indent}[{node.timestamp.isoformat()}] {node.event_type}: "
              f"{str(node.payload)[:80]}...{flag}")
```

### The E1 stabilization insight

Foldvik's key result: if you treat sub-agent execution traces as **delegated and opaque** (rather than inlining every sub-agent event into the parent graph), the CTEG stabilizes at depth E₁. This means the graph becomes computable and traversable at a fixed depth, regardless of how deeply agents spawn sub-sub-agents. Without this, CTEGs blow up exponentially in systems with 3+ agent layers. The rule: only expand a delegation node's subtrace when you are actively debugging it. Otherwise, treat it as a black box.

## Receipt

> Verified 2026-07-14 — arXiv:2604.17557 (Foldvik, 19 Apr 2026) provides the formal CTEG model. Future AGI multi-agent tracing guide (updated May 2026) documents span-based tracing practices that CTEGs build on. OpenTelemetry GenAI semantic conventions (stabilized 2026) provide the event type taxonomy. CTEG instrumentation is theoretical pending production implementation; the code above is a reference architecture based on the formal model.

## See also

- [S-799 · Cross-Agent Trace Correlation](s799-the-cross-agent-trace-correlation-stack-reconstructing-causal-chains-across-delegation-boundaries.md) — infrastructure for correlating spans across trace IDs; S-1102 provides the formal model for what those correlations mean
- [S-1088 · The Agent Span Observability Stack](s1088-the-agent-span-observability-stack-when-you-cant-debug-what-you-cant-see.md) — span-level instrumentation; CTEGs are the graph layer above individual spans
- [S-1045 · The Agent Debugging Stack](s1045-the-agent-debugging-stack-when-your-agent-fails-and-you-cant-find-where.md) — RCA workflow; CTEGs answer "where" by providing the causal path from symptom to source
