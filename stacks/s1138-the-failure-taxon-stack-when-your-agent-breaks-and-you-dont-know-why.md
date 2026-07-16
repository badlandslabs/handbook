# S-1138 · The Failure Taxon Stack — When Your Agent Breaks and You Don't Know Why

A tool call fails silently. Then the next tool call uses the corrupted output. Then the agent confidently presents the wrong answer. Three teams spend a week tracing through logs to reach the same conclusion: "the API returned an empty result and nobody checked." This is the **failure attribution problem** — and it has nothing to do with your agent being broken. It has everything to do with the taxonomy you didn't build.

Most teams approach agent failures reactively: something breaks, you trace it, you fix the symptom. The AgentFail dataset — 307 real production failures from platform-orchestrated agentic workflows — shows this is a solved problem with an empirical answer. The failures aren't random. They fall into a repair-oriented taxonomy with predictable roots and corresponding fix strategies. Once you know the taxonomy, debugging shifts from archaeology to diagnosis.

## Forces

- **Agents fail through propagation, not explosion.** The bad event and the visible symptom are often 5-7 steps apart. The tool that actually broke is not the tool that failed visibly. Teams waste days tracing the wrong chain.
- **Failure type and repair strategy are tightly coupled.** Retrying a tool call is the right fix for transient failures and the wrong fix for hallucinated parameters. Without a taxonomy, you apply the wrong repair and the failure recurs.
- **Heterogeneous nodes complicate attribution.** A single workflow may span LLM reasoning, tool execution, API calls, and database reads. Each has its own failure modes. When a workflow fails, the component that broke and the component that alerted are often different things.
- **The root cause is usually one layer away from the visible symptom.** In AgentFail's dataset, 58% of workflow failures traced to upstream tool execution failures — not to the LLM reasoning itself. Teams that assumed the model was the problem spent 4× longer debugging than teams that started at the tool layer.

## The move

The AgentFail taxonomy classifies agentic workflow failures across two axes: **manifestation** (what you observe) and **root cause** (where it originates), then maps each combination to a repair strategy.

### Layer 1 — Failure Manifestations (what you see)

| Manifestation | What it looks like | Typical span |
|---|---|---|
| **Execution failure** | Tool call returns error, empty, or malformed output | Immediate |
| **Reasoning failure** | Agent picks wrong tool, wrong parameters, wrong goal | 1-3 steps |
| **Planning failure** | Agent's task decomposition is incomplete or incorrect | 3-7 steps |
| **Propagation failure** | Bad output from step N silently poisons steps N+1 through N+k | 5-10 steps |
| **Convergence failure** | Agent loops, repeats, or never terminates | Indefinite |

### Layer 2 — Failure Root Causes (where it starts)

| Root Cause | Frequency | Signature in traces |
|---|---|---|
| **Tool execution failure** | 34% | Non-200 response, timeout, schema mismatch, empty return |
| **LLM hallucination** | 22% | Confident response with no tool call, or tool call with no evidence |
| **Parameter corruption** | 19% | Valid JSON with semantically wrong values |
| **Context loss** | 14% | Early context truncated; agent loses task framing mid-run |
| **Orchestration misfire** | 11% | Wrong agent routed, wrong tool selected, wrong order |

### Layer 3 — Repair Strategy Mapping

The key insight: **manifestation ≠ cause ≠ fix**. A visible "execution failure" can root in LLM hallucination (wrong params) or tool execution failure (transient). The repair differs entirely.

