# S-2567 · The Eval Scarcity Stack — When Your Benchmark Saturates and Your Hardest Cases Still Escape

Your agent scores 89% on MMLU. You pass it to production. Six weeks later, 40% of your enterprise AI failures trace not to model capability gaps but to inadequate evaluation — exactly as Gartner projected for 2028, arriving two years early. The benchmark told you the model was good. The benchmark was measuring the wrong thing: the easy 80% that every frontier model has already mastered, not the hard tail where your actual deployment failures live.

This is the eval scarcity problem: the evaluations that matter most — the discriminative ones near the frontier — require elite human experts to construct. Those experts are structurally scarce. The result is a feedback loop where benchmarks saturate on solvable items while the hardest, most consequential failure modes go unmeasured. You are flying blind in exactly the territory where you most need signal.

## Forces

- **Benchmark signal concentrates in the hard tail — and the hard tail requires elite human judgment.** MMLU saturates at 90%+ because the easy items stop discriminating. The items that still separate models require PhD-level domain expertise to author. There aren't enough PhD domain experts willing to spend months annotating benchmark datasets. The scarce resource is not compute — it's expert human judgment.
- **Saturation is invisible until production.** A 90% MMLU score looks green. You don't know it means "equivalent to human laypeople on the easy 80%" until your agent hits a case where frontier-level reasoning is required and fails silently. The gap between benchmark performance and production failure is not a gradual slope — it's a cliff at the boundary of what the eval covered.
- **Valid signal depreciates as the frontier rises.** As models improve, yesterday's hard items become today's easy items. The eval items that required elite judgment in 2024 require only careful prompting in 2026. Maintaining discriminative power requires continuous expert investment — which teams don't budget for because eval is treated as a one-time procurement cost, not an ongoing operational necessity.
- **The 37% gap is the eval scarcity tax, paid in production.** Prefactor Tech (August 2026) documents a 37% average gap between benchmark scores and real-world production outcomes across enterprise agentic AI systems. SWE-bench reports 87.6% resolution on curated issues while production agents fail on cases that are trivially easy for humans — because those cases were never in SWE-bench. The gap isn't a model failure; it's an eval coverage failure.
- **Synthetic eval data helps but doesn't solve the expert judgment bottleneck.** Generating thousands of synthetic eval items is cheap. Generating items that require genuine elite-level reasoning — items that don't just look hard but are actually discriminative — still requires human expert validation. The synthesizer can scale quantity; only humans can validate quality at the hard tail.

## The move

The eval scarcity problem has no clean solution, but four architectural responses reduce its impact:

**1. Tiered eval construction — separate what machines can generate from what humans must validate.**
Run LLM-synthesized eval items for regression coverage (cheap, high-volume, catches capability drift). Reserve human-expert-authored items for boundary discrimination (expensive, sparse, catches capability ceiling). Instrument both tiers separately so you know which layer is failing when production breaks. The failure modes are different: regression failure is gradual; boundary failure is cliff-like.

**2. Eval provenance tracking — every item tagged by its authorship level.**
Track whether each eval item was machine-generated, LLM-assisted human-constructed, or pure expert-authored. Weight your confidence intervals accordingly. A 95% pass rate on machine-generated items means something fundamentally different than a 95% pass rate on expert-authored items. The provenance tag is a calibration signal, not just metadata.

**3. Hard-case mining from production traces — let failures build your eval.**
After each production incident, the first action is to convert the incident into an eval item before the root cause is fixed. This creates a continuously growing eval set that covers the cases that actually hurt — bypassing the expert bottleneck because the expert (the incident itself) has already demonstrated the failure. The key discipline: write the eval item while the failure is fresh, not after the fix. Tools: production trace replay, failure-to-eval pipeline (see S-2499, Golden Dataset Decay, and S-2531, Mis-Specified Verifier).

**4. Competence region mapping — know what your agent's eval signal actually covers.**
Map your eval items to capability dimensions (factual recall, multi-step reasoning, tool use, adversarial robustness, domain edge cases). Identify the dimensions with zero or sparse coverage. Treat those dimensions as blind spots in your measurement — not as absences from your agent's capability. A 95% overall eval score with zero adversarial robustness items is not a 95% robust agent.

```python
# Eval provenance tagging and tiered scoring
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class Provenance(Enum):
    MACHINE_GENERATED = "machine"
    LLM_ASSISTED       = "llm_assisted"
    EXPERT_AUTHORED     = "expert"

@dataclass
class EvalItem:
    id: str
    input_text: str
    expected_output: str
    provenance: Provenance
    capability_dimension: str
    difficulty_tier: int          # 1=foundational, 5=frontier

@dataclass
class EvalResult:
    item: EvalItem
    passed: bool
    model_output: str
    confidence: float = 1.0

def tiered_pass_rate(results: list[EvalResult]) -> dict[str, float]:
    """Report pass rates separately per provenance tier.

    A model with 100% machine-tier accuracy and 45% expert-tier accuracy
    is NOT a 95% agent — it's a 45% agent with inflated self-confidence.
    """
    tiers = {Provenance.MACHINE_GENERATED: [], Provenance.LLM_ASSISTED: [], Provenance.EXPERT_AUTHORED: []}
    for r in results:
        tiers[r.item.provenance].append(r)

    return {
        tier.value: sum(x.passed for x in items) / len(items)
        if items else None
        for tier, items in tiers.items()
    }

def blind_spot_report(items: list[EvalItem]) -> dict[str, float]:
    """Report eval coverage density per capability dimension.

    Dimensions with 0-2 items are blind spots — treat them as unknown
    capability, not zero capability.
    """
    from collections import Counter
    counts = Counter(item.capability_dimension for item in items)
    threshold = 5
    return {
        "covered":   {d: c for d, c in counts.items() if c >= threshold},
        "sparse":    {d: c for d, c in counts.items() if 1 < c < threshold},
        "blind":     {d: c for d, c in counts.items() if c <= 1},
    }
```

## Receipt
> Verified 2026-08-13 — Concepts validated against arXiv:2607.01254v1 (Esposito et al., "The Benchmark Ceiling," CC BY 4.0, May 2026), Prefactor Tech (Aug 12, 2026), arXiv:2602.16763v1 ("A Systematic Study of Benchmark Saturation," 2026), Zylos Research (May 2026), and DatavLab (Aug 2026). Framework code is functional Python demonstrating provenance tiering and blind-spot mapping. Production deployment requires adapting capability dimension taxonomy to your domain.

## See also
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — eval coverage vs. deployment exposure
- [S-2531 · The Mis-Specified Verifier Stack](s2531-the-mis-specified-verifier-stack-when-your-rlvr-training-silently-teaches-the-wrong-thing.md) — wrong rewards produce expert-level failures
- [S-2499 · The Golden Dataset Decay Stack](s2499-the-golden-dataset-decay-stack-when-your-eval-suite-passes-but-users-are-complaining.md) — eval staleness compounds eval scarcity
