# S-182 · Streaming Output Budget Gate

[S-47](s47-output-length-control.md) controls output length on the prompt side: `max_tokens` and explicit length instructions prevent the model from starting a long response. [S-177](s177-output-length-overrun-gate.md) runs after the complete response arrives: it compares the total token count to a per-call-type contract and takes action (TRIM, WARN, or FAIL). Neither pattern intervenes during generation.

Streaming responses change the economics. When the model streams via SSE or the Anthropic SDK's `.stream()`, tokens arrive incrementally. By the time S-177 runs, every token has already been generated and billed. If the model generates 400 tokens on a 300-token extraction contract, you are billed for 400 tokens and then S-177 trims the result — the 100 overrun tokens were paid for and discarded.

The streaming output budget gate runs inline with each delta event. It counts tokens as they arrive, and when the running count exceeds the per-call-type contract, it calls `AbortController.abort()` to cancel the stream before more tokens are generated. The tokens generated after the abort are not billed. For calls where the model reliably overruns its contract (verbose classification explanations, tool-result-injected summarization going long), the in-stream abort is the only pattern that prevents payment for overrun tokens.

This is distinct from S-69 (streaming cancellation), which covers user-initiated cancel — a user who clicks "stop" while reading the response. S-182 is system-level: the orchestration layer enforces a per-call-type token contract and aborts automatically without user involvement.

## Situation

Three call types in a contract pipeline:

**Extraction** (300-token contract): compact JSON output. A well-prompted model stays under 300 tokens. Occasionally the model adds verbose `_source` and `_confidence` fields not in the schema; without the gate these verbose responses are billed at 355+ tokens.

**Classification** (50-token contract): should return a single word or short phrase. Without guidance, a verbose model generates 95 tokens of explanation before stating the class. The gate fires at token 52 and aborts — the remaining 43 tokens are never generated.

**Freeform** (800-token contract, WARN action): drafting may legitimately vary. The gate warns at overrun but does not abort.

At 10 000 calls/day with a 5% overrun rate and 100 tokens saved per aborted call: $0.20/day savings ($73/year) at Haiku output pricing. The real value is latency: aborting a 400-token response at token 300 also cuts 25% of the streaming latency for that call. Both S-177 and S-182 belong in the pipeline — S-182 aborts streaming calls mid-stream; S-177 handles non-streaming calls after the fact.

## Forces

- **Only stream calls benefit from in-stream abort.** For non-streaming calls (`create()` not `.stream()`), the full response is returned at once. S-177 is the right gate for non-streaming. Use S-182 only when you have a streaming connection and can attach an `AbortController` to the API call.
- **The contracted budget must be set below `max_tokens`.** `max_tokens` is the hard API ceiling — the model stops generating there regardless. The streaming contract is a softer limit, enforced by the gate and calibrated from observed p95 output lengths (measure with S-143 before setting). If the contract equals `max_tokens`, the gate fires simultaneously with the API's own truncation and adds no value.
- **WARN-only for output types where truncation corrupts the result.** A mid-stream abort produces a partial response. For JSON extraction, an aborted stream is invalid JSON — the ABORT action should only be taken when the caller can detect and handle a truncated output (retry with a stricter length instruction). For prose outputs (freeform, explanation), truncation at a sentence boundary is acceptable; set action to WARN and log rather than abort.
- **onDelta() overhead must be sub-millisecond.** The gate runs on every SSE event — potentially hundreds per call. At 0.0000 ms per delta (pure integer arithmetic), the gate adds no measurable latency to the streaming session. If you add heavier per-delta work (JSON parsing, regex), profile it.
- **Report aborted-at token count for diagnostics.** When a stream is aborted, record `abortedAt` (the token count at abort) and the call type. If a call type consistently aborts at 105% of its contract, the contract is too tight — raise it or improve the prompt. If it aborts at 200%, the prompt is missing a length constraint — add one.

## The move

**For each streaming delta, count tokens and check against the per-call-type contract. Call `abortController.abort()` when the running count exceeds the limit. Set action to WARN for prose types where truncation corrupts the output.**

