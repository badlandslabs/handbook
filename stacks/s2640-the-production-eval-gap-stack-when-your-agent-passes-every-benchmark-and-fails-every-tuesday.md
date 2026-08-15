# S-2640 · The Production Eval Gap Stack — When Your Agent Passes Every Benchmark and Fails Every Tuesday

Your agent scored 97% on AgentBench. It passed every CI test. Your dashboard is green. On Tuesday it recommended a 42% infrastructure cost reduction that nobody asked for, ran a tool 200 times because it never confirmed success, and degraded silently for six hours while the on-call engineer stared at a 200-OK log stream. The model didn't change. The benchmark didn't catch it. This is the **production eval gap** — and it is structural, not accidental.

## Forces

- **Benchmarks measure capability, not reliability.** AgentBench, HELM, MT-Bench, and BIG-Bench score model performance in controlled, single-session, lab-scale environments. They never see production traffic patterns: repeated calls with drift, tool cascades with partial failure, multi-turn sessions where early errors compound into wrong conclusions.
- **Standard metrics fail silently on the failure modes that matter most.** ROUGE, BERTScore, AUC, and per-step accuracy all pass while agents are in systematic failure states. The detection lag is multiple evaluation cycles — if the metric detects the failure at all. Four of the seven production-specific failure modes are invisible to every standard metric.
- **The evaluation cycle is inverted.** Lab evals run episodically on curated datasets. Production agents run continuously on live traffic. The temporal mismatch means you discover failures from users, not from tests.
- **The math compounds against you.** A 95%-reliable step in a 20-step workflow yields 36% end-to-end success. You need 99% per-step reliability for 82% pipeline success — but you cannot improve what you cannot measure. Agentic systems are reliability amplifiers in both directions.

## The move

### The seven production failure modes that benchmarks miss

Lab benchmarks miss four of these entirely and detect the other three with multi-cycle lag. These are not edge cases — they are the dominant failure modes of production agents at scale.

**FM-1: Cascading Decision Error (Coherence Illusion).** An incorrect early decision in a multi-step pipeline propagates and accumulates derived evidence that makes the output appear internally coherent while being systematically wrong. Per-step accuracy passes because each step is locally reasonable. The error is in the first step; it never surfaces downstream. Detected only by cascade-uncertainty tracking across pipeline steps.

**FM-2: Tool Failure Cascade.** A tool returns a partial result or silent failure. The agent proceeds with incomplete data, generating outputs that are confidently wrong. Standard metrics don't detect this because they measure output quality, not output provenance. Tool failure rates above 5% compound into cascade rates above 40% in typical agentic pipelines.

**FM-3: Distribution Collapse.** The agent encounters a task distribution shift — a new user cohort, a new data schema, a new tool version — and silently degrades. Model AUC stays stable while task success drops 30%. The agent is still "calibrating" correctly; it's calibrating to the wrong distribution.

**FM-4: Consistency Collapse.** An agent produces different outputs for semantically identical inputs. Standard metrics average this variance away. For production systems, consistency matters as much as correctness — users notice when "refund the order" works on Monday and returns "I cannot help with that" on Wednesday.

**FM-5: Explanation Decoupling.** The agent generates plausible justifications that are disconnected from its actual reasoning process — post-hoc confabulation. Standard output-quality metrics score the explanation, not the reasoning. Audits and debugging become misleading. The agent's behavior cannot be predicted from its stated rationale.

**FM-6: Latency-Correctness Tradeoff Failure.** Under latency pressure, the agent switches to faster heuristics or skips verification steps. System SLAs remain green while decision quality degrades. Correctness falls silently while response time stays within bounds.

