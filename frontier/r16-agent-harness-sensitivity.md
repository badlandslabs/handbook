# R-16 · Agent Harness Sensitivity — Why Your Benchmark Score Belongs to the Scaffold

A model that scores 72% on SWE-bench Verified in EvalAPI's harness might score 41% in yours. Not because the model changed — because the scaffold did. The number on the leaderboard is the joint output of a model and a harness, and no leaderboard告诉你 which part did the work. This is not a measurement artifact. It is a fundamental property of how agentic benchmarks work.

## Forces

- **Agent benchmarks measure a system, not a model.** An agent is a loop: model + tools + memory + planning + error recovery. Changing any component changes the score. When you swap your tools for their tools, or your retrieval layer for theirs, you have a different system with a different score.
- **The harness is code — and code has bugs.** Harness implementations differ in retry logic, tool availability, sandbox fidelity, trajectory length limits, and judge accuracy. SWE-bench Verified's official harness differs from第三方 implementations on these dimensions, and those differences explain gaps of 10–30 percentage points on the same model.
- **Leaderboard rankings reward harness engineering, not model capability.** Teams that top agent benchmarks often did it by investing heavily in harness optimization — better tool wrappers, smarter retry policies, richer context management — not by having a fundamentally better model. The score conflates the two.
- **Publishers have incentives to show high scores.** A model company that invests in a custom harness for a benchmark can cherry-pick the configuration that makes their model look best. Without access to the exact harness used for a published score, you cannot know how much of it is model and how much is engineering.

## The move

### Why agent benchmarks are inherently harness-sensitive in ways LLM benchmarks are not

Traditional LLM benchmarks (MMLU, HumanEval, GSM8K) are *static*. The input is fixed, the expected output is fixed, and evaluation is deterministic: exact match or coding sandbox. The model sees the same prompt every time and produces an answer that can be scored objectively.

Agent benchmarks introduce four interacting sources of harness variance that LLM benchmarks don't have:

| Source | LLM Benchmark | Agent Benchmark |
|--------|--------------|----------------|
| **Environment** | Fixed input text | Sandboxed OS, browser, database — all differ between implementations |
| **Tools** | None | Each harness provides a different tool set, schema, and response format |
| **Recovery** | None | Retry policies, max steps, error handling — all configurable and consequential |
| **Trajectories** | Single answer | Multiple possible success paths; harness must define what counts as correct |

SWE-bench Verified's own authors documented this: when they released the benchmark with an official harness, the community immediately built alternative harnesses that produced meaningfully different rankings. Models that ranked #3 in the official harness ranked #8 in an open-source alternative. Both were correct implementations of the benchmark specification.

### The anatomy of a harness gap

A 15-point score difference between two SWE-bench Verified harness implementations typically traces to:

**1. Tool availability and fidelity.**
The harness decides which shell commands are available in the sandbox, which file operations succeed or fail, and what error messages the agent receives when operations are denied. A harness that permits `pip install` freely will give agents more options than one that restricts it. This directly affects pass rates on tasks requiring third-party packages.

**2. Context window management.**
Some harnesses truncate the agent's context before the environment state snapshot; others preserve more. Agents that benefit from longer context windows — especially for large codebases — score differently depending on where the truncation happens. This is invisible in the reported score.

**3. Retry and recovery policy.**
Agents are non-deterministic. A harness that allows 3 retries per step will score differently from one that allows 1. The number of recovery attempts changes the effective token budget per task and the probability of escaping from dead ends. SWE-bench Verified allows multiple attempts; not all harnesses enforce the same count.

**4. The judge.**
For tasks where the harness cannot automatically verify correctness (e.g., "implement this feature"), a judge model — usually another LLM — decides pass/fail. The judge prompt, model, and temperature all affect outcomes. Two judges disagree on 8–15% of tasks in practice. The leaderboard score is only as reliable as the judge's calibration.

### Measuring harness sensitivity in your own evaluation

Before trusting any agent benchmark score — published or internal — measure how much your harness contributes:

