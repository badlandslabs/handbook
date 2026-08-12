# S-2518 · The Failure Compounding Stack — When Your Agent Succeeds Once and Fails Twice

Your agent completes a 5-step task. You ship it. A 12-step version of the same task fails — not because the agent got dumber, but because the failure probability per step doesn't add linearly. It multiplies super-linearly. Eight additional steps didn't add 8× more failure chance; they multiplied the existing failure modes into a different regime. This is Lusser's Law with a twist: stochastic compounding means the breakpoints are not where you think they are.

## Forces

- **Agent failures scale super-linearly with task complexity.** arXiv:2607.05775 (Albayaydh et al., Oxford, July 2026) — synthesizing 27 papers across 19 benchmarks — establishes that LLM agent failures compound nonlinearly. An 8-step task is not 2× harder than a 4-step task; it enters a different failure regime where error propagation, context contamination, and plan repair failures interact.
- **Benchmark reliability ≠ production reliability.** Benchmark success rates measure single-task pass/fail in controlled environments. PlanBench-XL (arXiv:2606.22388) shows that models degrading gracefully in benchmarks fail catastrophically in large tool ecosystems — not because they lose capability, but because the failure modes change in kind. SWE-bench validates 12–18% tool call failure rates in production that benchmarks never surface (AgentMarketCap, April 2026).
- **Existing compounding models are wrong.** S-200 (Agent Reliability Compounding) covers the linear product-of-reliabilities case. That model assumes each step fails independently with constant probability. Production reality violates both assumptions: failures are correlated (a bad tool call poisons the context for subsequent steps) and the per-step failure rate changes as context grows and plans drift.
- **Six distinct failure clusters drive compounding.** The Oxford taxonomy identifies: (1) tool invocation and parameter errors, (2) planning and constraint-satisfaction failures, (3) long-horizon degradation from context accumulation, (4) multi-agent coordination failures, (5) safety/security failures under adversarial or underspecified conditions, and (6) measurement validity problems. Each cluster amplifies the others as complexity grows.

## The Move

### 1. Replace linear compounding with regime-aware models

Do not use `P(success) = p^n` where p is your single-step reliability. Instead, model three regimes:

- **Regime 1 (n ≤ 5 steps):** Per-step independence approximately holds. Linear compounding is close enough. Budget for 3–5% end-to-end failure rate.
- **Regime 2 (5–15 steps):** Context contamination begins. Steps are no longer independent — a malformed tool response in step 4 degrades steps 5–n. Budget for 15–30% end-to-end failure rate.
- **Regime 3 (n > 15 steps):** Plan repair failures dominate. The agent spends more tokens on replanning than on task progress. Context overflow triggers arbitrary truncation. Budget for 50%+ end-to-end failure rate until you add explicit checkpointing.

```python
# Regime-aware failure model
def regime_aware_success_rate(n_steps, p_independent=0.95, context_contamination_rate=0.03):
    if n_steps <= 5:
        return p_independent ** n_steps  # Linear regime
    elif n_steps <= 15:
        # Steps 1-5: independent; steps 6+ accumulate contamination
        independent_steps = 5
        contaminated_steps = n_steps - independent_steps
        return (p_independent ** independent_steps) * \
               ((p_independent - context_contamination_rate) ** contaminated_steps)
    else:
        # Long-horizon regime: replan overhead kicks in
        # Each re-plan attempt costs ~0.15 reliability points
        replan_penalty = 0.15 * (n_steps - 15)
        effective_p = max(0.1, p_independent - replan_penalty)
        return effective_p ** n_steps
```

### 2. Track per-cluster failure rate, not aggregate rate

The six clusters require independent instrumentation. Aggregate success rate hides which cluster is degrading:

| Cluster | Signal to Measure | Threshold |
|---------|------------------|-----------|
| Tool invocation | `tool_call_error_rate / total_calls` | > 5% → investigate |
| Parameter errors | `malformed_argument_rate` | > 2% → schema drift check |
| Planning failures | `plan_invalidated_count / replan_count` | > 30% → task decomposition audit |
| Context accumulation | `context_truncation_count / session_length` | > 10% → compression strategy |
| Multi-agent coordination | `handoff_timeout_count / handoff_total` | > 15% → protocol check |
| Measurement validity | `kappa_score` of your eval judge | < 0.6 → re-evaluate eval |

### 3. Add the compounding budget at task submission

Before running any agent task, compute and log the expected failure probability for its complexity tier. Treat a Regime 2 task's 20% expected failure rate as a precondition, not a post-hoc surprise.

```python
def task_compounding_budget(n_steps: int, p: float = 0.92) -> dict:
    """Return compounding budget before running a task."""
    regime = "SHORT" if n_steps <= 5 else "MEDIUM" if n_steps <= 15 else "LONG"
    expected_failure = 1 - regime_aware_success_rate(n_steps, p)
    return {
        "steps": n_steps,
        "regime": regime,
        "expected_failure_rate": round(expected_failure * 100, 1),
        "mitigation": "checkpointing" if regime == "MEDIUM" else "checkpointing + human_review"
    }
```

### 4. Instrument the compounding boundary

The Regime 1→2 transition (step 5–6) is the highest-value instrumentation point. Track `replan_token_ratio = replanning_tokens / total_tokens`. Above 0.3, the agent is spending more effort recovering than progressing. Above 0.5, terminate and escalate.

### 5. Test at the compounding boundary, not at the happy path

Your eval suite should contain exactly one task at each regime boundary (5-step, 15-step, 30-step). These are your compounding breakpoints. If the agent passes the 5-step but fails the 15-step, you have a Regime 2 failure — context contamination — regardless of what the aggregate pass rate says.

## Receipt

> Verified 2026-08-12 — arXiv:2607.05775 (Albayaydh, Zhao, Flechais, Oxford, July 2026): 27 papers, 19 benchmarks, six failure clusters with nonlinear compounding confirmed. PlanBench-XL (arXiv:2606.22388, June 2026) validates long-horizon planning degradation in large tool ecosystems. AgentMarketCap (April 2026): 12–18% tool call failure rates in production vs. <1% in benchmark conditions. Regime-aware model confirms: tasks at 5/15/30 step boundaries enter distinct failure regimes. Linear compounding model (S-200) underestimates long-horizon failure rates by 3–4× at the 30-step boundary.

## See also

- [S-200 · Agent Reliability Compounding](/stacks/s200-agent-reliability-compounding.md) — linear compounding baseline (read this first)
- [S-1024 · The Kappa Deflation Problem](/stacks/s1024-the-kappa-deflation-problem-when-your-llm-judge-reports-85-but-has-kappa-0.48.md) — Cluster 6: eval measurement validity
- [S-2516 · The Sandbox Escape Taxonomy Stack](/stacks/s2516-the-sandbox-escape-taxonomy-stack-when-your-agent-escapes-the-box-you-forgot-to-build.md) — Cluster 5: adversarial/underspecified safety failures
- [S-2504 · The Escalation Ladder Stack](/stacks/s2504-the-escalation-ladder-stack-when-your-agent-is-stuck-but-refuses-to-stop.md) — replan overhead and when to terminate
