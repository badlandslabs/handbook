# S-1174 · The Scaffold Convergence Problem

You spent three weeks evaluating Claude Opus 4.6 versus GPT-5.2 for your coding agent. The SWE-bench difference is 0.1 points. Your peer team picked a different model and outscored you by 22 points — because they had a better harness.

In 2026, the model layer has converged. Six frontier models score within 0.8 percentage points on SWE-bench Verified. The durable engineering advantage is no longer the model — it is the scaffold wrapping it.

## Forces

- **Benchmark convergence is real.** Claude Opus 4.5 (80.9%), Claude Opus 4.6 (80.8%), Gemini 3.1 Pro (80.6%), Anthropic M2.5 (80.2%), GPT-5.2 (80.0%) — within 0.8 points. Selecting between them on benchmark score alone is noise.
- **Scaffold variance dwarfs model variance.** The same model scores 42% with a generic harness and 78% with an optimized one — a 36-point swing from zero change to the underlying model. This exceeds the entire typical gap between frontier model tiers.
- **Scaffolds are invisible until they fail.** Teams obsess over model cards while treating the harness as boilerplate. The first production incident usually reveals every retry assumption, timeout threshold, and context-management shortcut that was never validated.
- **Scaffolds are post-training targets.** Modern models are often fine-tuned with specific scaffolds in the loop — model "excellence" at filesystem ops or tool dispatch is partly harness-derived capability, not raw intelligence.
- **Scaffolds are the transferable asset.** Prompts and model configs are commodities. The durable moat is the orchestration intelligence: how your agent decomposes, retries, routes, and recovers.

## The Move

### Stop optimizing model selection; start engineering the harness

The three highest-leverage harness investments, in order of ROI:

1. **Tool-call retry with idempotency budgets.** Most scaffold defaults are "retry once on failure." Production-grade scaffolding needs: (a) per-tool retry limits, (b) exponential backoff with jitter, (c) idempotency keys so retries don't produce duplicate side effects (see S-352: Agentic Compensation Keys), (d) circuit breakers that stop hammering a degraded endpoint.

2. **Structured intermediate state storage.** Don't rely on the context window as the sole store for multi-step task state. Write outputs to a structured store (JSON, SQLite, a temp file) and retrieve them explicitly on resume. Context truncation mid-task is the leading cause of silent failures that look like model capability problems.

3. **Error taxonomy routing.** Classify failures into types (timeout, rate limit, tool schema mismatch, semantic error, loop detection) before selecting a response. The same HTTP 429 means different things from different tools — the scaffold, not the model, should route each to the right handler.

### Measure Pass^k, not Pass@1

Pass@1 (succeeds in one attempt) is the standard benchmark metric. It is optimistic. Pass^k (succeeds in k consecutive attempts) is the production reliability metric.

- A coding agent with 80% Pass@1 has ~51% reliability at k=3 (0.8³): it fails 3 consecutive times once every ~2 tasks.
- tau-bench (customer service) introduced Pass^k as a first-class metric. Most enterprise agents should target Pass^3 as the shipping threshold — three consecutive passes before you trust it unattended.
- Measure cost-per-task in addition to accuracy: a scaffold that scores 5 points higher but costs 3x more per call may not be the right trade.

### Benchmark your scaffold, not just your model

Run the same task suite through your scaffold against the top 3 frontier models. If the scaffold accounts for 30+ points of variance, invest in scaffold engineering before the next model evaluation cycle.

```python
# Scaffold comparison harness template
def run_benchmark(model, scaffold_fn, tasks, k=3):
    """Compare scaffolds on the same model, or the same scaffold on different models."""
    results = []
    for task in tasks:
        consecutive = 0
        for attempt in range(k):
            output = scaffold_fn(model, task)
            if output.success:
                consecutive += 1
            else:
                consecutive = 0  # reset on failure
        results.append(consecutive == k)  # Pass^k
    return sum(results) / len(results)
```

### Design for scaffold portability

A scaffold tightly coupled to one model's tool schema, response format, or token budget will become technical debt at every model upgrade. Decouple:

- Tool definitions from model-specific schemas (use a canonical tool manifest; transform per-model)
- Retry budgets from hard-coded timeout values (parameterize and version)
- Evaluation harnesses from the agent runtime (harness-as-a-service pattern separates scoring from execution)

## Receipt

> Verified 2026-07-16 — AgentMarketCap (April 2026) reports six frontier models within 0.8 points on SWE-bench Verified (Claude Opus 4.5–4.6, Gemini 3.1 Pro, Anthropic M2.5, GPT-5.2). HAL benchmark data shows same model scoring 42% (generic scaffold) vs 78% (optimized scaffold) — a 36-point swing. Meter study confirms agent solutions merge at roughly half the rate of human golden solutions on SWE-bench, validating the Pass^k gap. These findings are reproducible from published benchmark leaderboards and cited studies.

## See also

- [S-352 · Agentic Compensation Keys](/opt/data/handbook/stacks/s352-the-agentic-compensation-keys-stack-when-your-agent-retries-but-makes-things-worse.md) — idempotency keys and retry safety for scaffold-level tool calls
- [S-1172 · The Agent Eval Harness Stack](/opt/data/handbook/stacks/s1172-the-agent-eval-harness-stack-when-your-agent-scores-97-percent-on-benchmarks-and-explodes-in-production.md) — building an eval harness that tests the scaffold, not just the model
- [S-1001 · The Agent Evaluation Stack](/opt/data/handbook/stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — broader context on why benchmarks mislead
