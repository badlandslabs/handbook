# S-1009 · The Agentic RCA Stack — When Your Agent Has to Figure Out Why It Broke

A production agent silently degraded over 3 hours — all metrics said OK, task-completion SLI held at 99%, but error rate climbed from 0.1% to 8% and nobody noticed until customers complained. Manual RCA took 4 hours. The agent that caused the cascade couldn't have diagnosed it — it had already moved on, and its logs were designed for action, not analysis.

## Forces

- **Agents fail semantically, not just mechanically.** Silent failure (S-196) covers the case where the agent says "done" but nothing happened. Agentic RCA handles a harder case: the agent succeeded on every step, but the convergence path was wrong and the final answer is subtly broken. Traditional SLO burn-rate alerts miss this because the SLI ticked green.
- **RCA tooling assumes human-scale causality.** Kubernetes probes, Prometheus alerts, and log correlation assume a human operator who can grep logs, read dashboards, and trace因果 chains. Agents produce traces that span dozens of tool calls, memory writes, model calls, and sub-agent delegations. No human can reverse-engineer a 4-hour multi-turn trace manually.
- **The agent that failed is not the agent that can diagnose.** After a task completes (success or failure), the agent's working state resets. The diagnostic session starts with a blank context — it has to reconstruct what happened from traces, not from memory. This is a fundamentally different agent configuration from the task-execution agent.
- **Root causes in agentic systems are multi-hop.** An agent produces wrong answers because: (a) the knowledge base drifted, (b) a tool returned stale data, (c) the model subtly changed behavior after a version update, and (d) the agent's memory consolidation compacted the safety constraint that would have caught it. Any single one of these is a valid root cause — finding the actual one requires hypothesis testing, not log correlation.
- **LLM-as-diagnostician hallucinates root causes.** Giving a model a trace and asking "what went wrong" produces confident, plausible-sounding nonsense at non-trivial rates. The diagnostic loop needs a human-in-the-loop for hypothesis validation — not to do the work, but to filter confidentfabrications.

## The move

The agentic RCA stack is a four-layer diagnostic loop that runs between the task agent and a separate diagnostic agent. It detects semantic drift, reconstructs causal chains, validates hypotheses against golden cases, and implements fixes — closing the loop from failure detection to remediation.

### Layer 1 — Trace Instrumentation (the evidence base)

Without structured traces, RCA is storytelling. The diagnostic agent cannot reconstruct what happened if the traces are just `INFO: tool_called` and `INFO: response`. Instrument every agent with the OpenTelemetry GenAI semantic conventions (stable as of mid-2026):

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("invoke_workflow", kind=SpanKind.INTERNAL) as span:
    span.set_attribute("agent.id", agent_id)
    span.set_attribute("gen_ai.system", "anthropic")
    span.set_attribute("gen_ai.request.max_tokens", 4096)
    span.set_attribute("gen_ai.response.id", response.id)
    span.set_attribute("gen_ai.token_count.prompt", response.usage.input_tokens)
    span.set_attribute("gen_ai.token_count.completion", response.usage.output_tokens)
    span.set_attribute("agent.task.id", task_id)
    span.set_attribute("agent.tool.count", len(tool_calls))
    span.set_attribute("agent.step", step_number)

    # Tool calls get their own child spans
    for tc in tool_calls:
        with tracer.start_span("execute_tool", kind=SpanKind.CLIENT) as tool_span:
            tool_span.set_attribute("tool.name", tc.name)
            tool_span.set_attribute("tool.input", json.dumps(tc.args))
            tool_span.set_attribute("tool.status", tc.status)
```

The five OTel GenAI span types — `create_agent`, `invoke_agent_client`, `invoke_agent_internal`, `invoke_workflow`, `execute_tool` — plus `gen_ai.*` attributes, give the diagnostic agent structured inputs. Without this, you're doing RCA on prose logs.

### Layer 2 — Drift Detection (the trigger)

Three complementary detectors catch drift before customers do:

**SLO burn-rate alert**: Task-completion SLI drops below threshold → triggers diagnostic session. Tune the threshold with your error budget policy (S-651).

**Semantic regression detector**: Run golden inputs against the live agent periodically (e.g., every 30 minutes). Compare outputs to expected outputs. Catch drift even when the task-completion SLI hasn't fired.

```python
def detect_semantic_drift(agent, golden_set, similarity_fn, threshold=0.85):
    """
    Periodic shadow evaluation against a golden dataset.
    Returns (drift_detected, affected_cases, similarity_scores).
    """
    affected = []
    scores = []
    for case in golden_set:
        output = agent.run(case["input"], mode="shadow")  # no side effects
        score = similarity_fn(output, case["expected"])
        scores.append((case["id"], score))
        if score < threshold:
            affected.append(case)

    drift_rate = len(affected) / len(golden_set)
    return drift_rate > 0.05, affected, scores  # 5% golden-set failure = drift
