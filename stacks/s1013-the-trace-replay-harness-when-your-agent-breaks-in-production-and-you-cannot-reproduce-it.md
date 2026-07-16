# S-1013 · The Trace Replay Harness — When Your Agent Breaks in Production and You Cannot Reproduce It

An agent fails in production at 3 AM. You have the trace — timestamps, tool calls, LLM responses. You fix the prompt. You deploy. You have no way to know if the fix actually addressed the failure without waiting for the same rare condition to re-trigger in production. This is the debug debt of autonomous systems: you can observe what happened but you cannot replay it.

## Forces

- **Agents are unreproducible by default.** Unlike a crashed process that dumps core, an agent failure produces a log of reasoning steps that can never be re-executed identically — the next LLM call returns different tokens even with the same seed. The same input produces a different trajectory.
- **Offline eval suites don't cover the failure you just saw.** Your eval harness runs on the 200 examples you had last quarter. The failure that just hit production is a new edge case that isn't in any eval set. The harness can't help you verify the fix.
- **Replay without isolation hits production side-effects.** Naive "replay the trace" calls real APIs and mutates real state. You need to replay a trace without re-executing the side-effects — a test double for everything downstream of the agent's decisions.
- **Trajectory diffing requires a canonical trace format.** Two teams looking at the same failure can't compare unless they agree on what a "step" is, what fields are required, and what counts as a divergence.

## The move

The pattern: **freeze every failed run as a structured trace document, then replay that document deterministically against new candidates** — a new model, a new prompt, a new tool definition. The harness captures the trace as `agentreplay.trace.v1` JSON: user input, LLM call params, tool calls with arguments, tool responses, final output. The replay engine stubs out external calls and replays the LLM call with a different model or modified prompt, producing a new trajectory you can diff against the original.

### The trace schema

```json
{
  "version": "agentreplay.trace.v1",
  "testId": "sha256-hash-of-input",
  "capturedAt": "2026-07-12T03:00:00Z",
  "agent": "claude-sonnet-4-20250711",
  "prompt": "...",
  "llmCalls": [
    {
      "callId": "step-001",
      "role": "assistant",
      "content": "I'll use the web_search tool to...",
      "tools": ["web_search"],
      "toolCalls": [
        { "name": "web_search", "args": { "query": "current production metrics" } }
      ]
    }
  ],
  "toolResponses": [
    { "callId": "step-001", "name": "web_search", "response": { "results": [...] } }
  ],
  "outcome": {
    "type": "fail",
    "divergenceStep": "step-003",
    "failureReason": "wrong-tool-selected"
  }
}
```

### The replay engine stub

```python
import agentreplay as ar

harness = ar.ReplayHarness("traces/prod-fail-001.trace.v1.json")

# Stub all external calls — no real APIs hit during replay
harness.stub("web_search").returns([{"title": "Q3 metrics", "url": "..."}])
harness.stub("db_query").returns({"rows": [{"status": "active"}]})

# Replay against a new prompt
result = harness.replay(
    new_prompt="System: You MUST check the status field before calling web_search.",
    new_model="claude-opus-4-6-20250711",
    check=ar.trajectory_match  # compare step sequence, not just final output
)

if result.diverged:
    ar.diff(result.original_trace, result.replayed_trace)
    print(f"Divergence at {result.divergence_step}: {result.reason}")
    ar.save_regression_test(result)
else:
    print("Fix verified — trajectory now matches expected path")
```

### The diff output

```
--- original (failed)
+++ replayed (with new prompt)
@@ step-003
- "tool": "web_search",
+ "tool": "check_status",
  "reasoning": "Found metrics query — proceeding to fetch data"
+ "reasoning": "Status field unverified — must check before query"
```

### Gating CI with replay traces

```yaml
# .github/workflows/agent-regression.yml
- name: Replay production failure traces
  run: |
    agentreplay run \
      --traces traces/production-failures/*.v1.json \
      --stub-config stubs/prod-stubs.yaml \
      --candidate-prompt prompts/agent-v3.yaml \
      --candidate-model claude-opus-4-6-20250711 \
      --pass-threshold 0.90  # 90% of traces must not diverge
```

A new model or prompt change cannot be promoted unless all captured production failure traces pass the replay check — the specific failure you saw in production is now a regression test in CI.

### Golden trace selection

Not every failed run is worth replaying. The harness includes a selector:

- **Hard failure** (customer-visible): always capture, always replay
- **Silent degradation** (metrics changed, no error): capture the trace, replay periodically  
- **Lucky recovery** (wrong tool, correct final answer): capture and flag — the trajectory is wrong even if the outcome is right

The last category is the most valuable: agents that reach correct answers through reckless paths. A golden trace for "right answer, wrong path" trains the agent to choose better steps.

## Receipt

> Verified 2026-07-12 — Source: [anzal1/agentreplay](https://github.com/anzal1/agentreplay) (created 2026-05-06, MIT license, Node.js reference impl with Python/Go SDKs). Pattern confirmed against jamesm.blog trajectory eval guide (June 2026): "replay harnesses let you re-run a captured trace against a new model or policy without re-hitting production systems." The `agentreplay.trace.v1` JSON schema and CI gating pattern are directly from the repo's README.

## See also

- [S-1009 · The Agentic RCA Stack](/stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — RCA is diagnosis; replay harness is the capture layer that feeds diagnosis and verifies fixes
- [S-1010 · The Agent Eval Stack](/stacks/s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — Eval suites score offline datasets; replay harness scores against production failures the suite never saw
- [S-1012 · The Agent Failure Recovery Stack](/stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — Recovery stops a looping agent; replay harness prevents the same failure from shipping again
