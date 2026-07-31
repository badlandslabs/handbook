# S-1912 · The Latency-Quality Divorce Stack — When Your Agent SLA Is Green But Every Decision Is Wrong

Your real-time decisioning pipeline shows 100% SLA compliance — all requests resolve within the 120ms budget. Your weekly quality review shows that under load, the same pipeline approved transactions that should have been flagged, routed customers to wrong tiers, and made credit decisions that violated policy. Nobody caught it for three weeks. The latency dashboard never fired an alert. The quality dashboard showed gradual drift. The gap between them — that no single tool was designed to close — is the latency-quality divorce.

## Forces

- **Latency budgets are enforced; decision quality is not.** Every SRE team monitors p50/p95/p99 latency. Very few monitor whether decisions made under latency pressure are correct. The infrastructure layer enforces one; the business logic layer monitors the other — but nobody owns the correlation.
- **Degraded inference paths are invisible by design.** When a pipeline skips retrieval enrichment, falls back to a smaller model, or truncates context to meet budget, it still returns a valid response. The system behaves correctly from an infrastructure perspective. The decision is simply wrong.
- **SLA metrics and quality metrics use different dashboards, different owners, and different alerting thresholds.** They are never joined. A load spike that causes latency pressure and silently triggers degraded inference paths produces zero infrastructure alerts — only gradual quality degradation that looks like model drift.
- **Quality degradation under latency pressure is directional and consistent.** Unlike random errors, this failure mode systematically favors fast-but-wrong decisions during exactly the periods (load spikes) when the business is most sensitive to errors.

## The Move

### 1. Instrument the degradation path, not just the outcome

Every fallback path in your inference pipeline — model downgrade, context truncation, retrieval skip, enrichment bypass — must emit a structured signal. Do not rely on decision quality to surface these events. Log them explicitly:

```python
import time, random
from dataclasses import dataclass
from typing import Optional

@dataclass
class InferenceCall:
    request_id: str
    path: str              # "full" | "degraded" | "fallback"
    model_tier: str        # e.g., "frontier" | "mid" | "fast"
    latency_ms: float
    enrichment_depth: int  # how many enrichment steps completed
    context_tokens: int
    outcome: str           # "approved" | "declined" | "review"

# Instrument every call
call = InferenceCall(
    request_id="txn-8841",
    path="degraded",
    model_tier="mid",
    latency_ms=87,
    enrichment_depth=1,     # normally 4; skipped 3 under pressure
    context_tokens=1200,   # normally 4800; truncated
    outcome="approved"
)

# Key: emit the path signal alongside latency
print(f"[INFERENCE] path={call.path} latency={call.latency_ms}ms "
      f"enrichment={call.enrichment_depth}/4 "
      f"context={call.context_tokens} tokens "
      f"outcome={call.outcome}")
```

### 2. Build a joint alerting rule: latency pressure + quality change

The trigger is not "latency > threshold" and not "quality score dropped" — it is the *correlation*:

```python
def check_latency_quality_divorce(
    latency_p95_ms: float,
    latency_budget_ms: float,
    quality_score: float,
    quality_baseline: float,
    degradation_count: int,
    n_decisions: int
) -> dict:
    """Alert when latency pressure correlates with quality drop."""

    # Headroom ratio: how close to the budget
    headroom_ratio = latency_p95_ms / latency_budget_ms

    # Quality delta from baseline
    quality_delta = quality_score - quality_baseline

    # Degradation rate (fraction of calls on fallback paths)
    degradation_rate = degradation_count / max(n_decisions, 1)

    alert = {
        "divorce_detected": False,
        "latency_pressure": headroom_ratio > 0.85,  # >85% of budget
        "quality_eroding": quality_delta < -0.05,   # >5% drop from baseline
        "degradation_rate": degradation_rate,
        "severity": "none"
    }

    # Joint condition: both pressure AND quality erosion AND degraded paths
    if (alert["latency_pressure"]
            and alert["quality_eroding"]
            and degradation_rate > 0.1):
        alert["divorce_detected"] = True
        alert["severity"] = "critical"
    elif alert["latency_pressure"] and degradation_rate > 0.05:
        alert["severity"] = "warning"  # latent risk before quality shows it

    return alert

# Example: SLA green, quality cratering
result = check_latency_quality_divorce(
    latency_p95_ms=112,       # 93% of 120ms budget — SLA green
    latency_budget_ms=120,
    quality_score=0.71,        # baseline was 0.89 — 18% drop
    quality_baseline=0.89,
    degradation_count=847,
    n_decisions=5620
)
# → {"divorce_detected": True, "severity": "critical"}
# Latency SLA: green. Decision quality: critical.
```

