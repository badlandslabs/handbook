# S-2868 · The Harness-as-Reliability-System Stack — When Your Agent Works in the Demo Harness and Fails Everywhere Else

[When your agent scores 91% in your internal eval harness but 63% in production. The model didn't change. The harness did.]

## Forces

- **Harness is not passive infrastructure — it is an active reliability system.** The harness issues tools, manages context windows, enforces budgets, retries on errors, and decides when to stop. All of those decisions affect whether a task succeeds. Yet most teams treat the harness as a deployment detail, not an eval dimension.
- **Eval harness and production harness diverge by default.** Your internal eval harness is clean: fixed API keys, stable network, pinned dependency versions. Your production harness faces rate limits, auth expiry mid-session, network partitions, dependency version drift, and concurrent load. When these diverge, the agent's behavior diverges — even though the model weights are identical.
- **The harness attribution problem is unsolvable without instrumentation.** When a task fails in production, you cannot tell whether the agent made a bad decision, the harness timed out mid-retry, or a tool returned a different shape than expected. Without harness-level observability, every failure looks like an agent failure.
- **Scaffold variance exceeds model variance in production.** The same model scores 42–78% depending on which harness wraps it. This means a bad harness choice costs more than a bad model choice — but harness quality is never benchmarked.
- **Production introduces failure modes the eval harness never sees.** Auth token expiry mid-task, rate limit backoff decisions, concurrent session resource contention, partial tool responses from overloaded servers — all of these exist in prod and not in the eval harness.

## The move

The core move: **treat the harness as a first-class reliability system with its own instrumentation, parity testing, and regression suite.** The agent is only as reliable as the harness that wraps it.

### 1. Harness parity testing

Run your eval suite against both harnesses (eval and production) and compare results. Divergence in pass rate, step count, and error distribution reveals harness-induced failures.

```python
import asyncio
from dataclasses import dataclass

@dataclass
class HarnessResult:
    harness: str
    pass_rate: float
    median_steps: float
    error_rate: float
    tool_call_failures: int
    timeout_rate: float

async def parity_test(agent, eval_harness, prod_harness, eval_suite, n=100):
    """Run the same eval suite through two harnesses. Flag divergence."""
    tasks = []
    for h in [eval_harness, prod_harness]:
        tasks.append(run_harness(agent, h, eval_suite, n))
    eval_res, prod_res = await asyncio.gather(*tasks)

    delta = {
        "pass_rate_delta": abs(eval_res.pass_rate - prod_res.pass_rate),
        "step_count_ratio": prod_res.median_steps / max(eval_res.median_steps, 1),
        "tool_failure_delta": prod_res.tool_call_failures - eval_res.tool_call_failures,
        "timeout_delta": prod_res.timeout_rate - eval_res.timeout_rate,
    }

    # Alert if production is significantly worse
    if delta["pass_rate_delta"] > 0.05:
        raise RuntimeError(
            f"Harness parity breach: production scores "
            f"{prod_res.pass_rate:.1%} vs eval {eval_res.pass_rate:.1%} "
            f"(Δ={delta['pass_rate_delta']:.1%}). Fix harness before shipping."
        )
    return eval_res, prod_res, delta
```

### 2. Harness regression suite

Before deploying a harness change, run the harness alone against a golden eval suite. A harness regression suite tests the harness in isolation — no agent involved.

```python
def harness_regression_suite(harness, test_cases):
    """
    Test harness behavior in isolation.
    Each test_case: {tool_name, mock_response, expected_steps, should_timeout}
    """
    results = []
    for tc in test_cases:
        harness.reset()
        harness.install_mock_tool(tc["tool_name"], tc["mock_response"])

        try:
            result = harness.run_single_tool(tc["tool_name"], tc["tool_args"])
            results.append({
                "case": tc["name"],
                "passed": (
                    result["steps"] == tc["expected_steps"]
                    and result["error"] is None
                ),
                "steps": result["steps"],
                "error": result.get("error"),
            })
        except TimeoutError:
            results.append({
                "case": tc["name"],
                "passed": tc["should_timeout"],
                "error": "timeout",
            })

    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"Harness regression: {len(failed)}/{len(results)} cases failed")
        for f in failed:
            print(f"  FAIL: {f['case']} — {f['error']}")
        raise RuntimeError("Harness regression suite failed")
    return results
```

### 3. Harness attribution layer

Instrument the harness separately from the agent. When a trace shows a failure, tag whether it originated in the agent's reasoning or the harness's execution layer.

```python
def trace_with_harness_attribution(trace):
    """
    Classify each span in a trace as agent-origin or harness-origin.
    Agent-origin: model generates wrong action, wrong tool, wrong stop.
    Harness-origin: timeout, rate-limit, auth failure, network error, context overflow.
    """
    attributed = []
    for span in trace.spans:
        if span.name in {"tool_call", "tool_response", "retry", "context_truncate"}:
            attributed.append({**span.__dict__, "layer": "harness"})
        elif span.name in {"model_reasoning", "action_selection", "stop_decision"}:
            attributed.append({**span.__dict__, "layer": "agent"})
        else:
            attributed.append({**span.__dict__, "layer": "unknown"})
    return attributed
```

### 4. Production harness as eval target

Treat the production harness itself as a system under evaluation. Every harness change requires a harness eval run before it affects production agents.

```python
# Production harness minimum spec — fail fast if these are missing
MINIMUM_HARNESS_CAPABILITIES = [
    "retry_with_backoff",      # Exponential backoff on tool failures
    "auth_refresh",            # Refresh credentials mid-session without restart
    "rate_limit_handling",     # Respect X-RateLimit-Retry-After headers
    "timeout_per_tool",        # Per-tool timeout, not global timeout
    "context_eviction_policy", # LRU or priority-based, not random truncation
    "error_attribution",       # Tag errors as agent vs harness origin
    "budget_enforcement",      # Hard stop on token/spend limits
]

def validate_harness(harness):
    """Fail fast if harness is missing minimum reliability capabilities."""
    missing = [
        cap for cap in MINIMUM_HARNESS_CAPABILITIES
        if not hasattr(harness, cap)
    ]
    if missing:
        raise RuntimeError(
            f"Harness missing required capabilities: {missing}. "
            f"Deploy blocked until parity with eval harness is confirmed."
        )
```

## Receipt

> Verified — The pattern is confirmed by: (1) arXiv:2607.22585 (Vats & Golev, ICML 2026 DL4C Workshop) — harness induces 40× token variance and 0–8pt pass-rate variance across Goose/OpenCode/OpenHands on Terminal-Bench Pro; (2) AgentMarketCap July 2026 analysis — same model (Sonnet 4.5) scores 59.8% in Cline vs 43.2% in SWE-agent = 16.6-pt swing from harness alone; (3) AlphaEval (arXiv:2604.12162) — best model-harness pair (Claude Code + Opus 4.6) scores 64.41/100 vs best model alone (53.0/100), proving harness is a separate evaluation dimension; (4) Particula.tech analysis (2026) — scaffolding moves SWE-bench scores by 22 points while model upgrades move 1 point.

## See also

- [S-1174 · The Scaffold Convergence Problem](/stacks/s1174-the-scaffold-convergence-problem-when-frontier-models-cluster-within-1-point-and-the-real-engineering-is-in-the-harness.md) — model layer convergence and why harness is the durable lever
- [S-2671 · The Evaluation Gap Stack](/stacks/S-2671-the-evaluation-gap-stack-when-your-agent-aces-the-benchmark-and-flops-in-production.md) — benchmark vs production divergence
- [S-2862 · The Regression Gate Stack](/stacks/s2862-the-regression-gate-stack-when-your-agent-shipped-and-nobody-noticed-it-got-worse.md) — catching harness-induced regressions before deploy
- [S-2865 · The Multi-Dimensional Grader Stack](/stacks/s2865-the-multi-dimensional-grader-stack-when-your-single-score-tells-you-nothing-about-what-your-agent-actually-does.md) — disaggregating scores to expose harness failure modes
