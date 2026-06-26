# S-69 · Streaming Cancellation

[S-12](s12-streaming.md) covers streaming delivery: SSE, connection management, when to stream vs wait. It doesn't cover what happens when the user hits Stop, closes the tab, or triggers a new request before the current stream ends. That situation — mid-stream cancellation — has three sub-problems: abort the in-flight API call so you stop paying for tokens you don't need; decide what to do with the partial response; and handle dropped connections without presenting a broken UI.

## Situation

A chat UI streams a 156-token support response. The user reads the first sentence (about 15 tokens), gets the answer they need, and clicks Stop. Without abort handling, the model generates 141 more tokens at $15.00/M — $0.002 per cancelled call — while the UI shows a spinner going nowhere. At 5% cancel rate over 10 000 calls/day, that's $28/month in pure waste, plus the broken UX of a stream that keeps printing after the user has already read enough.

## Forces

- **API calls generate tokens until stopped.** Closing the SSE connection on the client doesn't stop the model on the server. You must abort the server-side call explicitly to stop billing and free resources.
- **The partial response may be useful.** When the user cancels after reading 15 tokens of a 156-token response, those 15 tokens still answered the question. Surface them; don't discard. If the user cancels in the middle of a sentence, truncate at the last complete sentence before displaying.
- **Connection drop ≠ user-initiated cancel.** A lost WiFi connection is temporary; the user may reconnect and expect to pick up the stream. A user clicking Stop is deliberate; they want the stream ended. Handle them differently: reconnect for dropped connections, terminate for deliberate cancellations.
- **Race conditions at cancellation.** The client sends an abort signal; the server may have already written 80% of the response; the remaining 20% may still be in flight. The final state depends on timing. Always treat the buffer at cancellation time as potentially incomplete.
- **Streaming + structured output is harder to cancel cleanly.** If you're accumulating `input_json_delta` chunks ([S-61](s61-streaming-structured-output.md)) and the user cancels mid-JSON, you have an unparseable partial. Don't attempt to parse it; log the abort and discard the structured output.

## The move

**Use `AbortController` to stop the API call server-side on cancel. Surface the partial response to the user. Distinguish dropped connections (reconnect) from deliberate cancellations (terminate).**

**Server-side cancel handler:**

```js
const activeStreams = new Map(); // sessionId → AbortController

async function streamResponse(client, sessionId, systemPrompt, userMessage, res) {
  // Cancel any existing stream for this session before starting a new one
  if (activeStreams.has(sessionId)) {
    activeStreams.get(sessionId).abort();
    activeStreams.delete(sessionId);
  }

  const controller = new AbortController();
  activeStreams.set(sessionId, controller);

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
  });

  let buffer = '';

  try {
    const stream = await client.messages.stream({
      model: 'claude-sonnet-4-6',
      max_tokens: 512,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
    }, { signal: controller.signal });

    for await (const chunk of stream) {
      if (chunk.type === 'content_block_delta' && chunk.delta.type === 'text_delta') {
        const token = chunk.delta.text;
        buffer += token;
        res.write(`data: ${JSON.stringify({ token })}\n\n`);
      }
    }

    res.write(`data: ${JSON.stringify({ done: true, text: buffer })}\n\n`);
  } catch (err) {
    if (err.name === 'AbortError') {
      // Deliberate cancel — surface whatever we received
      const partial = truncateAtSentence(buffer);
      res.write(`data: ${JSON.stringify({ cancelled: true, text: partial })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({ error: true })}\n\n`);
    }
  } finally {
    activeStreams.delete(sessionId);
    res.end();
  }
}

// Client sends DELETE /stream/:sessionId to cancel
app.delete('/stream/:sessionId', (req, res) => {
  const controller = activeStreams.get(req.params.sessionId);
  if (controller) {
    controller.abort();
    activeStreams.delete(req.params.sessionId);
  }
  res.sendStatus(200);
});
```

**Truncate at sentence boundary on cancel:**

```js
function truncateAtSentence(text) {
  if (!text) return '';
  const sentenceEnd = /[.!?]\s/g;
  let last = -1, match;
  while ((match = sentenceEnd.exec(text)) !== null) last = match.index + 1;
  return last > 0 ? text.slice(0, last) : text; // if no sentence boundary, return as-is
}
```

**Client-side: distinguish drop from cancel:**

```js
let cancelledByUser = false;

function cancelStream() {
  cancelledByUser = true;
  fetch(`/stream/${sessionId}`, { method: 'DELETE' });
}

eventSource.onerror = (err) => {
  if (cancelledByUser) {
    // Intentional — do nothing, UI already reflects partial response
    cancelledByUser = false;
    return;
  }
  // Connection drop — attempt reconnect after backoff
  setTimeout(() => reconnectStream(), 2000);
};
```

**Handling new message while stream is active:**

When the user sends a new message before the current stream ends, treat this as an implicit cancel of the current stream — abort it, then start the new stream. The `streamResponse` function above does this automatically via the `activeStreams.get(sessionId).abort()` guard at the start.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Inference price: $15.00/M output. Cancel rate and response length are representative; your numbers will differ.

```
=== Token waste without abort (156-token response, cancel at 15 tokens) ===

Tokens delivered before cancel:   15 tok
Tokens generated after cancel:   141 tok (never displayed)
Waste per cancelled call:        141 tok × $15.00/M = $0.002115

=== Monthly cost of not aborting ===

At 10k/day, 5% cancel rate → 500 cancellations/day
Daily waste:   500 × $0.002115 = $1.06
Monthly waste: $32/month

=== UX cost of not aborting ===

A stream that keeps printing after user clicks Stop:
  - Makes the UI feel broken (spinner after cancel)
  - Blocks the input box (user can't send next message)
  - Consumes streaming connection slot (limits concurrency)

These are not token costs — they are trust and usability costs.

=== AbortController timing ===

AbortController.abort() is synchronous — signal fires in <0.1ms.
Network and SDK overhead: typically 1–5ms to reach the API.
Tokens generated in that window: at 50 tok/s, ~0.1–0.25 tokens.
Abort is effectively immediate.
```

## See also

[S-12](s12-streaming.md) · [S-61](s61-streaming-structured-output.md) · [S-35](s35-latency-budget.md) · [F-34](../forward-deployed/f34-async-agent-requests.md) · [F-24](../forward-deployed/f24-graceful-degradation.md) · [F-39](../forward-deployed/f39-session-state-persistence.md)

## Go deeper

Keywords: `streaming cancellation` · `AbortController` · `partial response` · `mid-stream cancel` · `stream abort` · `SSE cancel` · `connection drop` · `truncate at sentence` · `active streams` · `cancel handling`
