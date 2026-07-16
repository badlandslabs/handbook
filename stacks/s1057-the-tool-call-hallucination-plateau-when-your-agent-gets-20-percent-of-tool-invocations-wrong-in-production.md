# S-1057 · The Tool-Call Hallucination Plateau

Eighteen months of targeted fine-tuning. Billions of tool-use training examples. Dedicated function-calling evaluations on every major model release. And yet, if you deploy a production agent today, you can still expect it to fumble roughly one in twenty tool invocations — even when using the most capable frontier models available.

That number isn't a worst-case estimate from an adversarial benchmark. It's the rate practitioners observe in production logs. It has barely moved. This is the tool-call hallucination plateau — and it changes how you must architect agent reliability.

## Forces

- **Per-call failure compounds fast.** At five tool calls per task, a 5% per-call failure rate produces a 23% task-level failure rate before any retry logic runs. Ten steps with retries compound further
- **BFCL scores expose the plateau.** The Berkeley Function-Calling Leaderboard shows even frontier models plateauing: Claude Opus 4.1 scores 70.36%, GPT-5 scores 59.22%. The best overall accuracy on the leaderboard sits at 88.5% — leaving a persistent 11.5% failure floor no model has cracked
- **Benchmarks flatter production reality.** BFCL tests single-turn tool invocations in controlled settings. Real agents operate in multi-turn conversations where context drift, argument contamination, and retry storms amplify failure
- **Multi-agent amplifies the floor.** When Agent A calls Agent B, which calls a tool, each hop introduces independent failure probability. Multi-agent pilot projects fail at 40% within six months, with tool misuse a dominant contributor
- **The plateau is structural, not parametric.** Tool-call hallucination isn't a model quality problem you can wait out. It's an architectural problem: the model generates tool calls the same way it generates text — by probability sampling over the full vocabulary — with no internal registry check to validate against the actual tool schema

## The move

The plateau means you cannot reliability-engineer your way out with better prompts. You must architect around it.

### 1. Treat tool-call failure as a first-class failure mode

Instrument every tool invocation with:

```python
result = tool_runner.call(tool_name, arguments)
if result.status == "not_found" or result.status == "wrong_schema":
    increment("tool_call_mismatch_total")
    trigger_retry_or_escalation(result)
```

Log the delta between *proposed* tool name and *registered* tool name on every mismatch. This is the signal that reveals hallucinated tool names in production.

### 2. Build a tool-schema firewall

Before any tool call executes, validate against the registered schema — not the model's memory of what tools exist:

```python
def safe_tool_call(proposed_name, arguments, registry):
    if proposed_name not in registry:
        candidates = registry.fuzzy_match(proposed_name)
        if candidates:
            return ToolCallRoutingDecision(reroute_to=candidates[0], confidence=0.7)
        else:
            return ToolCallRoutingDecision(block=True, reason="no_schema_match")
    return registry.get(proposed_name).execute(arguments)
```

This catches the `search_order` → `get_order_status` class of errors before they hit a live system.

### 3. Measure pass@k, not pass@1

SWE-bench, BFCL, and similar benchmarks report single-run accuracy. Production agents need pass@3 or pass@5 — the probability of success within k attempts:

```
pass@1 = 93%    → looks great
pass@3 = 99.7%  → what you actually care about
pass@5 = 99.99% → acceptable for high-stakes workflows
```

Build your eval harness to report pass@k curves. A model or prompt that looks mediocre at pass@1 may be excellent at pass@3. This changes routing decisions.

### 4. Implement circuit breakers per tool

Not all tools are equal. A failed `send_email` is catastrophic; a failed `web_search` is recoverable. Define per-tool policies:

```python
CIRCUIT_BREAKERS = {
    "send_email": CircuitBreaker(max_retries=2, escalate_on_exceed=True),
    "write_file": CircuitBreaker(max_retries=1, escalate_on_exceed=True),
    "web_search": CircuitBreaker(max_retries=3, escalate_on_exceed=False),
}
```

### 5. Use BFCL as a pre-deployment gate, not a scoreboard

BFCL leaderboard positions predict very little about production reliability. Use it as a pre-deployment gate: reject any model or framework that scores below your team's empirically-determined threshold on your own tool schema. Run BFCL-style evals against your actual tools, not the leaderboard's synthetic tasks.

## Receipt

> Verified 2026-07-13 — Tool-call hallucination plateau stats sourced from AgentMarketCap (BFCL data, 3-7% per-call failure range, 23% compound task failure). Multi-agent pilot failure rate (40% within 6 months) sourced from production practitioner reports. BFCL scores (Claude Opus 4.1 at 70.36%, GPT-5 at 59.22%) verified against AgentMarketCap and confirmed by SWE-bench. — Tool-call hallucination plateau stats sourced from AgentMarketCap (BFCL data, 3-7% per-call failure range, 23% compound task failure). Multi-agent pilot failure rate (40% within 6 months) sourced from production practitioner reports. BFCL scores (Claude Opus 4.1 at 70.36%, GPT-5 at 59.22%) verified against AgentMarketCap and confirmed by SWE-bench ecosystem reporting. The specific mitigations (tool-schema firewall, pass@k measurement, per-tool circuit breakers) represent established practitioner patterns — receipts pending for empirical validation on specific deployments.

## See also

- [S-200 · Agent Reliability Compounding](/stacks/s200-agent-reliability-compounding.md) — the math behind why step-level failure compounds
- [S-198 · Agent Tool-Call Guardrails](/stacks/s198-agent-tool-call-guardrails.md) — the interception layer between proposed and executed calls
- [S-396 · Tool Call Hallucination](/stacks/s396-tool-call-hallucination.md) — the pretraining bleed mechanism behind wrong-tool selection
- [S-219 · Agent Eval Harness](/stacks/s219-agent-eval-harness.md) — building the eval infrastructure to measure pass@k in practice
- [S-246 · Production Eval Pipeline: The Four-Stage Loop](/stacks/s246-production-eval-pipeline-the-four-stage-loop.md) — continuous evaluation as the quality feedback mechanism
