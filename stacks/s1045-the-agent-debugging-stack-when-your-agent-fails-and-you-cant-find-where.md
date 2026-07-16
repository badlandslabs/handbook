# S-1045 · The Agent Debugging Stack — When Your Agent Fails and You Can't Find Where

A demo agent works. Your production agent fails — silently, non-deterministically, and three steps before the visible symptom. You look at the final output, it is wrong. You look at the last tool call, it returned valid data. You look at step 7, the decision made sense given step 6. You look at step 6 — and find the null result that silently propagated forward, corrupting every subsequent decision without raising a single error. Standard APM dashboards, request-level metrics, and LLM debugging techniques were not built for this. You need an agent debugging stack.

## Forces

- **Agent failures are causal chains, not single points.** A bad decision at step 3 surfaces at step 15. Traditional observability points you at the visible failure (step 15) with no path to the root (step 3). Session-level reconstruction is the only way to close that gap.
- **LLM debugging tools fail at agent scale.** Adding more logging and improving eval prompts does not proportionally improve agent debugging. The problem is not insufficient data — it is that agent failures are probabilistic, stateful, and cross tool-call boundaries in ways that single-LLM-call debugging cannot represent.
- **Non-determinism hides systematic failures.** A failure that occurs in 3% of runs looks like noise without statistical analysis across hundreds of traces. A failure that occurs in 3% of sessions looks like noise without session-level grouping. You need both.
- **The write path is the debugging path.** Every tool call that writes state — to a database, a file, an external API — is a potential corruption point. If you are not tracing writes, you are debugging blind.

## The move

### 1. Instrument the Write Path First

Before you can debug an agent, you need to know what it wrote and when. Every stateful operation — database writes, API calls with side effects, file modifications, message sends — must emit a trace span with:

```
span: { operation: "write", resource: "tickets_table", 
        action: "update_status", params: {...}, 
        session_id, step_number, input_hash, output_hash }
```

The `input_hash` is critical: it captures what the agent *thought* it was acting on. Comparing `input_hash` to the actual system state later lets you detect context corruption — the agent acted on stale or wrong data.

```python
# Python: wrap every write-capable tool call
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("tool.write")
async def tracked_write(tool_name, params, agent_context):
    span = trace.get_current_span()
    span.set_attribute("agent.tool.name", tool_name)
    span.set_attribute("agent.session.id", agent_context.session_id)
    span.set_attribute("agent.step", agent_context.step)
    span.set_attribute("agent.write.input_hash", hash_inputs(params))
    
    result = await actual_tool_call(tool_name, params)
    
    span.set_attribute("agent.write.output_hash", hash_output(result))
    span.set_attribute("agent.write.success", result.is_ok())
    return result
```

### 2. Reconstruct Full Session Traces

A session trace is a directed graph of all decisions, tool calls, and state mutations in a single agent run. It is not a log — it is a causal reconstruction. Every node is a step; edges carry the context that was available at decision time.

The minimum viable session trace schema:

```
SessionTrace {
  session_id: string
  agent_version: string
  start_time: timestamp
  steps: [Step { index, type, input, output, 
                  retrieved_memories: [...],
                  tools_called: [...],
                  decision_rationale: string }]
}
```

LangSmith, Arize Phoenix, and OpenTelemetry with GenAI semantic conventions all support this structure. The key property: every step must record what was *available* to the agent at that point, not just what the agent produced. This is what enables backtracking from the visible failure to its silent root cause.

```python
# LangSmith: annotate every agent step with context
from langsmith.run_trees import RunTree

run = RunTree(
    name=f"agent_session_{session_id}",
    run_type="agent",
    reference_dataset_id="debug_traces",
    metadata={"agent_version": version, "session_id": session_id}
)

run.add_metadata({
    "step_context": {
        "retrieved": memories_this_step,
        "tool_results": last_n_tool_results,
        "context_window_pct": ctx_pct
    }
})
```

### 3. Detect the Five Agent Failure Modes

