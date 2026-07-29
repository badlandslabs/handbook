# S-1795 · The Intelligence Cliff Stack — When Your Agent Crashes at Exactly the Wrong Token Count

Your agent performs flawlessly on a 50-page codebase. You add one more file — 4 tokens over some invisible line — and accuracy collapses by 35%. No error message. No log entry. The API returns 200. Your eval suite is green. Your agent confidently answers the wrong question and ships a broken pull request.

This is not context exhaustion. It's not gradual degradation. It is a cliff — a sharp, non-linear performance boundary that your agent crosses without knowing it, and that your monitoring doesn't catch.

## Forces

- **Critical thresholds are real and non-obvious.** arXiv:2601.15300 (Weiwei Wang et al., January 2026) documents that every frontier long-context model exhibits a catastrophic >30% composite performance drop when context crosses a specific critical length. This threshold is not at the advertised context limit — it is somewhere before it, and it varies by model, task type, and input distribution. The model has no signal that it has crossed it.
- **The cliff is invisible to standard monitoring.** You track token counts, latency, and error rates. None of these spike at the cliff. The model's confidence stays high. It generates fluent, plausible wrong answers — not error messages. You don't discover the cliff until a user reports the wrong output, a week later.
- **The cliff moves with task type.** A model that degrades gracefully on retrieval tasks may cliff-dive on reasoning tasks at a completely different threshold. The "lost in the middle" problem — where models ignore relevant content positioned mid-context — compounds: near the cliff, the middle becomes a dead zone regardless of relevance.
- **Eval suites miss cliffs because they test at fixed lengths.** A benchmark that evaluates at 50K tokens and 100K tokens would miss a cliff at 78K. Your eval is green not because the agent is reliable — because it has never been tested at the length that breaks it.

## The move

The fix has three layers: **detect, avoid, and diagnose**.

### Layer 1 — Threshold Profiling

Before deploying, profile your model at multiple context lengths on your actual task distribution. Use synthetic inputs that grow incrementally and measure the task accuracy curve:

```python
import anthropic

client = anthropic.Anthropic()

def profile_cliff(model: str, task_fn, sizes: list[int]):
    """Run task at increasing context sizes; find cliff threshold."""
    results = []
    for size in sizes:
        ctx = generate_context(size)  # your domain-specific context generator
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": task_fn(ctx)}]
        )
        accuracy = task_fn.evaluate(response)
        results.append({"size": size, "accuracy": accuracy})
        print(f"  {size:>6,} tokens → accuracy={accuracy:.2%}")

    # Find cliff: first size where accuracy drops > 20pp from peak
    peak = max(r["accuracy"] for r in results)
    for r in results:
        if peak - r["accuracy"] > 0.20:
            cliff_size = r["size"]
            print(f"\n⚠️  CLIFF DETECTED at ~{cliff_size:,} tokens "
                  f"(dropped {peak - r['accuracy']:.1%} from peak)")
            return cliff_size
    return None

# Example: profile at 1K-token increments
cliff = profile_cliff(
    "claude-sonnet-4-20250514",
    task_fn=retrieval_task,  # your domain eval function
    sizes=[2000, 10000, 20000, 40000, 60000, 80000, 100000, 128000]
)
```

> Receipt pending — threshold profiling script is illustrative. Requires domain-specific `generate_context()` and `evaluate()` functions.

### Layer 2 — Active Context Budget Guard

Once you know your cliff threshold, set a hard operational budget below it:

```python
CONTEXT_BUDGET = {
    "claude-sonnet-4-20250514": {
        "cliff_threshold": 78_000,   # from profiling
        "safety_margin": 0.80,        # operate at 80% of cliff
        "effective_budget": 62_400,
    },
}

def build_message(user_content: str, ctx_tokens: int, model: str) -> bool:
    """Return True if context is safe to send; False triggers compact action."""
    budget = CONTEXT_BUDGET.get(model, {}).get("effective_budget", 128_000)
    if ctx_tokens > budget:
        return False   # trigger context compaction before this call
    return True
```

The safety margin matters because cliff position drifts slightly with input distribution. A 20% buffer accounts for variance in your actual prompts versus your profiling corpus.

### Layer 3 — Cliff-Aware Monitoring

Instrument your agent to flag when it operates near the profiled threshold:

```python
def agent_response(request_tokens: int, model: str, task_id: str) -> dict:
    budget = CONTEXT_BUDGET.get(model, {}).get("effective_budget", float("inf"))
    cliff_pct = request_tokens / budget if budget < float("inf") else 0

    response = agent.complete(request_tokens=request_tokens, model=model)

    if cliff_pct > 0.85:
        # Run shadow eval on the response: cheap consistency check
        shadow_verdict = shadow_judge(response, task_id)
        if shadow_verdict.confidence < 0.6 and cliff_pct > 0.95:
            # Near-cliff + low-confidence: surface to human
            escalate(task_id, reason="cliff_zone_low_confidence")
            return fallback_response(task_id)  # re-run with compacted context

    return response
```

The shadow judge doesn't re-solve the task — it checks consistency: does the response contradict the first half of the context? Does it repeat claims? Does it acknowledge uncertainty? Low consistency near the cliff is the behavioral signal that the cliff was crossed.

## See also

- [S-1000 · The Context Exhaustion Stack](/opt/data/handbook/stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — gradual degradation; the cliff is sharper and earlier
- [S-1062 · The Production Drift Stack](/opt/data/handbook/stacks/s1062-the-production-drift-stack-when-your-lab-evals-pass-and-your-production-fails-silently.md) — lab evals miss cliffs because they test at fixed lengths
- [S-1793 · The Calibration Gate Stack](/opt/data/handbook/stacks/s1793-the-calibration-gate-stack-when-your-agent-knows-nothing-but-acts-like-it-knows-everything.md) — the agent's high confidence at the cliff makes it unaware it has fallen
