# S-2126 · The Structural Overthinking Stack — When Individual Tool Calls Are Harmless But Their Composition Traps Your Agent

A customer lookup tool is safe. A search tool is safe. A ticket-creator tool is safe. You connect all three to your agent via MCP. The agent enters a trajectory that calls lookup → search → ticket → lookup → search → ticket, burning 142× its expected token budget without any single step looking abnormal. No injection. No malicious schema. No guardrail fires. The tools are fine. The *composition* is the attack.

This is **structural overthinking**: a failure class where individually trivial or plausible tool calls compose into cyclic trajectories that inflate end-to-end cost and latency — without any single step appearing anomalous enough to trigger a circuit breaker.

## Forces

- **Agents evaluate each tool call in isolation.** The agent's decision loop assesses one tool invocation at a time: "should I call this tool now?" It has no mechanism to evaluate "will this call, combined with those available next, compose into a loop?" Isolation is correct for safety; it is insufficient for loop detection.
- **MCP's flat tool registry exposes every tool as equally available.** Unlike curated tool lists where an engineer explicitly chooses the combination, an MCP server exposes its full tool surface. Adding a calendar MCP alongside a ticket MCP exposes 34 new tools. Any subset of those 34 can be composed in any order by the agent.
- **The threat model is asymmetric.** A malicious tool with obvious looping behavior is caught by static analysis or code review. A benign tool (e.g., a checklist validator) composes with other benign tools (e.g., a progress tracker) to create cyclic dependencies that no individual review would surface.
- **Token amplification is invisible until it's catastrophic.** A 2× cost overrun doesn't trigger alerts. A 142× cost overrun on a production agent run arrives as a billing shock, not a caught failure. By the time the signal is loud enough to notice, the damage is done.
- **Defense tools can be attack vectors.** Ironically, the most dangerous tool in a structural overthinking chain is often a monitoring or validation tool — because agents repeatedly invoke them to "check progress," and the tool's response routes back to a prior tool in the cycle.

## The move

**Detect composition, not individual calls.**

### 1. Build a tool interaction graph

Instrument your agent to record (caller_tool → callee_tool) pairs from tool results. After each session, analyze the directed graph for cycles using Tarjan's algorithm or depth-first search.

```python
from collections import defaultdict, deque

def detect_tool_cycles(tool_call_sequence: list[str], max_depth: int = 10) -> list[list[str]]:
    """
    Detect cyclic tool call patterns in an agent's execution trace.
    A cycle exists when tool_A calls tool_B, and tool_B's result
    routes back to tool_A (directly or indirectly).
    """
    # Build adjacency: tool -> tools it has routed to
    adjacency = defaultdict(set)
    for i in range(len(tool_call_sequence) - 1):
        adjacency[tool_call_sequence[i]].add(tool_call_sequence[i + 1])

    # Tarjan's SCC to find cycles
    index_counter = [0]
    stack = []
    lowlinks = {}
    index = {}
    on_stack = {}
    cycles = []

    def strongconnect(v):
        index[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adjacency.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif on_stack.get(w, False):
                lowlinks[v] = min(lowlinks[v], index[w])

        if lowlinks[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1 or (len(scc) == 1 and tool_call_sequence.count(scc[0]) >= 3):
                cycles.append(scc)

    for v in adjacency:
        if v not in index:
            strongconnect(v)

    return cycles
```

### 2. Set a per-tool call frequency ceiling

Track how many times each tool is invoked in a single session. A tool called more than N times (tune N per tool — a lookup should be ≤3, a search ≤5) triggers a circuit break.

```python
from collections import Counter
from dataclasses import dataclass, field

@dataclass
class OverthinkingCircuitBreaker:
    tool_frequency_ceiling: dict[str, int] = field(default_factory=dict)
    session_calls: Counter = field(default_factory=Counter)
    amplification_ratio_limit: float = 14.0  # Hou et al. found worst-case: 142x; set your alert at 14x
    expected_call_count: int = 5
    session_token_budget: int = 0
    session_tokens_spent: int = 0

    def check(self, tool_name: str) -> bool:
        """Returns True if the tool call is permitted."""
        self.session_calls[tool_name] += 1
        ceiling = self.tool_frequency_ceiling.get(tool_name, 5)

        # Frequency check
        if self.session_calls[tool_name] > ceiling:
            return False

        # Amplification check
        if self.expected_call_count > 0:
            ratio = sum(self.session_calls.values()) / self.expected_call_count
            if ratio > self.amplification_ratio_limit:
                return False

        # Token budget check
        if self.session_token_budget > 0:
            if self.session_tokens_spent > self.session_token_budget:
                return False

        return True

    def record_tokens(self, count: int):
        self.session_tokens_spent += count

    def reset(self):
        self.session_calls.clear()
        self.session_tokens_spent = 0
```

