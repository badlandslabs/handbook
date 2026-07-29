# S-1834 · The Partial-Output Termination Stack — When Your Agent Confidently Completes a Task It Only Half Did

Your database query returns the first 1,000 rows of 47,000. The LLM sees rows. It sees data. It never sees the word "truncated." It summarizes the results, reports the finding, and routes 9,000 customers to the wrong tier — because the outlier segment was in rows 1,001 through 47,000. No error. No exception. Just confident completion of an incomplete task. This is partial-output termination: the agent's most dangerous failure mode because it looks identical to success.

## Forces

- **The LLM sees data, not metadata.** A tool response with 1,000 rows looks identical to one with 47,000 rows inside the context window — unless the response includes a length header. The agent has no native signal for "you only have part of this."
- **Context overflow produces three distinct failure modes, only one of which is visible.** Hard context errors stop the task cleanly. Silent truncation lets the agent proceed on partial data and produce confident wrong answers. Degraded output causes the model to drop mid-reasoning with no indication that the input was incomplete.
- **Standard tool design hides the boundary.** Most tool schemas define output structure (the shape of each row) but omit metadata (how many rows exist, what fraction is returned, whether the result is complete). The agent infers completeness from the absence of error — a heuristic that fails whenever truncation is silent.
- **The cost asymmetry is brutal.** A task that completes incorrectly on truncated data costs the same as one that completed correctly. And the wrong answer often looks better than silence — the agent is more likely to report "here is the summary" than "I could not see all the data."

## The Move

Three patterns work together: **output-length signaling**, **completion-token injection**, and **progressive tool results** (S-108).

### 1. Output-Length Signaling

Every tool response includes metadata the LLM can read — not embedded in prose, but as structured header fields the model learns to recognize:

```python
# Tool response wrapper
def query_customers(filters: dict) -> dict:
    results = db.execute("SELECT * FROM customers WHERE ...", **filters)
    total = len(results)
    returned = len(results[:MAX_ROWS])

    return {
        "_meta": {
            "total_rows": total,
            "returned_rows": returned,
            "complete": total <= MAX_ROWS,
            "overflow_rows": max(0, total - MAX_ROWS),
            "sample_available": returned > 0
        },
        "data": results[:MAX_ROWS].to_dict(orient="records")
    }
```

The `_meta` block is the termination signal. If `complete` is `false` or `overflow_rows > 0`, the agent knows it has a partial result. If `total_rows` is not present, the agent knows the tool does not provide length signaling — and should treat all results with lower confidence.

### 2. Completion-Token Injection

For LLM providers that support it, detect truncation at the API level and inject a termination marker:

```python
import anthropic

def call_with_truncation_detection(
    client, model, system_prompt, max_output_tokens: int = 4096
) -> tuple[str, dict]:
    response = client.messages.create(
        model=model,
        system=system_prompt,
        max_tokens=max_output_tokens,
        # Request stop-reason metadata
    )

    truncated = response.stop_reason == "max_tokens"
    meta = {
        "truncated": truncated,
        "tokens_used": response.usage.output_tokens,
        "stop_reason": response.stop_reason
    }

    if truncated:
        # Append explicit termination signal the model trained to recognize
        body = response.content[0].text + "\n\n[OUTPUT TRUNCATED — continuation may be needed]"
        return body, meta

    return response.content[0].text, meta
```

### 3. Progressive Tool Results (S-108 Cross-Reference)

For tools returning large datasets, follow the progressive tool results pattern. Return a continuation token instead of truncating:

```python
def query_with_continuation(filters: dict, cursor: str | None = None) -> dict:
    page_size = 500
    results, next_cursor = db.execute_page(
        "SELECT ...", page_size=page_size, cursor=cursor
    )

    return {
        "_meta": {"complete": next_cursor is None, "continuation": next_cursor},
        "data": results.to_dict(orient="records")
    }

# Agent loop:
result = query_with_continuation(filters)
while not result["_meta"]["complete"]:
    continuation = result["_meta"]["continuation"]
    next_page = query_with_continuation(filters, cursor=continuation)
    result["data"].extend(next_page["data"])
    if result["_meta"]["complete"]:
        break
    if len(result["data"]) >= task_row_limit:
        result["_meta"]["capped"] = True
        break
```

### 4. The Agent-Side Awareness Pattern

Even with metadata, the agent needs to be prompted to check it:

```python
SYSTEM_PROMPT += """

TOOL RESPONSE RULES:
- Every structured tool response includes a `_meta` field.
- If `_meta.complete == false`, the result is PARTIAL.
  You MUST acknowledge partial results explicitly: "Based on {returned_rows} of {total_rows} records..."
- If `_meta` is absent, treat the result as potentially partial and flag it.
- Never report a count as the total if you only have a sample.
"""
```

## Receipt

> Receipt pending — 2026-07-29. The `_meta` signaling pattern and completion-token detection are production-tested at multiple teams. The progressive tool results loop is the pattern from S-108 with agent-awareness constraints layered on top. No live benchmark yet; running against synthetic truncation test suite (agent receives first 500 of 50,000 rows, measures whether it correctly reports partialness).

## See also

- [S-108 · Progressive Tool Results](s108-progressive-tool-results.md) — the pagination design pattern this extends
- [S-1831 · The Agent Trajectory Evaluation Stack](s1831-the-agent-trajectory-evaluation-stack-when-your-agent-passes-all-checks-and-still-fails-in-production.md) — why endpoint-only eval misses mid-trajectory data corruption
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — partial execution and silent corruption patterns
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — handoff completeness checking (analogous problem, different layer)
