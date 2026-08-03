# S-2094 · The Agent Regression Harness — When Your Test Suite Lets Bugs Ship

You added a new tool. You updated the prompt. You ran the same five test cases and they all passed. Then production caught fire because the agent now hallucinates tool names it learned from the new prompt, the new tool has a subtle schema mismatch that only triggers on optional fields, and the happy-path tests you ran never touched either. Your test suite gave you a green build and a broken system.

Traditional software testing assumes deterministic behavior: input X produces output Y. Agents are probabilistic trajectories. A single run is one sample from a distribution. Your suite passed — but it was testing one path, not the distribution. The agent regression harness is the operational discipline that makes agent testing reliable: it layers the right assertions at the right scope, mines golden cases from production failures, and gates every deploy on scores that actually measure what matters.

## Forces

- **Agents fail probabilistically, not deterministically.** A 90% reliable agent on a single run means 1 in 10 attempts fails — but a test suite that runs once per case will report pass/fail, not reliability. You need pass@k (at least one success in k attempts) and pass^k (all k attempts succeed) measured together.
- **Agent behavior lives in trajectories, not single outputs.** The bug is rarely the final answer — it's the tool call on step 3, the context carry-over between steps, the tool selected when two options are plausible. Testing only the output misses the mechanism.
- **Test cases decay faster than agent code.** A golden dataset built at launch grows stale as the agent evolves. Cases that matched the agent's behavior six months ago don't reflect where it actually breaks today. The harness must continuously incorporate production failures.
- **Span-level assertions are the missing middle.** Developers assert on the final output but not on the intermediate steps. Most agent failures — wrong tool selected, bad argument constructed, loop triggered — only appear in the trace tree, never in the output.
- **CI gates that teams don't trust get disabled.** If your eval suite has false positives (flaky scores) or false negatives (missed regressions), engineers will bypass the gate. The harness must earn confidence before it can enforce.

## The move

### Layer 0 — Data Certification Gate

Before any harness test runs, certify the data sources it depends on. Unstable data produces unstable eval results, and the symptom looks exactly like an agent regression.

```python
import pytest
from your_harness import DataCertification

def test_data_certification():
    """
    Layer 0: Every data dependency must pass certification
    before the eval harness is considered valid.
    """
    cert = DataCertification()
    
    # Certify the MCP tool catalog hasn't drifted
    assert cert.check_tool_catalog_stability(
        server_id="prod-mcp-filesystem",
        max_field_drift=0,        # strict: any schema change blocks the suite
        max_removed_tools=0,
    ), "Tool catalog drifted — run 'harness sync-catalog' before proceeding"
    
    # Certify the knowledge base index freshness
    assert cert.check_index_freshness(
        index="support-kb",
        max_age_hours=24,
    ), "Knowledge base older than 24h — retriever results will be stale"
```

### Layer 1 — Tool Call Assertions

Test tool selection and argument construction in isolation. These are the atomic units of agent behavior — wrong tool, wrong arguments, right tool at the wrong time.

```python
def test_tool_selection_deterministic_cases():
    """
    Layer 1: For cases where the correct tool is unambiguous,
    assert on both tool name AND argument structure.
    """
    cases = [
        {
            "id": "customer-refund-eligible",
            "input": "Refund order #4521 — customer is within 30-day window",
            "expected_tool": "process_refund",
            "expected_args_schema": {"order_id": str, "reason": str},
        },
        {
            "id": "escalation-high-value",
            "input": "Customer #8812 wants to cancel a $42,000 enterprise contract",
            "expected_tool": "escalate_to_sales",
            "expected_args_schema": {"customer_id": str, "contract_value": float},
        },
    ]
    
    harness = AgentHarness()
    
    for case in cases:
        trace = harness.run(case["input"], max_steps=3)
        tool_calls = trace.tool_calls
        
        # Assert 1: Correct tool selected
        assert len(tool_calls) > 0, f"{case['id']}: No tool called"
        assert tool_calls[0].name == case["expected_tool"], (
            f"{case['id']}: Wrong tool — got {tool_calls[0].name}, "
            f"expected {case['expected_tool']}"
        )
        
        # Assert 2: Arguments match expected schema
        actual_args = tool_calls[0].arguments
        for field, expected_type in case["expected_args_schema"].items():
            assert field in actual_args, (
                f"{case['id']}: Missing required argument '{field}'"
            )
            assert isinstance(actual_args[field], expected_type), (
                f"{case['id']}: Argument '{field}' has wrong type "
                f"({type(actual_args[field]).__name__}, expected {expected_type.__name__})"
            )
```

### Layer 2 — Trajectory Assertions

For multi-step workflows, assert on the full execution path — not just the final output. The bug is often in step 3, not in the answer.

```python
def test_span_trace_assertions():
    """
    Layer 2: Trajectory-level assertions.
    Each span = one step in the agent's execution.
    """
    harness = AgentHarness()
    trace = harness.run(
        "Compare our Q2 revenue to Q1 and summarize the delta",
        max_steps=10,
        config={"model": "claude-sonnet-4-20250514"},
    )
    
    # Assert on the span tree, not just the final output
    assert len(trace.spans) >= 3, (
        f"Expected ≥3 steps (query → retrieve → synthesize), got {len(trace.spans)}"
    )
    
    # The first span should be a retrieval
    assert trace.spans[0].type == "tool_call", (
        "First action should be a tool call, not reasoning"
    )
    assert "query" in trace.spans[0].name.lower(), (
        f"First tool should be a query, got '{trace.spans[0].name}'"
    )
    
    # The second span should not re-query the same thing
    assert trace.spans[1].type == "reasoning"
    assert trace.spans[1].input_token_count < trace.spans[0].input_token_count * 0.8, (
        "Step 2 reasoning context should be compacted, not full re-query"
    )
    
    # No step should loop back to a near-identical query
    loop = detect_repeated_span_type(trace.spans, threshold=0.85)
    assert loop is None, f"Loop detected at span {loop}: {trace.spans[loop]}"
    
    # Final output must reference actual retrieved data, not hallucinated figures
    final_span = trace.spans[-1]
    assert final_span.citations, "Final answer must cite retrieved sources"
    assert len(final_span.citations) >= 1, "Answer must contain at least one citation"
```

