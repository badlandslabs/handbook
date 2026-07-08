# S-693 · Agent Workflow Static Verification: Catch the Graph's Bugs Before the Agent Does

You deployed a LangGraph workflow. It passed code review. It passed unit tests. It ran for two weeks in staging. On day 15 in production, it routed a high-value customer complaint to the wrong queue — because the workflow graph had a dead-end node on the escalation path that was unreachable from the main entry. No test caught it. No trace surfaced it. The agent silently picked the only reachable path: the one that filed a ticket instead of alerting a human. This is not a model failure. It is a graph failure — and it is detectable before deployment.

Agent workflow graphs encode behavior as directed graphs: nodes are computation steps (LLM calls, tool invocations, conditional branches), edges are control or data flow. Agents make decisions at runtime; graphs describe the decision space statically. The gap between these — the graph you *designed* and the graph you *tested* — is where architectural defects hide. Static verification closes that gap. It analyzes the workflow graph at build time and reports structural defects, policy violations, and dangerous paths before a single request is served.

## Forces

- **Agent frameworks make graph authorship easy and graph auditing hard.** LangGraph, CrewAI, AutoGen, and Google ADK all expose workflow-as-graph APIs. They give you 20 lines to declare a multi-agent pipeline. None of them tell you whether the graph can reach its intended exit, whether a destructive tool is reachable without a human gate, or whether two agents can deadlock each other. Agentproof (arXiv:2603.20356) found that 27% of benchmark workflows contained structural defects and 55% violated human-gate policies — not because the teams were careless, but because the graphs were never audited.
- **Runtime testing cannot cover the graph's combinatorial space.** A 10-node graph with conditional branching has exponential paths. You can test 500 traces and miss the one path that routes admin actions through a bypassed approval gate. Static analysis traverses the entire graph exhaustively, not probabilistically.
- **Agent dependency chains are invisible to traditional static analysis.** Agent programs mix conventional code with framework-defined semantics: tool decorators, agent constructors, memory state declarations, handoff declarations. AgentFlow (arXiv:2607.01640) shows that these agent dependencies — the binding between an agent's capability declaration and its actual tool access — are not recoverable from standard call graphs. You need a framework-aware graph construction to see them.
- **The blast radius of a graph bug equals the agent's autonomy level.** A routing error in an L0 chatbot produces a wrong response. A routing error in an L3 agent that writes and deploys code can modify production infrastructure. The higher the autonomy level (S-355), the more critical graph verification becomes.

## The move

**Verify the workflow graph before every deployment.** Treat it like a linter — run it as part of CI, fail the build on violations.

### The Agent Dependency Graph (ADG)

AgentFlow's core contribution is constructing a framework-agnostic graph representation from heterogeneous agent frameworks. Nodes are typed: `AgentNode`, `ToolNode`, `MemoryNode`, `CapabilityNode`, `PolicyNode`. Edges carry dependency types: `COMPONENT`, `CONTROL_FLOW`, `DATA_FLOW`. The graph captures both what the code does and what the framework semantics say it should do.

```
// Framework-agnostic ADG construction (simplified from AgentFlow)
interface ADGNode {
  id: string;
  type: 'agent' | 'tool' | 'memory' | 'capability' | 'policy' | 'trigger';
  source: string;          // file + line
  framework?: string;      // langgraph | crewai | autogen | adk
  declaredCapabilities: string[];
  actualCapabilities: string[];  // resolved from decorators
}

interface ADGEdge {
  source: string;
  target: string;
  kind: 'component' | 'control_flow' | 'data_flow';
}
```

The critical check: **capability drift** — when `declaredCapabilities` (what the agent says it can do) diverges from `actualCapabilities` (what the tool decorators actually grant). This is how you catch "agent believes it can delete records but the decorator was removed."

### Structural Checks (Agentproof's six checks)

Agentproof compiles a policy DSL covering LTL safety fragments into deterministic finite automata (DFA) and applies six structural checks:

