# S-2384 · The Effective Uptime Stack — When Your Agent Returns 200 OK But Doesn't Do Its Job

Your monitoring dashboard shows 99.7% uptime. Your on-call rotation is quiet. Your SLOs are green. Then your VP of product asks why the customer success team flagged 14 tickets last week from users whose AI agent workflow completed successfully — and produced the wrong results. The agent didn't fail. It ran to completion. It returned 200 OK. It did not do its job. Your uptime metric was measuring the wrong thing.

This is the effective uptime gap — the distance between what your monitoring calls "up" and what your users call "working." It is the central reliability problem of production AI agents in 2026, and it is invisible to every conventional observability tool.

## Forces

- **Nominal uptime and functional uptime measure different things.** Traditional uptime checks: is the service reachable? Did the API respond? For agents, this answers whether the process ran — not whether it produced the right outcome. A 200 response with a wrong result is a success by every conventional metric and a failure by every business metric.

- **Agent completions are not goal completions.** Agents can complete a workflow by: finishing the action sequence, exceeding the step budget, hitting a rate limit, running into context overflow, or reaching a fallback that returns a plausible-but-wrong answer. All of these look like "success" in traces. Only the first is a genuine success.

- **The reliability gap is measured in percentage points that destroy trust.** AgentStatus (Carmel Labs, July 2026) measured 97.2% nominal uptime across thousands of validation checks — but effective uptime under semantic validation dropped to 84.8%. That 12.4-point gap represents agents returning completion signals for tasks that were not completed. At enterprise scale, this is not an edge case.

- **Standard SLOs were built for deterministic systems.** An SLO built on HTTP status codes and latency percentiles cannot capture: wrong tool selected, correct tool called with wrong arguments, right result filtered by a broken parser, or a multi-step plan abandoned at step 6. The agent is "up" on every metric that existed before agents.

- **Silent failures are the modal failure mode.** Unlike crashes or timeouts, semantic failures — returning a wrong answer, generating a plausible error, silently skipping a required step — produce no exception, no alert, and no rollback. They accumulate in user-facing outputs until a human notices or a customer flags it.

## The move

The fix requires replacing nominal uptime with effective uptime as your primary reliability SLO — and instrumenting the agent's execution layer to distinguish "it ran" from "it worked."

### 1. Define task-level completion criteria

Before measuring effective uptime, define what "done" means per task class:

```python
class TaskCompletionCriteria:
    def __init__(self, task_type: str):
        self.task_type = task_type
        # Maps task type → what must be true for the result to be "correct"
        self.completion_rules = {
            "data_extraction": [
                "all_required_fields_populated",
                "no_null_where_required",
                "values_within_expected_ranges",
            ],
            "api_workflow": [
                "all_destination_records_created",
                "no_error_responses_from_downstream",
                "audit_log_entry_written",
            ],
            "code_generation": [
                "tests_pass",
                "type_check_clean",
                "no_security_scan_flags",
            ],
        }
```

Without explicit completion criteria, you have no ground truth to validate against.

### 2. Build a semantic health check layer

Wrap every agent task with a validation function that inspects the output, not just the response:

```python
import asyncio
from anthropic import Anthropic
from openinference import trace

client = Anthropic()
model = "claude-opus-4-6"

SEMANTICALLY_VALID = "semantically_valid"
OUTCOME_INVALID = "outcome_invalid"
TECHNICAL_FAILURE = "technical_failure"

async def agent_task_with_effectiveness_check(prompt: str, criteria: list[str]) -> dict:
    with trace("agent_effectiveness_check") as tracer:
        # Execute the agent task
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        output = response.content[0].text
        
        # Validate against task completion criteria
        validation_results = await validate_output(output, criteria)
        
        tracer.set_attribute("nominal_outcome", "success")        # Traditional: API returned 200
        tracer.set_attribute("semantic_outcome", validation_results["status"])  # Actual: did it work?
        tracer.set_attribute("validation_failures", validation_results["failed_criteria"])
        
        return {
            "output": output,
            "status": validation_results["status"],
            "failed_criteria": validation_results.get("failed_criteria", []),
        }

async def validate_output(output: str, criteria: list[str]) -> dict:
    """Use a separate LLM call as judge to validate output quality."""
    judge_prompt = f"""Validate this agent output against these criteria:
Criteria: {criteria}
Output: {output}

For each criterion, respond: PASS or FAIL with a one-line reason.
Then respond overall: VALID or INVALID."""
    
    judge_response = client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": judge_prompt}]
    )
    
    judgment = judge_response.content[0].text
    
    if "INVALID" in judgment:
        return {
            "status": OUTCOME_INVALID,
            "failed_criteria": extract_failures(judgment),
        }
    return {"status": SEMANTICALLY_VALID, "failed_criteria": []}
```

