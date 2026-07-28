# S-1733 · The Speculative Execution Stack — When Your Agent Waits for Tools It Could Have Started Already

Your agent's loop runs: LLM thinks → emits a tool call → waits for the result → feeds it back → LLM thinks again. On a 10-step task with a 200ms LLM call and a 300ms database query, you spend 3 seconds waiting — half of it on I/O the LLM already told you it was going to do. The sequential loop is the bottleneck, not the model.

Speculative tool execution inverts the wait: while the LLM is still decoding its response, predict which tool it will call next and start executing it. If the prediction is right, the result is ready before the LLM even finishes thinking. If it is wrong, discard the work and fall back to synchronous execution. The cost is a wasted compute cycle; the gain is eliminating the tool-call latency from the critical path entirely.

## Forces

- **Tool calls dominate agent latency, not LLM inference.** In a typical retrieval-augmented agent loop, the LLM call takes 100–500ms while the tool (DB query, API call, file read) takes 200–2000ms. Parallelizing them eliminates the slower half.
- **LLM tool calls are predictable.** Agent tool use follows distributional patterns: given a session history and a partial LLM output, the next tool and its parameters can be predicted with high accuracy. The Sui et al. (2026) PASTE paper found "future tool use is often predictable before the LLM explicitly emits the next tool call" with 43.5% task completion time reduction.
- **The cost of a wrong speculation is bounded.** Unlike speculative decoding (where a bad draft token cascades into re-computation), a wrong tool speculation wastes a tool execution — typically a few hundred milliseconds and dollars of API calls. Rollback is cheap.
- **Prediction confidence must gate execution.** Speculatively writing to a database or sending an API call before the LLM confirms the intent crosses a trust boundary. Speculative execution is safe only for read-equivalent tools — the equivalent of CPU branch prediction vs. speculative store buffers.

## The move

### The execution loop anatomy

Standard agent loop (sequential):
```
LLM generates → [waits] → tool call executes → [waits] → LLM generates → ...
Total: sum of all LLM + tool latencies
```

Speculative loop (parallel):
```
LLM generates + speculative tool executes simultaneously
    └── If speculation correct → result already available
    └── If wrong → discard, fall back to synchronous
```

### Layer 1: Tool prediction

Predict the next tool call from the LLM's in-progress output. Two signal sources:

- **Output prefix matching.** Feed the LLM's streaming tokens (even partial) into a prediction head trained on tool-calling traces. Early output tokens (`"I'll fetch the`" → `file_read`, `"SELECT * FROM`" → `sql_query`) have high predictive signal before the full call is emitted.
- **Session pattern matching.** In structured agent workflows, the next tool is often deterministic given the current state and the agent's role. A code-review agent after `lint_check` always calls `fix_suggest`. Mine your replay traces for these patterns.

Confidence threshold: execute speculatively only when P(tool) > 0.85. Below that, fall back to synchronous.

### Layer 2: Read/write separation

Speculative execution is safe only for idempotent reads. Classify every tool:

| Type | Example | Speculative? |
|------|---------|-------------|
| Pure read | `file_read`, `db_query`, `web_search` | ✓ Always |
| Idempotent write | `file_append`, `update_record` | ✓ With rollback log |
| Non-idempotent write | `delete`, `send_email`, `payment` | ✗ Never |

The boundary is the same trust boundary as any other side effect — speculative execution doesn't relax it, it just starts the work earlier.

### Layer 3: Commit protocol

When the speculative result arrives before the LLM finishes:

```
if speculation.correct(params):
    inject_result(immediately)
    # LLM output matched prediction — no stall
elif speculation.partially_correct(params):
    inject_result(with_revalidation)
    # Params were right, verify output schema
else:
    discard_result()
    execute_synchronously(params)
    # Prediction was wrong — normal flow
```

The LLM never knows the difference. It receives the result as if it had waited.

### Layer 4: Observability

Speculative execution makes the causal chain non-linear. A trace that shows `tool_result` arriving before `tool_call` in the span tree breaks every debugging intuition. Instrument:

- `speculative.predicted_tool`, `speculative.confidence`, `speculative.outcome` (correct / partial / wrong)
- Correlation IDs linking the speculative execution to the LLM span that triggered it
- Fallback rate: if wrong speculation rate exceeds 20%, the prediction model needs retraining

```python
# Minimal speculative executor
from typing import Callable, Any
from dataclasses import dataclass

@dataclass
class SpeculativeResult:
    tool: str
    params: dict
    result: Any
    confidence: float
    outcome: str  # 'correct' | 'partial' | 'wrong'

async def speculative_execute(
    llm_stream,           # Streaming LLM response
    tool_predictor,       # Prediction model or rule engine
    tool_executor,        # Actual tool execution function
    confidence_threshold=0.85,
):
    speculation: SpeculativeResult | None = None
    spec_task = None

    async for token in llm_stream:
        # During streaming, keep predicting
        pred = tool_predictor.update(token)
        if pred and pred.confidence > confidence_threshold and spec_task is None:
            # Fire speculative execution
            spec_task = tool_executor(pred.tool, pred.params)

        yield token

        # Check if LLM has committed to a tool call
        if tool_call := parse_tool_call_from_stream(llm_stream):
            if spec_task and speculation_matches(tool_call, speculation):
                # Speculation correct — result already running or done
                result = await spec_task
                yield inject_result(result)  # No wait
                spec_task = None
            else:
                # Mismatch — cancel speculative and execute synchronously
                if spec_task:
                    spec_task.cancel()
                result = await tool_executor(tool_call.name, tool_call.params)
                yield inject_result(result)
            break
```

## Receipt

> Verified 2026-07-27 — Sources: PASTE (arXiv:2603.18897, Sui et al., SJTU/Microsoft/Stevens/HKUST), speculative-tools (GitHub, joelvarun, 2026-05), Zylos Research (2026-04-03), OpenReview "Speculative Actions" (P0GOk5wslg). PASTE reports 43.5% task completion time reduction, 1.8× tool latency speedup, 55.4% p99 tail latency improvement. Production status: PASTE is research (2026); speculative-tools is a nascent library (0 stars, May 2026); the underlying KV-connector pattern (vLLM, llm-d) is production-grade for cache reuse but speculative tool execution at the agent loop level remains early-stage infrastructure.

## See also

- [S-112 · Speculative Pre-Generation](s112-speculative-pre-generation.md) — token-level speculative execution for user queries; this entry covers tool-level
- [R-10 · Speculative Decoding](../frontier/r10-speculative-decoding.md) — draft token prediction inside the inference engine
- [S-08 · Prompt Caching](s08-prompt-caching.md) — KV cache reuse across agent turns; complements speculative execution by reducing prefill cost
- [S-1726 · The A2A Task State Divergence Stack](s1726-the-a2a-task-state-divergence-stack-when-your-agent-sends-a-task-and-never-knows-if-it-arrived.md) — observability for non-linear agent execution traces
