# S-857 · The Test-Time Compute Budget Stack — When Your Agent Thinks Too Much and Costs Too Much

Your agent spent 48,000 tokens reasoning about a task a human would have solved in two sentences. The answer was wrong anyway. Another agent silently gave up after 500 tokens — the task needed five minutes of deliberation, and nobody told it to take more time. Both failures have the same root: **reasoning budget is the knob nobody tunes**. Test-time compute (how long the model "thinks" at inference) is now the primary lever for agent quality and cost — and most agent stacks don't touch it deliberately.

## Forces

- **Reasoning time is the new parameter count.** Since 2025, the frontier has shifted from "how big is your model" to "how long does your model think." OpenAI o3 scores 45.1% on ARC-AGI-2 where pure LLM inference scores 0%. Kimi K2.5 deploys 100 specialized agents in parallel, each with tuned reasoning depth. Compute allocation at inference is now a first-class engineering concern.
- **Agents set reasoning budget once and forget it.** Fixed `max_tokens` or fixed loop counts apply the same thinking effort to a "what is 2+2" query and a multi-step code refactoring. Easy queries get over-budget; hard queries silently under-resolve. The result is Pareto waste — too much on simple tasks, too little on complex ones.
- **Reasoning budget is invisible unless you measure it.** If you don't log `completion_tokens` per step and correlate to outcome quality, you can't see the problem. Most agent observability tracks latency and error rates, not reasoning token efficiency.

## The move

Manage reasoning budget as a dynamic, observable, task-adaptive resource — not a fixed config value.

### 1. Milestone checkpoint with conditional expansion

At each sub-task boundary, inject a self-evaluation prompt that asks: "Am I confident in my current answer? What would more reasoning change?" If confidence is low, expand the budget for the next step. If high, commit and move on.

```python
THINK_BUDGET_INITIAL = 512   # tokens for first reasoning pass
THINK_BUDGET_EXPAND   = 2048 # tokens if self-eval signals low confidence
THINK_BUDGET_MAX      = 8192 # hard cap per step

def agent_step(state, task):
    budget = THINK_BUDGET_INITIAL
    for attempt in range(3):
        response = llm.call(
            prompt=build_prompt(state, task),
            max_tokens=budget,
            reasoning={"effort": "medium" if attempt == 0 else "high"}
        )
        # Milestone: self-evaluate before committing
        eval_prompt = (
            f"Task: {task}\n"
            f"Answer so far: {response.text}\n"
            "Rate confidence 0-1. If <0.7, list what more reasoning would change."
        )
        eval = llm.call(eval_prompt, max_tokens=128)
        confidence = parse_confidence(eval.text)
        if confidence >= 0.7 or budget >= THINK_BUDGET_MAX:
            return commit(response)
        budget = min(budget * 2, THINK_BUDGET_MAX)
```

### 2. Budget cascade: probe → allocate → verify

Rather than committing to a fixed budget upfront, use a cheap probe to estimate task difficulty, then allocate reasoning budget proportionally.

```python
def budgeted_agent(task):
    # Step 1: Probe — cheap, fast estimate of difficulty
    probe = llm.call(task, max_tokens=64, model="fast-cheap")
    difficulty_score = estimate_difficulty(probe)  # heuristic: token count, hesitation markers, sub-question count

    # Step 2: Allocate budget based on difficulty
    budget_map = {
        "trivial":    128,
        "standard":   512,
        "complex":    2048,
        "research":   8192,
    }
    budget = budget_map[bin(difficulty_score)]

    # Step 3: Full reasoning at allocated budget
    result = llm.call(task, max_tokens=budget, model="strong-reasoning")

    # Step 4: Optional verify pass for high-stakes outputs
    if is_high_stakes(task):
        verification = llm.call(
            f"Verify this answer for errors: {result.text}\nOriginal task: {task}",
            max_tokens=256
        )
        if verification.flags_critical():
            result = escalate_to_human(result)
    return result
```

### 3. Log and tune from production data

Instrument every step with `{step_id, task_type, budget_used, outcome_correct, outcome_quality_score}`. After N runs, compute the accuracy curve per task type as a function of budget. Use it to re-tune the budget_map.

```python
# Analysis: accuracy vs. budget per task type
# results_df from production telemetry
budget_curves = (
    results_df
    .groupby("task_type")["budget_used"]
    .apply(lambda x: accuracy_at_budget(x, results_df["outcome_correct"]))
)
# Tune budget_map: set budget where marginal accuracy gain < 5%
```

## Why this works

- **Pareto efficiency.** Resources go where they add value, not everywhere equally.
- **Graceful degradation.** Low-confidence responses don't silently propagate — the budget expands or the task escalates.
- **Observable tradeoffs.** Budget vs. quality curves give you a data-driven config, not a guess.
- **Model-agnostic.** Works with o3/o4, DeepSeek-R1, Claude 3.7 Sonnet extended thinking, or any reasoning-capable model.

## When to reach for it

- You have reasoning models in production and are not tracking `completion_tokens` per step.
- Your agent silently fails on complex tasks but over-spends on simple ones.
- You are evaluating whether to use a faster/cheaper model for some tasks but don't have the quality-vs-cost curve to decide.
- Your agent loop has no milestone gates — it commits after one pass.

## Connections

- S-854 (Token Spiral Kill Switch) — dollar budgets and reasoning budgets are related but distinct; this stack is about *how much thinking happens*, S-854 is about *whether it stops at a dollar threshold*.
- S-063 (Agentic Plan Caching) — plan caching reuses reasoning across similar tasks; reasoning budget determines how much planning happens per task before caching kicks in.
- S-853 (Agent Eval Stack) — test-time compute management is only tunable if you measure outcome quality per budget level, which requires the eval infrastructure from S-853.
- S-048 (Self-Correction Gap) — self-correction requires budget for the re-reasoning pass; agents that under-allocate budget can't self-correct even if they know they should.
- S-012 (Antagonistic Validation) — the multi-reviewer pattern is itself a compute allocation strategy: spend reasoning budget on a rival to verify the first agent's output.
