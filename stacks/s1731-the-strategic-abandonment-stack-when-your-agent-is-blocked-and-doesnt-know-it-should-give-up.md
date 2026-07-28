# S-1731 · The Strategic Abandonment Stack — When Your Agent Is Blocked and Doesn't Know It Should Give Up

An agent is given a task: extract customer records from the CRM, enrich them with billing data, and generate a churn report. After 40 minutes it produces a 12-page document titled "Churn Report." The data is from 2021. The API it queried was deprecated in 2023. The billing endpoint requires credentials the agent never had. Every downstream step ran on hallucinated inputs — not because the model hallucinated, but because the agent never detected the block and never course-corrected. It was not designed to abandon.

Most agent frameworks optimize for completion, not for adaptive abandonment. The agent runs until it produces output. The failure mode is not a crash — it is confident completion on corrupted state. This is the Strategic Abandonment gap: agents lack a structured mechanism for recognizing when a task is blocked, escalating or pivoting rather than compounding on stale inputs.

## Forces

- **Completion pressure is architectural.** Agent loops are designed to continue until a terminal condition. The terminal condition is typically token budget, not semantic success. This creates a systematic bias toward continued execution even when every signal suggests failure.
- **Agents cannot distinguish "blocked" from "slow."** A deprecated API returns empty results. A missing credential returns a 401. An empty dataset looks identical to a correct result at the API boundary — both are just JSON. Without explicit null-state detection and branching logic, the agent treats empty as valid and proceeds.
- **Compounding on stale inputs is invisible.** The Hugging Face eval model ran 17,000+ actions over a weekend because nothing told it to stop. The eval environment was degraded. The model adapted around the degradation rather than reporting it. The failure wasn't capability — it was the absence of a strategic abandonment signal.
- **Human escalation requires a signal, not a story.** If the agent silently compounds on stale data, the human overseer sees a completed task, not a blocked one. The escalation never fires.

## The move

Build an explicit Block-Detection → Strategy-Pivot → Escalation pathway into the agent loop. The mechanism has four layers:

### 1. Block-State Detection (per step)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class BlockState(Enum):
    CLEAR = "clear"
    EMPTY_RESULT = "empty_result"      # API returned, but no data
    AUTH_FAILURE = "auth_failure"       # 401/403, credential missing
    RATE_LIMITED = "rate_limited"       # 429, temporary block
    SCHEMA_MISMATCH = "schema_mismatch" # response shape unexpected
    DEPRECATED = "deprecated"           # version header or sunset notice
    UNKNOWN = "unknown"

@dataclass
class StepResult:
    tool_name: str
    raw_response: dict
    block_state: BlockState
    attempts: int = 1
    degraded_since: Optional[str] = None  # ISO timestamp of first degradation

def detect_block(result: StepResult) -> BlockState:
    if result.raw_response is None:
        return BlockState.UNKNOWN
    if result.raw_response.get("error"):
        code = result.raw_response["error"].get("code", "")
        if "auth" in code or "credential" in code:
            return BlockState.AUTH_FAILURE
        if "rate" in code or "quota" in code:
            return BlockState.RATE_LIMITED
    if result.raw_response.get("__deprecated__") or "sunset" in str(result.raw_response):
        return BlockState.DEPRECATED
    if isinstance(result.raw_response.get("data"), list) and not result.raw_response["data"]:
        return BlockState.EMPTY_RESULT
    # Schema drift: response has unexpected structure
    if "billing_records" in result.raw_response and "records" in result.raw_response:
        return BlockState.SCHEMA_MISMATCH  # duplicate alias, possible version mismatch
    return BlockState.CLEAR
```

### 2. Strategy-Pivot Rules (per task phase)

```python
class PivotStrategy(Enum):
    RETRY_SAME_ENDPOINT = "retry_same"
    SWAP_TO_FALLBACK_ENDPOINT = "swap_fallback"
    DECOMPOSE_TO_SIMPLER_STEP = "decompose"
    REQUEST_MISSING_CONTEXT = "request_context"   # ask human for credentials, API key
    ABANDON_AND_REPORT = "abandon_report"
    ESCALATE = "escalate"

PIVOT_TABLE = {
    # (block_state, attempts, has_fallback) -> pivot_strategy
    (BlockState.CLEAR, 1, _): PivotStrategy.RETRY_SAME_ENDPOINT,  # shouldn't happen
    (BlockState.AUTH_FAILURE, 1, False): PivotStrategy.REQUEST_MISSING_CONTEXT,
    (BlockState.AUTH_FAILURE, 2, _): PivotStrategy.ESCALATE,
    (BlockState.RATE_LIMITED, 1, _): PivotStrategy.RETRY_SAME_ENDPOINT,
    (BlockState.RATE_LIMITED, 3, _): PivotStrategy.DECOMPOSE_TO_SIMPLER_STEP,
    (BlockState.EMPTY_RESULT, 1, True): PivotStrategy.SWAP_TO_FALLBACK_ENDPOINT,
    (BlockState.EMPTY_RESULT, 2, _): PivotStrategy.REQUEST_MISSING_CONTEXT,
    (BlockState.DEPRECATED, 1, True): PivotStrategy.SWAP_TO_FALLBACK_ENDPOINT,
    (BlockState.DEPRECATED, 1, False): PivotStrategy.ESCALATE,
    (BlockState.SCHEMA_MISMATCH, 1, _): PivotStrategy.DECOMPOSE_TO_SIMPLER_STEP,
    (BlockState.SCHEMA_MISMATCH, 2, _): PivotStrategy.ESCALATE,
}

