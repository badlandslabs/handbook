# S-1505 · The Graph Engineering Stack — When Your Multi-Agent System Is a Programmable Topology

Your first multi-agent system starts as a Python script: Agent A calls Agent B. Then you add a reviewer. Then a fallback. Then a second path for premium users. Three months later, the "script" is a tangled web of function calls with no clear ownership, no version history, and no way to route around the reviewer without a code change. You didn't have an architecture problem — you had a topology problem. Graph engineering is the discipline of treating that topology as a first-class, versionable artifact from day one.

## Forces

- **Topology "emerges" from code by default.** The natural way to build multi-agent systems is to write agents and connect them with function calls. The resulting topology is invisible — not modeled, not versioned, not introspectable — until it breaks.
- **Topology determines reliability, cost, and latency more than any other factor.** S-1067 established that orchestration pattern choice is a major driver of outcomes. Graph engineering goes further: the ownership structure, edge semantics, and shared-state boundaries are the topology decisions that compound at scale.
- **Hard to refactor after launch.** Unlike prompts or model choices, topology changes often require rewriting the connections between agents. Teams defer the investment until the cost is already being paid.
- **Governance requires topology.** EU AI Act Article 12 (effective August 2, 2026) requires tracing every delegation chain. A graph representation makes this trivially queryable. A tangled function-call graph makes it impossible.

## The Move

Graph engineering models a multi-agent system as an explicit directed graph: **nodes** (agents, functions, routers, joins, human checkpoints) connected by **edges** (routing relationships with semantics). The graph itself is a versionable, deployable artifact — not embedded in application code.

### The Three Components

**Nodes** are the units of work. Each node has a single responsibility and a defined ownership boundary:
- Specialized agents (researcher, writer, reviewer, security-checker)
- Deterministic functions (schema validation, data transform, cost gate)
- Routers (conditional dispatch based on input shape or confidence)
- Joins (wait for N inputs before proceeding)
- Human checkpoints (pause for approval on high-stakes edges)

**Edges** carry work and metadata between nodes. Each edge is typed:
- `sequential` — pass output to next node
- `conditional` — pass to branch A or B based on a predicate
- `fan-out` — dispatch to multiple nodes in parallel, collect results
- `fan-in` — wait for all fan-out results before proceeding
- `fallback` — try primary, route to fallback on failure
- `escalation` — route to human reviewer or supervisor

**Shared state** flows along edges or is stored in a graph-level context:
- Passed as edge payloads (explicit, traceable)
- Held in a shared context store (implicit, must be scoped)
- Governance metadata: which policy version governs each node, audit IDs, data classification

### Ownership Topology: The First Design Decision

Before routing logic, define **ownership boundaries**: which agent owns which domain, tool, or data. This mirrors organizational structure and maps directly to EU AI Act Article 12 accountability requirements.

```
Security agent    → owns auth, permissions, audit logs
Data agent        → owns schema, migrations, data quality
API agent         → owns endpoints, rate limits, response contracts
Frontend agent    → owns component rendering, user-facing validation
```

Each node is accountable through exactly one owner. Cross-node data access requires an explicit edge, not shared mutable state.

### Topology as a Versioned Artifact

The graph definition lives in a declarative format (YAML, JSON, or a DSL) separate from node implementations:

```yaml
# agent-graph.yaml — versioned topology definition
version: "1.3"
nodes:
  intake_router:
    type: router
    owner: platform-team
  researcher:
    type: agent
    model: claude-sonnet-4
    owner: research-team
    max_steps: 8
  writer:
    type: agent
    model: gpt-4o-mini
    owner: content-team
    depends_on: [researcher]
  security_review:
    type: agent
    model: claude-opus-4
    owner: security-team
    mandatory: true   # always runs, non-skippable
  human_approval:
    type: human_check
    owner: compliance-team
    trigger: output.confidence < 0.7 OR action.write == true

edges:
  - from: intake_router
    to: researcher
    type: sequential
  - from: researcher
    to: security_review
    type: sequential
  - from: security_review
    to: [writer, human_approval]
    type: conditional
    predicate: security_review.clear == true
  - from: writer
    to: human_approval
    type: conditional
    predicate: writer.action.flags_write == true
```

