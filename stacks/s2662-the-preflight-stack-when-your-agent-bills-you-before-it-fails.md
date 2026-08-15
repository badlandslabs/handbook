# S-2662 · The Preflight Stack — When Your Agent Bills You Before It Fails

You receive a task request at 2am. Your agent starts running. Eighteen minutes and $34 later, it produces nothing useful. Nobody saw it coming. No dashboard warned you. No budget alert fired. This is not a monitoring problem. It is a **preflight problem**: you have no way to estimate the cost of a task before your agent commits to it.

The research is unambiguous. Enterprise AI token consumption grew 1,001% between January 2025 and April 2026. 85% of companies miss their AI cost forecasts by more than 10%. A single agentic session can consume 1–3.5 million tokens — 50 to 500× the footprint of a traditional API call. And the brutalest finding: on identical tasks, the same agent can consume 30× more tokens on one run than another. Token usage is stochastic, not deterministic. You cannot control what you cannot predict.

The Preflight Stack is the architectural layer that predicts cost, complexity, and risk at **decision time** — before the first token is spent. Not a dashboard. A gate.

## Forces

- **Agents are structurally unpredictable.** A chatbot makes one API call. An agentic workflow makes N calls, where N is itself an LLM output. N can be 2 or 200 for the same nominal task. Per-request pricing models cannot capture this.
- **Post-hoc monitoring is too slow.** By the time your cost dashboard shows an anomaly, the invoice is already written. Cost control after execution is accounting, not engineering.
- **Preflight estimates are hard.** Models self-predict their own token usage with at most 0.39 correlation (Bai et al., 2026) — barely better than guessing. Naive prompt-based "how many tokens will this take" fails.
- **The right model depends on the task.** Routing a $0.50 task to a $15/1M-token frontier model is waste. Routing a complex one to a cheap model produces rework that costs more than the original would have. Cost-aware routing requires preflight data.
- **Cost attribution after the fact is lossy.** If you cannot estimate cost before running, you cannot budget per task, per user, or per feature. You get a total bill with no actionable signal.

## The move

### 1. Build the Task Profile

Before any LLM call, construct a lightweight **task profile** from structural signals:

```
task_profile = {
  input_tokens: estimate_from_prompt_structure(task_description),
  expected_turns: estimate_from_task_complexity(task_description),
  tool_count: count_tools_agent_will_invoke(task_description),
  domain: classify_domain(task_description),
  retry_probability: estimate_from_historical_data(domain),
}
```

Input token count is estimable from prompt structure. Expected turns correlate with: (a) the presence of qualifiers like "research," "analyze," "find all," "until done"; (b) the number of tool domains touched; (c) historical median turns for similar tasks. Do not ask the model — ask the task shape.

### 2. Calculate the Cost Envelope

Translate the task profile into a **cost envelope** before execution:

```
envelope = {
  estimated_input_tokens: task_profile.input_tokens
                          * task_profile.expected_turns
                          * tool_call_overhead_factor,
  estimated_output_tokens: avg_output_per_turn * task_profile.expected_turns,
  estimated_cost: (input_tokens * model.input_price
                   + output_tokens * model.output_price)
                  * task_profile.retry_probability_penalty,
  max_acceptable_cost: get_budget_for(task.type, user.tier),
}
```

Key inputs: model pricing tiers (which differ 100× between cheapest and most expensive), tool-call overhead (each tool call adds 200–2,000 tokens to context on average), and a retry multiplier derived from domain-specific failure rates.

### 3. Route to the Right Model Tier

Use the cost envelope to make the routing decision:

```
if envelope.estimated_cost < $0.01:
    tier = "fast_cheap"    # e.g., Gemini Flash, DeepSeek V3
elif envelope.estimated_cost < $0.50:
    tier = "balanced"      # e.g., Claude Sonnet, GPT-4o
else:
    tier = "frontier"       # e.g., o3, Claude Opus, o4-mini
    # and: require human approval for >$5
```

This is not just cost optimization — it is risk stratification. Frontier-tier tasks warrant tighter preflight scrutiny: circuit breakers, step-count limits, and explicit escalation gates.

### 4. Dry-Run Estimation (Optional but High-Value)

For high-stakes tasks (>$1 estimated), run a **lightweight dry-run** before committing:

```python
def dry_run(task_description, model="fast-cheap"):
    """Estimate actual cost with a stripped-down agent run."""
    stripped = strip_to_minimal_context(task_description)
    result = agent.run(stripped, model=model, max_steps=3)
    return {
        "steps_observed": result.step_count,
        "tokens_consumed": result.total_tokens,
        "cost_estimate": result.total_cost,
        "confidence": "low/medium/high"  # based on step saturation
    }
```

The dry-run is not a guarantee — it is a data point. If the dry-run burns 3 steps on a task, full execution on the same task typically consumes 3–8× more tokens (Bai et al.). Use the multiplier conservatively.

### 5. Hard Circuit Breakers at the Envelope Boundary

Integrate cost gating into the execution loop — not as a post-run check:

```python
def execute_with_preflight(task):
    envelope = calculate_cost_envelope(task)
    if envelope.estimated_cost > envelope.max_acceptable_cost:
        return {"status": "blocked", reason: "cost_exceeds_envelope",
                estimate: envelope.estimated_cost,
                limit: envelope.max_acceptable_cost}
    # Attach envelope as execution context
    task.cost_ceiling = envelope.max_acceptable_cost
    task.cost_spent = 0
    return run_with_circuit_breaker(task, on_budget_exceeded=abort)
```

The circuit breaker fires when cumulative cost exceeds the envelope ceiling mid-execution. It is not a kill switch for runaway loops — it is a **predictive gate** that stops tasks before they exceed their assigned budget.

### 6. Spend Attribution Downstream

Every task gets a cost fingerprint at preflight time. Wire it into your observability layer:

- `preflight_estimate`: the envelope calculated at decision time
- `actual_cost`: real cost after execution
- `variance`: actual vs. estimated (tracks prediction accuracy over time)
- `blocking_events`: count of times preflight blocked execution

Track variance per task type, per user tier, per model. Feed it back into the estimation model. Preflight accuracy improves with historical data — a model trained on your own execution traces will outperform generic token counters within weeks.

## Receipt

> Verified 2026-08-14 — Research synthesis from: Bai et al. (arXiv:2604.22750) on agent token consumption patterns; Zylos Research "Token Budget Management for Autonomous AI Agents" (2026-06-30); Brendan Bondurant "Why Your LLM Bill Exploded Overnight" (2026-07-13); GitHub repos hermes-preflight and pre-run-token-estimator as implementation references. Enterprise AI token consumption: 1,001% growth Jan 2025–Apr 2026. Cost forecast miss rate: 85% by >10%. Token variance on identical tasks: up to 30×. Model self-prediction correlation: max 0.39. Implementation confirmed workable via existing OSS tools (hermes-preflight, pre-run-token-estimator) plus structural envelope estimation from prompt/task signals.

## See also

- [S-1080 · The Agent Cost Forecaster Stack](/stacks/s1080-the-agent-cost-forecaster-stack-when-your-budget-meets-stochastic-execution.md) — forecasting aggregate spend across an agent fleet
- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — detecting and stopping runaway agent loops mid-execution
- [S-1079 · The Tool-Aware Model Router](/stacks/s1079-the-tool-aware-model-router-when-cheap-tools-burn-budget-because-routing-ignores-them.md) — routing decisions that account for tool-call token overhead
- [S-103 · Cost-Aware Context Management](/stacks/s03-context-budget.md) — managing the context window that drives token consumption
