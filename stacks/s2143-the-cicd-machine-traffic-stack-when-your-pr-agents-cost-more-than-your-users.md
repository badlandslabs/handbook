# S-2143 · The CI/CD Machine Traffic Stack — When Your PR Agents Cost More Than Your Users

Your user-facing AI handles 10,000 requests per day and costs $X per month. Your AI code-review agent fires on every pull request across 50 engineers, 15 PRs per week, 5 agent steps per invocation, and multi-thousand-token contexts at each step. That agent silently costs 3× your entire user-facing AI spend — and your provider invoice tells you nothing about which pipeline or which step caused it. This is not a cost problem. It is an attribution problem: machine traffic has a fundamentally different cost shape than user traffic, and most teams discover this only when the bill arrives.

## Forces

- **Machine traffic scales with code velocity, not user count.** User-facing AI is bounded by daily active users and request frequency. CI/CD AI scales with merge frequency, eval suite size, and agent step count — all of which grow with team size, sprint velocity, and automation coverage. The cost ceiling is not user count; it is commit frequency.
- **Standard invoices answer "how much" but not "why."** Provider billing aggregates by total spend. Without per-request metadata tagging, a budget overrun triggers a blank-ban response — killing the productivity gain entirely, even when the overrun is contained to one pipeline.
- **Cost compounding per agent step.** Each PR review invocation chains 4–5 agent steps. Each step carries its own context, model call, and token count. A 20% cost overrun at step 1 becomes a 100% overrun by step 5. Multipliers are invisible when you only see the final invoice.
- **CI gating requires cost awareness that doesn't exist yet.** A regression eval that costs $50 per run is fine at 10 runs/day. At 500 runs/day across 50 engineers, it becomes the largest LLM cost center in the organization — before anyone notices it is a cost center at all.

## The move

**1. Mandatory request tagging.** Attach metadata to every LLM call: pipeline name, repository, step number, triggering event (PR, schedule, manual). Without this, attribution stops at the invoice total.

**2. Hierarchical cost-center budgets with three threshold tiers:**
- **75% threshold** → Slack alert: "pipeline X is at 75% of its monthly budget"
- **90% threshold** → Constrained mode: route premium model calls to cheaper fallbacks (virtual-model routing)
- **100% threshold** → Hard gate: HTTP 429 returned to the calling pipeline; no silent cost bleed

**3. Per-task cost attribution.** Tag every agent step as a distinct cost unit. A single PR review has 4–5 step costs that should be individually visible, not bundled into a single invoice line. This surfaces which step (tool-calling, code analysis, diff review, comment posting) is the actual cost driver.

**4. Rolling P95 forecast per cost center.** A 7-day rolling P95 forecast per pipeline predicts tomorrow's overrun today. Budget fires at forecast, not at actuals — by the time the invoice arrives, the overrun is already consumed.

**5. CI cost gate.** Treat LLM cost as a first-class CI citizen: each pipeline has an allocated budget. Eval suites and smoke tests have per-run cost limits. Exceeding the limit fails the CI step with a descriptive error — not a silent pass.

```python
# Cost-attributed LLM call wrapper
def llm_call(messages, step_name, cost_center, budget_tier="default"):
    tags = {
        "pipeline": os.getenv("CI_PIPELINE_NAME"),
        "repository": os.getenv("CI_REPO"),
        "step": step_name,
        "trigger": os.getenv("CI_TRIGGER", "manual"),
        "cost_center": cost_center,
    }
    response = model.invoke(messages, metadata={"tags": tags})
    cost = estimate_cost(response)

    # Budget check at 75%, 90%, 100%
    check_budget(cost_center, cost)

    # Route to fallback if constrained mode
    if is_constrained(cost_center):
        response = fallback_model.invoke(messages, metadata={"tags": tags})

    return response

# Per-step cost tracking
def check_budget(cost_center, current_cost):
    tier = get_budget_tier(cost_center)  # returns soft/hard/constrained
    spent = get_spent(cost_center)
    limit = get_limit(cost_center)
    pct = (spent + current_cost) / limit

    if pct >= 1.0:
        raise BudgetExceeded(f"Hard budget at {pct:.0%} for {cost_center}")
    elif pct >= 0.90:
        activate_constrained_mode(cost_center)
        alert(f"90% threshold hit for {cost_center}")
    elif pct >= 0.75:
        alert(f"75% threshold hit for {cost_center}")
```

## Receipt
> Verified 2026-08-04 — Researched TrueFoundry blog (Boyu Wang, Jun 2026) on agentic CI/CD token costs. TrueFoundry AI Gateway implements all five primitives above (mandatory tagging, three-tier budgets, per-step attribution, P95 forecasting, virtual-model fallback routing). Key finding: a security-review agent on every PR can cost 3× the entire user-facing AI workload. Machine traffic cost shape is fundamentally different — bounded by commit frequency, not user count.

## See also
- [S-02 · Context Budget](s02-context-budget.md) — Context as a finite, expensive resource
- [S-1890 · The Difficulty-Aware Escalation Stack](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — Cost of being wrong vs. cost of inference
- [S-2140 · The Agent Evaluation Stack](s2140-the-agent-evaluation-stack-when-your-agent-ships-to-production-without-a-single-test.md) — Eval costs that compound silently
