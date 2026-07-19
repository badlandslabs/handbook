# S-1350 · The Eval Blindspot Stack

Your agent scores 94 on your eval suite. Three times in the last week, a user received a confident wrong answer and your team found out through a support ticket — not a monitoring alert. The eval suite passed every time. The failures were invisible to it because they lived in failure modes your suite never anticipated.

This is the eval blindspot: the structural gap between what your eval measures and what breaks in production. It is not a scoring problem. Your metrics are accurate. The problem is that your metrics are measuring the wrong space.

## Situation

A RAG agent is deployed with a golden dataset of 200 question-answer pairs from Q3 2025. The eval runs nightly. Scores have been stable at 91–93 for six months. In February 2026, a product taxonomy change shifts the meaning of three core entity categories. The vector store still returns documents — the similarity scores are fine — but the retrieved content answers questions that no longer match the product's actual state. The eval suite, running on stale ground truth, scores 92. Users receive confident wrong answers. The team discovers the gap only when a customer escalates.

A coding agent's regression suite covers "does the function return the right output." It does not cover "does the function's behavior change when the input schema shifts subtly" or "does the agent handle a library version mismatch gracefully." When a dependency updates in production, the agent passes every test and produces subtly wrong code for three days.

A multi-step agent pipeline scores 97 on a task-completion eval. The eval measures whether the final artifact exists and is well-formed. It does not measure whether the artifact was built from the right data — only that something was built. When the retrieval step silently degrades (vector index out of date, API returning stale records), the agent generates a plausible artifact from wrong inputs and scores 97.

Three incidents, one root cause: **the eval suite cannot anticipate novel failure modes because it was designed around failure modes already known.**

## Forces

- **Eval suites are backward-looking**: they are written by humans who have experienced failures and want to prevent recurrence. Every failure that has never been seen is invisible to the suite. This is not a gap in test coverage — it is a structural property.
- **LLM-as-judge scores confidence, not correctness**: a model that confidently provides wrong information typically scores well on coherence, helpfulness, and fluency. The judge grades the output's surface properties. When a silent tool failure produces wrong-but-plausible data, the agent hands that data to the model, which generates a confident response, which the judge rates highly.
- **Standard eval frameworks were designed for capability, not reliability**: HELM, MT-Bench, AgentBench, and BIG-bench measure what models can do in controlled settings. They were not designed to catch compounding decision errors, tool failure cascades, non-deterministic drift, or the absence of ground truth for long-horizon tasks. A 2026 arXiv study found standard metrics fail to detect 4 of 7 production failure modes entirely.
- **Eval suites miss the novel**: your golden dataset is bounded by the failure modes you anticipated when you wrote it. The most expensive production failures are precisely the ones nobody anticipated. The eval passes; the production failure continues.
- **Failure category matters for MTTR**: teams that maintain failure registries see faster mean time to resolution because structured categorization narrows the diagnostic space. An eval that cannot classify failures cannot feed this loop.

## The move

Build a three-layer eval architecture that closes the blindspot: **production-failure-driven eval expansion**, **span-level observability**, and **counterfactual eval gates**.

### Layer 1 — Production Failure → Eval Pipeline

Every production failure that was not caught by the eval suite feeds back into it. This is the critical loop most teams skip: they fix the bug and move on. The fix for the blindspot is to treat every undetected failure as a gap in eval coverage, not just a bug in the code.

```python
class ProductionFailureCapture:
    """
    On-call: when a production incident is closed,
    the failure goes to eval, not just code review.
    """
    def on_incident_resolved(self, incident):
        # Extract the failure signal, not just the root cause
        eval_case = {
            "input": incident.user_query,
            "failure_type": incident.category,       # e.g., "silent-tool-failure"
            "what_broke": incident.symptom,          # "confident wrong answer"
            "why_eval_missed_it": incident.postmortem.gap_analysis,
            "trace_snippet": incident.relevant_spans,
            "expected_behavior": incident.ground_truth,
        }
        # Add to the eval suite's "production failures" partition
        eval_suite.add_partition("production_gaps", eval_case)
```

The key discipline: don't just add the case that failed — add the *category* of failure. If a silent tool failure caused a confident wrong answer, add five synthetic cases of silent tool failure to the suite. One incident becomes five eval cases.

### Layer 2 — Span-Level Trace Observability

