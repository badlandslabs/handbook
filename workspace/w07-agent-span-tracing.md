# W-07 · Agent Span Tracing

An agent run fails. You have the final output — wrong answer, empty result, crash. Without spans, you have no idea what the model received at step 2, what the tool returned at step 3, or which call burned 80% of the latency. A run-level log tells you the outcome; spans tell you the story.

## Forces

- Agent failures are non-deterministic — the same bug may appear once per thousand runs; you need the trace from that specific run, not a replay
- Three operation types fail for different reasons: LLM calls fail on bad input or cost; tool calls fail on network or bad args; routing decisions fail silently (wrong branch, wrong tool)
- A single token total hides everything — you need per-call counts to know where budget went
- Multi-step agents compound: a problem in step 3 was often planted in step 1's output; trace context is the only way to see the chain
- Latency attribution is impossible without per-span timing — you can't optimize what you can't locate

## The move

Emit a **span** for every operation; attach every span to a shared `trace_id`.

**Three span types:**

| Operation | Required attributes |
|---|---|
| `llm.*` | model, input\_tokens, output\_tokens, duration\_ms, prompt hash (optional) |
| `tool.*` | tool\_name, args, result, success, duration\_ms |
| `agent.*` | decision, chosen\_branch, reasoning (if available), duration\_ms |

**Implementation pattern:**
```js
const TRACE_ID = `trace-${Date.now().toString(36)}`;

function startSpan(name, attrs = {}) {
  return { trace_id: TRACE_ID, span_id: `span-${++seq}`, name, start_ms: Date.now(), ...attrs };
}
function endSpan(span, result = {}) {
  span.duration_ms = Date.now() - span.start_ms;
  Object.assign(span, result);
}
```

Call `startSpan` before each operation; call `endSpan` after. Emit to `console.log` in development; pipe to an OTel collector in production.

**Attribute names:** follow OTel GenAI semantic conventions (`gen_ai.usage.input_tokens`, `gen_ai.request.model`, etc.) — this makes spans compatible with Arize Phoenix, Langfuse, and any OTel-native backend without vendor lock-in.

**Log both sides of every tool call.** Record the raw proposal *and* the result. Proposal-only logs hide what was rejected; result-only logs hide what the model asked for.

## Receipt

> Verified 2026-06-26 — llama3.2 via Ollama (localhost:11435). Two-step support agent: classify ticket → lookup order → draft reply. Three spans emitted and linked to one trace.

```
Trace: trace-mqulcb6t

[span-1] llm.classify       in=2581  out=20   (1887ms)
[span-2] tool.lookup_order  args={"order_id":"ORD-5521"}  success=true  (0ms)
[span-3] llm.draft_reply    in=2582  out=179  (4675ms)

total_tokens: 5362  (in=5163  out=199)
total_ms:     6562
```

**Full span-1 (JSON):**
```json
{
  "trace_id": "trace-mqulcb6t",
  "span_id": "span-1",
  "name": "llm.classify",
  "gen_ai.request.model": "llama3.2",
  "gen_ai.usage.input_tokens": 2581,
  "gen_ai.usage.output_tokens": 20,
  "duration_ms": 1887,
  "gen_ai.response.text": "{\"order_id\": \"ORD-5521\", \"intent\": \"shipping_status_inquiry\"}"
}
```

**What the spans revealed that the total couldn't:**
- span-1 used only 20 output tokens — the classify step was cheap; do not optimize it
- span-3 used 179 output tokens and took 4,675ms — nearly all wall-clock time and most output cost lived here
- span-2 took 0ms (in-process lookup); replace with an external API call and this span immediately surfaces any latency regression
- Without per-span breakdown, the total (5,362 tokens, 6,562ms) gives no signal on where to look

## See also

[W-04](w04-observability.md) · [W-05](w05-llmops-observability.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [F-11](../forward-deployed/f11-agent-reliability.md) · [F-16](../forward-deployed/f16-tool-call-validation.md)

## Go deeper

Keywords: `OpenTelemetry GenAI semantic conventions` · `OTel spans` · `Arize Phoenix` · `Langfuse` · `distributed tracing` · `LLM observability` · `agent debugging`
