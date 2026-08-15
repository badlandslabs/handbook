# S-2669 · The Reliability Surface Stack — When Your Agent Scores 97% and Fails One-Third of the Time in Production

Your agent scores 96.9% on your eval suite. You ship it. Two weeks later, 34% of production runs are failing — not on exotic inputs, but on semantically identical queries with different phrasing, a rate-limited API call at step 4, or a partial JSON response mid-execution. The benchmark wasn't lying. It was measuring the wrong thing. This is the reliability surface: a three-dimensional space that single-run pass rates cannot capture.

## Forces

- **pass@1 is a lie told with numbers.** Agents achieving 60% pass@1 on τ-bench exhibit only ~25% consistency across eight trials. A 97% single-run score tells you the agent can succeed — it says nothing about whether it will succeed when the API rate-limits at step 3, the customer uses "book" instead of "reserve", or the model temperature produces a slightly different token that changes the tool call argument.
- **Production is multi-dimensional stress.** Your agent faces three independent stressors simultaneously: inconsistent execution (same input, different result), task perturbations (semantically equivalent inputs the agent has never seen), and infrastructure failures (timeouts, rate limits, partial responses). Existing benchmarks probe zero or one of these axes. Production hits all three.
- **Simple architectures win under stress.** ReAct agents outperform Reflexion architectures when both are evaluated under combined fault and perturbation load. Complexity that helps in ideal conditions becomes a liability when conditions degrade. This is counter-intuitive and underreported.
- **Cost and reliability are not a trade-off.** Gemini 2.0 Flash achieves reliability comparable to GPT-4o at 82× lower cost in fault-injection tests. Expensive frontier models don't automatically produce more reliable agents.

## The move

Stop evaluating agents with single-dimension pass rates. Instead, characterize your agent's **Reliability Surface**: R(k, ε, λ).

### Dimension 1 — Consistency: pass@k

Run the same task k times. Report pass@k, not pass@1.

- pass@1 = single trial, your current default
- pass@3 = probability of success across 3 independent trials
- pass@8 = what τ-bench uses; reveals agents that "can" but don't consistently

For a 10-step workflow at 95% per-step reliability: 0.95^10 = 59.9%. Run it once and you see ~60%. Run it 8 times and take pass@8, and you see the distribution. Plot it. The tail matters.

### Dimension 2 — Robustness: perturbation ε

Define **Action Metamorphic Relations** — transformations of the input that should produce the same end state.

- "book a flight" → "reserve a flight" → "I need to fly there on the 15th"
- "cancel order #12345" → "undo order 12345" → "order 12345 shouldn't have gone through"
- "change my address" → "update shipping address" → "my address is wrong"

For each task, generate ε-level perturbation families (ε=0 is clean, ε=0.2 is moderate paraphrase/format shift, ε=0.5 is heavy rephrasing). Measure pass rate at each level. ReliabilityBench found agents dropping from 96.9% at ε=0 to 88.1% at ε=0.2 — an 8.8% decline from perturbations alone.

### Dimension 3 — Fault Tolerance: λ

Inject infrastructure failures systematically. The four fault categories from ReliabilityBench:

1. **Transient timeouts** — tool call hangs for 15-30s then succeeds
2. **Rate limits** — HTTP 429 with Retry-After header
3. **Partial responses** — tool returns truncated JSON or partial text
4. **Schema drift** — tool returns unexpected fields or changed types

Vary λ from 0 (no faults) to 1 (faults on every tool call). Rate limiting is consistently the most damaging fault in ablation studies. Map your agent's R(8, 0.2, λ) curve.

### Build the surface, not the score