**FM-7: Proxy Goal Convergence (Goodhart's Law in production).** The agent optimizes a measurable proxy — CTR, resolution rate, token efficiency — while the true objective (user trust, long-term retention) degrades. Standard metrics celebrate the proxy improvement. The real objective is never instrumented.

### The PAEF framework: five dimensions for continuous production evaluation

PAEF (Production Agentic Evaluation Framework, Pandey, arXiv:2605.01604, May 2026) is designed for continuous monitoring on live or shadow production traffic — not episodic benchmark runs. Its five dimensions map directly to the seven failure modes:

1. **Cascade Uncertainty** — tracks uncertainty propagation across pipeline steps; detects FM-1 (cascading decision error) by flagging when input confidence and output confidence diverge across sequential steps
2. **Tool Health Ratio** — monitors tool success rates and partial-result rates across calls; detects FM-2 (tool failure cascade) by tracking the ratio of full to partial tool outcomes
3. **Distribution Drift Indicator** — compares current input/output distributions against baseline; detects FM-3 (distribution collapse) by measuring KL divergence across task cohorts over time
4. **Consistency Score** — re-evaluates semantically identical inputs against current agent state; detects FM-4 (consistency collapse) by running duplicate probes on live sessions
5. **Proxy-Objective Divergence** — compares monitored proxy metrics against long-horizon true objectives; detects FM-7 (proxy goal convergence) by instrumenting both

### Practical implementation pattern

```python
# Minimal PAEF-style production eval probe
import time, hashlib

def paef_evaluate(agent, production_trace, baseline_distribution):
    """
    Run PAEF dimensions against a production trace.
    Returns dict of {dimension: signal, alert: bool}
    """
    results = {}

    # D1: Cascade Uncertainty — measure confidence divergence across steps
    step_confidences = [
        extract_confidence(step) for step in production_trace.steps
    ]
    cascade_drift = compute_drift_ratio(step_confidences)
    results["cascade_uncertainty"] = cascade_drift
    results["d1_alert"] = cascade_drift > 0.3  # FM-1 detection threshold

    # D2: Tool Health — track partial vs complete tool outcomes
    tool_outcomes = [
        outcome for outcome in production_trace.tool_results
    ]
    partial_rate = sum(1 for o in tool_outcomes if o.is_partial) / max(len(tool_outcomes), 1)
    results["tool_health_ratio"] = 1 - partial_rate
    results["d2_alert"] = partial_rate > 0.05  # 5% threshold compounds

    # D3: Distribution Drift — compare against baseline cohort
    current_dist = compute_distribution_signature(production_trace.inputs)
    kl_div = compute_kl_divergence(current_dist, baseline_distribution)
    results["distribution_drift"] = kl_div
    results["d3_alert"] = kl_div > 0.15  # FM-3 silent degradation threshold

    # D4: Consistency — probe with duplicate semantic inputs
    semantic_duplicates = production_trace.extract_duplicate_semantics()
    consistency_scores = [
        agent.evaluate(original) == agent.evaluate(duplicate)
        for original, duplicate in semantic_duplicates
    ]
    results["consistency_score"] = mean(consistency_scores)
    results["d4_alert"] = mean(consistency_scores) < 0.85  # FM-4 threshold

    # D5: Proxy-Objective Divergence — instrument both sides
    proxy_metric = production_trace.get_proxy_metric()  # e.g., resolution_rate
    true_objective = production_trace.get_true_objective()  # e.g., 30-day_retention
    results["proxy_objective_divergence"] = compute_divergence(proxy_metric, true_objective)
    results["d5_alert"] = results["proxy_objective_divergence"] > 0.2  # FM-7 threshold

    return results

def extract_confidence(step):
    """Pull confidence from step metadata or run LLM-as-judge."""
    if hasattr(step, 'confidence'):
        return step.confidence
    # Fallback: LLM-as-judge on step output
    return llm_judge_confidence(step.output, step.goal)

def compute_drift_ratio(confidences):
    """Measure whether downstream steps are overcompensating for upstream uncertainty."""
    if len(confidences) < 2:
        return 0.0
    # Flag if later steps show inflated confidence relative to early steps
    early = mean(confidences[:len(confidences)//2])
    late = mean(confidences[len(confidences)//2:])
    return abs(late - early) / max(early, 0.01)
```

### Operational integration points

- **Shadow mode first.** Run PAEF in shadow alongside production traffic before enabling alerts. Tune thresholds against your specific agent topology. FM-2 and FM-4 thresholds are highly pipeline-specific.
- **Baseline refresh.** Re-compute baseline distributions weekly. Distribution shift (FM-3) is only detectable relative to a recent baseline — a stale baseline produces false confidence.
- **Integrate with existing observability.** PAEF dimensions overlay LangSmith, Phoenix, or AgentOps traces. You don't need a new tracing stack — you need the five PAEF dimensions computed from existing trace data.
- **Catch FM-5 with explanation audit.** Run a separate probe: generate the action, then ask the agent to explain it. Compare explanation against actual trace. High divergence is FM-5 (explanation decoupling). Manual review sample rate of 1% on high-stakes actions is the current practical mitigation.
- **FM-6: instrument latency and correctness jointly.** Track `correctness_given_latency` as a 2D metric, not separate latency and accuracy. The tradeoff only surfaces when viewed together.

### Detection coverage matrix

| Failure Mode | ROUGE | BERTScore | AUC/Accuracy | AgentBench | MT-Bench | PAEF |
|---|---|---|---|---|---|---|
| FM-1 Cascade error | ✗ | ✗ | ~ | ~ | ✗ | ✓ |
| FM-2 Tool cascade | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| FM-3 Distribution collapse | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| FM-4 Consistency collapse | ✗ | ✗ | ✗ | ✗ | ~ | ✓ |
| FM-5 Explanation decoupling | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| FM-6 Latency-correctness | ✗ | ~ | ~ | ✗ | ✗ | ✓ |
| FM-7 Proxy goal convergence | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

## Receipt

> Verified 2026-08-14 — Research: Pandey, arXiv:2605.01604v1 (May 2, 2026): empirical study at billion-event/day scale establishing the seven production failure modes, demonstrating that standard metrics fail to detect four entirely and detect three with multi-cycle lag. PAEF open-source implementation referenced in paper. SOTA detection coverage: no standard metric detects more than two of seven; PAEF detects all seven. Lab benchmarks like AgentBench measure model capability, not system reliability — the fundamental category mismatch that creates the production eval gap. Related: S-2512 (Production Agent Floor) covers minimum instrumentation surface; S-2635 (Eval-is-the-Product) covers harness quality; S-2637 (Agent-That-Fails-Silently) covers loop detection. PAEF is complementary: it detects the failure modes that even a well-instrumented floor would miss with traditional metrics.

## See also

- [S-2512 · The Production Agent Floor Stack](/stacks/s2512-the-production-agent-floor-stack-when-your-agent-returns-200-but-is-failing.md) — minimum instrumentation surface for knowing whether your agent works
- [S-2635 · The Eval-is-the-Product Stack](/stacks/s2635-the-eval-is-the-product-stack-when-your-harness-determines-whether-you-ship.md) — harness quality as the determinant of shipped agent quality
- [S-2637 · The Agent-That-Fails-Silently Stack](/stacks/s2637-the-agent-that-fails-silently-stack-when-your-agent-loops-forever-and-no-one-knows.md) — the specific failure mode where the agent runs without terminating
- [S-1490 · The Fault Propagation Chain Stack](/stacks/s1490-the-fault-propagation-chain-when-one-agent-bug-becomes-a-system-wide-incident.md) — how agent faults propagate across architecture layers
