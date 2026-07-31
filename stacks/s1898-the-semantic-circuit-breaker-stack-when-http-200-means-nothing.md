# S-1898 · The Semantic Circuit Breaker Stack — When HTTP 200 Means Nothing

Your circuit breaker is open. Five consecutive HTTP 500s tripped the threshold. Traffic stopped. Infrastructure is safe. But the agent is still failing — silently, expensively, correctly — because the tool returns HTTP 200 with hallucinated JSON, the schema validation silently dropped fields, and the downstream CRM has wrong data. Your circuit breaker protected you from a problem that wasn't happening. It did nothing about the problem that was.

## Forces

- **Traditional circuit breakers trip on protocol failures, not semantic failures.** HTTP 500, timeout, parse error — these are the language of classical circuit breakers. But production agents fail most dangerously when the protocol succeeds and the content is wrong. A circuit breaker that only watches HTTP codes watches nothing that matters.
- **Quality degradation compounds silently.** A tool whose accuracy drifts from 95% to 70% over six weeks doesn't throw errors. It returns plausible wrong answers. Without a quality signal, the circuit stays closed indefinitely. At 70% per-call accuracy across a 10-step workflow, you get 96.7% compound failure rate — worse than random.
- **Detection latency is the damage.** The average time to detect a semantic failure in production is 11 days (Sherlocks.ai, 2026). The average time to detect a protocol failure is minutes. Every day without detection is another 24 hours of wrong decisions, corrupted state, and wasted spend compounding.
- **LLM circuit breakers require material modification from classical counterparts.** You must trip on quality degradation, not just exceptions. This means integrating quality signals — output schema validation, confidence scoring, downstream task completion verification — directly into the circuit logic.

## The Move

### 1. Define quality signals, not just error signals

A semantic circuit breaker monitors what the agent *produced*, not just whether the tool *responded*. Map quality signals to each tool:

```
QualitySignal = {
  schema_valid: bool,       # Does the output match the expected schema?
  required_fields_present: bool,  # Are all non-optional fields populated?
  value_range_check: bool,  # Are numeric fields within expected bounds?
  cross_reference_check: bool,    # Do field values contradict each other?
  confidence_score: float,  # Model's own confidence, if available
  downstream_verify: bool, # Did the downstream system confirm the write?
}
```

### 2. Implement per-tool circuit state machines

Each tool gets its own three-state machine: `CLOSED` (normal operation), `HALF_OPEN` (probing), `OPEN` (quality-degraded, traffic blocked). The trip condition is compound — either protocol failures OR quality signal violations:

```
OPEN when any of:
  - protocol_failures >= 5 in 60s
  - quality_score < threshold for 3 consecutive calls
  - schema_valid == false for 2 consecutive calls
  - downstream_verify == false for 2 consecutive calls

HALF_OPEN: allow N probe calls; trip OPEN on any failure, CLOSED on N successes

CLOSED: reset all counters on successful quality-verified call
```

### 3. Trip on the failure axis, not the protocol axis

Separate error classification into two orthogonal axes:

| Axis | Protocol | Semantic |
|------|----------|---------|
| **Retry-worthy?** | Yes (transient) | No (systematic) |
| **Circuit action** | Standard retry with backoff | Replan or reset, not retry |
| **Detection method** | HTTP codes, timeouts | Schema validation, cross-reference checks |
| **Example** | API returns 503 | API returns 200 with `amount: -5000` |

The circuit breaker must maintain separate failure counters on each axis. A tool can have 0 protocol failures and 5 semantic failures — and still need to trip.

### 4. Integrate with the agent loop

The circuit state feeds the agent's next-step decision:

```
if circuit_state[tool] == OPEN:
    escalate_to_human()  # or use fallback tool
    return "quality_degraded: {tool} circuit open"

if circuit_state[tool] == HALF_OPEN:
    attach_warning_context(f"probing {tool} recovery — expect degraded quality")
```

### 5. Cascade breaker: multi-tool quality gates

In multi-step workflows, quality failures at step N infect step N+1. Implement a cascade gate that checks upstream quality before executing downstream steps:

```
def execute_step(step, upstream_quality):
    if upstream_quality < cascade_threshold:
        return {
            "blocked": True,
            "reason": f"upstream quality {upstream_quality} below cascade threshold",
            "action": "replan"  # not retry
        }
    return execute(step)
```

This prevents the common failure where an agent spends 40 minutes on step 2–5 using corrupted data from step 1.

## Receipt

> Verified 2026-07-31 — Production thresholds (5 failures to trip, 60s cooldown, alert at >5% error rate, critical at >15%) sourced from AgentMarketCap (April 2026) circuit breaker pattern analysis. Quality signal taxonomy validated against Sherlocks.ai incident data (11-day average semantic failure detection latency). Cascade breaker pattern validated against AgentMarketCap production study on tool-call failure compounding (12-18% per-call in production vs. 3-7% benchmark rate). Semantic vs. protocol failure classification axis validated against BuildMVPFast/AgentBrisk production error recovery guides (2026).

## See also
- [S-1023 · The Recovery Ladder](/opt/data/handbook/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — semantic failure classification and the retry/replan/reset decision tree
- [S-1509 · The Oracle Problem](/opt/data/handbook/stacks/s1509-the-oracle-problem-stack-when-you-cannot-tell-if-your-agent-is-right.md) — the verification problem that makes semantic circuit breaking necessary
- [S-1079 · The Tool-Aware Model Router](/opt/data/handbook/stacks/s1079-the-tool-aware-model-router-when-cheap-tools-burn-budget-because-routing-ignores-them.md) — cascade breaker pattern for quality-gated model routing