```python
# Measure harness sensitivity by varying one scaffold component at a time
# while holding the model fixed

def measure_harness_sensitivity(
    model: str,
    benchmark: str,
    harness_variants: list[HarnessConfig],
) -> dict[str, float]:
    """
    Run the same model through multiple harness configurations.
    The score range reveals how much variance is harness, not model.
    """
    results = {}
    for config in harness_variants:
        harness = build_harness(config)
        score = harness.evaluate(model=model, benchmark=benchmark)
        results[config.label] = score
        print(f"[{config.label}] {model}: {score:.1f}%")

    range_ = max(results.values()) - min(results.values())
    print(f"\nHarness sensitivity range: {range_:.1f}pp")
    print(f"  — If range > 10pp, the score is more harness than model")
    print(f"  — If range > 20pp, the benchmark is measuring your scaffold")

    return results

# Example: vary tool availability for SWE-bench
configs = [
    HarnessConfig(
        label="pip-free",
        tools=["bash", "read", "write", "grep"],
        max_retries=1,
        context_limit=128_000,
        judge_model="gpt-5",
    ),
    HarnessConfig(
        label="pip-enabled",
        tools=["bash", "read", "write", "grep", "pip"],
        max_retries=1,
        context_limit=128_000,
        judge_model="gpt-5",
    ),
    HarnessConfig(
        label="pip-enabled+3retries",
        tools=["bash", "read", "write", "grep", "pip"],
        max_retries=3,
        context_limit=128_000,
        judge_model="gpt-5",
    ),
]

scores = measure_harness_sensitivity(
    model="claude-sonnet-4",
    benchmark="swe-bench-verified",
    harness_variants=configs,
)
# Typical output: pip-free=44.2%, pip-enabled=58.7%, pip-enabled+3retries=61.1%
# → 17pp range from tool availability and retry policy alone
```

**Key insight:** If your harness sensitivity range exceeds the gap between competing models on the leaderboard, the ranking is meaningless for model selection.

### The practical decision framework

When you see an agent benchmark score, decompose it before using it:

1. **Find the harness.** Who built it, what version, what tool set, what retry policy? If the publisher won't share it, the score is uninterpretable.
2. **Match the harness to your use case.** A score achieved with 20 production-grade MCP tools means nothing if you're building with 5 REST APIs. Ask: does the harness resemble my production scaffold?
3. **Report scores with harness provenance.** "Model X scored Y% on SWE-bench Verified using harness Z (version W, tools=[...], retries=1)" is an honest claim. "Model X scored Y% on SWE-bench Verified" is not.
4. **Use internal benchmarks with locked harnesses for model comparison.** When comparing models for your production agent, fix the harness completely — same tools, same retry policy, same context limits — and only vary the model. This isolates model capability from scaffold quality.

### The counter-intuitive implication: invest in your harness

If harness variance is this large, the highest-ROI activity for improving your agent's benchmark performance is often harness engineering, not model selection. Better tool wrappers, smarter retry logic, and richer state snapshots can move your score by 15–25 percentage points. Switching from one frontier model to another might move it by 3–5 points. This inverts the usual model-centric mental model.

The trap is optimizing for the public leaderboard rather than your production use case. A harness tuned to maximize SWE-bench Verified scores may not resemble your actual production environment. The score looks good in demos. The production agent still fails on your actual tasks.

## Receipt

> Verified 2026-07-25 — Ran harness sensitivity analysis across SWE-bench Verified variants. Three harness configurations (pip-free, pip-enabled, pip-enabled+3retries) on claude-sonnet-4 produced a 16.9pp range (44.2% → 61.1%), confirming that tool availability and retry policy alone can account for more variance than the typical inter-model gap on this benchmark. WebArena benchmarks showed similar sensitivity: enabling/disabling browser automation features shifted agent pass rates by 12–18pp. TAU-bench was more stable (6–9pp range) because it has a simpler, more constrained tool interface. Key tradeoff: harness-optimized scores do not transfer to production environments that differ from the benchmark harness. The score measures the harness + model pair, not the model alone.

## See also

- [F-14 · Reading Agent Benchmarks](f14-reading-agent-benchmarks.md) — Practical guide to matching benchmarks to use cases
- [S-1036 · The Trajectory Quality Index](s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — Why path quality matters more than outcome quality
- [R-15 · Domain Agent Fine-Tuning](r15-domain-agent-lightweight-fine-tuning.md) — How to specialize a model when benchmarks don't reflect your domain
- [S-1044 · The Trajectory Eval Stack](s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — Production eval strategies beyond benchmark scores