def decide_pivot(result: StepResult, attempts: int, has_fallback: bool) -> PivotStrategy:
    key = (result.block_state, attempts, has_fallback)
    if key in PIVOT_TABLE:
        return PIVOT_TABLE[key]
    if attempts >= 3:
        return PivotStrategy.ESCALATE
    return PivotStrategy.DECOMPOSE_TO_SIMPLER_STEP
```

### 3. Abandonment Report (emit on strategic give-up)

When the pivot strategy is `ABANDON_AND_REPORT`, the agent emits a structured abandonment record — not a raw error, but a semantic summary:

```python
@dataclass
class AbandonmentReport:
    task_id: str
    blocked_at_step: int
    block_state: BlockState
    attempted_endpoints: list[str]
    degradation_duration_seconds: Optional[int]
    compounding_risk: bool        # True if downstream steps ran on degraded input
    human_readable_summary: str
    recovery_hint: str             # What a human would need to unblock

def format_abandonment(report: AbandonmentReport) -> str:
    risk_flag = "⚠️ COMPOUNDING" if report.compounding_risk else "✓ isolated"
    return (
        f"[STRATEGIC ABANDONMENT]\n"
        f"Task: {report.task_id}\n"
        f"Blocked at step {report.blocked_at_step}: {report.block_state.value}\n"
        f"Risk: {risk_flag}\n"
        f"Downstream steps compromised: {report.compounding_risk}\n"
        f"Recovery requires: {report.recovery_hint}\n"
        f"\n{report.human_readable_summary}"
    )
```

### 4. The Orchestration Loop

```python
def agent_loop(task: str, steps: list[dict], max_attempts: int = 3):
    context = {}
    abandonment: Optional[AbandonmentReport] = None

    for step_idx, step in enumerate(steps):
        for attempt in range(1, max_attempts + 1):
            result = execute_tool(step["tool"], step["params"], context)
            block = detect_block(result)

            # Track degradation across attempts
            if block != BlockState.CLEAR:
                if result.degraded_since is None:
                    result.degraded_since = result.timestamp

            pivot = decide_pivot(block, attempt, has_fallback=step.get("fallback_tool"))
            if pivot == PivotStrategy.RETRY_SAME_ENDPOINT and attempt < max_attempts:
                continue
            elif pivot in (PivotStrategy.SWAP_TO_FALLBACK_ENDPOINT, PivotStrategy.DECOMPOSE_TO_SIMPLER_STEP):
                step = apply_pivot(step, pivot)
                continue
            elif pivot == PivotStrategy.REQUEST_MISSING_CONTEXT:
                context.update(request_missing_info(step, block))
                continue
            elif pivot in (PivotStrategy.ABANDON_AND_REPORT, PivotStrategy.ESCALATE):
                abandonment = AbandonmentReport(
                    task_id=task["id"],
                    blocked_at_step=step_idx,
                    block_state=block,
                    attempted_endpoints=[...],
                    degradation_duration_seconds=...,
                    compounding_risk=(attempt > 1),
                    human_readable_summary=summarize_block(task, step, block),
                    recovery_hint=recovery_hint_for(block),
                )
                return {"status": "abandoned", "report": abandonment}
            else:
                break  # pivot applied, continue to next step

        context[step["key"]] = result.raw_response

    return {"status": "completed", "context": context, "abandonment": abandonment}
```

The key insight: abandonment is not failure — it is a correct strategy response to an unsolvable condition. Agents that never abandon will always produce output. That output is not a success signal.

## See also
- [S-1716 · The Egress Boundary Stack](/stacks/s1716-the-egress-boundary-stack-when-your-sandbox-leaks-through-the-proxy.md) — the Egress Boundary failure is often enabled by an agent that compounds rather than abandons when degraded
- [S-1730 · The Cascading Silence Stack](/stacks/s1730-the-cascading-silence-stack-when-your-agent-fails-and-takes-down-the-pipeline.md) — cascading silence is the consequence when abandonment is absent from the orchestration loop
- [S-1662 · The Runaway Retry Stack](/stacks/s1662-the-runaway-retry-stack-when-your-agent-spends-47-attempts-on-the-same-failing-call.md) — retry without abandonment compounds on the same degraded input; strategic abandonment is the fix
