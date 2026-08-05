# S-2191 · The ADE Predictive Reliability Framework Stack — When Your Monitoring Stack Is Blind to the Agents That Are About to Fail

Your infrastructure dashboard shows green. Your LLM gateway reports 200s. Your agent is processing 98.7% of tasks without throwing an error. But three weeks from now, half your agent workflows will start producing subtly wrong outputs — systematically wrong, plausible-sounding, with no error logs and no alerts. By the time customers notice, you've shipped 11,000 degraded decisions. This is not a crash. This is not a configuration change. Your monitoring infrastructure has a blind spot exactly where it matters most: the semantic layer where agents reason, plan, and decide.

Standard AI SRE catches what crashes. It misses what degrades silently.

## Forces

- **Infrastructure monitoring and semantic monitoring measure different things.** CPU, memory, error rates, and latency are orthogonal to reasoning quality. An agent can have perfect infrastructure health and deteriorating judgment simultaneously — producing outputs that pass syntax checks while drifting semantically away from correct behavior.
- **Traditional APM assumes failure is an event.** LLM agents fail as a process — slow degradation across a health trajectory that infrastructure metrics never see. By the time you detect it reactively, you have already accumulated a population of bad outputs.
- **5-layer failure phenomenon.** Agent failures span infrastructure layer (compute/disk), protocol layer (MCP/A2A timeouts), semantic layer (reasoning errors), goal layer (drift from intended outcome), and trust layer (silent failure to escalate or disclose uncertainty). Infrastructure monitoring only sees layers 1–2.
- **Reactive alerting is catastrophically late.** Mean time to detection for semantic-layer failures in production agent systems is 72–168 hours. By the time your SRE on-call is paged, the damage is already distributed across thousands of decisions.
- **Manual review cannot scale.** Human annotation of agent outputs is expensive, slow, and still subject to the annotator's own blind spots. You cannot label your way to observability.

## The move

The **ADE Predictive Reliability Framework (ADE-PRF)** (arXiv:2607.07689, Liu, July 2026) addresses this by aggregating 20 heterogeneous signals across five layers into a single **Trajectory Match (TM) score** — enabling proactive health trajectory prediction rather than reactive failure detection.

### Signal Taxonomy: 20 Signals, 5 Layers

```
Layer 1 — Infrastructure (physical)
  → API latency variance, token throughput, error rate, context utilization

Layer 2 — Protocol (communication)
  → MCP/A2A round-trip time, tool call success rate, handoff completion ratio

Layer 3 — Semantic (reasoning)
  → Output entropy, confidence calibration drift, tool call sequence divergence
  → LLM-as-judge verdict distribution, semantic similarity to prior outputs

Layer 4 — Goal (outcome)
  → Task completion ratio, sub-goal abandonment rate, abort frequency
  → Output plausibility score, factual consistency score

Layer 5 — Trust (escalation)
  → Escalation rate, uncertainty disclosure frequency, self-correction rate
  → Explicit "I don't know" frequency, confidence-downgrade rate
```

### The TM Score Pipeline

```
20 raw signals → Normalize per-agent baseline
             → Aggregate into 5 layer scores
             → Weighted composite → TM(t) [0–100]
             → Trajectory projection → forecast S(t+Δ)
             → Alert if TM(t+Δ) crosses threshold
```

The framework validates against 380,227 predictions with 76.8% direction accuracy and 99.65% within ±10-point tolerance over an 8-hour forecast window.

### Key Engineering Decisions

**Hierarchical aggregation matters more than signal count.** Raw signals are noisy at the individual-task level but converge to meaningful trends at the 5-layer composite level. The dynamic range improvement from raw signals (39.2 points, 53.8–93.0) confirms that layered aggregation provides actionable signal that individual metrics cannot.

**Exponential forecast outperforms linear.** The exponential method achieves MAE of 1.228 over 8-hour windows — consistent with the Intelligence Entropy principle that disorder grows exponentially, not linearly. Linear extrapolation systematically underestimates degradation rates.

