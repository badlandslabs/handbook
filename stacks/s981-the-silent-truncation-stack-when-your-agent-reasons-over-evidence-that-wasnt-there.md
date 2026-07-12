# S-981 · The Silent Truncation Stack: When Your Agent Reasons Over Evidence That Wasn't There

Your database query returned 50 rows. The agent saw 7 and confidently reported that no matching records exist. Your support agent answered "no, your order shipped on time" while the delay flag — rows 8 through 50 — sat in the data the model was never given. No error fired. No exception was raised. The API returned HTTP 200. The agent produced a confident, wrong answer from evidence it never knew was incomplete.

This is the silent truncation failure mode: frameworks apply hard caps on tool output size at layers the developer doesn't control, then present the fragment to the model as if it were the complete result. The model has no signal that what it received is partial. It reasons from the truncated evidence as confidently as it would from the full picture.

## Forces

- **Truncation is invisible by design.** Most frameworks drop overflow silently and return HTTP 200. The model receives no indication that the result was clipped.
- **Evidence gaps produce confident wrong answers.** A model that sees a partial dataset "knows" only that partial dataset. It has no epistemic signal that it lacks context — that signal requires seeing the truncation marker.
- **The problem lives in four layers you may not control.** MCP hosts, CLI wrappers, HTTP proxies, and provider APIs each apply their own limits independently. Your tool may return complete data that arrives at the model incomplete.
- **LLM summarization of tool results (S-97) and structured compression (S-130) are proactive fixes — but they don't address the silent gap.** Proactive compression is opt-in and semantic. Silent truncation is the default, happens everywhere, and provides no marker.
- **The failure is post-hoc undetectable without instrumentation.** Once the agent answers, the truncated evidence is gone from the trace. You can only find it by measuring tool output size at the framework boundary, not downstream.

## The move

**1. Audit your framework's truncation surface.**

Each layer in your stack applies its own output cap. Map them:

| Layer | Example limit | Can you see it in traces? |
|---|---|---|
| MCP host / CLI | Claude Code: 25k tokens (tool results); ~700-char display cap (2025) | No |
| HTTP proxy / load balancer | Configurable, often 64KB–1MB | Sometimes |
| Provider API | OpenAI: 512 KB tool output cap; Claude: error on overflow | Yes (API error) |
| Framework wrapper | Codex: 10 KiB or 256 lines | No |

Run a probe: instrument your tool wrapper to emit the raw byte count of every tool result before and after it enters the agent's context. Compare against what the trace shows the model received.

**2. Add a truncation awareness header to every tool result.**

Wrap every tool call to inject a metadata header the model can read:

```python
def wrap_tool_result(raw_result: dict, max_chars: int = 50_000) -> dict:
    serialized = json.dumps(raw_result)
    truncated = serialized[:max_chars]
    was_truncated = len(serialized) > max_chars
    return {
        "result": truncated,
        "_meta": {
            "truncated": was_truncated,
            "original_size_chars": len(serialized),
            "original_size_tokens_approx": len(serialized) // 4,
            "truncation_boundary": max_chars,
            "omitted_chars": len(serialized) - max_chars if was_truncated else 0,
        }
    }
```

The `_meta` object is small, structured, and readable by the model. When `truncated: true`, the model can self-correct: "I only saw the first 50K characters — I cannot answer this definitively without the omitted data."

**3. Enforce a semantic truncation boundary, not a byte cap.**

Byte-level caps are blind to structure. A JSON array with 500 records might serialize to 48KB and fit under a 50KB limit, but the last 400 records are semantically critical. Apply truncation at a semantic boundary instead:

```python
def semantic_truncate_tool_result(result: dict, max_output_tokens: int = 2000) -> dict:
    """Truncate at a semantic boundary — don't cut mid-record."""
    serialized = json.dumps(result)
    rough_tokens = len(serialized) // 4

    if rough_tokens <= max_output_tokens:
        return {"result": result, "_meta": {"truncated": False}}

    # For arrays: return full records up to token budget
    if isinstance(result, list):
        budget = max_output_tokens * 4  # chars
        truncated = []
        accumulated = 0
        for item in result:
            item_str = json.dumps(item)
            if accumulated + len(item_str) + 2 < budget:  # +2 for comma/bracket
                truncated.append(item)
                accumulated += len(item_str)
            else:
                break
        return {
            "result": truncated,
            "_meta": {
                "truncated": True,
                "records_returned": len(truncated),
                "records_omitted": len(result) - len(truncated),
                "original_size_tokens_approx": rough_tokens,
                "semantic_boundary": "complete-array-records",
            }
        }

    # For objects: return top-level keys within budget
    if isinstance(result, dict):
        budget = max_output_tokens * 4
        truncated = {}
        accumulated = 0
        for key, value in result.items():
            item_str = json.dumps({key: value})
            if accumulated + len(item_str) + 2 < budget:
                truncated[key] = value
                accumulated += len(item_str)
            else:
                break
        return {
            "result": truncated,
            "_meta": {
                "truncated": True,
                "keys_returned": list(truncated.keys()),
                "keys_omitted": len(result) - len(truncated),
                "original_size_tokens_approx": rough_tokens,
                "semantic_boundary": "complete-object-keys",
            }
        }

    # Fallback: rough character truncation
    return {
        "result": serialized[:max_output_tokens * 4],
        "_meta": {
            "truncated": True,
            "original_size_tokens_approx": rough_tokens,
            "semantic_boundary": "raw-character-truncation-warning",
            "warning": "Result was cut mid-structure. Do not assume completeness."
        }
    }
```

