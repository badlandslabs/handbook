# S-1151 · The Behavioral Telemetry Stack — When Your Agent Returns 200 OK and a Wrong Answer

Your agent ran 40,000 requests last night. Your observability dashboard shows green. Zero 5xx errors. P99 latency normal. Token spend on budget. But 2,400 of those requests — roughly 6% — returned subtly wrong answers to production-critical questions. Your pipeline passed them through because nothing in your stack was watching for the right wrong signal.

This is the behavioral telemetry gap: infrastructure telemetry (latency, error rates, cost) tells you the agent ran. It tells you nothing about whether the agent ran correctly. Datadog's State of AI Engineering 2026 found 1 in 20 production AI requests fail — and 60% of those failures are capacity-related (rate limiting, context exhaustion, model throttling). But the remaining 40% are semantic: wrong answers, reasoning collapse, and context degradation that return HTTP 200 and a confident lie.

## Forces

- **Agents are inherently unobservable at the semantic layer.** A SQL query that returns zero rows fails loudly. A RAG agent that retrieves the second-best document and returns it as fact fails silently. The difference is that one has a schema violation; the other has a plausible wrong answer.
- **Output quality is probabilistic, not binary.** Traditional software either works or crashes. An agent can return an answer that is 40% wrong, 70% wrong, or confidently fabricated — all within normal latency and cost parameters.
- **Aggregate metrics lie.** Accuracy across all requests can look stable while a specific input cluster degrades silently. An agent that handles 95% of requests perfectly but fails on 100% of medical queries is not a 95%-accurate system.
- **Ground truth is expensive and slow to obtain.** Behavioral telemetry requires actual outcomes — did the agent's action produce the right result? In production, that answer may not arrive for hours or days.

## The Move

Behavioral telemetry is the practice of instrumenting your agent to emit structured signals about *how it is reasoning*, not just *what it returned*. The stack has five layers:

**Layer 1 — Execution Telemetry (required floor)**
Emit structured spans for every agent action: tool calls, tool results, reasoning steps, and final output. Include a confidence signal (if your framework exposes it), token budget consumption, and retrieval provenance. This is the minimum — without it, debugging is archaeology.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

# Instrument the agent loop
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent.turn") as span:
    span.set_attribute("agent.loop_count", loop_count)
    span.set_attribute("agent.tool_count", len(tool_calls))
    span.set_attribute("agent.context_tokens", estimated_context_tokens)
    span.set_attribute("agent.retrieval_hit_count", retrieval_count)
    span.set_attribute("agent.retrieval_confidence", retrieval_confidence)
    span.set_attribute("agent.output_length", len(final_output))

    # Emit reasoning-step spans for downstream anomaly detection
    for step in reasoning_trace:
        with tracer.start_as_current_span(f"reasoning.{step.type}") as step_span:
            step_span.set_attribute("step.partial_correctness", step.confidence)
            step_span.set_attribute("step.tool_used", step.tool or "none")
```

**Layer 2 — Answer-State Verification (the key differentiator)**
After the agent completes, extract the *answer state* — the key claims, decisions, and facts the agent acted on — and store them independently of the output. These are the signals you can compare against later outcomes or re-verify against a grounding source.

```python
import structlog
logger = structlog.get_logger()

# After agent completion — extract answer state
answer_state = {
    "claims": extract_claims(final_output),
    "actions_taken": [t.name for t in tool_calls],
    "confidence": agent.confidence_score,
    "retrieval_grounded": all(r.relevance_score > 0.7 for r in retrievals),
    "loop_count": loop_count,
    "context_truncated": was_context_truncated(),
}

# Emit as a structured event for downstream telemetry pipeline
logger.log("agent.answer_state", **answer_state)
```

**Layer 3 — Semantic Canary Queries (continuous sanity check)**
Run a rotating set of known-answer queries against your live agent — shadow traffic that produces verifiable outcomes. These are not production requests; they are diagnostic probes that run in parallel with live traffic. When a canary's accuracy drops below threshold, alert on it.

```python
class SemanticCanary:
    def __init__(self, agent, threshold=0.90):
        self.agent = agent
        self.threshold = threshold
        self.canaries = load_canary_set("canaries/grounded_probes.json")

    def run_probe_set(self, sample_rate=0.01):
        results = []
        for canary in random.sample(self.canaries, k=int(len(self.canaries) * sample_rate)):
            predicted = self.agent.run(canary.input)
            correct = self.judge(canary.input, predicted, canary.expected)
            results.append(correct)

        accuracy = mean(results)
        span = get_current_span()
        span.set_attribute("canary.accuracy", accuracy)
        span.set_attribute("canary.sample_size", len(results))

        if accuracy < self.threshold:
            emit_alert(
                "canary_accuracy_degraded",
                actual=accuracy,
                threshold=self.threshold,
                delta=accuracy - self.threshold
            )

    def judge(self, input_text, predicted, expected):
        # LLM-as-judge or exact-match depending on answer type
        ...
