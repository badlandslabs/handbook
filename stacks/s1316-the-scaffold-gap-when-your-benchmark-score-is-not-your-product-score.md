# S-1316 · The Scaffold Gap — When Your Benchmark Score Is Not Your Product Score

Your vendor scores 87% on SWE-bench. You buy their agent. Your product scores 61%. Nobody lied — the benchmark was real, the model was real. The gap is the scaffold: the evaluation harness around the model that no one puts in the procurement deck.

## Forces

- **Model swaps move the needle by ~1 point.** At the frontier, swapping GPT-5.3 for Claude Opus 4.7 gains roughly 1–3 percentage points on standardized tasks. The same 1–3 point delta comes from swapping a timeout from 60s to 120s.
- **Scaffold swaps move the needle by 5–22 points.** Context retrieval strategy, turn budget, tool call error handling, retry logic, patch extraction — each is a lever the benchmark harness pulls that your production code may not.
- **Vendor scores are always optimized scores.** A vendor's published benchmark uses their own scaffold. That scaffold is not documented, not shared, and not reproducible by the buyer. It is the vendor's competitive advantage in scoring.
- **SWE-bench Pro vs. Verified: 23-point gap on the same model.** Claude Opus 4.7 scored 87.6% on SWE-bench Verified and 64.3% on SWE-bench Pro. That 23-point swing is harness configuration, not model capability. GPT-5 scored ~70%+ on Verified, 23.3% on Pro (public), 14.9% on Pro (commercial).
- **The procurement decision is made on the wrong number.** Engineering leaders use benchmark scores in $100K–$500K procurement decisions. The number in the deck is always the scaffold-optimized score. The production number is always lower.

## The move

**Separate scaffold configuration from model capability before you evaluate anything.**

### 1. Decompose the harness into five independently tunable axes

```
Fixed base:  prompt template · task set · execution container · timeout · patch extraction · evaluator
Replaceable: the harness ("claw")
```

This is the Claw-SWE-Bench decomposition (arXiv:2606.12344, TokenRhythm/Infinigence AI, June 2026). It reveals that prior benchmarks bundled everything into a single opaque system — making it impossible to know whether a score delta came from the model or the scaffold.

### 2. Audit your evaluation harness against five disclosure dimensions

| Dimension | What to check |
|-----------|---------------|
| **Turn budget** | Max reasoning steps, not just timeouts. A 60s vs 120s timeout can account for 4–8 points on long-horizon tasks. |
| **Tool call error handling** | Does the harness retry on schema errors, rate limits, or malformed JSON? Production code usually does not — or does it differently. |
| **Context retrieval strategy** | Vector search, full-context dump, or selective retrieval? Retrieval quality is the largest single source of scaffold variance. |
| **Patch extraction** | How does the harness extract the final code artifact? Greedy last-output vs. semantic diff vs. file-system snapshot — each produces different pass rates. |
| **Prompt template** | The vendor's system prompt vs. your system prompt. A single directive difference can shift scores by 3–5 points. |

### 3. Run a scaffold gap test before every model swap

```python
import json
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ScaffoldConfig:
    max_turns: int = 30          # turn budget
    tool_retry_count: int = 2     # retries on tool failure
    timeout_seconds: int = 120    # per-step timeout
    retrieval_strategy: str = "selective"  # full | selective | vector
    patch_extraction: str = "last_output"  # last_output | semantic_diff | snapshot
    system_prompt_template: str = ""

@dataclass
class ScaffoldComparison:
    config_a: ScaffoldConfig
    config_b: ScaffoldConfig
    task_suite: list[str]
    model: str
    scores_a: list[float] = field(default_factory=list)
    scores_b: list[float] = field(default_factory=list)

def run_scaffold_gap_test(comparison: ScaffoldComparison) -> dict:
    """
    Run the same task suite with two scaffold configs on the same model.
    The score delta is your scaffold gap — not a model difference.
    """
    results = {}
    for task in comparison.task_suite:
        score_a = evaluate_with_scaffold(task, comparison.model, comparison.config_a)
        score_b = evaluate_with_scaffold(task, comparison.model, comparison.config_b)
        results[task] = {"scaffold_a": score_a, "scaffold_b": score_b}
    
    delta = mean([r["scaffold_b"] - r["scaffold_a"] for r in results.values()])
    return {
        "scaffold_gap": delta,
        "per_task": results,
        "interpretation": (
            f"{delta:+.1f}pp from scaffold alone. "
            "If this exceeds your model upgrade delta, optimize the scaffold first."
        )
    }

# Example: vendor harness vs. your production harness
gap = run_scaffold_gap_test(ScaffoldComparison(
    config_a=ScaffoldConfig(max_turns=50, tool_retry_count=3, timeout_seconds=180),
    config_b=ScaffoldConfig(max_turns=30, tool_retry_count=1, timeout_seconds=60),
    task_suite=["SWE-bench instances or your own task suite"],
    model="claude-opus-4.7"
))
print(gap["interpretation"])
```

### 4. Require harness disclosure in every vendor benchmark submission

SWE-bench Pro now requires harness configuration disclosure as a mandatory submission field. Apply the same standard internally: any model evaluation must document the full harness configuration. If the vendor won't disclose, treat their score as an upper bound.

### 5. Build your production harness as a first-class artifact

The scaffold is not a throwaway evaluation concern — it is the actual product. Treat it with the same rigor:

- Version-control your harness configuration
- Run regression tests when you change scaffold settings
- Name your harness configuration (e.g., `prod-v3`, `eval-v2`) so scores are comparable across runs
- Profile each axis independently: change one at a time, measure the delta

## Receipt

> Verified 2026-07-18 — AgentMarketCap (September 26, 2026): model swaps account for ~1pp delta at frontier; scaffold swaps account for 5–22pp. Claw-SWE-Bench (arXiv:2606.12344, June 2026, TokenRhythm/Infinigence AI): formalized harness decomposition into fixed base + replaceable claw, enabling fair cross-harness comparison. Claw-SWE-Bench Lite (80 instances) enables fast iteration on harness design. Vibe Code Bench (arXiv:2603.04601): found that evaluator choice substantially affects results — some evaluator pairs agree, others diverge, confirming that evaluation infrastructure is itself a variable.

## See also
- [S-413 · The Test-Production Reliability Gap](s413-production-reliability-gap.md) — the broader reliability collapse between test and prod, of which the scaffold gap is a specific mechanism
- [S-1310 · The Agent Eval Stack](s1310-the-agent-eval-stack-when-your-benchmark-says-pass-and-production-says-fail.md) — building production-grade eval infrastructure beyond benchmark scores
- [f14 · Reading Agent Benchmarks](../forward-deployed/f14-reading-agent-benchmarks.md) — how to interrogate a benchmark score before trusting it