**4. Route to handler when truncation is severe.**

Not all truncations are equal. A 100-token tool result truncated to 50 tokens is a 50% evidence loss. A 100,000-token result truncated to 25,000 is a 75% evidence loss that may still contain sufficient signal. Set policy thresholds:

```python
TRUNCATION_SEVERITY = {
    "informational": 0.10,   # <10% lost: model can self-correct with _meta
    "significant": 0.50,     # 10–50% lost: inject warning + suggest re-call
    "critical": 0.90,        # >90% lost: block and require re-call or pagination
}

def handle_truncation(meta: dict) -> str:
    loss_ratio = meta["omitted_chars"] / (
        meta["original_size_chars"] + meta["omitted_chars"]
    )
    severity = next(
        (k for k, v in TRUNCATION_SEVERITY.items() if loss_ratio >= v),
        "informational"
    )
    if severity == "critical":
        raise TruncationError(
            f"Tool result truncated at {meta['truncation_boundary']} chars. "
            f"{meta['omitted_chars']:,} chars omitted (>90%). "
            f"Use pagination or streaming result delivery."
        )
    elif severity == "significant":
        return "warning: partial result, model should qualify conclusions"
    return "informational: model notified via _meta"
```

**5. Instrument the truncation boundary in your observability layer.**

Add a span attribute at the tool-result layer so you can query it in production:

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

def observed_tool_call(tool_name: str, raw_result: dict):
    wrapped = wrap_tool_result(raw_result)
    span = trace.get_current_span()
    span.set_attribute(f"tool.{tool_name}.truncated", wrapped["_meta"]["truncated"])
    span.set_attribute(f"tool.{tool_name}.original_tokens", wrapped["_meta"]["original_size_tokens_approx"])
    if wrapped["_meta"]["truncated"]:
        span.set_attribute(f"tool.{tool_name}.omitted_chars", wrapped["_meta"]["omitted_chars"])
        span.set_attribute("hazard:truncated_tool_result", True)
    return wrapped
```

In your observability dashboard, alert when `hazard:truncated_tool_result == true` co-occurs with `outcome: failure` or `outcome: quality_flag` — that correlation is the signal that silent truncation caused a production incident.

## Receipt

> Verified 2026-07-12 — Framework limits confirmed from: Claude Code (25k token tool result cap, ~700-char display cap per tianpan.co May 2026), OpenAI Codex (10 KiB / 256-line cap per GitHub issue #14466), OpenAI API (512 KB cap per dev.to Anhaia Mar 2026), Copilot CLI (10KB truncation before large-output mechanism per GitHub issue #1732, closed Mar 2026). The `_meta` wrapper and semantic truncation patterns are implemented in Python pseudocode; the core insight (truncation without model-visible marker = confident wrong answers) is confirmed across three independent sources. See: tianpan.co/blog/2026-05-10, dev.to/gabrielanhaia/tool-result-truncation, GitHub #1732, GitHub #14466, bytortuga.com/how-we-fixed-claude-codes-truncation-problem.

## See also

- [S-97 · Tool Result Summarization](s97-tool-result-summarization.md) — proactive LLM compression of oversized results (addresses the problem upstream)
- [S-130 · Structured Tool Result Compression](s130-structured-tool-result-compression.md) — code-only compression before deciding whether to invoke the LLM
- [S-121 · Context Window Utilization Monitor](s121-context-window-utilization-monitor.md) — proactive detection of context growth trajectory (context window overflow is the cousin failure mode)
- [S-02 · Context Budget](s02-context-budget.md) — token counting before you assume something fits
- [F-87 · Tool Call Argument Audit Log](f87-tool-call-argument-audit-log.md) — immutable record of what the agent was given to reason with