```

**Layer 4 — Behavioral Drift Detection**
Track rolling statistics on your answer-state telemetry: refusal rate per topic, average confidence score, retrieval hit rate, and claim agreement with upstream sources. A statistically significant shift in any metric — even without a specific failure event — warrants investigation.

```python
from collections import deque
from scipy import stats

class BehavioralDriftDetector:
    def __init__(self, window=500):
        self.window = window
        self.confidence_scores = deque(maxlen=window)
        self.refusal_counts = deque(maxlen=window)
        self.grounding_scores = deque(maxlen=window)

    def ingest(self, answer_state: dict):
        self.confidence_scores.append(answer_state["confidence"])
        self.refusal_counts.append(1 if answer_state.get("refused") else 0)
        self.grounding_scores.append(
            1.0 if answer_state["retrieval_grounded"] else 0.0
        )

    def check(self, z_threshold=2.5):
        if len(self.confidence_scores) < self.window:
            return  # warmup

        # Rolling z-score vs. baseline window
        baseline_conf = mean(list(self.confidence_scores)[:self.window // 2])
        current_conf = mean(list(self.confidence_scores)[self.window // 2:])
        std_conf = stdev(list(self.confidence_scores))

        if std_conf > 0:
            z = (current_conf - baseline_conf) / std_conf
            if abs(z) > z_threshold:
                emit_alert(
                    "behavioral_drift_confidence",
                    z_score=z,
                    baseline=baseline_conf,
                    current=current_conf
                )
```

**Layer 5 — Outcome Feedback Loop**
Close the loop by routing actual outcomes back into the telemetry system. If the agent filed a support ticket and the ticket was escalated, that's a negative signal on the agent's routing decision. If a code change the agent proposed was rejected, that's a negative signal on the code generation step. These signals are sparse but high-value.

## When to Reach for It

Reach for this when your agent touches production decisions with real consequences (financial, medical, legal, customer-facing) and you currently monitor it with the same signals you'd use for a REST API. Reach for it especially when you have a green dashboard and growing anecdotal evidence from users that "something feels off." That gap is behavioral telemetry debt.

Do not reach for it when your agent is experimental or low-stakes — the stack adds meaningful instrumentation overhead and is not worth it for a prototype that might be replaced in two weeks.

## Tradeoffs

- **Layer 3 (canary queries) requires maintenance.** Your canary set must be kept current with your agent's domain. A stale canary that no longer matches your agent's actual inputs will give false confidence.
- **Behavioral drift detection produces false positives.** Rolling z-scores catch distribution shifts that are legitimate (seasonality, new user populations) rather than agent failures. Tune your threshold and invest in root-cause investigation before dismissing alerts.
- **Outcome feedback loops are slow.** The highest-value signal (actual outcomes) takes the longest to arrive. Do not wait for it before instrumenting Layers 1–4.

## Receipt

> Verified 2026-07-15 — Research from: Datadog State of AI Engineering 2026 (5% failure rate, 60% capacity-caused), AlgeriaTech analysis of 40,000+ production agent interactions (silent failures, context degradation, reasoning drift taxonomy), Zeltrex paper on crash resilience (Fix Cascade Model, MAPE-K autonomic loop). StackPulsar production agent observability guide (June 2026) confirmed behavioral telemetry as the primary gap teams discover post-deployment. The 6-layer framework distills Zeltrex's MAPE-K autonomic model into a practical telemetry stack tailored for agentic systems specifically.

## See also

- [S-821 · The Production Failure Stack](/stacks/s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — covers infrastructure failure modes (loops, cost, retries) rather than semantic failures
- [S-818 · The Longitudinal Agent Eval Stack](/stacks/s818-the-longitudinal-agent-eval-stack-continuous-regression-detection-in-production.md) — covers benchmark regression over time rather than in-session behavioral anomaly
- [S-106 · The Answer-State Contract](/stacks/s106-the-answer-state-contract-explicit-output-contracts-for-autonomous-agents.md) — structural output contracts that complement behavioral telemetry
