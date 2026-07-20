# S-1374 · The Agent Streaming Event Protocol: When Your Agent Runs Silent for 20 Seconds and Your Users Abandon It

Your agent is doing real work — researching, calling tools, reasoning through a 6-step plan. The user clicked submit and is staring at a spinner. They don't know if it's working, which step it's on, or whether it will finish. They refresh. They start over. They file a bug. This is not a UX problem. It is a **streaming architecture problem**.

## Forces

- **The black-box wait.** Agents take 30 seconds to 5 minutes on complex tasks. A blank screen drives abandonment even when the agent is healthy.
- **Token streaming is table stakes.** Users now expect to see words arrive in real time — but for agents, tokens are the least interesting part of what's happening.
- **The multi-channel problem.** Real-time agent UX needs tokens + tool calls + thinking blocks + progress + done — four fundamentally different event types on one stream.
- **Chunk-boundary parsing.** SSE `event:` and `data:` lines can arrive in different TCP chunks. Hand-rolled parsers silently drop events at chunk boundaries — usually discovered in production at 2am.
- **Proxy interference.** Zscaler and other SSL-inspecting corporate proxies break SSE over HTTPS, silently dropping streams. Detection requires a synthetic `done` event with a timeout.
- **Token batching vs. rendering thrash.** Fast models emit 30-40 text chunks/second. Without batching, React re-renders on every chunk. With batching (50ms flush interval), ~20 renders/second — a 2x improvement in UI smoothness.

## The move

**Use a structured multi-channel SSE event protocol.** The stream carries five event types, each with a consistent schema. The client routes each event type to the appropriate UI renderer.

### Event schema

```json
// Token stream — raw text fragments
{"t": 0.052, "event": "token", "data": {"text": "Hello"}}

// Tool invocation — emitted when the agent decides to call a tool
{"t": 0.894, "event": "tool_use", "data": {
  "tool_name": "search",
  "tool_version": "1.2",
  "arguments": {"query": "llm evaluation 2026"},
  "tool_call_id": "tc_7f3a"
}}

// Tool result — emitted when the tool returns
{"t": 1.736, "event": "tool_result", "data": {
  "tool_call_id": "tc_7f3a",
  "duration_ms": 842,
  "success": true,
  "output_size_bytes": 4821
}}

// Thinking block — the agent's reasoning trace
{"t": 0.201, "event": "thinking", "data": {
  "block_id": "th_2b1c",
  "text": "The user wants me to research... I should start with a search query...",
  "finished": false
}}

// Progress update — human-readable step indicator
{"t": 0.100, "event": "progress", "data": {
  "step": 2,
  "total_steps": 6,
  "label": "Searching for relevant papers",
  "percent": 33
}}

// Done — stream termination with final summary
{"t": 8.204, "event": "done", "data": {
  "num_turns": 1,
  "total_tokens": 4821,
  "tool_calls": 3,
  "duration_ms": 8204,
  "success": true,
  "error": null
}}
```

### Token batching on the client

```python
from collections import deque

class TokenBatcher:
    def __init__(self, interval_ms: int = 50):
        self.interval_ms = interval_ms
        self.buffer = deque()
        self.timer = None

    def push(self, text: str):
        self.buffer.append(text)

    async def flush(self):
        if not self.buffer:
            return
        combined = "".join(self.buffer)
        self.buffer.clear()
        await self.render(combined)

    async def render(self, text: str):
        # Batched DOM update — one render per 50ms interval, not per token
        pass
```

Without batching: 40 renders/second → CPU thrash and dropped frames.
With 50ms batching: 20 renders/second → smooth UX.

### Chunk-boundary resilience

SSE events can span TCP segments. Track the partial event state:

```javascript
let currentEventType = null;
let partialLine = "";

socket.on('data', (chunk) => {
  const lines = (partialLine + chunk.toString()).split('\n');
  partialLine = lines.pop(); // incomplete line — carry forward

  for (const line of lines) {
    if (line.startsWith('event:')) {
      currentEventType = line.slice(6).trim();
    } else if (line.startsWith('data:') && currentEventType) {
      const data = JSON.parse(line.slice(5).trim());
      this.route(currentEventType, data);
    }
  }
});
```

Every hand-rolled SSE parser eventually hits this bug. This is the fix.

### Synthetic done for proxy robustness

If the server drops the connection without emitting `done` (proxy timeout, crash, nginx buffer limit), the client must recover:

```javascript
const DONE_TIMEOUT_MS = 30000; // 30s without done → synthetic close

const doneTimer = setTimeout(() => {
  this.route('done', {
    synthetic: true,
    reason: 'timeout',
    message: 'Connection closed before completion'
  });
  this.setLoadingState(false);
}, DONE_TIMEOUT_MS);

// Cancel on real done
socket.on('done', () => clearTimeout(doneTimer));
```

### Session recording and replay

For debugging production agent runs, record every event to `.jsonl`:

```jsonl
{"session": "a1b2c3...", "started_at": "2026-07-19T10:14:00+00:00", "t": 0}
{"t": 0.0,   "event": "token",      "data": {"text": "Starting"}}
{"t": 0.894, "event": "tool_use",   "data": {"tool_name": "search", ...}}
{"t": 1.736, "event": "tool_result","data": {"tool_call_id": "tc_7f3a", ...}}
{"t": 8.204, "event": "done",       "data": {"num_turns": 1, ...}}
```

Replay at original timing for forensics, or at 2x/4x for quick review:

```bash
agent-stream replay session.jsonl --speed 2
```

The `.jsonl` format is human-readable and greppable — `grep "tool_use" session.jsonl | wc -l` tells you tool call frequency instantly.

## Receipt

> Verified 2026-07-19 — agent-stream GitHub repo (abhichat85/agent-stream, MIT, 3.11+) implements all five event types with Python emitter + React hook; agent-event-stream on PyPI and @agent-stream/react on npm as the distributable packages. Kindatechnical.com (updated Mar 2026) confirms the token/thinking/tool/progress/done pattern as the standard agent UX event set. GitHub shows 561.6K stars for terminal-based AI coding agents — streaming UX is now a production requirement, not a nicety.

## See also

- [S-12 · Streaming Response Delivery](s12-streaming.md) — the SSE decision rule (stream to humans, not to code); complementary to this entry which covers the multi-channel protocol
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — tracing and session replay for agent debugging; this entry's `.jsonl` recording feeds into that infrastructure
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — the agent execution loop that emits the events this protocol carries