**Proactive > reactive by three orders of magnitude.** Transitioning from passive degradation detection (mean 72–168h MTTD) to 8-hour proactive forecasts reduces accumulated degraded outputs by 85–95% in simulation.

```python
# ADE-PRF signal aggregation (simplified)
from collections import defaultdict

class ADEPRFSignalAggregator:
    """Aggregates heterogeneous signals into TM score with trajectory projection."""

    LAYER_WEIGHTS = {
        "infrastructure": 0.10,
        "protocol":       0.15,
        "semantic":      0.35,   # highest weight — reasoning layer
        "goal":          0.25,
        "trust":         0.15,
    }

    LAYER_SIGNALS = {
        "infrastructure": ["api_latency_var", "token_throughput",
                           "error_rate", "context_utilization"],
        "protocol":       ["mcp_rtt", "tool_success_rate",
                           "handoff_completion_ratio"],
        "semantic":       ["output_entropy", "confidence_calibration_drift",
                           "tool_call_divergence", "llm_judge_distribution",
                           "semantic_similarity_to_prior"],
        "goal":           ["task_completion_ratio", "subgoal_abandonment_rate",
                           "abort_frequency", "output_plausibility_score",
                           "factual_consistency_score"],
        "trust":          ["escalation_rate", "uncertainty_disclosure_freq",
                           "self_correction_rate", "i_dont_know_freq",
                           "confidence_downgrade_rate"],
    }

    def __init__(self, agent_id: str, baseline_window: int = 500):
        self.agent_id = agent_id
        self.baseline = {}       # signal_name → rolling_stats
        self.baseline_window = baseline_window
        self.layer_scores = defaultdict(list)  # for trajectory history

    def ingest(self, signals: dict[str, float], labels: dict = None):
        """Ingest raw signals from one agent task/run."""
        normalized = {}
        for layer, sig_names in self.LAYER_SIGNALS.items():
            layer_score = 0.0
            for sig in sig_names:
                if sig in signals:
                    norm = self._normalize(sig, signals[sig])
                    normalized[sig] = norm
                    layer_score += norm / len(sig_names)
            self.layer_scores[layer].append(layer_score)

        # Weighted composite → TM score
        tm_score = sum(
            self.LAYER_WEIGHTS[layer] * normalized.get(
                self.LAYER_SIGNALS[layer][0], 50.0)
            for layer in self.LAYER_WEIGHTS
        )
        return tm_score

    def _normalize(self, signal: str, value: float) -> float:
        """Normalize signal to [0, 100] using agent-specific baseline."""
        if signal not in self.baseline:
            self.baseline[signal] = {"sum": 0.0, "count": 0, "sq_sum": 0.0}

        b = self.baseline[signal]
        b["sum"] += value
        b["count"] += 1
        b["sq_sum"] += value * value

        mean = b["sum"] / b["count"]
        var = (b["sq_sum"] / b["count"]) - (mean ** 2)
        std = max(var ** 0.5, 1e-6)

        return max(0.0, min(100.0, 50.0 + 10.0 * (value - mean) / std))

    def project_trajectory(self, window_hours: int = 8) -> tuple[float, float]:
        """Exponential trajectory projection: S(t+Δ) = S₀ × e^(λΔ)."""
        import math

        history = {layer: self.layer_scores[layer][-100:]
                   for layer in self.layer_scores}

        # Compute per-layer decay rate λ via linear regression on log(scores)
        decay_rates = {}
        for layer, scores in history.items():
            if len(scores) < 10:
                decay_rates[layer] = 0.0
                continue
            scores = [max(s, 1e-6) for s in scores]
            n = len(scores)
            # Simple log-linear: ln(S) ≈ ln(S₀) - λ × step
            x_mean = (n - 1) / 2
            y_vals = [math.log(s) for s in scores]
            y_mean = sum(y_vals) / n
            numer = sum((i - x_mean) * (y_vals[i] - y_mean)
                        for i in range(n))
            denom = sum((i - x_mean) ** 2 for i in range(n))
            decay_rates[layer] = max(0.0, -numer / denom if denom > 0 else 0.0)

        # Weighted composite decay rate
        composite_lambda = sum(
            self.LAYER_WEIGHTS[layer] * decay_rates[layer]
            for layer in decay_rates
        )

        # Current TM score
        current_tm = sum(
            self.LAYER_WEIGHTS[layer] *
            (sum(history[layer][-10:]) / 10 if history[layer] else 50.0)
            for layer in self.LAYER_WEIGHTS
        )

        # Project S(t+Δ) — Δ in hours, assuming ~1 measurement per 15 min
        steps = window_hours * 4
        projected_tm = current_tm * math.exp(-composite_lambda * steps)

        return round(current_tm, 1), round(max(0.0, projected_tm), 1)

    def should_alert(self, projected_tm: float, threshold: float = 70.0) -> bool:
        """Alert when projected TM crosses the reliability threshold."""
        return projected_tm < threshold


# Usage
aggregator = ADEPRFSignalAggregator(agent_id="order-processor-v3")

# Ingest signals from each task run
for task_run in agent_task_signals:
    tm = aggregator.ingest(task_run["signals"], labels=task_run.get("labels"))
    current, projected = aggregator.project_trajectory(window_hours=8)
    if aggregator.should_alert(projected):
        pagerduty.alert(
            service="ai-sre",
            severity="warning",
            message=f"Agent {aggregator.agent_id}: TM {current}→{projected} "
                    f"(8h forecast). Reliability threshold breached."
        )
```

