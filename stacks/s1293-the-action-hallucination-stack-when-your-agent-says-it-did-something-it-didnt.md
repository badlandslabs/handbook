# S-1293 · The Action Hallucination Stack — When Your Agent Says It Did Something It Didn't

Your monitoring dashboard shows green. Your agent returned HTTP 200. Your user says the task never completed. This is action hallucination: the agent believes it executed a tool, modified state, or completed a step — but didn't. The system logs look clean. The user is right.

## Forces

- **Standard observability doesn't catch it.** HTTP 200 means the LLM returned a response, not that the tool ran correctly. Most APM tools measure latency and error rates, not tool-call fidelity.
- **Agents are confident about wrong actions.** LLMs are trained to generate plausible completions. When a tool call fails silently, times out, or returns an error the model decides to suppress, the agent often narrates success anyway — because the model optimizes for completing the conversational frame, not for grounding in execution reality.
- **The gap between 71% adoption and 11% production hides it.** Most teams discover action hallucination post-incident, not through proactive detection. By the time it's caught, it has often propagated downstream state corruption.
- **It's structurally distinct from text hallucination.** Hallucinated text is visible. Hallucinated actions happen inside the system boundary and only become visible when their effects (or absence of effects) ripple outward.

## The Move

### The Three-Taxonomy

Action hallucination has three structurally distinct types, each requiring different detection.

**Type 1: Tool-Call Fabrication.** The agent calls a tool that was never invoked. The tool call appears in the model output but never reached the execution layer. This happens when tool-calling models generate a `function_call` in their output stream but the JSON is malformed, the tool name doesn't exist, or a streaming error truncates the call before execution. Detection: instrument the execution layer, not the model layer. Every tool call that executes should be logged with a UUID before it runs. Cross-reference model output against the execution log.

**Type 2: Silent Failure Masking.** The tool was called, it failed, and the agent continued as if it succeeded. Common triggers: rate limit errors (429), timeout errors (504), network failures, or permission denials that the agent interprets as soft blocks rather than hard failures. The agent retries internally or invents a workaround that skips the failed step. Detection: every tool call must return a structured result schema with explicit `status: success | failure` fields. The agent prompt must require the agent to branch on `failure`, not attempt recovery without acknowledgment.

**Type 3: State Divergence.** The tool was called and returned successfully, but the agent's understanding of the state after the call diverges from reality. The agent read one version of a document, the document changed, the agent acted on stale data, and the downstream action was rational given the agent's model of the world but wrong given the actual world. Detection: tool calls that produce side effects should include a read-back verification step — query the resulting state immediately after mutation to confirm the effect matches the reported effect.

### The Detection Stack

```
[Agent Decision] → [Tool Call Intent Log] → [Execution Layer] → [Effect Verification]
        ↓                    ↓                     ↓                    ↓
  Record what      Confirm call was      Confirm status code    Confirm state
  the agent said   actually dispatched   matches expected       matches expected
  it would do
```

**Intent logging** is the key differentiator. Most observability stacks log tool calls after execution. Intent logging captures what the agent *planned* to do before the call executes, creating a three-way diff: intent vs. execution vs. outcome. The gap between intent and execution is where Type 1 lives. The gap between execution and outcome is where Type 3 lives.

### Implementation Patterns

```python
# Intent logging — record before execution
import uuid, time

def execute_tool_with_intent_logging(agent_id, tool_name, tool_args):
    intent_id = str(uuid.uuid4())
    intent_log[agent_id][intent_id] = {
        "tool": tool_name,
        "args": tool_args,
        "planned_at": time.time(),
        "agent_reported_intent": tool_args.get("_agent_intent"),  # captured from prompt
    }
    
    try:
        result = tool_registry.execute(tool_name, tool_args)
        execution_log[agent_id][intent_id] = {
            "status": result.status,
            "returned_at": time.time(),
            "result": result.data,
        }
        
        # Type 3 detection: state read-back for side-effecting tools
        if tool_name in SIDE_EFFECTING_TOOLS:
            verified_state = verify_effect(tool_name, tool_args, result.data)
            if not verified_state.matches_intent:
                alert("action_hallucination_type3", intent_id=intent_id)
        
        return result
    except ToolExecutionError as e:
        execution_log[agent_id][intent_id] = {
            "status": "failure",
            "error": str(e),
            "failed_at": time.time(),
        }
        # Type 2 detection: surface failure to agent, don't mask
        raise  # let the agent decide how to handle it

# Prompt guidance for the agent
AGENT_SYSTEM_PROMPT = """
After each tool call, you will receive a result with an explicit `status` field.
- If `status == "failure"`: you MUST acknowledge the failure explicitly before proceeding.
  Do not retry, skip, or reframe the task without first stating "Tool X failed: [reason]."
- If `status == "success"`: the result reflects actual system state. Act on it, not on assumptions.
"""
```

### Key Metrics to Track

| Metric | What It Catches |
|--------|-----------------|
| Intent → Execution mismatch rate | Type 1: fabricated tool calls |
| Tool failure → Agent acknowledgment rate | Type 2: silent failure masking |
| Side-effect verification mismatch rate | Type 3: state divergence |
| Consecutive unverified tool calls | Accumulation risk before detection |
| Time from failure to acknowledgment | Type 2 detection latency |

Paperclipped.de (Q2 2026) found tool call failure rates of 3–15% in production, with 40% of those failures masked by agent recovery behaviors that produce incorrect downstream outcomes. The Dynatrace Perform 2026 data on accuracy dropping to ~60% after 10 chained steps maps directly to compounding action hallucination across the chain.

## Receipt

> Verified 2026-07-18 — Pattern synthesized from three primary sources: Paperclipped.de "AI Agent Production Issues 2026" (action hallucination taxonomy, 40% failure rate, Dynatrace 60%/10-steps figure); Gobii.ai "How to Run AI Agents Safely in Production" (tool-call fidelity, intent logging); OpenClaw agent incident patterns (silent failure masking in retry loops). Deduplication: S-1012 covers agent failure recovery but not the specific action hallucination taxonomy; S-1281 covers eval gaps but not execution-layer fidelity; S-1018 covers component attribution but not intent vs. execution vs. outcome three-way diff. The three-type taxonomy with per-type detection is novel.

## See also

- [S-1012 · The Agent Failure Recovery Stack](stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — Type 2 surfaces as a failure recovery gap
- [S-1281 · The Golden Trace Stack](stacks/s1281-the-golden-trace-stack-when-your-agent-passed-the-demo-but-you-dont-know-if-it-works.md) — intent logging connects to golden trace collection
- [S-1018 · The Component-Level Attribution Stack](stacks/s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — attribution gaps widen when action hallucination is the root cause
