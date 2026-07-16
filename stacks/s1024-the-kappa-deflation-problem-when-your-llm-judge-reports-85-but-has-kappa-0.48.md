# [S-1024] · The Kappa Deflation Problem

*When your LLM judge reports 85% accuracy — but its chance-corrected reliability is κ ≈ 0.48. Every team using LLM-as-judge without computing Cohen's κ is flying blind.*

You spend three weeks building an LLM-as-judge eval pipeline. The judge scores your agent at 87% on a 500-item golden set. You ship it as your production quality gate. Six weeks later, your agent's real-world accuracy has dropped 23 points — and the judge still reports 85%. This is not a model degradation problem. It is a measurement problem that was there from day one. The 87% was always a fiction.

The gap between exact-match agreement and chance-corrected Cohen's κ is not a rounding error. It is a systematic inflation of 33–41 percentage points across every major judge provider — a finding from the largest systematic evaluation of LLM-as-judge to date: 21 judges, 9 providers, 3 benchmarks, 118 runs, approximately 541,000 individual judgments (Norman, Rivera & Hughes, arXiv:2606.19544, June 2026). The percentage your dashboard shows is not the number you should trust.

## Forces

- **Reliability without validity is invisible.** A judge can be internally consistent — same input, same score — while being systematically wrong about what "good" means. Exact-match agreement measures only the first property.
- **The compounding agent loop amplifies judge error.** If your agent uses a judge for self-correction, and the judge has kappa deflation, every correction is downstream of a measurement artifact. Errors don't average out — they propagate.
- **Judges are self-preferential.** When the judge and the agent share a provider or model family, agreement inflates by 8–12 pp. Cross-family judging is not a nice-to-have; it is the only way to get an honest signal.
- **Single-run evaluation is unreliable.** LLM outputs have inherent stochasticity. One eval run tells you what the judge said once — not whether the judge is stable. Test-retest consistency is a separate dimension from human agreement.
- **The eval gap compounds agentic failures.** A judge used as a production gate (reject below score X) amplifies kappa deflation into actual task failures: good agents get rejected, mediocre agents pass.

## The move

### 1. Use Cohen's κ as the primary metric — not agreement percentage

Cohen's κ corrects for chance agreement: `κ = (pₒ − pₑ) / (1 − pₑ)`. Exact-match agreement pₒ overstates κ by 33–41 pp on MT-Bench across all providers. A judge reporting "85% agreement" typically has κ ≈ 0.48 — moderate, not near-perfect.

**κ interpretation thresholds:**

| κ range | Signal | Action |
|---------|--------|--------|
| < 0.40 | Poor | Do not use; find root cause |
| 0.40–0.60 | Moderate | Valid for high-volume/low-stakes only |
| 0.60–0.75 | Good | Valid for most production uses |
| > 0.75 | Very good | High-stakes gatekeeper |

These are stricter than the Landis-Koch "substantial" threshold of 0.61. For agent quality gates, treat κ < 0.60 as unreliable.

### 2. Validate with a golden set of 50–200 human-labeled items

Minimum viable golden set for κ estimation: 50 items. For stable κ estimates with tight confidence intervals: 150–200 items. Golden items should span difficulty levels and include edge cases where your agent is known to struggle.

```
For each golden item:
  1. Obtain human label (ground truth: pass/fail, score, or preference)
  2. Run judge independently
  3. Compute κ across all items
  4. Report: κ, 95% CI, pₒ, pₑ
```

Never report only pₒ. The gap between pₒ and κ is the diagnostic.

### 3. Measure test-retest reliability — judges are stochastic

Run the judge on the same 50-item golden set twice, independently. Compute agreement between the two judge runs (not against humans — this is internal stability). If the judge's two runs disagree on >10% of items, the judge is too stochastic for single-run eval gating.

```
Test-retest reliability check:
  Run 1: [score₁, score₂, ..., score₅₀]
  Run 2: [score'₁, score'₂, ..., score'₅₀]
  Retest κ (against itself) should be > 0.80 for production gates
  If < 0.80: increase temperature consistency or use ensemble
```

### 4. Detect and correct self-preference bias

Cross-family judging: evaluate the judge using outputs from a *different* model provider. Self-preference inflates agreement by 8–12 pp when judge and agent share a provider. For a real signal, always pair the judge against an out-of-family agent.

```
Self-preference audit:
  Judge A (provider X) + Agent from provider X  → κ₁
  Judge A (provider X) + Agent from provider Y  → κ₂
  κ₁ − κ₂ = self-preference inflation (~8–12 pp is typical)
  Use κ₂ as the real reliability estimate
```

### 5. Monitor κ continuously in production — not just at onboarding

Judge reliability drifts with: model version upgrades, golden set staleness, distribution shift in agent outputs, prompt changes to the judge itself. Establish a rolling κ monitor on a held-out sample of 20–30 golden items run weekly.

```
Rolling κ monitoring:
  Weekly: sample 25 held-out items
  Compute κ against golden labels
  Alert threshold: κ drops > 0.05 pp from baseline
  Alert threshold: κ crosses below 0.60
  On alert: freeze quality gates, re-validate judge
```

### 6. Use multi-judge voting for high-stakes gates

A single judge run is unreliable. Three independent judges with majority voting improve reliability measurably — but only if the judges are from different providers (same-provider judges are not independent). Budget for 3× the eval cost in high-stakes paths.

```
Multi-judge high-stakes gate:
  Judge A (provider X) scores item
  Judge B (provider Y) scores item
  Judge C (provider Z) scores item
  Accept: ≥ 2/3 judges above threshold
  Confidence: only meaningful if judges are cross-family
```

## See also

- [S-451 · LLM-as-Judge Failure Modes: The Echo Chamber Problem](s451-llm-as-judge-failure-modes.md) — self-preference, position bias, and capability mirroring as systematic judge biases (complements kappa deflation; together they explain *why* κ deflates)
- [S-987 · The Agent Evaluation Stack: When You Can't Tell If Your Agent Is Actually Working](s987-the-agent-evaluation-stack-when-you-cant-tell-if-your-agent-is-actually-working.md) — rolling eval, probe sets, and golden trace management as the infrastructure layer kappa deflation lives inside
- [S-202 · LLM-as-Judge Evaluation Harness](s202-llm-as-judge-harness.md) — technical harness design for running judge pipelines (the operational home for κ computation)
