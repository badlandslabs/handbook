# F-31 · Structured Call Logging

The API call returns a response. Most applications log that response as a string, or not at all. When something goes wrong three weeks later — wrong output, unexpected cost spike, latency regression — the debug record is gone. Structured call logging is the discipline of capturing a minimal, consistent record per call so that any production question can be answered from logs, not guesswork.

This is distinct from business attribution ([F-29](f29-cost-attribution.md)), which rolls up cost per feature/customer. Attribution answers "what did this feature cost?" Structured call logging answers "what happened on call X at timestamp Y, and why did it stop/fail?"

## Situation

A support agent starts returning oddly truncated responses in week three. Error rate in the monitoring dashboard is zero — the API returned 200. Nobody logs `stop_reason`. Nobody logs `latency_ms`. Reproducing the failure means re-running suspect inputs blind. With a 12-field log record per call, the investigation takes ten minutes: `WHERE stop_reason = 'max_tokens' AND feature = 'support'` shows 8% of calls hitting the output cap, starting on deploy day 18 when someone lowered `max_tokens` from 512 to 128 for a different feature and the config leaked.

## Forces

- `stop_reason` is the most-overlooked field in the API response. A 200 from the API does not mean a complete response. `max_tokens` (truncated), `tool_use` (yielded for a tool call), and `stop_sequence` (custom stop hit) all return 200 but mean different things. Logging the raw string costs nothing; missing it costs debugging hours.
- `request_id` and `trace_id` serve different purposes. The API's `request_id` uniquely identifies a single call — useful for provider support tickets. Your `trace_id` groups calls that belong to the same user action or agent run. You need both: one for per-call debug, one for end-to-end trace reconstruction.
- `latency_ms` catches provider slowdowns that surface as user complaints before they show up as errors. A call that returns 200 in 8 000 ms is not a success from the user's perspective.
- Error taxonomy must be application-defined. The API returns HTTP status codes; the application layer classifies causes. A 429 is `rate_limit`. A timeout before the first byte is `timeout`. A 200 with `stop_reason: max_tokens` where truncation breaks a downstream parse is `context_length` — the same taxonomy as a 400 from the model, from the application's perspective. Unifying these lets you query `WHERE error_type IS NOT NULL` for any degradation.
- Log overhead is minimal. At 258 bytes per record, 10 000 calls/day costs 2.58 MB/day. This fits in any logging system — no sampling, no aggregation needed at this scale.

## The move

**Wrap every model call to append an 11-field record. Log synchronously; do not drop on failure.**

**Canonical schema:**

```js
// Append this record per call, verbatim or adapted to your log sink
const logRecord = {
  request_id:    response.id,           // API-issued; use for provider support tickets
  trace_id:      ctx.traceId,           // your ID; groups calls in one agent run / user action
  model:         response.model,        // pin; catches accidental model drift
  input_tokens:  response.usage.input_tokens,
  output_tokens: response.usage.output_tokens,
  latency_ms:    Date.now() - startMs,
  stop_reason:   response.stop_reason,  // end_turn | max_tokens | tool_use | stop_sequence
  error_type:    null,                  // set in catch block; see taxonomy below
  feature:       ctx.feature,           // 'summarize' | 'draft' | 'triage' — from call site
  env:           process.env.NODE_ENV,
  ts:            new Date().toISOString(),
};
```

**Wrapper:**

```js
async function tracedCall(client, params, ctx) {
  const startMs = Date.now();
  let response, errorType = null;

  try {
    response = await client.messages.create(params);
  } catch (err) {
    errorType = classifyError(err);
    await callLog.append({ ...buildBaseRecord(params, ctx, startMs), error_type: errorType });
    throw err;
  }

  await callLog.append({
    request_id:    response.id,
    trace_id:      ctx.traceId,
    model:         response.model,
    input_tokens:  response.usage.input_tokens,
    output_tokens: response.usage.output_tokens,
    latency_ms:    Date.now() - startMs,
    stop_reason:   response.stop_reason,
    error_type:    null,
    feature:       ctx.feature,
    env:           process.env.NODE_ENV,
    ts:            new Date().toISOString(),
  });
  return response;
}

function classifyError(err) {
  if (err.status === 429) return 'rate_limit';
  if (err.status === 400 && err.message?.includes('context')) return 'context_length';
  if (err.code === 'ETIMEDOUT' || err.name === 'TimeoutError') return 'timeout';
  return 'api_error';
}
```

**`stop_reason` taxonomy:**

| Value | Meaning | Action |
|---|---|---|
| `end_turn` | Model finished naturally | Normal case |
| `max_tokens` | Output truncated at limit | Raise `max_tokens` or shorten prompt ([S-47](../stacks/s47-output-length-control.md)) |
| `tool_use` | Model yielded for tool call | Expected in agentic loops — resume with `tool_result` |
| `stop_sequence` | Custom stop token hit | Extraction pattern working correctly |

**`error_type` taxonomy (application-defined):**

| Value | Cause | Fix |
|---|---|---|
| `null` | Call succeeded | — |
| `timeout` | Wall-clock limit exceeded | Retry or route to async; check if input too large |
| `rate_limit` | RPM/TPM ceiling hit | Jitter-backoff ([F-20](f20-rate-limits-and-retry.md)) |
| `context_length` | Input exceeded model window | Pre-flight token check ([S-56](../stacks/s56-preflight-token-check.md)) |
| `api_error` | Provider 5xx | Retry with backoff; alert if sustained >5 min |

**Diagnostic query patterns:**

```
Truncation rate:         WHERE stop_reason="max_tokens" / total  — catches silent output cuts
P99 latency by model:   GROUP BY model → percentile(latency_ms, 0.99)
Error rate by feature:  WHERE error_type IS NOT NULL GROUP BY feature
Tool abandonment:       trace_id with tool_use events and no following end_turn
Cost by feature:        SUM(input_tokens + output_tokens) × price GROUP BY feature → see F-29
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Sample record built from realistic values; sizes measured directly.

```
=== Structured call logging: per-record overhead ===

Sample record (JSON, 11 fields):
{"request_id":"req_01Abc123Def456","trace_id":"trace_abc789","model":"claude-sonnet-4-6",
"input_tokens":847,"output_tokens":213,"latency_ms":1240,"stop_reason":"end_turn",
"error_type":null,"feature":"summarize","env":"production","ts":"2026-06-26T14:32:01Z"}

Size:         258 bytes / 86 tokens
10k calls/day: 2.58 MB/day
30 days:       77.4 MB/month

Storage cost at $0.023/GB-month (S3 standard): $0.002/month at 10k calls/day
  → effectively free; log every call, zero sampling

stop_reason values (Anthropic API):
  end_turn       → model finished naturally — normal case
  max_tokens     → truncated; increase max_tokens or shorten prompt (S-47)
  tool_use       → yielded for tool call; resume with tool_result
  stop_sequence  → custom stop token hit; extraction pattern working

Truncation scenario: max_tokens dropped 512→128 on deploy day 18
  Before: stop_reason="end_turn" 100% of calls
  After:  stop_reason="max_tokens" 8% of calls — caught by WHERE stop_reason="max_tokens"
```

## See also

[F-29](f29-cost-attribution.md) · [W-07](../workspace/w07-agent-span-tracing.md) · [W-05](../workspace/w05-llmops-observability.md) · [F-20](f20-rate-limits-and-retry.md) · [S-56](../stacks/s56-preflight-token-check.md) · [F-26](f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `structured logging` · `call logging` · `stop_reason` · `request_id` · `trace_id` · `latency_ms` · `error classification` · `max_tokens truncation` · `LLM observability` · `debug schema`