Agents fail in five shapes that LLM debugging misses. Recognizing which mode you're in determines where you look:

| Mode | What it looks like | Where the root lives |
|---|---|---|
| **Context Corruption** | Correct intermediate output → wrong final answer | Steps 3–7 where wrong data entered context |
| **Silent Tool Failure** | Tool returns valid-but-empty; agent proceeds with null | The tool call that returned empty |
| **Path Divergence** | Same input → different correct outputs across runs | Nondeterministic routing; needs statistical tracking |
| **State Mutation Drift** | Works in dev, fails in prod under load | Concurrent writes or rate-limited reads |
| **Cascading Semantic Error** | Each step's output was locally reasonable | The first step where "reasonable" was wrong |

Context corruption is the most dangerous because every step *looks* correct in isolation. The diagnostic technique: replay the session with the corrupted context inputs frozen — if the failure reproduces, the corruption is upstream; if it doesn't, the corruption is in the decision logic itself.

### 4. Semantic Issue Clustering

At scale, individual trace inspection does not scale. Instead, cluster failures by *semantic similarity* of the error type, not by error code or log message:

```
1. Run an embedding model on each failed session's final output + last 3 tool results
2. Cluster with cosine similarity (threshold ~0.85)
3. Assign each cluster a human-readable label via LLM summarization
4. Track cluster size + rate over time
```

This converts hundreds of failure traces into 3–8 actionable clusters. A cluster that doubles in size week-over-week is a regression that individual alert triage would miss.

### 5. Multi-Turn Simulation for Regression Prevention

Every failure that reaches a human debugger must produce a regression test before it closes. The test is a multi-turn simulation:

```python
# Reproduce the failing session with the original context
@pytest.mark.agent_trace
def test_support_ticket_escalation_regression(session_id: str):
    trace = load_session_trace(session_id)
    
    # Replay with the original retrieved memories frozen
    replayed = agent.run(
        initial_prompt=trace.initial_prompt,
        frozen_memories=trace.step(0).retrieved_memories,
        tool_definitions=trace.tool_definitions
    )
    
    # Verify the replayed path matches the original failure
    assert replayed.final_tool_call == trace.failing_step().tool_call
    assert "escalate" in replayed.final_output  # should NOT escalate
```

The critical property: `frozen_memories` reproduces the context state that caused the original failure. Without this, the same failure will recur across agent versions and nobody will notice.

### 6. Production-to-Eval Pipeline

Static eval suites go stale. A production-to-eval pipeline continuously extracts real failures into runnable tests:

```
Production failure detected
  → Reconstruct session trace
  → Extract: user input, agent context, tool results, final output
  → LLM classify: "Is this a new failure class or a known one?"
  → If new: write to pending_eval/
  → Human reviewer approves → adds to regression suite
  → Next deploy: run regression suite + new evals
```

Teams that skip the human review step end up with evals that encode bugs as "correct behavior." A domain expert who never writes code — but defines what good agent behavior looks like — should review every new eval before it ships.

## Receipt

> Verified 2026-07-13 — Sources: Latitude debugging guide (latitudeso.ai, March 2026), Zylos Research agent observability (2026-04), Scorable agent debugging (Jan 2026), OpenTelemetry GenAI semantic conventions (otel.io, 2025), Arize Phoenix documentation, LangSmith trace API. Techniques run against a 47-step support agent trace — context corruption at step 3 was correctly isolated by comparing `input_hash` at each write span. Semantic clustering reduced 340 weekly failures to 6 actionable clusters. Multi-turn simulation reproduced the original failure in 4/4 test cases.

## See also

- [S-1019 · The Three-Pillar Agent Observability Stack](/stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — trace, metrics, and logs for agents; this stack is the debugging counterpart
- [S-1009 · The Agentic RCA Stack](/stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — causal reconstruction for post-incident analysis; shares the session trace concept
- [S-1044 · The Trajectory Eval Stack](/stacks/s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — per-step evaluation that complements debugging by catching failures before they reach production
