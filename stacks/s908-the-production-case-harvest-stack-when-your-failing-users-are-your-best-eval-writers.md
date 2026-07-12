# S-908 · The Production Case Harvest Stack — When Your Failing Users Are Your Best Eval Writers

Your eval suite has 200 cases. Your production agent has handled 80,000 sessions. Your eval pass rate is 94%. Your production failure rate is 31%. The gap is not a measurement problem — it's a pipeline problem. The 200 cases were written by engineers who knew what the agent should do. The 80,000 sessions contain every edge case the engineers never imagined. The Production Case Harvest Stack closes that gap: a systematic pipeline that converts failing production traces into scored, tagged, reproducible regression test cases — automatically, continuously, and with semantic grounding so they don't just reproduce the failure, they explain it.

## Situation

A customer-service agent in a multi-agent pipeline misclassifies a billing dispute and routes it to the wrong team. Nobody noticed for 72 hours. When the triage engineer finally reproduces the failure from the trace log, the root cause is a formatting quirk in how the upstream CRM API encodes invoice amounts — `{"total": "USD 47.50"}` vs the expected `{"total": 47.50}` — that the agent's JSON parser silently treats as a string, corrupting the downstream routing logic. The engineer writes one regression test. It passes. Three weeks later, a different numeric format from a different API triggers the same silent corruption and nobody catches it because the regression test only covered the one observed case.

The harvest stack prevents this by treating every production failure as a potential case in a growing, versioned eval corpus — and by building the case with enough structure that it catches the *pattern*, not just the instance.

## Forces

- **Eval suites are backward-looking.** They cover the failures you already know about. Production surfaces the failures you don't — yet. A static eval suite is a snapshot that grows stale the moment it ships.
- **Manual case authoring doesn't scale.** Engineers writing eval cases from scratch spend 80% of time on setup and 20% on the actual edge case. Production traces provide the setup automatically.
- **Single-case regression tests have low coverage.** A test written from one failure instance catches that instance. A test built from a failure cluster — N similar traces with the same failure pattern — catches the class.
- **Unscored production failures are wasted signal.** A trace where the agent failed can be replayed and scored, but without the replay infrastructure and the scoring logic, it just sits in the log as a story nobody reads twice.
- **Harvesting without scoring creates noise.** Every production failure converted to a test case that always passes is worse than no case at all — it gives false confidence. Cases need to be scored in the eval harness to verify the agent actually fails them.

## The move

**Three-stage pipeline: extract → cluster → certify.**

### Stage 1 — Extract (Continuous Failure Capture)

Run a semantic classifier over every production trace completion. Two signals matter:

1. **Outcome scoring:** Does the agent's final output pass the downstream validation gate? (Does the JSON parse? Does the routing decision match the expected team? Does the tool call succeed?)
2. **Confidence mismatch:** The agent reported success; downstream validation disagrees. This is the highest-value failure class — it bypasses all error-rate metrics.

On mismatch, snapshot the full trace: user input, agent reasoning chain, all tool calls, all tool responses, final output, and the validation failure signal. Store in a `failing_traces/` artifact store with metadata: timestamp, user geography, session length, model version, tool schemas active at time of call.

```python
# Production interception point
def capture_on_mismatch(
    trace: AgentTrace,
    validator: Callable[[Output, ToolContext], bool],
) -> None:
    output = trace.final_output
    tool_ctx = trace.tool_context_snapshot()
    
    if validator(output, tool_ctx) is False:
        # Triggered: agent said done, validator says no
        artifact = {
            "trace_id": trace.id,
            "user_input": trace.user_input,
            "reasoning_chain": trace.reasoning,
            "tool_calls": trace.tool_calls,
            "tool_responses": trace.tool_responses,
            "final_output": output,
            "validation_signal": "downstream_rejection",
            "model_version": trace.model_version,
            "session_duration_ms": trace.duration_ms,
            "captured_at": datetime.utcnow().isoformat(),
        }
        harvest_store.append(artifact)
```

### Stage 2 — Cluster (Pattern Generalization)

Raw failing traces sit in the store like unfiled bug reports. Cluster by failure type using semantic similarity on the tool-call sequence (not the natural language text — the *intent* of the tool call pattern).

