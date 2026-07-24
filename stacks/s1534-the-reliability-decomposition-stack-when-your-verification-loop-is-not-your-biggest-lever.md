# S-1534 · The Reliability Decomposition Stack — When Your Verification Loop Is Not Your Biggest Lever

You added a verification loop. You calibrated your judge. You run pass@k curves in CI. Your agent is still failing at 35% of hard tasks, and you don't know why. The uncomfortable answer: you may have been optimizing the wrong component. Reliability in production agents comes from four places — and the verification loop is usually the smallest one.

## Situation

Your team spent three weeks building an Execute → Observe → Compare → Correct verification loop. It works. Your agent now catches its own mistakes 70% of the time. But overall reliability barely moved — from 61% to 64% on your hardest benchmark. Meanwhile, the same evaluation shows that enabling a specialist model router and improving scaffolding would move the needle by 10× more. This is the reliability decomposition problem: knowing where your agent's reliability actually comes from, and how much each component contributes to the final score.

## Forces

- **Verification loops are visible; scaffolding contributions are invisible.** A verification loop produces logs, metrics, and a visible quality gate. Scaffolding changes — better prompt structures, smarter routing logic, improved context windows — produce diffuse improvements that are hard to attribute. Teams invest in what they can measure, not what moves the needle most.
- **Specialist models compound with scaffolding, not replace them.** Adding a Haiku-classifier + Sonnet-coder + Opus-reasoner trio sounds like a routing trick. In practice, the routing decision only pays off when scaffolding (the control flow around it) is also right. A good specialist router with poor scaffolding underperforms a mediocre router with excellent scaffolding.
- **Cross-benchmark variance hides the decomposition.** An agent that scores 88% on one benchmark and 52% on another is not inconsistent — it's revealing that different benchmarks stress different components. Your hardest tasks may be failing not because of the model or the verification loop, but because routing decisions on novel inputs are being made without enough context.
- **The isolated verification contribution is small but positionally decisive.** Across multiple benchmarks, verification loops contribute +1.5pp in isolation. But they concentrate their gains exactly where everything else fails — at the top of the score distribution. Killing verification to save cost is a false economy; over-investing in it while neglecting scaffolding is a different false economy.

## The Move

Decompose your agent's reliability into four independent components. Measure each in isolation. Allocate engineering effort proportionally.

### The Four Reliability Sources

| Component | What It Does | Reliability Contribution | Cost |
|-----------|-------------|------------------------|------|
| **Scaffolding** | Control flow, error handling, state management, tool orchestration | **Highest** (primary driver) | Engineering time |
| **Routing / Specialist Models** | Task → model assignment, cost-quality tradeoff | **High** (multiplicative with scaffolding) | Inference + routing logic |
| **Specialist Models** | Domain-specific models for classification, code, reasoning | **Moderate** (task-dependent) | Per-token cost |
| **Verification Loops** | Execute → Observe → Compare → Correct | **Small isolated, positionally decisive** | Latency + inference cost |

### The Decomposition Experiment

Run a controlled ablation across all four components on your hardest benchmark:

```python
from dataclasses import dataclass
from typing import Callable, Any
import numpy as np

@dataclass
class AblationResult:
    component: str
    baseline_score: float
    component_score: float
    isolated_contribution_pp: float  # percentage points

def decompose_reliability(
    agent_fn: Callable,
    hard_benchmark: list[dict],
    components: list[str] = ["scaffolding", "routing", "specialist", "verification"],
) -> list[AblationResult]:
    """
    Measure isolated reliability contribution of each component.
    
    Run each component in isolation against the same benchmark.
    Baseline = all components disabled.
    Component score = all EXCEPT this component disabled.
    """
    results = []
    baseline = evaluate(agent_fn, hard_benchmark, disable_all=True)
    
    for component in components:
        # Disable all except this component
        enabled = {component}
        score = evaluate(agent_fn, hard_benchmark, enabled_components=enabled)
        contribution = (score - baseline) * 100  # percentage points
        
        results.append(AblationResult(
            component=component,
            baseline_score=baseline,
            component_score=score,
            isolated_contribution_pp=round(contribution, 2),
        ))
        
    # Full system score
    full_score = evaluate(agent_fn, hard_benchmark, disable_all=False)
    
    # Non-additive interaction effects
    interactions = {
        "scaffolding × routing": full_score - sum(r.isolated_contribution_pp for r in results) - baseline,
    }
    
    return results, full_score, interactions

# Example output (illustrative — actual numbers from Leni eval):
# component='scaffolding',  isolated_contribution=+18.3pp
# component='routing',       isolated_contribution=+11.7pp  
# component='specialist',    isolated_contribution=+7.2pp
# component='verification',  isolated_contribution=+1.5pp
# interactions['scaffolding × routing'] = +6.1pp (multiplicative)
# full_score = 34.8pp above baseline
```

### The Proportionality Rule

After decomposition, apply the **10× rule**: if scaffolding contributes 10× more than verification in isolation, invest 10× more engineering time in scaffolding improvements. Verification is still worth doing — its position at the top of the distribution (where other components fail) makes it irreplaceable for high-stakes tasks. But it should be the last component you optimize, not the first.

### Routing as Multiplier, Not Additive

Do not treat routing as an independent reliability source. Leni's cross-benchmark data shows routing and scaffolding interact multiplicatively — the combined effect is larger than the sum of parts. This means:

1. Improve scaffolding first.
2. Add routing only when scaffolding is solid.
3. Treat routing gains as scaffolding-dependent: a mediocre scaffold with good routing = unreliable. A good scaffold with mediocre routing = unreliable. Both need to be above a minimum threshold.

## Receipt

> Receipt pending — 2026-07-23. Ablation experiment requires a production agent with independently disableable components. Run with a representative hard-benchmark (SpreadsheetBench or equivalent task suite). Key benchmark data sourced from Leni Inc. arXiv:2607.17044v1 (July 2026), evaluating a production business analyst agent across multiple benchmarks.

## See also

- [S-846 · The Reliability Surface Stack](stacks/s846-the-reliability-surface-stack-when-90-percent-passes-are-lying-to-you.md) — R(k,ε,λ) evaluation framework; complementary to decomposition (measure the surface, then decompose it)
- [S-1039 · The Specialist Router Stack](stacks/s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — routing as cost-quality lever; this entry covers its reliability contribution, not its cost contribution
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-when-inline-verification-at-production-scale-is-not-optional.md) — the Execute → Observe → Compare → Correct loop; see this entry for the verification component in isolation
- [S-1261 · The Confidence Calibration Stack](stacks/s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — predictability dimension; the fourth reliability dimension not covered by the decomposition experiment