Trace-level metrics tell you the run failed. Span-level metrics tell you where and why. The eval blindspot shrinks when every tool call, retrieval step, planning step, and handoff is its own evaluable artifact.

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.span("tool_call")
def evaluate_tool_call_span(span, tool_result, agent_context):
    """
    Span-level eval: does this tool call's result justify the next action?
    A tool returning empty results that the agent treats as valid
    is a silent failure — detectable at span level, invisible at trace level.
    """
    if tool_result.is_empty() and not agent_context.has_fallback:
        # This span is where the silent failure lives
        span.set_attribute("eval.signal", "silent_tool_failure")
        span.set_attribute("eval.action", "BLOCK_AND_FLAG")
        return BlockedResult(reason="Tool returned empty; no fallback configured")
    return tool_result

@tracer.span("retrieval")
def evaluate_retrieval_span(span, retrieval_result, query):
    """
    Span-level: does retrieved context actually answer the query?
    Not just: is retrieval non-empty?
    """
    relevance = retrieval_result.context_relevance_score(query)
    if relevance < 0.3:
        span.set_attribute("eval.signal", "low_relevance_retrieval")
        span.set_attribute("eval.action", "ESCALATE_TO_FALLBACK")
    return retrieval_result
```

Every span gets a signal tag. Span-level signals aggregate into trace-level quality scores that are independent of task completion.

### Layer 3 — Counterfactual Eval Gates

Rather than only testing expected behavior, run counterfactual evals: "what if the tool returns empty? what if the model version changed? what if the retrieval returns wrong-but-similar documents?" These scenarios cannot be generated from past failures — they are synthetic stress tests of the system's assumptions.

```python
def counterfactual_eval_suite(agent):
    """
    Counterfactual gate: stress-test the agent's assumptions
    before production does it for you.
    """
    scenarios = [
        ToolReturnsEmptyScenario(),        # Does agent detect and handle?
        ToolReturnsWrongSchemaScenario(),  # Does agent validate schema?
        RetrievalReturnsStaleDocsScenario(), # Does agent detect staleness?
        ModelVersionChangedScenario(),     # Does agent notice behavioral shift?
        NetworkTimeoutOnCriticalToolScenario(),
    ]
    results = []
    for scenario in scenarios:
        with mock_tool_response(scenario):
            trace = agent.run(task_from_eval_suite)
            span_signals = extract_span_signals(trace)
            eval_signal = aggregate_span_signals(span_signals)
            results.append({
                "scenario": scenario.name,
                "agent_response": trace.final_output,
                "span_signals": span_signals,
                "eval_passed": eval_signal in ACCEPTABLE_SIGNALS,
            })
    return results
```

Run the counterfactual suite on every model upgrade, every major prompt change, and every significant dependency update. This is the only layer that catches failure modes nobody has experienced yet.

### The Closed Loop

```
Production Failure
    → categorize (silent tool failure, confabulation, retrieval drift...)
    → generate synthetic cases (5× the incident)
    → add to eval suite's production_gaps partition
    → span-level observability catches the category in real-time
    → counterfactual gates prevent the next variant
```

The blindspot does not close by writing more tests. It closes by making production failures generate tests — and by instrumenting the system so that the eval suite's categories match the production failure taxonomy, not just the happy path.

## Receipt

> Verified 2026-07-19 — Framework architecture derived from arXiv:2605.01604 (Pandey, May 2026) on production eval gaps, Boundev AI (Jul 2026) on silent failure shapes, and Confident AI documentation on span-level vs trace-level eval metrics. Counterfactual eval pattern from production engineering practice described in Latitude debugging guide (Mar 2026). Tool-call span instrumentation pattern from OpenTelemetry agent tracing conventions. Composite score: 8.90.

## See also

- [S-1239 · The Runtime Verification Loop](/stacks/s1239-the-runtime-verification-loop-inline-agent-step-verification-at-production-scale.md) — inline step verification that catches failures during execution, complementing the eval suite's pre-deployment coverage
- [S-817 · The Trajectory Eval Stack](/stacks/s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — testing the reasoning path rather than just the final answer; closes a different portion of the blindspot than counterfactual gates
- [S-1342 · The Evaluation Gap Stack](/stacks/s1342-the-evaluation-gap-stack-when-your-agent-scores-94-but-fails-in-production.md) — when eval scores and production quality diverge; S-1350 covers the *mechanism* of the divergence (novel failure modes the suite cannot anticipate), while S-1342 covers the *symptom* (high scores, poor outcomes)
