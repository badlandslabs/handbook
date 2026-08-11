# S-2468 · The Look-Don't-Pick Stack — When Your Agent Knows the Right Tool but Picks the Wrong One

Your agent has the right tool visible. It is attending to it — the model's attention weights confirm it. And then it calls the wrong one. Every observability dashboard shows green. Every trace looks clean. The failure is invisible because it happens after the right answer is already computed, inside the decision-readout layer where nobody looks.

This is the "look but don't pick" failure class, documented by Shiyang Chen (arXiv:2606.16364, Jun 2026) through attention-segment analysis on BFCL tool-call benchmarks, and independently diagnosed by Anand & Chattaraj (arXiv:2608.04719, Aug 2026) via canary tool probes in MCP tool sets. Together they establish the same counterintuitive finding from two angles: the problem is not that the model failed to see the right tool. The problem is that it saw the right tool and still got the decision wrong.

## Forces

- **The crowded-harness hypothesis is wrong.** The intuitive explanation for wrong-tool calls is that the model is overwhelmed by too many tools — lost in the middle, unable to locate the right one in the tool list. Chen's attention analysis directly refutes this: models attend most to the correct tool 80% of the time (vs. 21% random baseline), and the gold tool is under-attended in only 10% of failures. The perception is correct. The readout is broken.

- **Standard observability misses the failure mode entirely.** Tool-call traces show the final decision, not the attention state that produced it. An agent that calls `search_database` instead of `query_analytics` looks identical to one that called the right tool — until you inspect attention maps. This makes the failure class invisible to Langfuse, Phoenix, and every span-based tracer that practitioners rely on.

- **Substring-based evaluation makes it look like the tools are the problem.** AgentProp-Bench (Gurram, arXiv:2604.16706) shows substring-based automated judges agree with human annotation at κ=0.049 — chance level. A judge that can't tell right from wrong teaches you nothing about the actual failure.

- **The fix layer is post-attention but pre-execution.** The failure sits between the module that computes attention over tool definitions and the module that maps that computation to a tool name. Adding more tools, better descriptions, or better prompts does not fix this — because the model already knows the right answer. The fix layer needs to intervene at the readout, not the input.

## The move

The diagnosis is architectural: your agent has three distinct processing stages for tool selection, and most engineering only addresses the first two.

**Stage 1 — Perception (working correctly):** The model attends to tool-definition tokens. Attention is correctly weighted toward the right tool in 80% of failure cases.

**Stage 2 — Reasoning (working correctly):** The model internally computes the correct tool as the best action. This reasoning state exists inside the forward pass.

**Stage 3 — Readout (broken):** The model's final logit bias maps the internal computation to a tool name. This is where the wrong answer gets selected despite correct internal state.

The Look-Don't-Pick Stack is the set of techniques that intercept failures at Stage 3, after the correct tool has been identified internally but before it reaches the execution layer.

### Canary Tool Probes (diagnosis)

Plant diagnostic probe tools in your MCP tool set to triangulate which readout failure type is occurring. Anand & Chattaraj's six-type taxonomy:

| Failure Type | What it probes | Signal |
|---|---|---|
| **Semantic decoys** | Similar-sounding name, wrong function | Model picks decoy over correct tool |
| **Parameter traps** | Similar interface, wrong parameter handling | Correct tool selected but wrong params |
| **Capability mirages** | Tool appears capable but isn't | Tool selected that can't fulfill the request |
| **Prerequisite blindness** | Tool needs missing preconditions | Correct tool called with wrong pre-state |
| **Temporal confusion** | Same-named tools at different times | Model picks stale vs. current version |
| **Compositional misfire** | Tool composable but not in this context | Correct sub-tool selected at wrong scope |

### Attention-Segment Logging (runtime capture)

Log the model's per-token attention over tool-definition segments during tool selection, not just the final tool call. Compare the attended segment against the selected segment. A divergence is your Look-Don't-Pick signal.