This format enables:
- **Topology diffing** — what changed between v1.2 and v1.3?
- **Simulated dry runs** — test routing logic without running agents
- **Policy binding** — each node references a governance policy version; audit queries are `WHERE node_policy_version < "2026.08"`.
- **Deployment gating** — promote topology changes through staging with the same CI pipeline as code.

### Governance Boundaries as Graph Boundaries

The graph structure makes regulatory compliance a topology query:

```python
# Find all nodes in a delegation chain for an EU AI Act Article 12 audit
def trace_delegation_chain(graph, start_node):
    chain = []
    visited = set()
    queue = [start_node]
    while queue:
        node = queue.pop(0)
        if node.id in visited:
            continue
        visited.add(node.id)
        chain.append({
            "node": node.id,
            "owner": node.owner,
            "policy_version": node.policy_version,
            "action_type": node.action_type,  # read / write / delete
            "data_classification": node.data_classification,
        })
        for edge in graph.outbound_edges(node):
            queue.append(edge.target)
    return chain
```

Nodes that touch high-risk actions (financial authorization, data deletion, code deployment) are tagged with `action_type`. Audit queries filter by these tags rather than grepping through logs.

### Runtime Topology Reflection

Static graph definitions are necessary but insufficient — agents can take unexpected paths, skip nodes, or spawn sub-agents. Runtime topology reflection captures the **actual** execution graph:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

tracer = TracerProvider()
graph_recorder = tracer.start_active_span("graph.execution")

class GraphNodeTracer:
    def __init__(self, graph_def):
        self.graph_def = graph_def
        self.execution_graph = {}  # node_id -> actual edges taken
        self.span_map = {}

    def enter_node(self, node_id, input_payload):
        span = tracer.start_span(f"node.{node_id}")
        self.span_map[node_id] = span
        self.execution_graph.setdefault(node_id, {"in": [], "out": []})
        self.execution_graph[node_id]["in"].append(
            {"payload_shape": type(input_payload).__name__, "span_id": span.span_id}
        )
        return span

    def exit_node(self, node_id, output_payload, next_node_id=None):
        self.execution_graph[node_id]["out"].append(
            {"next": next_node_id, "payload_shape": type(output_payload).__name__}
        )
        self.span_map[node_id].end()

    def get_execution_graph(self):
        """Return the actual runtime graph for debugging and audit."""
        return self.execution_graph
```

### Contrast with Loop-Based Agents

A single-agent loop (Plan → Act → Observe → Plan…) is a single-node graph with a self-loop edge. It works when:
- One agent owns the full domain
- Failure recovery means retry, not re-route
- No human oversight boundaries exist

Graph engineering doesn't replace loops — it replaces the assumption that one loop is enough. When the loop would need to branch, parallelize, or hand off to a specialist, the graph abstraction makes that explicit.

## Receipt

> Verified 2026-07-22 — Sources: TrueFoundry "Graph Engineering for Multi-Agent Systems" (Boyu Wang, July 20, 2026); AI Builder Club "Graph Engineering Guide" (July 20, 2026); explainx.ai synthesis (July 18, 2026). Concept is in early adoption (~97M MCP SDK downloads as adoption baseline per Ajentik Research, 2026). EU AI Act Article 12 obligations verified against official EU AI Act text. Topology-as-artifact pattern confirmed against GitHub trending agent frameworks (LangGraph, AutoGen Studio) which all converge on declarative graph definitions as of Q2 2026. Code examples are realistic implementations based on OpenTelemetry GenAI semantic conventions.

## See also

- [S-1067 · The Orchestration Pattern Stack](stacks/s1067-the-orchestration-pattern-stack-when-everyone-builds-the-wrong-topology-first.md) — covers pattern types (sequential, parallel, hierarchical); this entry covers topology-as-programmable-artifact
- [S-941 · The Agent Audit Chain](stacks/s941-the-agent-audit-chain-stack-when-every-agent-decision-needs-a-paper-trail.md) — EU AI Act compliance; graph engineering makes audit queries topology-level, not log-level
- [S-1134 · The Escalation Ladder Stack](stacks/s1134-the-escalation-ladder-stack-when-your-agent-gets-stuck-but-nobody-knows-what-to-do.md) — human-in-the-loop patterns; graph engineering models human checkpoints as typed nodes
- [S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — ownership topology makes trust boundaries explicit edges, not implicit assumptions
