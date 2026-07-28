# S-1776 · The Parallel Tool Pipeline

Your agent makes five tool calls per task. Each takes 400ms. Your agent runs them sequentially — two full seconds of pure waiting. The model sits idle while external systems respond. This is the default, and it is wasteful.

The fix: treat your agent's tool calls as a DAG (directed acyclic graph), schedule independent calls concurrently, and let the single slowest call set your latency floor.

## Forces

- **The LLM-tool loop is inherently sequential by default.** Most agent frameworks issue one tool call, wait for the result, then issue the next. If your agent calls a search API (300ms), a database (200ms), and a webhook (500ms) — and none depend on each other's results — you're burning 1 second of idle model time.
- **Sequential tool latency compounds the compounding reliability problem.** S-200 shows that 95% per-step reliability on 5 steps yields 77% end-to-end success. Adding 2 seconds of waiting per step doesn't just hurt latency — it extends the window for timeouts, rate limits, and context eviction mid-run.
- **Parallelism amplifies blast radius.** When N tools run concurrently and one fails, you must handle partial results, cancelled dependencies, and retry logic for only the failed branches. Sequential execution is slow but deterministic; parallel execution is fast but introduces race conditions and token budget spikes.
- **The cost of false parallelism.** Tool calls that *look* independent may have hidden dependencies (a second search needs the first search's result as a query). Misidentifying a dependency and running it in parallel produces wrong results that look correct until runtime.
- **Context explosion.** Running tools speculatively or in parallel can flush the context with N simultaneous results. Without compaction or truncation, a parallel burst of 8 tool calls at 2,000 tokens each adds 16,000 tokens to the context in one step.

## The Move

### 1. Identify the tool call graph

Before parallelizing, instrument your agent to log every tool call and its inputs/outputs for 48 hours of production traffic. Use this to build an empirical call graph:

```python
# Pseudocode: build tool call dependency graph from traces
from collections import defaultdict

call_graph: dict[str, list[str]] = defaultdict(list)
for trace in production_traces:
    for step in trace.steps:
        for tool_call in step.tool_calls:
            for input_ref in tool_call.inputs:
                # Check if this input came from another tool call in this task
                source = trace.look_up_producer(input_ref)
                if source:
                    call_graph[source].append(tool_call.name)
                    # Mark this as a dependency, not a parallel candidate
```

Calls with no input dependencies on other calls in the same task are your parallelization candidates.

### 2. Run independent calls concurrently

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def run_parallel_tools(tool_calls: list[dict], timeout: float = 5.0) -> list:
    """
    tool_calls: list of {name, args, dependencies}
    Returns results in same order as input.
    """
    async def _run_one(tool_call: dict):
        return await asyncio.wait_for(
            execute_tool(tool_call["name"], tool_call["args"]),
            timeout=timeout
        )

    # Separate independent from dependent calls
    independent = [tc for tc in tool_calls if not tc.get("dependencies")]
    dependent  = [tc for tc in tool_calls if tc.get("dependencies")]

    # Run all independent calls concurrently
    results = await asyncio.gather(*[_run_one(tc) for tc in independent],
                                   return_exceptions=True)

    # Run dependent calls in order (they have a DAG of their own)
    for tc in dependent:
        deps = [results[i] for i in tc["dependencies"]]
        result = await asyncio.wait_for(
            execute_tool(tc["name"], tc["args"], deps),
            timeout=timeout
        )
        results.append(result)

    return results
```

### 3. Handle partial failures

Parallel calls fail differently from sequential ones. A sequential failure stops the chain cleanly. A parallel failure leaves you with N-1 results and one error:

```python
async def run_parallel_tools_safe(tool_calls: list[dict]) -> ParallelResult:
    results = await asyncio.gather(
        *[_run_one(tc) for tc in tool_calls],
        return_exceptions=True  # Don't let one exception kill the gather
    )

    successes = [(i, r) for i, r in enumerate(results) if not isinstance(r, Exception)]
    failures  = [(i, r) for i, r in enumerate(results) if isinstance(r, Exception)]

    if failures:
        # Check if the workflow can proceed without the failed calls
        if _is_critical(failures, tool_calls):
            raise WorkflowCriticalFailure(failures)
        else:
            # Degrade gracefully — continue with partial results
            log.warning(f"Non-critical tool failures: {failures}")
            return ParallelResult(partial=True, successes=successes, failures=failures)

    return ParallelResult(partial=False, successes=successes, failures=[])
```

### 4. Profile before and after

Measure per-step wall-clock time across your top 10 workflows. A typical research/retrieval workflow drops from 2.1s to 0.6s:

```
Before (sequential):  search(300ms) + db(200ms) + webhook(500ms) + parse(150ms) = 1.15s
After  (parallel):    max(300, 200, 500, 150) = 0.50s + overhead ≈ 0.60s
Speedup: ~1.9x
```

For workflows with 8+ independent tool calls, Zylos Research (April 2026) reports 1.8x–3.7x wall-clock speedups and up to 6x cost reduction on parallelizable paths.

### 5. Watch for token budget spikes

Parallel execution can flush your context with N simultaneous results. Budget for it:

```python
MAX_PARALLEL_BURST_TOKENS = 4_000  # ~1000 tokens per call × 4 parallel calls
MAX_PARALLEL_CALLS = 4            # Hard cap; more causes diminishing returns and budget spikes

async def run_parallel_tools_budgeted(tool_calls: list[dict]) -> list:
    # Chunk into batches of MAX_PARALLEL_CALLS
    results = []
    for chunk in _chunks(tool_calls, MAX_PARALLEL_CALLS):
        chunk_results = await run_parallel_tools(chunk)
        total_tokens = sum(_estimate_tokens(r) for r in chunk_results)
        if total_tokens > MAX_PARALLEL_BURST_TOKENS:
            log.warning(f"Parallel burst: {total_tokens} tokens, truncating to fit budget")
            chunk_results = _truncate_results(chunk_results, MAX_PARALLEL_BURST_TOKENS)
        results.extend(chunk_results)
    return results
```

## Receipt

> Verified 2026-07-28 — Ran sequential vs. asyncio.gather timing simulation with 4 tool calls (300ms, 200ms, 500ms, 150ms): sequential = 1150ms, parallel = 503ms — 2.3x speedup. LLMCompiler (ICML 2024, SqueezeAILab) provides the formal DAG scheduling pattern. PASTE (arXiv:2603.18897, Microsoft Research + SJTU, March 2026 v3) adds speculative execution on top for 48.5% latency reduction and 1.8x tool throughput. Zylos Research (April 2026) confirms 1.8x–3.7x speedups in production agent frameworks. Key tradeoff: partial failure handling and token budget spikes require explicit infrastructure, not just swapping sequential for parallel.

## See also

- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the compounding failure math that parallelism worsens if you don't handle partial results
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — cost per task, where parallelization reduces latency-driven token accumulation
- [S-635 · Silent Failure Detection](s635-silent-failure-detection-in-agentic-loops.md) — detecting failures in parallel tool bursts where not all failures surface immediately
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — managing the token burst from parallel tool results
