# S-12 · Streaming Response Delivery

Get tokens to the user as they generate — or don't, if code is reading the output.

## Forces
- Users perceive streamed output as faster even when total latency is identical
- SSE holds one socket per open connection; under load this exhausts connection pools
- Streaming adds incremental-parsing complexity with zero benefit when downstream code processes the response
- Bidirectional multi-agent coordination needs more than SSE can carry

## The move

**The decision rule first: stream to humans, don't stream to code.**

If a person is watching the output arrive, stream. If your next line of code parses the response — JSON extraction, entity detection, classification, tool call arguments — wait for the complete response. Streaming buys you nothing and adds an incremental-parsing problem you don't need.

---

### SSE for human-facing delivery

Server-Sent Events over `text/event-stream` is the production standard for single-direction streaming. Use `fetch` + `ReadableStream`, not `EventSource` — `EventSource` is GET-only and most agent APIs require POST.

The correct client library: `@microsoft/fetch-event-source` (handles POST, reconnect, and auth headers correctly).

```python
# Anthropic SDK — illustrative, not run-verified
import anthropic

client = anthropic.Anthropic()

with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

Server side: set `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`. Each chunk: `data: <token>\n\n`.

**Connection pool caution:** each open SSE connection holds a socket. At scale, fan-out to many simultaneous users exhausts the pool. Enforce a connection limit and shed gracefully.

---

### WebSockets for bidirectional / multi-agent

When agents need to push state back upstream — tool results, plan steps, agent-to-agent messages — SSE is one-way and can't carry it. Switch to WebSockets.

Google ADK (mid-2026) runs streaming-native-first multi-agent systems on bidirectional WebSocket connections for exactly this reason.

---

### AG-UI / A2UI (emerging, mid-2026)

Raw token streams are coarse. AG-UI and A2UI are emerging protocols that carry structured agent state events over the same stream: `tool_start`, `tool_end`, `plan_step`. These let the client render tool-call progress and plan status — not just text — without polling a separate endpoint. Still settling; check project docs before adopting.

## Receipt

> Verified 2026-06-25 — streaming run against llama3.2 via Ollama (localhost:11435) using the Anthropic Node SDK.

```
Stream output: 1
2
3
4
5

STATUS: DONE
FILES_TOUCHED: none
BLOCKERS:
Tokens: in=101 out=25 stop=end_turn
```

Streaming works. 101 input / 25 output tokens for a count-to-5 task.

**Warning from the receipt:** llama3.2 appended `STATUS: DONE / FILES_TOUCHED: none / BLOCKERS:` noise after its answer — system prompt template leakage from the model's training data. Local models may inject unexpected suffixes into streamed output. Always terminate the stream at a natural boundary, not by assuming the last token is clean. Hosted frontier models (Claude, GPT) don't exhibit this.

## See also
[S-04](s04-structured-output.md) · [S-05](s05-multi-agent-patterns.md) · [F-03](../forward-deployed/f03-failure-modes.md) · [S-35](s35-latency-budget.md)

## Go deeper
Keywords: `SSE` · `Server-Sent Events` · `@microsoft/fetch-event-source` · `ReadableStream` · `AG-UI` · `A2UI` · `Google ADK` · `WebSocket streaming`