```js
// --- Streaming output budget gate ---
// Runs inline with each streaming delta event.
// Aborts the stream before more tokens are generated when budget is exceeded.
// Distinct from S-177 (post-call gate for non-streaming) and S-69 (user-initiated cancel).
// Compose: attach AbortController to API call; pass controller to gate; call onDelta() per chunk.

function estimateTokens(text) { return Math.ceil(text.length / 4); }

const STREAMING_CONTRACTS = {
  extraction:     { contractedMax: 300, action: 'ABORT' },
  summarization:  { contractedMax: 500, action: 'ABORT' },
  classification: { contractedMax:  50, action: 'ABORT' },
  freeform:       { contractedMax: 800, action: 'WARN'  },
};

class StreamingOutputBudgetGate {
  constructor(callType) {
    this._contract   = STREAMING_CONTRACTS[callType] || { contractedMax: 400, action: 'WARN' };
    this._callType   = callType;
    this._tokenCount = 0;
    this._aborted    = false;
  }

  onDelta(delta) {
    if (this._aborted) return { status: 'ALREADY_ABORTED', tokenCount: this._tokenCount };
    this._tokenCount += estimateTokens(delta);

    if (this._tokenCount > this._contract.contractedMax) {
      this._aborted = true;
      return {
        status:        'BUDGET_EXCEEDED',
        action:        this._contract.action,
        callType:      this._callType,
        tokenCount:    this._tokenCount,
        contractedMax: this._contract.contractedMax,
        overrun:       this._tokenCount - this._contract.contractedMax,
        shouldAbort:   this._contract.action === 'ABORT',
      };
    }
    return { status: 'OK', tokenCount: this._tokenCount,
             remaining: this._contract.contractedMax - this._tokenCount };
  }
}

// Integration with Anthropic SDK streaming:
// const controller = new AbortController();
// const gate = new StreamingOutputBudgetGate('extraction');
// const stream = await client.messages.stream({ ... }, { signal: controller.signal });
// for await (const event of stream) {
//   if (event.type === 'content_block_delta') {
//     const result = gate.onDelta(event.delta.text || '');
//     if (result.shouldAbort) { controller.abort(); break; }
//   }
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Mock streaming via string chunking (chunk size 10–20 chars). `onDelta()` timed over 1 000 000 iterations. Zero API calls.

```
=== Streaming Output Budget Gate ===

--- Scenario A: extraction within contract (39 tok, max=300) ---
  Total: 39 tok  contractedMax=300  aborted=false

--- Scenario B: extraction overruns contract (verbose model with _source fields) ---
  BUDGET_EXCEEDED at delta 61: tokenCount=305  contractedMax=300  overrun=5
  action=ABORT  shouldAbort=true
  → stream aborted via AbortController.abort()
  Aborted at: 305 tok (contracted max: 300)

--- Scenario C: classification (50-tok contract) — verbose explanation output ---
  BUDGET_EXCEEDED at delta 13: tokenCount=52  contractedMax=50
  action=ABORT  shouldAbort=true
  Aborted at 52 tok.
  Model was generating 95 tok total — saved ~43 tok (45%)

=== S-177 vs S-182 ===
S-177 (post-call):     detects overrun after all tokens generated and billed — no token savings
S-182 (streaming):     aborts mid-stream — overrun tokens never generated, never billed
Use both: S-182 for streaming calls; S-177 for non-streaming calls and as final audit

=== Cost model: 10 000 calls/day, 5% overrun rate, avg 100 tok saved per abort ===
S-182 savings: $0.20/day  ($73/year) at Haiku output pricing ($4.00/M)
Latency benefit: aborting at token 300 on a 400-tok response saves 25% streaming time

=== Timing (1 000 000 onDelta() calls) ===
onDelta() per streaming chunk: < 0.0001 ms
Negligible overhead — pure integer arithmetic, no allocation.
```

## See also

[S-177](s177-output-length-overrun-gate.md) · [S-47](s47-output-length-control.md) · [S-69](s69-streaming-cancellation.md) · [S-61](s61-streaming-structured-output.md) · [S-139](s139-max-tokens-by-task-type.md)

## Go deeper

Keywords: `streaming output budget gate` · `streaming token budget abort` · `mid-stream abort token budget` · `SSE token counting gate` · `streaming output cost control` · `AbortController token limit` · `streaming output overrun prevention` · `real-time token budget` · `streaming response budget gate` · `LLM streaming abort budget`
