# S-919 · Agent Production Readiness Gate

An agent that passes its code review is not ready for production autonomy. A customer-service agent can generate valid outputs and handle the happy path — and still escalate every edge case to a human in ways that cost $12/session, or silently degrade on new product launches without any alert firing. The Agent Production Readiness Gate is the discipline of answering: *is this agent trustworthy enough to operate at autonomy level N in production?* — before you let it.

## Forces

- **Autonomy level != readiness level.** S-355 defines L0–L5 autonomy. S-282 defines guardrails. Neither answers whether your specific agent instance at L3 is actually safe to flip on this Tuesday. Readiness is agent-specific, task-specific, and time-varying — not a one-time classification.
- **Teams mistake "it works" for "it's ready."** A demo with 20 hand-picked test cases passing is not a production readiness signal. The median production agent degrades within 72 hours of deployment on real traffic — not because of bugs, but because real inputs differ from test inputs in ways that weren't anticipated.
- **Readiness gates need to gate something real.** A readiness checklist that produces a green/red badge nobody acts on is theater. The gate must gate actual autonomy escalation — the thing that causes customer impact when it fails.
- **Readiness decays.** An agent ready last month may not be ready today. Model updates, tool schema changes, MCP config drift (S-874), and upstream data source changes all erode readiness silently.

## The Move

### Layer 1 — The Readiness Contract

Before any autonomy escalation, define the **readiness contract**: the set of conditions that must hold for the agent to operate at autonomy level N. Each condition has a metric, a threshold, and a measurement method.

```
Readiness Contract (example: L3 customer-service agent)
├── Safety: zero P0 tool-call violations in 500 eval runs
├── Accuracy: ≥92% task success on golden eval set (S-901)
├── Trajectory: ≥90% tool-call correctness on adversarial eval (S-817)
├── Cost: ≤$2.00 avg session cost (S-389)
├── Escalation: ≤15% human escalation rate on shadow traffic
└── Latency: P95 session completion ≤30s (S-368)
```

Each dimension is measured independently. All must pass. Any failure blocks escalation or triggers downgrade.

### Layer 2 — The Three Evaluation Gates

**Gate 1 — Static Eval Gate (pre-deploy)**
Run against a curated eval set that includes: happy paths, known failure modes from prior incidents, adversarial inputs (S-289), boundary conditions per tool, and at least one scenario per documented failure mode from your logs.

Anthropic's recommended minimum: 20–50 test cases drawn from real failures. Prioritize the ones that have caused customer impact.

**Gate 2 — Shadow Traffic Gate (pre-autonomy)**
Route real production traffic through the agent in shadow mode — it executes, you observe, but actions are not taken. Run for a minimum window (72 hours or 1,000 sessions, whichever comes first). Collect: escalation rate, cost per session, tool-call error rate, and trajectory divergence from expected paths.

Shadow traffic catches what static evals miss: degradation on real input distributions, tool-call failures under load, and cost anomalies that only manifest at scale.

**Gate 3 — Graduated Autonomy Gate (canary rollout)**
Escalate autonomy incrementally. Start at L1 (advisory only). Advance to L2 (human-in-the-loop). Advance to L3 (autonomous with monitoring). Each step gates on the readiness contract passing for the prior step.

```
L1 (Advisory)     → passive; user sees recommendation, takes action
L2 (HITL)         → agent acts; human approves before irreversible steps
L3 (Autonomous)   → agent acts; human reviews post-hoc, not pre-hoc
```

### Layer 3 — Continuous Readiness Monitoring

The gate is not a one-time check. After autonomy escalation, run the readiness contract on a schedule:

- **Every model change**: full static eval gate + shadow traffic re-run
- **Every tool/MCP change**: re-run tool-call correctness dimension
- **Weekly**: sample 5% of autonomous sessions for human review (S-281)
- **On cost anomaly**: trigger readiness contract re-evaluation (S-389)

A rolling readiness score below threshold on any dimension triggers automatic autonomy downgrade to the last passing level — not a human review request, an automatic response. Degrade first, ask questions later.

### The Minimum Viable Version

If you can't build all three layers today, start with Gate 1 + the weekly sample. That's enough to catch the most common failure mode: shipping an agent that works on test data and silently fails on production data.

```python
# Minimal readiness checker — one function
def check_readiness(agent_id: str, autonomy_level: int) -> dict:
    """Returns {dimension: (passed: bool, score: float, threshold: float)}"""
    contract = READINESS_CONTRACTS[agent_id]  # loaded from config

    results = {}
    for dimension, threshold in contract.items():
        metric_fn = DIMENSION_METRICS[dimension]
        score = metric_fn(agent_id)  # runs the actual measurement query
        results[dimension] = {
            "passed": score >= threshold,
            "score": score,
            "threshold": threshold
        }

    all_passed = all(r["passed"] for r in results.values())
    readiness_level = min(
        dim_level
        for dim, (passed, _, _) in results.items()
        if not passed
        for dim_level, dims in AUTONOMY_REQUIREMENTS.items()
        if dim in dims
    ) if not all_passed else autonomy_level

    return {
        "agent_id": agent_id,
        "current_autonomy": autonomy_level,
        "recommended_autonomy": readiness_level,
        "all_passed": all_passed,
        "dimensions": results
    }
```

## Receipt

> Receipt pending — run against your eval harness with real traffic data. Minimum verification: confirm the function returns a `recommended_autonomy` lower than `current_autonomy` on at least one dimension for your current agent fleet. If all agents pass all gates, your thresholds are too loose.

## See also
- [S-355 · Agent Autonomy Levels](s355-agent-autonomy-levels-bounded-autonomy.md) — the autonomy level definitions this gate operates on
- [S-282 · Agent Guardrails](s282-agent-guardrails.md) — what guardrails do; the readiness gate determines when they're sufficient
- [S-874 · MCP Config Drift](s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — silent change is the most common readiness eroder
- [S-901 · Golden Set Trap](s901-the-golden-set-trap-when-your-eval-suite-gives-you-confidence-you-havent-earned.md) — eval sets go stale; your readiness contract needs the same maintenance discipline