| Check | What it finds |
|-------|--------------|
| **Dead-end nodes** | Nodes with no outgoing edges that are not the intended exit |
| **Unreachable exits** | Exit nodes unreachable from the main entry |
| **Missing human gates** | Paths reaching sensitive tools (write, delete, deploy) without a human-approval node |
| **Tool reachability** | Whether a tool can actually be called from the entry point |
| **Deadlock detection** | Cycles where two agents each wait for the other's output |
| **Temporal policy violation** | Paths that violate `G(¬sensitive_tool ∨ approved)` — "always: if sensitive tool, then approved" |

```
# LTL safety policy for "no destructive tool without human gate"
# Compiled to DFA and model-checked against the workflow graph
policy: G(¬deploy_tool ∨ human_approved)
# G = globally (always holds on all paths)
# ¬ = not, ∨ = or, deploy_tool ∧ ¬human_approved must never happen
```

### Practical verification pipeline

```python
# agent_verify.py — run in CI before deploy
from agentflow import build_adg
from agentproof import PolicyVerifier

ADG = build_adg(
    entry="src/workflows/customer_complaint.py",
    frameworks=["langgraph", "crewai"],
    check_capability_drift=True,
)

# Structural checks
structural = ADG.check_structural()
if structural.dead_ends or structural.unreachable_exits:
    print(f"STRUCTURAL DEFECTS: {structural}")
    exit(1)  # fail CI

# Policy verification
verifier = PolicyVerifier(ADG)
policies = [
    "G(¬deploy_tool ∨ human_approved)",
    "G(¬delete_db ∨ human_approved)",
    "F(exit_node)",  # F = eventually: every path must reach an exit
]
results = verifier.verify_all(policies)
for r in results:
    if not r.sat:
        print(f"POLICY VIOLATION: {r.policy} violated on path {r.counterexample}")
        exit(1)
```

Sub-second verification on graphs up to 5,000 nodes (Agentproof, 2026). For most teams, this is faster than running a single integration test.

### Cross-links to existing entries

- **S-355 (Bounded Autonomy):** Static verification is the engineering counterpart to the governance taxonomy. Once you've classified your agent's autonomy level, the verification policy DSL enforces those boundaries structurally — not just in documentation.
- **S-238 (Deterministic Guardrails Outside the LLM Loop):** Guardrails are the runtime version of this same insight. Static verification catches violations at build time; deterministic guardrails catch them at runtime. Together they cover both phases.
- **S-204 (Agent Circuit Breaker):** The circuit breaker handles runtime failure modes. Static verification handles architectural failure modes. You need both.
- **S-261 (MCP Security Attack Surface):** Static analysis of tool reachability catches MCP server permission escalation — can the agent reach a tool it shouldn't be able to invoke from the control flow graph alone?
- **S-691 (Agent Handoff Problem):** Handoff failures often trace to unreachable nodes in the graph — the receiving agent's entry is unreachable because a prior node routed to a dead-end instead. Static verification catches this.

## Receipt

> Verified 2026-07-06 — AgentFlow (arXiv:2607.01640) and Agentproof (arXiv:2603.20356) both published July 2026. Agentproof's empirical evaluation: 27% of 18 benchmark workflows contained structural defects, 55% violated human-gate policies. Verification runs sub-second on graphs up to 5,000 nodes. No existing agent framework ships with these checks — teams must integrate externally. No live execution was run; pattern synthesized from published papers and verified against existing handbook entries for non-duplication.

## See also
- [S-355 · Agent Autonomy Levels: Bounded Autonomy](s355-agent-autonomy-levels-bounded-autonomy.md)
- [S-238 · Deterministic Guardrails Outside the LLM Loop](s238-deterministic-guardrails-outside-the-llm-loop.md)
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md)
- [S-261 · MCP Security: The Attack Surface You Inherited](s261-mcp-security-attack-surface.md)
- [S-691 · The Agent Handoff Problem Is Where Multi-Agent Systems Die](s691-the-agent-handoff-problem-is-where-multi-agent-systems-die.md)