```

**Behavioral invariant monitor**: Monitor trajectories for violations of hardcoded invariants — e.g., "tool X is never called without a prior validation check," or "memory writes are never older than context." These catch structural regressions that output-comparison misses (S-703).

### Layer 3 — Hypothesis Generation and Validation (the core loop)

The diagnostic agent receives a structured context: affected task IDs, step-level traces, golden-case comparison outputs, recent tool/server changes. It generates 3-5 ranked hypotheses:

```python
SYSTEM_PROMPT = """You are an SRE diagnostic agent. Given a structured failure report,
propose exactly 3 ranked hypotheses for the root cause. For each hypothesis:
1. State the root cause in one sentence
2. List 2-3 trace features that support this hypothesis
3. Propose one diagnostic query that would confirm or refute it
4. Rate confidence 0-100%

Format as a markdown table. Do NOT propose fixes — only diagnose."""

diagnostic_context = f"""
FAILURE REPORT:
- Task IDs: {affected_task_ids}
- Golden-set drift rate: {drift_rate:.1%}
- Affected time window: {time_window}

TRACE SUMMARY (last 5 steps of affected session):
{trace_summary}

TOOL CALL HISTORY:
{tool_call_table}

LATEST KNOWLEDGE BASE UPDATE: {kb_last_updated}
LATEST MCP SERVER VERSION: {mcp_server_versions}
LATEST MODEL DEPLOYMENT: {model_version} ({model_version_change_date})
"""
```

**Critical: human-in-the-loop gate.** The diagnostic agent outputs hypotheses ranked by confidence. A human engineer reviews and selects one before the remediation layer runs. This gate prevents confident diagnostic hallucinations from driving unnecessary or harmful automatic changes.

### Layer 4 — Remediation and Verification (the fix)

Once the human approves a hypothesis, the remediation agent acts:

```python
def remediate_and_verify(hypothesis, task_context, rollback_plan):
    """
    Given an approved root-cause hypothesis, implement fix and verify.
    Returns (fix_applied, verification_passed, rollback_available).
    """
    fix = generate_fix(hypothesis, task_context)  # LLM-generated patch

    # Apply to shadow environment first
    shadow_result = apply_in_shadow(fix, task_context)
    if shadow_result.passes_golden_set():
        apply_to_production(fix)
        verification = run_golden_set_live()
        if verification.pass_rate >= 0.98:
            return True, True, rollback_plan
        else:
            rollback()
            return True, False, rollback_plan  # fix failed, rolled back
    else:
        return False, False, None  # fix doesn't work even in shadow
```

The golden-set pass rate (98%) is the production-readiness gate. Run fixes through shadow evaluation before touching production. Never apply a fix with zero shadow validation.

### The full RCA loop

```
Task fails or drifts detected
  → Alert fires
  → Diagnostic agent spawned (new context, read-only traces)
  → Hypothesis generation (3 ranked hypotheses)
  → Human selects hypothesis
  → Remediation agent generates fix
  → Shadow validation against golden set
  → Production apply if pass rate ≥ 98%
  → Live verification
  → If fails: rollback
  → Golden set updated with new failure case
```

**Proactive RCA variant**: Schedule diagnostic sessions during low-traffic windows. Catch drift before the SLO fires. The agent that proactively diagnoses itself at 2 AM prevents the page at 9 AM.

## Receipt

> Verified 2026-07-12 — OpenTelemetry GenAI semantic conventions are documented at opentelemetry.io/schemas (v1.35+), with `create_agent`, `invoke_agent_client`, `invoke_agent_internal`, `invoke_workflow`, and `execute_tool` span types. Langfuse (acquired by ClickHouse, Jan 2026) and Galileo (acquired by Cisco, May 2026) both ingest OTel-shaped traces as primary wire format. RubixKube (F6S, 2026) implements autonomous diagnostic loops for Kubernetes with agentic RCA. PagerDuty's SRE Agent (2025) implements the detect-triage-diagnose-remediate loop for incident management. The 50% faster incident resolution figure is PagerDuty's published claim for early adopters. Confidence threshold and golden-set sizing are documented in Zylos Research's AI Agent Self-Healing Patterns (2026-03-02). Receipt pending — pattern not yet run against production traces.

## See also

- [S-196 · Silent Failure Detection](s196-silent-failure-detection-the-production-mode-where-your-agent-succeeds-and-delivers-nothing.md) — what silent failure looks like and why traditional metrics miss it
- [S-703 · Trajectory Invariants](s703-agent-trajectory-invariants-behavioral-regression-testing-for-agent-systems.md) — behavioral invariant monitoring as a regression detector
- [S-651 · Agentic SLOs](s651-agentic-slos-the-six-metrics-that-actually-matter.md) — task-completion SLI and error-budget framing for the burn-rate trigger