### 3. Design fallback paths with explicit quality contracts

Every degraded inference path should have a documented quality contract — what it guarantees and what it sacrifices:

| Path | Trigger | Quality Guarantee | Latency | Decision Impact |
|------|---------|-------------------|---------|-----------------|
| Full | Always | Full enrichment, frontier model | < 120ms | Reference quality |
| Degraded-A | p95 > 100ms | Skip third-party enrichment | < 100ms | Minor accuracy loss on edge cases |
| Degraded-B | p95 > 110ms | Smaller model, full context | < 80ms | 5–8% accuracy reduction on complex cases |
| Fallback | p99 > 115ms | No retrieval, fast model | < 40ms | Approve/refuse only; no nuanced routing |

### 4. Canary test degraded paths continuously

Run a continuous 1% shadow traffic sample through every path — including degraded ones — with known ground truth, so you measure decision quality per path, not just in aggregate:

```python
def shadow_test_degraded_paths(shadow_ratio=0.01):
    """
    Route 1% of production traffic through all paths
    and score decisions against ground truth.
    """
    production_volume = get_production_volume(window_minutes=60)
    shadow_volume = int(production_volume * shadow_ratio)

    results = {}
    for path in ["full", "degraded_a", "degraded_b", "fallback"]:
        shadow_requests = sample_requests(shadow_volume, path=path)
        scores = [evaluate_decision(req, ground_truth) for req in shadow_requests]
        results[path] = {
            "n": len(scores),
            "accuracy": mean(scores),
            "false_negative_rate": mean([1 - s for s in scores if ground_truth_is_positive(req)])
        }

    # Alert if any degraded path accuracy diverges from full path by > threshold
    full_accuracy = results["full"]["accuracy"]
    for path, data in results.items():
        delta = full_accuracy - data["accuracy"]
        if delta > 0.05:  # 5% accuracy gap threshold
            emit_alert(f"Path {path} quality gap: {delta:.1%} below full path")
```

## Receipt

> Verified 2026-07-31 — arXiv:2605.01604 (Pandey, May 2026) documents FM-6 (Silent Correctness Erosion Under Latency Pressure) as a production failure mode operating at O(10⁹) events/day scale. Real-time decisioning pipeline example: 100–150ms SLA budget, under load the pipeline fell back to skipping retrieval enrichment and routing to a simpler model path. SLA metrics remained green. Decision accuracy degraded by 18–22% across a two-week period — undetected until the weekly quality review. Standard metrics (ROUGE, AUC, accuracy) detected the problem only after multiple evaluation cycles; PAEF's latency-correctness correlation dimension detected it within one cycle. No single existing handbook entry addresses this specific failure mode — the latency-quality divorce — as a distinct pattern.

## See also

- [S-1026 · The PAEF Stack](s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — the broader evaluation framework that defines FM-6's detection
- [S-1173 · The Degraded-Mode Agent Stack](s1173-the-degraded-mode-agent-stack-when-your-agent-breaks-the-question-is-how-fast-it-recovers.md) — graceful degradation patterns; complements this by addressing detection
- [S-06 · Model Routing](s06-model-routing.md) — the routing tiers that make degraded paths possible; this entry explains why routing to them under load is the hidden failure