Three cluster types:
- **Exact-duplicate cluster:** Same tool, same args, same failure. Deduplicate immediately — one canonical case, N supporting traces.
- **Schema-variant cluster:** Same tool, different data format (USD string vs float, ISO date vs unix timestamp). This is the high-value cluster: it catches the parser/semantic-gap pattern.
- **Behavioral cluster:** Same user goal, different agent strategy chosen (wrong tool selected). Lower priority — harder to turn into a reproducible case.

Tag each cluster with: failure type label, affected tool, root-cause hypothesis, and the minimum viable reproduction input.

```python
def cluster_traces(traces: list[TraceArtifact]) -> list[TraceCluster]:
    embeddings = encode([t.tool_call_sequence for t in traces])
    clusters = cluster_by_similarity(embeddings, threshold=0.85)
    
    for cluster in clusters:
        cluster.tag = infer_failure_type(cluster.traces)
        cluster.root_cause = hypothesize(cluster.traces)
        cluster.canonical_input = extract_minimal_repro(cluster.traces)
        cluster.frequency = len(cluster.traces)
    
    return clusters
```

### Stage 3 — Certify (Eval Conversion with Scoring)

Convert each cluster's canonical input into an eval case with an automated scorer. The scorer must not be the same logic the production agent uses — if it is, the eval will always pass. Use an independent verification path:

| Failure type | Independent verifier |
|---|---|
| JSON corruption | Downstream schema validator (JSON Schema / pydantic) — run against expected schema |
| Wrong routing | Labeled routing oracle — check destination against golden label |
| Silent tool failure | Tool response audit — re-call the tool with same args, check status field |
| Semantic mismatch | LLM-as-judge with chain-of-thought, anchored on explicit rubric |

Cases that score 100% on the independent verifier are discarded (no failure reproduced — the production failure was a transient). Only cases that consistently fail the verifier across all cluster traces become certified regression cases.

```python
def certify_case(cluster: TraceCluster, verifier: Callable) -> EvalCase | None:
    case = EvalCase(
        input=cluster.canonical_input,
        expected_behavior=cluster.root_cause.explanation,
        scorer=verifier,
        tags=[cluster.tag, cluster.failure_type],
        source_traces=cluster.trace_ids,
    )
    
    # Verify this case actually fails the agent
    agent_output = agent.run(case.input)
    if verifier(agent_output, case.tool_context) is True:
        return None  # Agent passes — not a reliable regression case
    
    # Score with independent verifier
    score = case.run_scorer(agent_output, case.tool_context)
    if score == 0.0:
        harvest_corpus.add(case)
        return case
    
    return None  # Partial failure — too noisy for regression suite
```

### Operationalize: The Harvest Gate

Integrate the certified corpus into CI. Run harvest cases on every prompt or model version change alongside the static eval suite. Track coverage: what percentage of production failure clusters are represented in the corpus?

The goal is not 100% coverage — it's bounded unknown. A cluster you haven't harvested yet is a failure you haven't learned from yet. Measure the harvest rate: `certified_cases / total_failing_clusters`. If it's below 60% after 30 days, the extraction or clustering logic needs tuning.

## Receipt

> Verified 2026-07-10 — Pipeline described is a synthesis of patterns from Zylos Research 2026 (eval-production gap), CallSphere eval pipeline guide (CI regression), Data-Gate 2026 (custom eval for agents), and production observability patterns from S-196 (OTel GenAI), S-274 (failure localization), and S-569 (eval illusion). The code examples follow real production patterns from Langfuse, DeepEval, and Arize Phoenix harvest workflows. No fabricated API signatures.

## See also

- [S-196 · OTel GenAI Telemetry](s196-otel-genai-telemetry.md) — trace instrumentation that makes harvest-quality traces possible
- [S-274 · Agent Failure Localization](s274-agent-failure-localization.md) — from trace to regression test, the manual version
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — where harvested cases run
- [S-569 · The Eval Illusion](s569-the-eval-illusion-when-passing-evals-dont-prevent-production-failures.md) — why the static eval suite misses what harvest catches
- [S-658 · Golden Trace Set Curation](s658-golden-trace-set-curation.md) — the curated version of what harvest produces systematically
