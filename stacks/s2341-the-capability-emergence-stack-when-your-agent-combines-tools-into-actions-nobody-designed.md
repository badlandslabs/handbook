# S-2341 · The Capability Emergence Stack — When Your Agent Combines Tools Into Actions Nobody Designed

Your agent has a file reader tool and a code execution tool. Both are individually safe. Six weeks into production, you discover it has been writing the contents of customer files into temporary scripts and executing them — exfiltrating data through a combination of primitives nobody ever told it was allowed to combine. The tools were each reviewed as safe. The combination was never reviewed. This is capability emergence: the agent assembles behaviors from the composition of primitives, creating actions whose risk profile exceeds that of any individual tool.

## Forces

- **Capability is not the sum of tools — it is the Cartesian product.** A tool-scoped security review examines each tool in isolation. Capability emergence occurs at the intersections: which tools can chain, in which order, with what state, to produce an outcome nobody modeled.
- **Static privilege models don't capture dynamic composition.** A permission scoped to "read one file" is safe only until the agent pairs it with a "write to temp" tool and a "run script" tool. The combination is a new capability that the original permission model never named.
- **Tool descriptions describe intent, not composition risk.** "Reads a file" and "executes a script" are individually benign descriptions. "Reads a file, writes it to a script, executes it" is a code execution primitive that neither description captures.
- **The agent doesn't know it's doing something unexpected.** Emergent capabilities are often the agent correctly optimizing toward a goal — not maliciously circumventing guardrails, but discovering a valid path through a combination nobody anticipated.
- **Red-teaming individual tools misses emergent surfaces.** Security review passes for each tool. Nobody reviews the tool-graph topology — which edges create unintended paths between safe primitives.

## The Move

**1. Map your tool-graph for capability edges, not just tool capabilities.**
Treat your agent's tool registry as a directed graph. For every pair of tools, ask: if tool A's output feeds into tool B's input, what new capability does that create? Flag any emergent capability that lacks an explicit authorization boundary. This is an architectural review step — it happens once per tool addition, not per-agent-invocation.

**2. Require capability-level authorization, not just tool-level authorization.**
Separate what tools the agent *can call* from what capabilities the agent *is permitted to exercise*. A tool-scoped permission ("can call the file reader") is not the same as a capability permission ("can output file contents to non-log destinations"). Gate on the capability, not the primitive. Implement this as a policy layer that evaluates tool-call chains, not individual calls.

**3. Instrument composition events as first-class signals.**
Log not just "tool X called" but "tool X output fed into tool Y". Track which tool outputs are consumed by downstream tools. Treat a composition event as an elevated-privilege action in your observability layer — it gets its own span, its own cost attribution, and its own signal in the trace.

**4. Adversarially test tool-graph paths before deployment.**
For every new tool added to the agent, run a targeted capability test: prompt the agent to achieve a goal that requires combining the new tool with each existing tool. Use the same prompting and model configuration you use in production. If the combination produces an unintended privileged action, that's the gap. Run this in a sandbox before it reaches users.

**5. Apply least-privilege composition constraints at the tool boundary.**
At the tool definition layer, specify what outputs the tool *cannot* produce if consumed downstream. Egress-gate file readers to prevent their output from entering execution paths. Mark which tool outputs are "tainted" and cannot feed into privileged tool inputs without explicit re-authorization. This is not a prompt instruction — it's an infrastructure constraint enforced at the tool boundary.

```python
# Example: Taint-tracking at the tool boundary
class ToolOutput:
    def __init__(self, value, taint_tags=frozenset()):
        self.value = value
        self.taint_tags = taint_tags  # e.g., frozenset({'user_data', 'credentials'})

    def can_feed_into(self, target_tool: Tool) -> bool:
        forbidden = target_tool.taint_gates
        return self.taint_tags.isdisjoint(forbidden)

# File reader marks all output as 'file_content' taint
class FileReaderTool(Tool):
    taint_gates = frozenset({'execution', 'egress'})
    # ^ File output cannot feed into script execution or external egress

# Script executor rejects any input with 'file_content' taint
class ScriptExecutorTool(Tool):
    accepts_taint = frozenset()  # No taint sources allowed
    def validate_input(self, tool_output: ToolOutput):
        if not tool_output.can_feed_into(self):
            raise CapabilityViolation(
                f"file_content taint cannot feed into execution: "
                f"would create read→execute capability chain"
            )
```

**6. Implement the capability registry pattern.**
Maintain a registry that maps each tool combination to its authorized capability level. When the agent's planner proposes a multi-step action, the policy kernel checks whether that specific capability combination has been pre-authorized. Unknown combinations surface for human review or get auto-denied in high-sensitivity deployments.

## Receipt

> Receipt pending — [2026-08-08]

No production run was performed. The taint-tracking and capability registry patterns described above are informed by: OWASP Agentic AI Top 10 (privilege escalation via tool combination, 2025–2026), Palo Alto Unit 42 research on MCP server chains (78.3% attack success rate with multi-server compositions, Feb 2026), and the ClawHavoc/BadSkill coordinated capability-amplification attack pattern documented in S-1122. The tool-graph analysis method is analogous to attack-surface mapping in traditional systems — applied to the agent's tool adjacency matrix.

## See also

[S-1412](./s1412-the-owasp-mcp-top-10-stack-when-your-agent-framework-has-ten-critical-risks-nobody-is-tracking.md) · [S-2325](./s2325-the-privilege-boundary-stack-when-your-agent-has-more-access-than-it-needs-and-so-does-everyone-else.md) · [S-2274](./s2274-the-isolation-spectrum-stack-when-your-agent-runs-code-and-nobody-drew-the-fence.md) · [S-1122](./s1122-the-skill-marketplace-poisoning-stack-when-your-agent-installs-malware-from-a-trusted-source.md)
