# S-1349 · The Pre-Flight Cost Estimation Stack

When you dispatch an agent task, the orchestrator has no idea what it will cost. It fires the task and finds out at the end of the month. Every runaway AI bill — the $87,000 in 11 days, the $500M enterprise Claude bill, the $500–2,000 individual monthly invoices — shares the same root cause: **cost is discovered after commitment, not before.**

## Situation

A background monitoring agent reviews a context window every five minutes. At 1M tokens per read at $15/M input tokens, that's $180/hour. Fifty engineers with this pattern running in parallel: $9,000/hour, $216,000/day — before a single line of code is committed. The orchestrator approved each dispatch. It had no way to know. An agent tasked with generating a weekly report autonomously pulls ten thousand rows, runs them through a frontier model, and iterates six times. The report delivers $30 of business value. The compute bill is $340.

Standard agent frameworks operate on `reason → act → observe → repeat`. They are completely blind to unit economics. The agent treats all computational pathways as free. Naive agents don't estimate before spending; they optimize for task completion regardless of cost.

## Forces

- **Token cost is asymmetric**: output tokens are 4–5× more expensive per token than input tokens. A verbose agent generates more cost than a concise one for the same task.
- **Context accumulation makes costs superlinear**: after 20 steps, a task that started at 5K tokens may consume 80K–200K. Cost grows quadratically, not linearly. Linear cost models are systematically wrong.
- **Recursive loops compound silently**: when agents review each other's outputs in a loop (plan → review → revise → review → ...), each pass re-ingests the full context. A $0.003 review pass becomes $180/hour at enterprise scale.
- **Production volume breaks pilot extrapolations**: a pilot running 100 simple sessions/day can extrapolate to 10,000 complex multi-step sessions. Realistic production cost is typically 1.5–3× the pilot extrapolation.
- **Cost is invisible at dispatch time**: traditional observability captures cost *after* it accumulates. The invoice arrives after the damage is done.

## The move

Inject a **pre-flight estimation step** into the agent dispatch cycle. Before the orchestrator commits a task, it estimates the full task-chain cost — then routes, approves, blocks, or alerts based on that projection.

### Architecture: Five-Layer Estimator

**Layer 1 — Input Token Projection**
```
estimated_input_tokens =
  system_prompt_tokens
  + tool_definitions_tokens (× step_count)
  + conversation_history_tokens
  + task_input_tokens
  + per_step_accumulation_cost
```
Per-step accumulation is the key variable: `input_tokens(step_n) = input_tokens(step_1) + (n × avg_turn_size)`. This is the superlinear term.

**Layer 2 — Output Token Projection**
Use task-type priors:
| Task type | Expected output tokens | Confidence |
|---|---|---|
| Classification | 50–200 | High |
| Summarization | 500–2,000 | Medium |
| Code generation | 2,000–10,000 | Medium |
| Multi-step research | 5,000–50,000 | Low |
| Recursive review | Unknown (flag) | None |

**Layer 3 — Step Count Estimation**
Estimate steps from task complexity classification:
- Single-step: 1 call
- Linear multi-step: 3–8 calls
- Branching: 8–20 calls
- Recursive/review: Unbounded (flag for approval)

**Layer 4 — Cost Projection**
```
estimated_cost =
  (estimated_input_tokens × input_rate)
  + (estimated_output_tokens × output_rate)
  × retry_multiplier
  × volume_discount_factor
```
The `retry_multiplier` accounts for the reality that 15–30% of agent tasks require at least one retry.

**Layer 5 — Dispatch Gate**
```
if estimated_cost > hard_cap:         BLOCK → route to cheaper model or single-call fallback
if estimated_cost > soft_cap:         ALERT → notify owner, log intent, proceed
if task_complexity == "recursive":    ESCALATE → require human approval
if step_estimate > max_steps:          FLAG → pre-flight must reconfirm mid-stream
if task_value < estimated_cost:        WARN → task cost may exceed business value
else:                                  PROCEED
```

### Key Data Sources for Estimation

- **Task-type cost priors**: historical data from completed tasks of the same type — the most accurate predictor.
- **Model pricing sheets**: current rates from OpenAI, Anthropic, Google. Keep in a config file, not hardcoded.
- **Context window sampling**: sample actual token counts from production logs to calibrate the superlinear term.
- **Tool call overhead**: measure average tool definition token count per framework (LangChain, CrewAI, custom) — differs by 2–5×.