### Layer 3 — Fault Injection

Inject failures at each layer and assert the agent's recovery behavior. A 10-step pipeline at 85% reliability per step achieves ~20% end-to-end success. Recovery contracts are non-negotiable.

```python
def test_tool_timeout_recovery():
    """
    Layer 3: Fault injection — inject MCP server timeouts
    and verify the agent either retries or escalates gracefully.
    """
    harness = AgentHarness()
    
    with harness.simulate_failure(
        tool="search_knowledge_base",
        failure_type="timeout",
        probability=1.0,
    ):
        trace = harness.run(
            "What's the status of ticket #8812?",
            max_steps=5,
        )
    
    # Acceptable recovery paths:
    # 1. Retry with backoff (trace shows 2+ attempts on same tool)
    # 2. Fall back to cached data (trace shows fallback_tool call)
    # 3. Graceful degradation (trace shows explicit uncertainty statement)
    recovery_paths = {
        "retried": len([s for s in trace.spans if "search_knowledge_base" in s.name]) >= 2,
        "fallback": any("fallback" in s.name.lower() for s in trace.spans),
        "degraded": trace.final_output.uncertainty_flag is True,
    }
    
    assert any(recovery_paths.values()), (
        f"No acceptable recovery path found. "
        f"Retried: {recovery_paths['retried']}, "
        f"Fallback: {recovery_paths['fallback']}, "
        f"Degraded: {recovery_paths['degraded']}"
    )
    
    # Unacceptable: silent pass-through (agent returned a hallucinated answer)
    assert not trace.final_output.is_hallucinated_response, (
        "Agent produced hallucinated response on tool failure — "
        "must fail gracefully"
    )
```

### Layer 4 — CI/CD Regression Gate

The harness must gate production. This is where most teams fail — not in the tests, but in the enforcement.

```yaml
# .github/workflows/agent-harness.yml
name: Agent Regression Harness

on:
  pull_request:
    paths:
      - 'agents/**'
      - 'prompts/**'
      - 'tools/**'

jobs:
  harness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync tool catalog
        run: harness sync-catalog --env prod
        
      - name: Run Layer 0 — Data Certification
        run: harness certify --layers 0
        # Blocks immediately if tool schema drifted
      
      - name: Run Layer 1+2 — Unit & Trajectory Tests
        run: |
          harness run \
            --suite regression \
            --pass-k 5 \
            --baseline main \
            --threshold 0.88
        env:
          EVAL_DATASET: "golden-datasets/regression-v3.jsonl"
      
      - name: Run Layer 3 — Fault Injection
        run: harness run --suite fault-injection --fail-fast false
        # Does not block, but results go to report
      
      - name: Upload trace artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: agent-traces-${{ github.sha }}
          path: .harness/traces/
      
      - name: Gate on pass rate
        run: |
          PASS_RATE=$(harness report --format json | jq '.regression.pass_rate')
          echo "Pass rate: $PASS_RATE"
          if (( $(echo "$PASS_RATE < 0.88" | bc -l) )); then
            echo "FAIL: Pass rate $PASS_RATE below threshold 0.88"
            exit 1
          fi
          echo "PASS: Regression gate cleared"
```

### The Production → Regression Pipeline

The highest-value regression cases come from production, not imagination. Every confirmed failure in production should become a permanent regression test.

```python
# A confirmed production failure is converted to a golden case in one step:
harness.export_production_failure(
    trace_id="trace-2026-08-03-4421f9",
    label="wrong-refund-amount",
    severity="p1",
    tags=["finance", "calculation", "regression"],
    expected_behavior="Agent should verify refund amount against order.total "
                      "before calling process_refund",
)
# Writes to golden-datasets/regression-v3.jsonl
# Next CI run includes this case automatically
```

The loop: **production failure → trace → golden case → CI gate → regression never ships again**.

## Receipt

> Verified 2026-08-03 — Framework layers drawn from Atlan's six-layer testing stack (atlan.com, 2026). Fault injection patterns from Confident AI's agent testing guide (confident-ai.com). CI/CD gating from Harness AgentTrace documentation (harness.io). Golden case export from Arthur's regression testing methodology (arthur.ai, June 2026). Code examples constructed from production patterns; not run against a live agent.

## See also

- [S-987 · The Agent Evaluation Stack](s987-the-agent-evaluation-stack-when-you-cant-tell-if-your-agent-is-actually-working.md) — the eval foundations this harness builds on
- [S-1062 · The Production Drift Stack](s1062-the-production-drift-stack-when-your-lab-evals-pass-and-your-production-fails-silently.md) — monitoring for drift after the CI gate passes
- [S-2085 · The Evaluation Gap Stack](s2085-the-evaluation-gap-stack-when-your-pass1-is-green-but-your-production-is-on-fire.md) — the gap between pass@1 and production reliability
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the SRE practice that makes harness engineering sustainable
