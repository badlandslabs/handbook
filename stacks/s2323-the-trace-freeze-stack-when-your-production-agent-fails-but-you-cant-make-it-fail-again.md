# S-2323 · The Trace Freeze Stack — When Your Production Agent Fails but You Can't Make It Fail Again

Your agent failed in production on Tuesday. You know exactly what the user asked and roughly what went wrong. But when you run the same input locally, the model returns different tokens and the failure doesn't reproduce. The agent's non-determinism means the failure is real but unreproducible — and unreproducible failures can't be verified, can't be regression-tested, and can't be fixed with confidence.

## Forces

- **Agent failures are stochastic by default.** Even with temperature=0 and a fixed seed, the model can return different tokens across runs due to KV cache initialization, batching non-determinism, or hardware-level nondeterminism. A failure that occurred in production with 10k users may never occur again in a 10-run eval.
- **The freeze-and-replay gap.** Standard observability tells you what happened. It does not freeze the causal chain — the exact prompt hash, tool schemas, tool call arguments, tool responses, and model outputs — in a format you can re-execute offline. Without that, every production failure is a one-time event.
- **Production traces contain the ground truth.** The failing run has the actual context, the actual tool responses, and the actual decision points. Hand-reconstructed evals from memory are approximations and miss the subtle conditions that caused the failure.
- **Frozen traces need deterministic replays.** Capturing a trace is only half the problem. The replay harness must stub external dependencies (tool responses, time, randomness) so the run replays identically, or the frozen trace ages into the same unreproducibility problem it was meant to solve.

## The move

**Capture the causal chain at failure time. Serialize it as a deterministic replay artifact. Convert it to a regression test.**

The `agentreplay.trace.v1` format (anzal1/agentreplay, 2026-05) standardizes this as JSON:

```json
{
  "version": "1.0",
  "user_input": "Summarize the Q3 revenue report for the Southeast region",
  "agent_metadata": {
    "agent_name": "revenue-agent",
    "model": "claude-sonnet-4-20250514",
    "prompt_hash": "sha256:a3f9c2..."
  },
  "tool_schemas": [...],
  "tool_calls": [
    {
      "call_id": "tc_01",
      "tool": "query_db",
      "arguments": {"sql": "SELECT * FROM revenue WHERE region='SE'"},
      "response": {"rows": 47, "data": [...]},
      "latency_ms": 234,
      "state_mutating": true
    }
  ],
  "final_output": "The Southeast region generated $...",
  "outcome": "failed",
  "failure_reason": "wrong_aggregation"
}
```

**The freeze criteria.** Not every failure needs freezing. Gate on:
- User-reported or P0/P1 severity
- Involves state mutation (writes, API calls, DB changes)
- Involves a tool-call sequence (not a single-turn hallucination)
- Reproducible with multiple runs on the same seed (if so, standard eval is sufficient)

**The replay harness.** Given a frozen trace, the harness replays it with external calls stubbed:

```python
# agentreplay harness (agentreplay v1, anzal1/agentreplay)
from agentreplay import ReplayHarness, TraceLoader

loader = TraceLoader("traces/failed_run_2026-08-07.trace.v1.json")
harness = ReplayHarness(loader)

# Stub external services so replay is deterministic
harness.stub("query_db").returns(loader.frozen_response("tc_01"))
harness.stub("fetch_report").returns(loader.frozen_response("tc_02"))

# Replay against the current agent version
result = harness.replay(agent="current", runs=5)

# Score: same tool calls, same args, same output?
score = result.tool_call_accuracy()   # did it call the same tools?
path_score = result.trajectory_match()  # same sequence?
outcome_score = result.output_match()   # same final answer?

result.assert_regression_free(threshold=0.9)  # ≥90% match or fail CI
```

**Tool responses marked by state-mutating flag.** This is the key distinction:
- `state_mutating: false` → safe to replay from the frozen trace
- `state_mutating: true` → replay from stub OR accept that the replay tests the recovery path, not the original state

**The production-to-eval pipeline:**
1. Production agent emits a structured trace (OpenTelemetry spans with `genai.span.type=agent` or LangSmith `trace_id`)
2. On P0/P1 failure, the trace is serialized to `agentreplay.trace.v1` and written to object storage
3. The on-call engineer reviews the trace, annotates the failure reason, and approves it for the eval set
4. The trace is converted to a test case: frozen inputs + expected output + tool-call sequence
5. The harness runs it against every agent version (nightly + pre-deploy CI gate)
6. A statistical pass threshold (e.g., 4/5 runs pass) handles residual nondeterminism

**The statistical catch.** Run each frozen trace 5–10 times. A regression is flagged if the pass rate drops below threshold — this catches failures that reproduce in 2/5 runs but not deterministically.

## Receipt

> Verified 2026-08-08 — AgentReplay (anzal1/agentreplay, GitHub, created 2026-05) implements the full trace.v1 → replay → CI-gate pipeline. James M (jamesm.blog, June 2026) describes the same pattern with production traces → per-step rubrics → regression suites. Langfuse Phoenix and Arize AI both surface the "trace to eval" workflow natively. Core claim confirmed: the agent failure is non-deterministic by default but deterministic when external calls are frozen. The `state_mutating` flag is the critical split that makes replay tractable.

## See also

- [S-1004 · The Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — the eval taxonomy this fits into; S-2323 is the reproduction layer S-1004's measurement layer needs
- [S-538 · Agent Evaluation Harness](s538-the-agent-evaluation-harness-when-your-agent-is-always-green.md) — pinned eval sets; this entry adds the production-capture layer that feeds the pinned set
- [S-658 · Golden Trace Set Curation](s658-the-golden-trace-set-curation-when-you-dont-know-if-your-agents-improved.md) — trace grading and curation; S-2323 is the automated capture that supplies the raw traces for curation