### 3. Instrument the effectiveness metric

Track effective uptime alongside nominal uptime in your metrics pipeline:

```python
from prometheus_client import Counter, Histogram, Gauge

# Traditional metrics (nominal)
nominal_requests_total = Counter(
    "agent_requests_total", "All agent requests completed nominally"
)
nominal_errors_total = Counter(
    "agent_errors_total", "Agent requests that returned error status"
)

# Effectiveness metrics (actual)
effective_success_total = Counter(
    "agent_effective_success_total", 
    "Agent requests that completed with semantically valid output"
)
effective_failure_total = Counter(
    "agent_effective_failure_total",
    "Agent requests that completed nominally but failed semantic validation"
)

# The gap: effective_failures / nominal_requests
effectiveness_ratio = Gauge(
    "agent_effectiveness_ratio",
    "Ratio of effective success to nominal success"
)

def record_outcome(nominal_success: bool, semantic_valid: bool):
    nominal_requests_total.inc()
    if nominal_success:
        if semantic_valid:
            effective_success_total.inc()
        else:
            effective_failure_total.inc()  # This is your gap
    effectiveness_ratio.set(
        effective_success_total._value.get() / nominal_requests_total._value.get()
    )
```

### 4. Set effective uptime as your SLO

```yaml
# Your SLO definition (Datadog / Grafana / your-observability-tool)
slo:
  name: agent_effectiveness_slo
  type: metric_ratio
  numerator: "agent_effective_success_total"
  denominator: "agent_requests_total"
  target: 0.90        # 90% of completions must be semantically valid
  window: 30d
  
  # Alert on the gap, not just the floor
  alert:
    - condition: "effective_uptime < 85%"
      severity: critical
      message: "Semantic failure rate exceeds 15% — investigation required"
    - condition: "effective_uptime < effective_uptime_7d_avg - 5%"
      severity: warning
      message: "Effective uptime degraded vs. 7-day baseline"
```

The second alert — regression from your own baseline — is critical. A 90% effective uptime is meaningless if it was 95% last week.

### 5. The minimum viable effective uptime stack

If you're starting from zero, in priority order:

1. **Add one validation check per task type.** Pick your top 3 task classes. For each, write one `assert` that validates the output structure and range. No LLM judge needed at first — deterministic checks catch most failures.
2. **Track the gap.** Every agent completion: increment `nominal_requests`. If validation passes: increment `effective_success`. If it fails: increment `effective_failure`. The ratio is your effective uptime.
3. **Set a canary alert.** When effective uptime drops 5+ points below your 30-day rolling average, page someone. This is your regression signal.
4. **Graduate to semantic validation.** Once deterministic checks are stable, add LLM-as-judge validation for output quality on a 10% sample. Scale to 100% for high-stakes task types.

> Receipt pending — 2026-08-09

## See also

- [S-2277 · The Reliability Surface Stack](s2277-the-reliability-surface-stack-when-your-agent-passes-97-percent-in-eval-and-fails-12-percent-in-production.md) — the eval-side version of the same gap
- [S-1191 · The Correctness SLO Stack](s1191-the-correctness-slo-stack-when-your-agent-is-accurate-94-percent-of-the-time-and-you-dont-know-it.md) — SLOs for correctness vs. availability
- [S-1235 · The Semantic Error Gap Stack](s1235-the-semantic-error-gap-stack-when-your-agent-succeeds-on-every-metric-and-fails-on-every-truth.md) — structural validity vs. semantic correctness
- [S-1066 · The Invisible Failure Stack](s1066-the-invisible-failure-stack-when-your-agent-succeeds-and-burns-47k-instead.md) — silent success with wrong outcomes
