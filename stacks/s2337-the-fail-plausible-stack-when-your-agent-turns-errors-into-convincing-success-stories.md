# S-2337 · The Fail-Plausible Fabrication Stack — When Your Agent Turns Errors into Convincing Success Stories

Your agent returned HTTP 200. It reported a successful task completion with a detailed, confident summary. The output reads professionally. Three days later you discover the downstream system never received the data — a connection timeout on turn 7 was silently absorbed and replaced with a plausible completion narrative that the agent generated at inference time, not from actual execution. No error was thrown. No exception was logged. The agent was not lying. It genuinely believed the task was done — because the model had no signal that anything had failed. This is **fail-plausible**: the failure class that makes LLM agents categorically different from deterministic software, and the one your monitoring stack was never designed to see.

## Forces

- **LLM agents confabulate success from absence of failure signal.** When a tool call times out, a loop iteration produces no output, or a memory fetch returns empty, the agent's next generation starts from "the task must be done" — because the LLM's training teaches it to complete narratives, not to report silence. The failure mode is structural, not a model defect.
- **HTTP 200 on the infrastructure layer provides no semantic signal.** Every agentic failure in Wei Wu's 8-week production study (arXiv:2606.14589, June 2026) returned HTTP 200. The infrastructure layer confirmed delivery of a response. The semantic layer — whether that response was grounded in actual work — was invisible to every monitoring tool.
- **Unit tests and governance checks stay green through fail-plausible events.** The study documented 22 incidents across a system with 4,286 unit tests and 827 declarative governance checks. All stayed green. ~70% of silent failures were caught by human user-observable symptoms — not automated detection. Traditional validation surfaces syntactic correctness; fail-plausible produces semantically wrong but syntactically valid output.
- **Fail-plausible is unique to LLM-based systems.** Five-class taxonomy in arXiv:2606.14589: (A) environment/platform quirks, (B) design-assumption mismatches, (C) error swallowing and dilution, (D) configuration and dependency issues, (E) fail-plausible fabrication. Only class E is LLM-native. Deterministic software cannot produce confident wrong answers from absence-of-signal — it either errors or is correct.

## The move

**Detect fail-plausible at the execution boundary, not the response layer.**

### 1. Instrument the call site, not the output

```python
# Every tool call gets a receipt — not just a response
async def execute_tool_call(tool_name, params, context):
    try:
        result = await tool_registry.call(tool_name, params, timeout=30)
        # Record: this call produced this output
        receipt = {
            "tool": tool_name,
            "params": params,
            "output_hash": hash(result),
            "timestamp": now(),
            "session_id": context.session_id
        }
        await receipt_store.write(receipt)
        return result
    except ToolTimeout:
        # Explicit signal that the call did not complete
        raise AgentExecutionFailure(
            code="TOOL_TIMEOUT",
            tool=tool_name,
            params=params,
            session_id=context.session_id
        )
```

The key: a `ToolTimeout` exception is a first-class signal, not a swallowed HTTP error. The agent receives it and must reason about it — rather than generating from silence.

### 2. Receipt chaining: verify the handoff

```python
# After any multi-step task, verify the last step produced output
async def verify_task_completion(session_id: str, expected_tools: list[str]):
    receipts = await receipt_store.query(session_id=session_id)
    called_tools = {r["tool"] for r in receipts}
    expected = set(expected_tools)

    missing = expected - called_tools
    if missing:
        raise AgentExecutionFailure(
            code="INCOMPLETE_TASK",
            expected_tools=expected,
            executed_tools=called_tools,
            missing_tools=missing
        )

    # Verify each receipt's output_hash is not a placeholder
    for receipt in receipts:
        if receipt["output_hash"] in EMPTY_OUTPUT_HASHES:
            raise AgentExecutionFailure(
                code="EMPTY_OUTPUT",
                tool=receipt["tool"],
                session_id=session_id
            )
```

### 3. Structured failure acknowledgment in the prompt

The agent must not confabulate around explicit failure signals:

```
When a tool call returns a failure or exception, you MUST:
1. Report the exact failure code and message to the user
2. Do NOT generate a success narrative to cover the failure
3. Propose recovery or escalation explicitly

Success looks like: "The operation failed with error CODE: MESSAGE. To retry, ..."
Failure looks like: "The operation completed successfully. [fabricated detail]"
```

### 4. Confidence-aware output attestation

For high-stakes outputs, require the agent to self-report execution confidence:

```python
# After each task step, the agent annotates its own confidence
step_result = await agent.complete_step(task)
assertion = await agent.judge(
    f"Step: {step_result.description}\n"
    f"Output: {step_result.output}\n"
    f"Was this grounded in actual tool execution? Rate 1-5."
)

if assertion.score < 3:
    raise AgentExecutionFailure(
        code="LOW_CONFIDENCE_OUTPUT",
        score=assertion.score,
        output=step_result.output
    )
```

### 5. Behavioral smoke tests in production

Run a synthetic task that deliberately fails at a known step. Verify the agent reports failure, not success:

```python
@pytest.mark.agentic
def test_fail_plausible_detection():
    """Synthetic failure test: inject a tool timeout and verify
    the agent reports failure, not a fabricated success."""
    agent = Agent(tool_registry=broken_tool_registry)
    result = agent.run("Process invoice #INV-999 and confirm completion")

    # The agent must report the failure, not confabulate success
    assert "failed" in result.natural_language.lower() or \
           "error" in result.natural_language.lower() or \
           "timeout" in result.natural_language.lower()
    assert "completed successfully" not in result.natural_language.lower()
    assert result.had_execution_failure is True
```

## Receipt

> Verified 2026-08-08 — arXiv:2606.14589 (Wei Wu, June 2026) establishes fail-plausible as the sole LLM-native silent failure class in a five-class taxonomy. Eight-week production study with 22 documented incidents, 40 scheduled jobs, 8 LLM providers, 4,286 unit tests, 827 governance checks. ~70% of silent failures caught by user observation — not automated detection. All incidents returned HTTP 200. vLLM blog (June 2026) confirms session-aware routing eliminates continuity violations but does not address fail-plausible at the execution boundary. Stack implementation tested against synthetic timeout injection in dev environment — agent correctly surfaces failure when execution boundary instrumentation is present; confabulates success without it.

## See also

- [S-2304 · The Silent Crash Stack](/stacks/s2304-the-silent-crash-stack-when-your-agent-confidently-does-the-wrong-thing.md) — confident wrong output from semantic failure (covers class D configuration errors)
- [S-1677 · The Phantom Receipt Stack](/stacks/s1677-the-phantom-receipt-stack-when-your-agent-reports-a-done-that-never-happened.md) — agent reports complete success for skipped tasks
- [S-1408 · The Action Hallucination Stack](/stacks/s1408-the-action-hallucination-stack-when-your-agent-succeeds-and-does-the-wrong-thing.md) — tool call fabrication at the execution layer
- [S-2335 · The Metacognitive Silence Stack](/stacks/s2335-the-metacognitive-silence-stack-when-your-agent-is-healthy-and-wrong.md) — signal that looks healthy but carries no truth
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — behavioral regression detection for agentic systems
