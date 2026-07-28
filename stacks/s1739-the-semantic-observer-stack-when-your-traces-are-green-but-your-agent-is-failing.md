# S-1739 · The Semantic Observer Stack — When Your Traces Are Green But Your Agent Is Failing

Your agent loops 18 times calling the same search tool, never finds the file, and reports success. Every trace span returned 200. Latency was normal. Token usage was unremarkable. Your observability dashboard shows a healthy agent. The product is broken.

## Forces

- **Structural tracing measures mechanics; semantic failure is a goal-level problem.** An agent can return 200 on every span while pursuing the wrong sub-goal, looping on a dead-end strategy, or drifting from the original intent. Standard OTEL spans capture *what happened* — they don't capture *whether what happened was correct*.
- **Per-step correctness is invisible to dashboards that only measure throughput.** HTTP status codes, latency percentiles, and token counts are proxy metrics. They detect crashes and timeouts, not quiet wrongness — the agent that completes its task without achieving its goal.
- **The gap between "ran successfully" and "did the right thing" is where production agents silently fail.** This is the dominant failure mode in long-horizon agentic systems, and standard observability tooling has no instrument for it.

## The move

### Layer 1 — Per-Turn Semantic Classifier

At every step boundary, run a lightweight classifier that evaluates *semantic correctness* of the last action:

```
Input:  (intent_assertion, tool_call_args, tool_result, agent_response)
Output: { on_goal: bool, divergence_signal: float, confidence: float }
```

The classifier does NOT re-run the agent's reasoning — it compares *observed behavior* against *stated intent*. It runs at <90ms and costs <$0.001/call with a 1B-classifier model.

```python
# Per-turn semantic observer (lightweight, in-process)
import httpx

SEMANTIC_CLASSIFIER_URL = "http://localhost:8001/classify"

def observe_step(intent: str, tool_name: str, tool_args: dict,
                 tool_result: str, agent_response: str) -> dict:
    """
    Runs a per-turn semantic correctness check.
    Detects: goal drift, loop behavior, wrong-tool selection, silent failure.
    """
    payload = {
        "intent": intent,
        "tool_name": tool_name,
        "tool_args": str(tool_args),
        "tool_result": tool_result[:2000],   # truncate for cost
        "agent_response": agent_response[:1000],
    }
    with httpx(timeout=2.0) as client:
        resp = client.post(SEMANTIC_CLASSIFIER_URL, json=payload)
    return resp.json()
    # Returns: {"on_goal": true, "divergence_signal": 0.03, "confidence": 0.91}

# Integration into agent loop
def agent_loop_with_observer(intent: str, tools: list, max_steps: int = 20):
    state = {"messages": [], "steps": 0, "off_goal_count": 0}
    for step in range(max_steps):
        action = agent.decide(state["messages"])
        result = agent.execute(action)
        obs = observe_step(
            intent=intent,
            tool_name=action.tool_name,
            tool_args=action.args,
            tool_result=result.raw,
            agent_response=result.response
        )

        if not obs["on_goal"]:
            state["off_goal_count"] += 1
            logger.warning(
                f"Step {step}: off-goal signal={obs['divergence_signal']:.2f} "
                f"confidence={obs['confidence']:.2f}"
            )
            if obs["divergence_signal"] > 0.7:
                return {"status": "diverged", "step": step, "observation": obs}
        state["messages"].append(result)
    return {"status": "completed", "steps": state["steps"]}
```

### Layer 2 — Intent Assertion at Handoff Points

Multi-agent handoffs are the highest-risk moments for silent semantic failure. Before passing context to the next agent, assert that the *upstream output satisfies the upstream intent*:

```python
def handoff_with_assertion(sender: str, recipient: str,
                            upstream_intent: str, output: str) -> bool:
    """
    Gate: upstream output must satisfy upstream intent before handoff proceeds.
    """
    assertion_prompt = (
        f"Intent: {upstream_intent}\n"
        f"Output: {output}\n"
        f"Does this output fulfill the stated intent? "
        f"Answer: SATISFIED | PARTIAL | UNSATISFIED"
    )
    result = llm.call(assertion_prompt, model="fast-classifier")
    verdict = extract_verdict(result)  # SATISFIED / PARTIAL / UNSATISFIED

    if verdict == "UNSATISFIED":
        alert(f"Handoff gate failed: {sender} → {recipient}")
        return False
    elif verdict == "PARTIAL":
        attach_partial_disclosure(output, "handoff_incomplete")
    return True
```

### Layer 3 — Loop Detection Beyond Step Count

Step-count limits catch obvious infinite loops but miss *productive-looking failure loops* — the agent tries different queries, different tools, but never reaches the goal. Combine step count with *strategy diversity*:

```python
def detect_strategy_loop(steps: list[dict]) -> bool:
    """
    An agent is looping not because it repeats actions,
    but because it tries N variations of the same failed strategy.
    """
    tool_sequence = [s["tool_name"] for s in steps[-10:]]
    if tool_sequence.count("search") >= 6 and not any(s["found"] for s in steps[-10:]):
        return True  # Same tool, same failure, different query — loop
    return False
```

### Layer 4 — Divergence Budget

Track cumulative divergence signal across the session. When it crosses a threshold, surface a structured *partial result* rather than continuing:

```python
DIVERGENCE_BUDGET = 0.6  # Sum of divergence_signal across all steps

def check_divergence_budget(steps: list[dict], threshold: float = DIVERGENCE_BUDGET) -> dict:
    cumulative = sum(s.get("divergence_signal", 0) for s in steps)
    if cumulative >= threshold:
        return {
            "halt": True,
            "reason": "divergence_budget_exhausted",
            "cumulative": cumulative,
            "partial": build_partial_result(steps)
        }
    return {"halt": False}
```

## Receipt

> Verified 2026-07-27 — MorphLLM (morphllm.com/agent-observability) documents the <90ms per-turn classifier pattern and the "green trace / broken product" failure mode with concrete case: 18-step loop where all spans returned 200. AgentLens (HN Show HN, July 2026) and Sentrial (YC W26) are both production tools addressing this exact gap. The per-turn classifier layer is the structural solution: structural tracing measures mechanics, semantic classifiers measure correctness.

## See also

- [S-635 · Silent Failure Detection](/stacks/s635-the-silent-failure-detection-stack-when-your-agent-wont-tell-you-it-broke.md) — structural silent-failure patterns
- [S-1372 · The Correctness SLO Stack](/stacks/s1372-the-correctness-slo-stack-when-your-dashboard-says-99.4-percent-and-your-customer-says-the-feature-has-been-broken-for-3-weeks.md) — correctness SLOs vs. HTTP SLOs
- [S-1004 · The Agent Eval Stack](/stacks/s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — three-layer eval (final-answer, trajectory, per-turn)
