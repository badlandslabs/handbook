# S-61 · Streaming Structured Output

[S-12](s12-streaming.md) covers streaming text to the browser. [S-04](s04-structured-output.md) covers getting JSON back from the model. Neither covers the combination: streaming a model call whose output is a tool call or JSON schema, where you need the output immediately for latency reasons but can't parse it until the stream ends. The gap is the accumulation pattern and the failure mode when the stream cuts off early.

## Situation

A coding assistant uses tool calls to return a structured action (`write_file`, `run_tests`, `edit_function`). Without streaming, the user sees nothing until the full tool call arrives — 1–3 seconds of blank screen. With streaming, you can show "Generating action: write_file..." as soon as the tool name arrives in `content_block_start`, and show the filling arguments as they stream in. But naive code that calls `JSON.parse` on each `input_json_delta` fragment throws on every event except the last one.

## Forces

- **Streaming adds zero tokens.** It's the same model call, same prompt, same output — just delivered incrementally via SSE. There is no cost premium for streaming structured output.
- **`input_json_delta` fragments are not valid JSON.** Each event carries a partial string (`partial_json`). Only the complete accumulated string — after `content_block_stop` fires — is parseable. Parse only at `content_block_stop`.
- **`max_tokens` during a tool call produces a broken JSON string.** If output is truncated, `stop_reason` becomes `max_tokens` and the accumulated `partial_json` string will be incomplete. `JSON.parse` throws. This is distinct from a text response being truncated — a truncated JSON payload is silently unusable if you don't check `stop_reason` first.
- **Text streaming and tool-call streaming use different delta types.** Text uses `content_block_delta` with `delta.type = "text_delta"` and `delta.text`. Tool calls use `content_block_delta` with `delta.type = "input_json_delta"` and `delta.partial_json`. A handler that treats all deltas as text will miss tool call arguments entirely.
- **The content block type arrives before any arguments.** `content_block_start` carries `content_block.type` ("tool_use" or "text"), `content_block.name` (the tool name), and `content_block.id`. You know what tool is being called before a single character of arguments arrives — use this for early UI feedback.

## The move

**Accumulate `partial_json` strings into a buffer. Check `stop_reason` before parsing. Parse only at `content_block_stop`.**

**Event sequence for a streaming tool call:**

```
message_start         → { message: { id, model, usage: { input_tokens } } }
content_block_start   → { content_block: { type: "tool_use", id, name: "send_email", input: {} } }
content_block_delta   → { delta: { type: "input_json_delta", partial_json: "{\"action\":" } }
content_block_delta   → { delta: { type: "input_json_delta", partial_json: "\"send_email\"" } }
... (N more input_json_delta events)
content_block_stop    → {}  ← parse accumulated JSON here
message_delta         → { delta: { stop_reason: "tool_use" | "max_tokens", usage: { output_tokens } } }
message_stop          → {}
```

**Accumulation handler:**

```js
async function streamToolCall(client, messages, tools) {
  const toolBuffers = {};   // tool_use_id → accumulated partial_json string
  const toolNames   = {};   // tool_use_id → tool name
  let stopReason    = null;

  const stream = await client.messages.create({
    model:      'claude-sonnet-4-6',
    max_tokens: 1024,
    tools,
    messages,
    stream:     true,
  });

  for await (const event of stream) {
    switch (event.type) {
      case 'content_block_start':
        if (event.content_block.type === 'tool_use') {
          toolBuffers[event.content_block.id] = '';
          toolNames[event.content_block.id]   = event.content_block.name;
          // UI: show tool name immediately — arguments follow
          onToolStart?.(event.content_block.name);
        }
        break;

      case 'content_block_delta':
        if (event.delta.type === 'input_json_delta') {
          toolBuffers[event.index] ??= '';
          // Find the buffer by scanning (index maps to content_block order)
          const id = Object.keys(toolBuffers)[event.index] ?? event.index;
          toolBuffers[id] += event.delta.partial_json;
        } else if (event.delta.type === 'text_delta') {
          onTextDelta?.(event.delta.text);  // handle text streaming separately
        }
        break;

      case 'message_delta':
        stopReason = event.delta.stop_reason;
        break;
    }
  }

  // Only parse after stream ends; check stop_reason first
  if (stopReason === 'max_tokens') {
    // Accumulated partial_json is incomplete — do not parse
    throw new Error('Tool call truncated by max_tokens. Increase max_tokens or shorten the input.');
  }

  return Object.entries(toolBuffers).map(([id, json]) => ({
    id,
    name:  toolNames[id],
    input: JSON.parse(json),  // safe: only reached when stop_reason !== max_tokens
  }));
}
```

**Simpler pattern (SDK `stream` helper):**

```js
// The Anthropic Node SDK's stream helper handles accumulation internally
const stream = client.messages.stream({ model, max_tokens: 1024, tools, messages });

// Text delta events (for mixed text + tool-use responses)
stream.on('text', (text) => process.stdout.write(text));

// Tool call available after stream ends — SDK accumulated input_json_delta internally
const message = await stream.finalMessage();
const toolUseBlocks = message.content.filter(b => b.type === 'tool_use');
// toolUseBlocks[0].input is already parsed JSON — SDK did the accumulation
```

The SDK helper is correct for most cases. Use the raw event loop above only when you need mid-stream UI updates (showing tool name before arguments arrive) or fine-grained error handling.

**For text responses (not tool calls):**

```js
// text_delta events: safe to display immediately
stream.on('text', chunk => uiAppend(chunk));

// Don't parse streaming text as JSON; wait for finalMessage() if you need the full string
const finalText = await stream.finalText();
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Tool call payload: `send_email` action with 5 fields. Event sequence follows Anthropic streaming API documentation (verified structure; actual chunk boundaries vary by provider load).

```
=== Streaming structured output: accumulation pattern ===

Final JSON payload: 212 chars / 50 tokens
Simulated input_json_delta events: 15
Successful JSON.parse calls before content_block_stop: 1 (only the last chunk)
  → Parsing on every delta throws 14/15 times — wait for content_block_stop

Token overhead vs non-streaming: 0 tokens
  Tool definition: 70 tokens (identical whether streaming or not)
  Tool output:     50 tokens (identical — same model output, different delivery)

=== Early truncation (stop_reason: max_tokens) ===

Partial JSON accumulated: {"action":"send_email","to":"alice@example.com","subject":"Invoice
JSON.parse throws: Unterminated string in JSON at position 66
Correct handling: check stop_reason BEFORE parse; throw/fallback if max_tokens
```

In 15 streaming events, only 1 produces valid JSON — the final fragment. Parsing on every delta isn't just unnecessary; it produces 14 silent `try/catch` swallows or unhandled exceptions if not guarded. Parse at `content_block_stop` only.

## See also

[S-12](s12-streaming.md) · [S-04](s04-structured-output.md) · [S-55](s55-parallel-tool-calls.md) · [S-51](s51-tool-schema-design.md) · [S-47](s47-output-length-control.md)

## Go deeper

Keywords: `streaming structured output` · `input_json_delta` · `content_block_delta` · `tool call streaming` · `partial JSON` · `SSE tool use` · `stream accumulation` · `content_block_stop` · `stop_reason max_tokens`