### The Background Agent Problem

Background and recursive agents are the highest-risk category. For any agent that runs without human-initiated dispatch:
- Set a **maximum dispatch rate**: no more than N dispatches per hour without explicit re-approval.
- Estimate the **per-hour burn rate** from dispatch frequency × estimated per-dispatch cost.
- Alert when burn rate exceeds a configured threshold — before the day-end invoice.

### Implementation: Minimal Working Estimator

```python
# hermes-preflight-style estimator (~50 lines, zero dependencies)

from dataclasses import dataclass
from typing import Literal

@dataclass
class ModelRate:
    input_per_million: float
    output_per_million: float

MODEL_RATES = {
    "gpt-4o":       ModelRate(2.50, 10.00),
    "claude-opus":  ModelRate(15.00, 75.00),
    "claude-sonnet":ModelRate(3.00, 15.00),
    "claude-haiku": ModelRate(0.25,  1.25),
}

def estimate_task_cost(
    task_type: Literal["classify", "summarize", "research", "code", "review"],
    input_size: int,           # tokens in the initial input
    model: str = "claude-sonnet",
    expected_steps: int | None = None,
) -> dict:
    rates = MODEL_RATES[model]

    # Step count heuristic by task type
    step_defaults = {"classify": 1, "summarize": 1, "code": 5,
                     "research": 12, "review": 8}
    steps = expected_steps or step_defaults.get(task_type, 3)

    # Superlinear accumulation: each step adds prior turns
    avg_turn_size = input_size
    accumulated_input = sum(
        avg_turn_size + (i * avg_turn_size * 0.1)
        for i in range(steps)
    )

    # Output projection
    output_estimates = {"classify": 200, "summarize": 1500,
                        "code": 5000, "research": 8000, "review": 2000}
    output_tokens = output_estimates.get(task_type, 1000)
    total_output = output_tokens * steps

    cost = (accumulated_input / 1_000_000 * rates.input_per_million
            + total_output   / 1_000_000 * rates.output_per_million)
    cost *= 1.25  # retry multiplier

    return {
        "estimated_cost_usd":  round(cost, 4),
        "estimated_steps":     steps,
        "estimated_input_tokens": int(accumulated_input),
        "estimated_output_tokens": int(total_output),
        "gate": "PROCEED" if cost < 0.10
               else "ALERT" if cost < 1.00
               else "BLOCK",
    }
```

### Operational Pattern: FinOps-Native Orchestration

1. **Register task types** with cost priors and value thresholds in the orchestrator config.
2. **Run pre-flight** before every dispatch — synchronous, <10ms.
3. **Route on gate result**: BLOCK → cheaper model or single-call fallback; ALERT → log and proceed with tracking; ESCALATE → queue for human approval.
4. **Track actual vs. estimated** to calibrate priors. Systematic over/under-estimation reveals model behavior changes or context accumulation drift.
5. **Daily burn rate alerts**: sum pre-flight estimates for the day, compare against budget. Alert at 50%, 80%, 100% of daily budget.

## Receipt

> Verified 2026-07-19 — Research synthesis from: ByteIOTA ($500M enterprise AI bill analysis, June 2026); a21ai.hashnode.dev (FinOps-native orchestration patterns, 2026); tokenscost.com agent loop cost estimator; GitHub hermes-preflight (hijrahassalam/hermes-preflight, MIT, May 2026); Solv Systems AI agent cost benchmarks (June 2026); AnhTu.dev token economics guide. Pre-flight estimation is operationally distinct from S-832 (quadratic cost mechanics), F-23 (pre-build estimation), S-99 (per-task unit economics), and I-175 (trace-attributed post-hoc cost optimization). The novel contribution is dispatch-time estimation enabling gate decisions before commitment.

## See also

- [S-832](s832-the-quadratic-cost-stack-when-linear-steps-create-quadratic-bills.md) — The Quadratic Cost Stack: why costs compound superlinearly in agent loops
- [S-99](s99-agent-task-economics.md) — Agent Task Economics: per-task unit cost model
- [F-23](../forward-deployed/f23-cost-estimation.md) — Pre-Build Cost Estimation: design-time estimation before agent construction
- [S-56](s56-preflight-token-check.md) — Pre-Flight Token Check: context capacity verification before dispatch