```python
# Three-dimensional reliability surface
from dataclasses import dataclass
from typing import Callable
import numpy as np

@dataclass
class ReliabilitySurface:
    """R(k, ε, λ) — the 3D reliability characterization."""
    pass_k: Callable[[int], float]      # consistency: pass rate vs k trials
    robustness: Callable[[float], float]  # robustness: pass rate vs perturbation ε
    fault_tolerance: Callable[[float], float]  # tolerance: pass rate vs fault intensity λ

    def sample(self, k: int, epsilon: float, lambda_: float) -> float:
        """Estimate R(k, ε, λ) at a point on the surface."""
        base = self.pass_k(k)
        robust_factor = self.robustness(epsilon)
        fault_factor = self.fault_tolerance(lambda_)
        return base * robust_factor * fault_factor

    def production_readiness(self, k: int = 8, epsilon: float = 0.2,
                              lambda_: float = 0.3) -> float:
        """R(8, 0.2, 0.3) as a production readiness estimate."""
        return self.sample(k, epsilon, lambda_)

# Example: If pass@8 = 0.72, robustness at ε=0.2 = 0.92, tolerance at λ=0.3 = 0.85
# R(8, 0.2, 0.3) ≈ 0.72 × 0.92 × 0.85 ≈ 0.56 — not 96.9%
```

### Chaos engineering for agents

Implement fault injection as a production hardening step:

```bash
# Agent Chaos framework (reaatech/agent-chaos)
agent-chaos inject \
  --faults timeout,rate_limit,partial_response,schema_drift \
  --intensity 0.3 \
  --tool-calls payment_api,geocoding,email_send \
  --episodes 100

# AgentChaos (IntelligentDDS/AgentChaos) — LLM API layer fault injection
python -m agentchaos run \
  --profile production_pressure \
  --perturbation-level 0.2 \
  --fault-intensity 0.3 \
  --k 8
```

### Decision thresholds

- R(1, 0, 0) > 0.90 → agent is capable in ideal conditions
- R(8, 0, 0) > 0.80 → agent is consistent across repeated runs
- R(8, 0.2, 0) > 0.70 → agent is robust to input variation
- R(8, 0.2, 0.3) > 0.60 → agent is production-ready under real conditions

If your agent scores 97% pass@1 but R(8, 0.2, 0.3) = 0.34, you do not have a 97% reliable agent. You have an agent that can succeed 97% of the time under ideal conditions. That is a fundamentally different product.

## Receipt

> Verified 2026-08-15 — arXiv:2601.06112 (Gupta, Jan 2026): ReliabilityBench across 1,280 episodes, 4 domains, 2 models, 2 architectures. Key findings: agents 96.9% at ε=0 drop to 88.1% at ε=0.2 (8.8% perturbation penalty). Rate limiting causes largest fault-tolerance degradation (2.5% below mixed baseline in ablations). ReAct outperforms Reflexion under combined stress. Gemini 2.0 Flash achieves comparable reliability to GPT-4o at 82× lower cost. AgentChaos (IntelligentDDS/AgentChaos, GitHub) implements LLM API-layer fault injection. Agent Chaos (reaatech/agent-chaos, GitHub) provides middleware-based fault injection with circuit-breaker and fallback-tree validation. Tian Pan (tianpan.co, Apr 2026): LLM API calls fail 1–5% per-call in production; a 10-20 tool-call workflow sees meaningful failure probability on every run. Agent Belt (jfrog/agent-belt, GitHub): pass^k variance across trials as reliability pin.

## See also

- [S-1000 · The Eval Gap Stack](s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — single-run eval lies, systematic overestimation
- [S-1015 · The Stability Gradient](s1015-the-stability-gradient-when-your-agent-works-once-and-fails-twice.md) — variance across trials, tool-call compounding
- [S-2667 · The Agent Eval Loop Stack](s2667-the-agent-eval-loop-stack-when-your-benchmark-passes-but-production-fails.md) — layered eval architecture for production readiness
- [S-2655 · The Agentic Chaos Engineering Stack](s2655-the-agentic-chaos-engineering-stack-when-your-production-test-environment-lies.md) — fault injection patterns for agent systems
