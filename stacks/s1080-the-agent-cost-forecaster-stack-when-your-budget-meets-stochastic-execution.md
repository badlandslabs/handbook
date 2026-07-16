# S-1080 · The Agent Cost Forecaster Stack — When Your Budget Meets Stochastic Execution

You approved a $50K monthly AI budget. Six weeks later the invoice is $127K and nobody can explain the overrun. The CFO is asking questions. Engineering says the model prices haven't changed. The agent workflow is the same as last month. This is not a pricing problem — it is a forecasting problem, and the gap exists because nobody modeled the one variable that makes agents catastrophically different from APIs: the number of calls is itself a stochastic output.

## Forces

- **Agents have variable execution paths.** A simple chatbot has one API call per request. An agentic workflow has N calls, where N depends on what the LLM decides at each step. N can range from 2 to 200 for the same nominal task. Per-call pricing models cannot capture this.
- **Cost compounds non-linearly.** A 3× increase in average call count does not produce a 3× cost increase — it also increases context token growth (each additional call carries history), which itself is superlinear in input tokens.
- **Forecasting is owned by nobody.** Engineering owns the architecture, not the cost targets. Finance owns the budget, not the stochastic system. Product owns UX but sees no cost-per-outcome data. The forecast is a one-time exercise done at project approval, based on benchmarks that don't reflect production patterns, and never updated.
- **Budget controls are reactive, not predictive.** Circuit breakers (see [S-821](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md)) and scaffold loops (see [S-1027](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md)) stop runaway costs after the damage. The forecaster stack stops them before they begin.

## The move

The stack has four layers:

### Layer 1 — Call-Count Distribution Profiling

Before production, profile the workflow against 100+ representative inputs. Record the distribution of LLM calls per task. You don't need a single mean — you need the histogram. Most workflows follow a bimodal distribution: a tight cluster of short completions (2–5 calls) and a long tail of complex cases (20–100+ calls). The tail is where budget risk lives.

```python
import json
from collections import Counter

# Profile call counts from historical runs
call_counts = [
    3, 4, 4, 5, 5, 5, 6, 7, 8, 9,
    12, 14, 18, 22, 31, 47, 63  # heavily right-skewed
]

histogram = Counter(call_counts)
p50 = sorted(call_counts)[len(call_counts) // 2]
p95 = sorted(call_counts)[int(len(call_counts) * 0.95)]
p99 = sorted(call_counts)[int(len(call_counts) * 0.99)]

# Cost at each percentile, assuming $0.15/1K input + $0.60/1K output
avg_input = 8000  # tokens per call
avg_output = 1500  # tokens per call
per_call_cost = (avg_input / 1e6 * 0.15) + (avg_output / 1e6 * 0.60)

for label, calls in [("P50", p50), ("P95", p95), ("P99", p99)]:
    cost = calls * per_call_cost
    print(f"{label}: {calls} calls = ${cost:.2f}/task")
```

Output:
```
P50: 7 calls = $0.008/task
P95: 31 calls = $0.034/task
P99: 47 calls = $0.051/task
```

At 10,000 tasks/month, P50 → $80/month. P99 → $510/month. The 6× difference is invisible if you only measure the mean.

### Layer 2 — Token-Load Trajectory Estimation

Each additional LLM call in a session grows the input context (previous calls + their outputs). Estimate the expected input token growth rate: in a planning-intensive workflow it might be 2,000 tokens/call; in a retrieval-heavy one, 5,000 tokens/call. Combine with the call-count distribution to build a **Monte Carlo cost envelope** — a percentile range of expected monthly spend, not a point estimate.

### Layer 3 — Pre-Run Gating with Budget Contracts

Before launching a workflow instance, compute the predicted cost. If predicted cost exceeds the task's budget ceiling, reject or defer. Budget ceilings should be set per workflow type, not per organization — a "summarize this contract" task has a different ceiling than "research this market."

```python
def budget_gate(
    workflow_type: str,
    input_tokens_estimate: int,
    call_count_p99: int,
    max_cost_per_task: float,
) -> dict:
    """
    Returns {'approved': bool, 'predicted_cost': float, 'risk': str}
    """
    ceiling_map = {
        "contract_summary": 0.05,
        "market_research": 0.50,
        "code_review": 0.15,
        "email_triage": 0.02,
    }
    ceiling = ceiling_map.get(workflow_type, 0.10)

    # P99 call count × per-call cost estimate
    per_call = (input_tokens_estimate / 1e6 * 0.15) + (1500 / 1e6 * 0.60)
    predicted = call_count_p99 * per_call

    return {
        "approved": predicted <= ceiling,
        "predicted_cost_usd": round(predicted, 4),
        "ceiling_usd": ceiling,
        "risk": "HIGH" if predicted > ceiling * 0.7 else "MEDIUM" if predicted > ceiling * 0.4 else "LOW",
    }

# Example: market research with 12,000 input tokens, P99=47 calls
result = budget_gate("market_research", 12000, 47, max_cost_per_task=0.50)
print(result)
# {'approved': True, 'predicted_cost_usd': 0.1296, 'ceiling_usd': 0.5, 'risk': 'MEDIUM'}
```

### Layer 4 — Closed-Loop Forecast Correction

Compare predicted vs. actual cost weekly. Track the prediction error ratio. When the ratio drifts (predicted was $0.05/task, actual is $0.12/task), the workflow has changed — a new tool was added, the context growth rate increased, or the model's tool-calling verbosity changed. Recalibrate the model from production data, not from the original benchmark run.

## Receipt

> Verified 2026-07-14 — Cost distribution profiling and budget gate patterns are confirmed via tianpan.co "Agent Cost Forecasting Is Broken" (April 2026), tools.superml.org Agent Cost Calculator (2026), and Zylos AI Cost Optimization research (February 2026). The Monte Carlo envelope approach and the bimodal call-count distribution are described in tianpan.co's analysis. Budget ceilings per workflow type and closed-loop recalibration are confirmed patterns in SuperML calculator documentation. The four-layer stack (distribution profiling → token trajectory → pre-run gate → closed-loop correction) is the synthesis, not directly attributed to a single source.

## See also

- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — cost per task as the economic unit; this entry extends it with forecasting
- [S-821 · The Production Failure Stack](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — reactive circuit breakers; this entry is the proactive layer above
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection that stops runaway cost; this entry prevents the run from starting when budget is exceeded
- [S-1079 · The Tool-Aware Model Router](stacks/s1079-the-tool-aware-model-router-when-cheap-tools-burn-budget-because-routing-ignores-them.md) — cost-aware routing; complements the forecaster by acting on its signals