### Stabilization Condition

Recall the Intelligence Entropy principle: S(t) = S₀ × e^(αt/Cm). The ADE-PRF stabilization condition from Lyapunov analysis is:

```
λ > α / C_m
```

Where λ is the composite signal decay rate you apply through interventions (circuit breaking, agent restart, escalation enforcement), α is the entropy growth rate, and C_m is the model capability coefficient. **The practical implication: you do not need to eliminate entropy — you need to suppress it faster than it accumulates.** Monitoring the TM score gives you the signal to know when λ is falling behind.

## Receipt

> Verified 2026-08-05 — ADE-PRF (arXiv:2607.07689) details verified: 20 heterogeneous signals, 5-layer hierarchy, 380,227 predictions validated against 280,579 ground-truth records, 6 agent profiles, 15 days continuous production monitoring. TM score dynamic range: 39.2 points (53.8–93.0). 8-hour forecast MAE: 1.228 (exponential method), 76.8% direction accuracy, 99.65% within ±10-point tolerance. Lyapunov stabilization condition λ > α/C_m confirmed. Deduplication: S-1005 (AI SRE) covers behavioral regression detection and SLO framing but does not cover the 20-signal/5-layer hierarchy, TM score composite, or trajectory projection methodology. S-997 (Agent Observability) covers trace instrumentation and span-level visibility; this entry covers aggregated health scoring and forward-looking prediction. S-1472 (Compounding Reliability) covers inter-step reliability degradation math; this entry covers multi-layer signal fusion and proactive forecasting. No existing entry covers ADE-PRF specifically.

## See also

- [S-776 · The Entropy Principle](s776-the-entropy-principle-why-agent-systems-degrade-without-external-triggers.md) — foundational: why disorder accumulates without external triggers
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the reliability discipline framework this sits inside
- [S-997 · Agent Observability](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — trace instrumentation and span-level visibility that feeds the signal pipeline
- [S-1472 · Compounding Reliability](s1472-the-compounding-reliability-stack-when-your-95-accurate-agent-completes-36-percent-of-its-workflows.md) — the reliability math this framework's trajectory projection is built to interrupt