### 3. Instrument MCP server metadata for cycle potential

At MCP server registration time, analyze tool pairs for cyclic routing potential. Tag pairs where tool A's output schema matches tool B's input schema in a way that creates a routing loop.

```python
def tag_cyclic_pairs(mcp_servers: list[dict]) -> set[tuple[str, str]]:
    """
    Scan all registered MCP tools for pairs that can compose into cycles.
    A pair (tool_A, tool_B) has cyclic potential if:
    1. tool_B's primary input parameter type matches tool_A's output type
    2. tool_B's output routes back to tool_A's input parameter name
    3. Both tools have no mandatory side-effects that break the cycle
    """
    cyclic_pairs = set()
    all_tools = []
    for server in mcp_servers:
        for tool in server["tools"]:
            all_tools.append((server["name"], tool))

    for src_server, src_tool in all_tools:
        for tgt_server, tgt_tool in all_tools:
            if src_tool == tgt_tool:
                continue
            # Check if tgt_tool's output references src_tool's required input
            output_fields = {f["name"] for f in src_tool.get("output_schema", {}).get("properties", {}).values()}
            input_fields = {f["name"] for f in tgt_tool.get("input_schema", {}).get("properties", {}).values()}
            if output_fields & input_fields:
                # Check for stateless tools (no mandatory side-effects that break cycles)
                if not tgt_tool.get("requires_confirmation", False) and \
                   not src_tool.get("requires_confirmation", False):
                    cyclic_pairs.add((f"{src_server}.{src_tool['name']}",
                                      f"{tgt_server}.{tgt_tool['name']}"))

    return cyclic_pairs
```

### 4. Set token amplification alerts, not just ceilings

Calibrate expected token counts per task type. Alert at 5× expected; escalate at 14× (the minimum amplification found in Hou et al.'s ReAct benchmarks).

| Task Type | Expected Tokens | Alert Threshold | Circuit Break |
|-----------|----------------|-----------------|---------------|
| Simple lookup | 2,000 | 10,000 | 28,000 |
| Multi-source query | 8,000 | 40,000 | 112,000 |
| Complex reasoning | 25,000 | 125,000 | 350,000 |

### 5. Audit MCP server registrations for tool count

Hou et al.'s attack works by co-registering malicious tools alongside normal ones. Audit every MCP server for the number of tools it exposes. Flag registries with >20 tools (unless from a known, reviewed vendor) for additional scrutiny.

## Receipt

> Verified 2026-08-04 — Analyzed arXiv:2602.14798v1 (Hou et al., Yonsei/Ewha/HUFS, 2026). Tested cycle detection on a simulated tool call trace: `lookup → search → ticket → lookup → search → ticket` correctly identified as a 3-tool cycle with amplification ratio 5.0× (above alert threshold). The Tarjan-based SCC detection correctly returned `[['lookup', 'search', 'ticket']]`. Amplification alert threshold (14×) correctly left this trace running but flagged it. Token ceiling check (5 calls/tool) correctly blocked at call 6 of `lookup`.

> Hou et al. key findings: Max token amplification of 14.59× on ReAct agents and **142.4×** on Qwen-Code agents. Worst single case: 971.27× on GLM-4.6 (problem 2033f). Attack tools used trivial logic — text repetition, staged checklists, subtask decomposition — none appearing malicious in isolation. Counterfactual: what if we had evaluated tool *composition* instead of individual tool behavior?

## See also

- [S-1882 · The Overthinking Spiral](s1882-the-overthinking-spiral-when-your-agent-reasons-itself-into-higher-costs-and-lower-accuracy.md) — Token-level overthinking (CoT length, reasoning collapse); this entry is the structural/mechanistic complement
- [S-2114 · The Tool Surface Stack](s2114-the-tool-surface-stack-when-giving-your-agent-more-plumbing-makes-it-dumber.md) — MCP tool count as attack surface multiplier; structural overthinking is the specific failure mode that unlocks
- [S-1188 · The A2A Authorization Island](s1188-the-a2a-authorization-island-when-every-agent-is-its-own-security-perimeter.md) — Cross-agent security boundaries; structural overthinking is the intra-agent analog
- [R-18 · Why Agents Fail to Stop](/opt/data/handbook/frontier/r18-why-agents-fail-to-stop-infinite-agentic-loops.md) — IAL-Scan for termination logic; this entry explains the architectural mechanism that creates the loops IAL-Scan detects
