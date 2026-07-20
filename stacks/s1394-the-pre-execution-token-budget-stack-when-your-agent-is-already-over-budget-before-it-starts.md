# S-1394 · The Pre-Execution Token Budget Stack — When Your Agent Is Already Over Budget Before It Starts

Your agent is mid-task, 23 steps in, and has burned through $47 in API costs. The task will take another 12 steps. Nobody set a budget, nobody estimated ahead of time, and the system prompt never defined what "too expensive" means. By the time the monthly invoice surfaces the problem, the damage is done. This is not a cost optimization problem. It is a **pre-execution budget problem**: you do not know what a task will cost until after you have paid for it.

S-1027 (scaffold stack) covers loop detection and mid-run circuit breakers. S-1130 (trace-attributed cost) covers post-hoc cost attribution. S-103 (cost-aware context) covers compaction economics. None of them answer the question you need answered before the first token is spent: **what will this task cost, and is that acceptable?**

## Forces

- **Agents have stochastic step counts.** A task that should take 3 steps sometimes takes 30. Without pre-execution estimation, you cannot distinguish "expected" from "catastrophic" cost until the invoice arrives.
- **The unit economics look fine at demo scale.** One task at $0.14 appears trivial. At 3,000 tasks/day × $0.14 = $420/day = $153,000/year — and outliers at $5–8/task (software engineering) make the average meaningless without variance tracking.
- **Cost compounds with token count multiplicatively.** Each step re-sends the accumulated context. A 20-step task doesn't cost 20× a 1-step task — it costs 20× the average step, but each step is larger than the last. The real cost curve is superlinear, not linear.
- **Runtime circuit breakers are too late.** A budget that only fires when tokens are exhausted lets the agent run over budget until the protocol boundary stops it. The goal is to estimate and approve before any spend occurs.

## The move

Three estimation layers, applied in order before the first LLM call is dispatched:

### 1. Task-type cost fingerprinting

Classify the incoming task by type (classification, extraction, reasoning, code generation, research synthesis). Each type has a measurable average step-count and token-per-step from historical data. Use the empirical distribution — not the happy path — for the budget estimate.

```python
TASK_COST_FINGERPRINTS = {
    "classification":      {"mean_steps": 1.2,  "p95_steps": 3,   "tokens_per_step": 800},
    "extraction":          {"mean_steps": 2.1,  "p95_steps": 5,   "tokens_per_step": 1200},
    "single_hop_reason":   {"mean_steps": 3.4,  "p95_steps": 8,   "tokens_per_step": 2000},
    "multi_hop_reason":    {"mean_steps": 9.7,  "p95_steps": 25,  "tokens_per_step": 3200},
    "code_generation":     {"mean_steps": 11.2, "p95_steps": 35,  "tokens_per_step": 4500},
    "research_synthesis":  {"mean_steps": 22.0, "p95_steps": 60,  "tokens_per_step": 6000},
}

def estimate_task_cost(task_type: str, model: str, prompt_tokens: int) -> dict:
    fp = TASK_COST_FINGERPRINTS[task_type]
    # Estimate at p95 to be conservative
    estimated_input_tokens = fp["p95_steps"] * fp["tokens_per_step"] + prompt_tokens
    estimated_output_tokens = fp["p95_steps"] * 400  # output per step
    cost = (estimated_input_tokens * INPUT_PRICE[model]
            + estimated_output_tokens * OUTPUT_PRICE[model])
    return {"estimated_steps": fp["p95_steps"],
            "estimated_tokens": estimated_input_tokens,
            "estimated_cost": cost,
            "confidence": "p95"}
```

### 2. The budget gate

Before dispatch, compare the estimate against a per-task budget set by policy. The budget should be derived from the task's business value — not from what the model "usually" costs. A $0.05 classification task and a $50 contract review have different appropriate budgets. If estimated_cost > task_budget, reject or route to a cheaper execution path (different model, different agentic depth, or human escalation).

```python
TASK_BUDGETS = {
    "classification":      0.01,
    "extraction":         0.05,
    "single_hop_reason":  0.15,
    "multi_hop_reason":   1.00,
    "code_generation":    5.00,
    "research_synthesis": 10.00,
}

def budget_gate(task_type: str, model: str, prompt_tokens: int) -> str:
    estimate = estimate_task_cost(task_type, model, prompt_tokens)
    budget = TASK_BUDGETS.get(task_type, 0.50)
    if estimate["estimated_cost"] <= budget:
        return "dispatch"
    # Try cheaper model first
    if model != CHEAP_MODEL:
        cheap_estimate = estimate_task_cost(task_type, CHEAP_MODEL, prompt_tokens)
        if cheap_estimate["estimated_cost"] <= budget:
            return f"dispatch:{CHEAP_MODEL}"
    return "escalate"
```

### 3. Runway monitoring

Even with pre-execution gating, track cumulative spend per session against a rolling budget. Fire a soft warning at 50% of budget consumed (the agent can still proceed but the user gets a notification). Fire a hard stop at 90% and route to a supervisor review. Never let an agent run to the protocol-level context or budget exhaustion — the last 10% of a runaway agent's spend is entirely waste.

## When to use it

- **New agent deployments** — before going live, profile the actual step distributions for each task type with the target model. Fingerprints built on demos are wrong by 2–5× in production.
- **Cost overruns that surface on invoices** — the invoice is a lagging indicator. The pre-execution gate is the leading one.
- **Per-customer or per-tenant budgets** — multi-tenant agents need per-tenant budget enforcement that is independent of the global agent state.
- **High-variance task types** (code generation, research synthesis) — these have the widest step-count distributions and are where the superlinear cost curve bites hardest.

## See also

- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — mid-run loop detection and liveness monitoring
- [S-1130 · The Trace-Attributed Cost Optimization Stack](s1130-the-trace-attributed-cost-optimization-stack-when-cheaper-models-cost-more.md) — post-hoc cost attribution by span
- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model selection as a cost lever
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — when compaction economics override context capacity