```python
from anthropic import Anthropic
import json

client = Anthropic()

# Intercept at the readout layer
# In production: use a trace hook that captures per-token attention weights
# against tool definition segments before the tool_use block is returned

def log_readout_divergence(messages: list, selected_tool: str, attention_map: dict) -> None:
    """
    attention_map: {tool_name: max_attention_weight_over_definition_segment}
    """
    attended_tool = max(attention_map, key=attention_map.get)
    if attended_tool != selected_tool:
        divergence_ratio = attention_map[attended_tool] / (attention_map[selected_tool] + 1e-9)
        print(
            f"[LOOK-DON'T-PICK] Attended: {attended_tool} "
            f"(w={attention_map[attended_tool]:.3f}) "
            f"but selected: {selected_tool} "
            f"(w={attention_map[selected_tool]:.3f}) "
            f"divergence={divergence_ratio:.2f}x"
        )
        # Alert: readout layer divergence detected
        # Trigger: log to observability, halt execution if divergence > 2x

def readjust_tool_logits(attention_map: dict, selected_tool: str, threshold: float = 2.0) -> str:
    """
    Runtime mitigation: re-check if attention divergence should override selection.
    Use when the selected tool is wrong at a higher ratio than threshold.
    """
    attended_tool = max(attention_map, key=attention_map.get)
    divergence = attention_map[attended_tool] / (attention_map[selected_tool] + 1e-9)
    if divergence >= threshold:
        print(f"[READOUT OVERRIDE] Redirecting to {attended_tool} (divergence={divergence:.2f}x)")
        return attended_tool
    return selected_tool
```

### Semantic Disambiguation Wrapper (fix)

For production deployments, wrap the tool selection with a lightweight semantic verification step that re-checks the selected tool's name against the task description — not as a re-reasoning pass, but as a readout validation.

```python
def semantic_tool_validator(task_description: str, tool_schemas: list[dict], selected_tool: str) -> str:
    """
    Verifies the selected tool's semantic alignment with the task description.
    Falls back to re-ranking by description similarity if alignment is low.
    """
    from anthropic import Anthropic
    client = Anthropic()
    
    selected_schema = next((t for t in tool_schemas if t["name"] == selected_tool), None)
    if not selected_schema:
        return selected_tool
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": (
                f"Task: {task_description}\n"
                f"Selected tool: {selected_schema['name']} — "
                f"description: {selected_schema.get('description', '')}\n"
                f"Does this tool directly address the task? Answer yes or no."
            )
        }]
    )
    
    aligned = "yes" in response.content[0].text.lower()
    if not aligned:
        # Fall back: re-rank tools by semantic alignment and pick the top
        return re_rank_tools(task_description, tool_schemas, client)
    return selected_tool
```

## Receipt

> Verified 2026-08-11 — arXiv:2606.16364 (Chen, Jun 2026): attention-segment analysis on BFCL v2 failures confirms 80% attention-on-correct-tool vs. 21% random baseline. arXiv:2604.16706 (AgentProp-Bench, Gurram): substring-based judge κ=0.049 confirms standard eval misses readout failures. arXiv:2608.04719 (Anand & Chattaraj, Aug 2026): six-type canary taxonomy provides diagnostic taxonomy. Production deployment patterns from AgentMarketCap (Apr 2026) confirm MCP reliability ceiling from readout failures.

## See also

- [S-989 · The Tool Surface Stack](stacks/s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — the surface area angle (more tools → more readout confusion)
- [S-1014 · Evaluating Agents in Production](stacks/s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — why trajectory evaluation catches readout failures that single-step eval misses
- [S-1000 · The Eval Gap Stack](stacks/s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — κ=0.049 substring judges are the eval gap made quantitative
- [S-2346 · MCP Production Reliability](stacks/) — MCP tool supply chain and the Perplexity CTO critique of early MCP production ceilings
