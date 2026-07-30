# S-1865 · The Scaffold-First Fallacy — When a Model Upgrade Costs Less Than a Harness Fix

You spend two quarters benchmarking GPT-5.5 vs Claude Opus vs Gemini 3. Select the winner. Ship it. Performance improves by 3 points. Meanwhile, the same model running through your production scaffold scores 36 points below the bare-model benchmark. You bought the wrong upgrade. The harness is the bottleneck, not the model.

## Forces

- **The 36-point swing.** SWE-bench Pro data from 2026 shows the same model, different scaffolds, produces 22–36 percentage point performance swings. That exceeds the gap between most frontier tiers. Enterprise procurement ignores this at massive cost.
- **Benchmarks measure bare models, not systems.** Published leaderboards test the model in a standardized harness. Your production system has custom tooling, retrieval, memory, retries, and orchestration. These change the effective capability dramatically — in both directions.
- **Harness engineering is invisible labor.** Scaffolding work (tool description framing, result parsing, error recovery paths, retry budgets) is undocumented, unrewarded, and usually inherited from a prototype that was never designed to scale.
- **The upgrade reflex.** When agents underperform, the reflex is "try a better model." This is usually the most expensive way to close a small gap — and it papers over a harness problem that will degrade the next model too.

## The move

### Diagnose before you upgrade

Run your agent with two scaffolds simultaneously: your current one and a minimal ReAct harness with no custom recovery logic. The performance delta isolates the harness contribution. If the gap is >15 points, fix the harness first.

```python
import subprocess
import json

def diagnose_harness_gap(model_id: str, test_set: str, harness_a: dict, harness_b: dict) -> dict:
    """
    Compare two scaffold configs on the same model + test set.
    Returns the performance delta attributable purely to harness engineering.
    """
    results = {}
    for name, harness in [("current", harness_a), ("minimal", harness_b)]:
        cmd = [
            "python", "-m", "agent_benchmark",
            "--model", model_id,
            "--testset", test_set,
            "--harness", json.dumps(harness),
            "--output", f"/tmp/{name}_results.json",
        ]
        subprocess.run(cmd, check=False)
        with open(f"/tmp/{name}_results.json") as f:
            results[name] = json.load(f)

    delta = results["current"]["pass_rate"] - results["minimal"]["pass_rate"]
    return {
        "current": results["current"]["pass_rate"],
        "minimal": results["minimal"]["pass_rate"],
        "harness_delta": delta,
        "recommendation": "fix_harness" if delta < -5 else "model_limited",
    }
```

### Invest in the five harness primitives before the next model upgrade

1. **Tool description quality** — Framing matters more than schema completeness. Test with adversarial tool names.
2. **Result parser resilience** — Structured output failure is the top cause of scaffold breakdown on model upgrades.
3. **Recovery path coverage** — Map every tool error to a retry, escalate, or abort decision. Don't let errors fall through.
4. **Step budget enforcement** — Hard cap on tool calls per task with exponential backoff. Catches the loops s1027 covers.
5. **Trajectory instrumentation** — Emit structured spans for every step. Without this, you cannot attribute failures to model vs. harness.

### The procurement filter

Before evaluating a new model, establish a harness ceiling. Improve your current scaffold until diminishing returns are clear. Only then benchmark the new model — using your best harness, not a vanilla one. The model deserves a fair test.

## Receipt

> Receipt pending — 2026-07-30. SWE-bench Pro and agentmarketcap.ai (2026-04-23) report 22–36 point swings attributable to scaffold differences. The pattern holds across Claude, GPT, and Gemini model families. Verified against published data from particula.tech and agentmarketcap.ai.

## See also

- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection and budget enforcement within scaffolds
- [S-1133 · The Trajectory-First Eval Stack](/stacks/s1133-the-trajectory-first-eval-stack-when-your-agent-succeeds-but-you-cant-tell-if-it-got-lucky.md) — measuring the path, not just the output
- [S-1000 · The Eval Gap Stack](/stacks/s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — why benchmark-to-production translation fails
- [S-1220 · The Agent Eval Loop Stack](/stacks/s1220-the-agent-eval-loop-stack-when-everything-succeeds-but-nothing-is-measured.md) — the measurement infrastructure scaffolds need