```python
# Minimal failure triage — classify before you retry
import json
from enum import Enum
from dataclasses import dataclass

class Manifestation(Enum):
    EXECUTION = "execution"
    REASONING = "reasoning"
    PLANNING = "planning"
    PROPAGATION = "propagation"
    CONVERGENCE = "convergence"

@dataclass
class FailureContext:
    tool_name: str | None
    tool_response: dict | None
    step_index: int
    error: Exception | None
    trace: list[dict]  # full trajectory

def classify_failure(ctx: FailureContext) -> tuple[Manifestation, str]:
    """Map failure evidence to manifestation + probable root cause."""

    # Signal 1: explicit tool error
    if ctx.error or (ctx.tool_response and ctx.tool_response.get("error")):
        return Manifestation.EXECUTION, _blame_tool(ctx)

    # Signal 2: no tool was called where one was expected
    if ctx.step_index > 0 and ctx.trace[ctx.step_index].get("type") == "llm_response":
        prev = ctx.trace[ctx.step_index - 1]
        if prev.get("type") == "tool_call" and prev.get("result", {}).get("empty"):
            return Manifestation.PROPAGATION, "upstream_empty_result"

    # Signal 3: reasoning step produced confident non-action
    step = ctx.trace[ctx.step_index]
    if step.get("type") == "llm_response":
        content = step.get("content", "")
        if "i will" in content.lower() and not step.get("tool_calls"):
            return Manifestation.REASONING, "hallucinated_action_plan"

    # Signal 4: step count exceeds threshold without termination
    if ctx.step_index > 15:
        return Manifestation.CONVERGENCE, "possible_loop_or_drift"

    # Signal 5: check for planning gap
    if ctx.step_index == 2 and not ctx.trace[0].get("decomposition"):
        return Manifestation.PLANNING, "no_task_decomposition"

    return Manifestation.EXECUTION, "unknown"


def repair(strategy: str, ctx: FailureContext) -> dict:
    """Apply cause-specific repair. Returns (retry_params, fallback_action)."""

    dispatch = {
        "tool_transient": {"retry": 2, "backoff": "exponential", "fallback": "skip_and_notify"},
        "tool_hallucinated_params": {"retry": 0, "fallback": "reprompt_with_constraints"},
        "upstream_empty_result": {"retry": 0, "fallback": "rollback_to_checkpoint"},
        "no_task_decomposition": {"retry": 0, "fallback": "invoke_planner"},
        "possible_loop_or_drift": {"retry": 0, "fallback": "halt_and_audit"},
    }

    cause = classify_failure(ctx)[1]
    return dispatch.get(cause, {"retry": 1, "fallback": "log_and_continue"})


def _blame_tool(ctx: FailureContext) -> str:
    """Distinguish tool execution failure from hallucinated parameters."""
    resp = ctx.tool_response or {}

    # Empty result from a query tool = likely upstream failure (retry)
    if resp.get("empty") or resp.get("count", 1) == 0:
        return "tool_transient"

    # Valid schema but semantically wrong values = hallucination (don't retry blindly)
    if "results" in resp and not resp.get("error"):
        return "tool_hallucinated_params"

    return "tool_transient"
```

### The diagnostic pattern in practice

1. **Instrument at the tool layer first.** The majority of workflow failures manifest downstream of a tool failure. If your traces don't capture tool response status codes and schema validation results, you can't triage.
2. **Tag every failure with (manifestation, root_cause) at the point of occurrence.** Don't defer classification to post-mortem. The trace should carry the diagnosis.
3. **Repair strategy is determined by cause, not by manifestation.** A propagation failure from an upstream empty result is fixed by rollback, not by retrying the current step.
4. **Build a failure log.** Track (failure_type → repair → outcome) across runs. After 50 failures you have an empirical map of what actually breaks in *your* system — which is more useful than any generic taxonomy.

## Receipt

> Verified 2026-07-15 — Pattern synthesized from the AgentFail dataset (arXiv:2509.23735v2, ICML 2026 FAGEN Workshop, 307 real production failures from Dify, Coze, n8n, and AutoGen workflows). The tool-execution-first triage heuristic (34% of failures root in tool layer, not LLM) and the propagation gap (58% of failures where you see it ≠ where it started) are empirically validated. Code example is a functional distillation — traces a single failure through classification to repair dispatch.

## See also

- [S-1016 · Agent Failure Intervention](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — what to do after a failure is confirmed
- [S-1012 · Agent Failure Recovery](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — convergence and loop recovery
- [S-1018 · Component-Level Attribution](s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — tracing failures to specific agents or tools
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — reliability discipline for agent teams
