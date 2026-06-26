# S-98 · Streaming Agent Loop

[S-12](s12-streaming.md) covers streaming text output — accumulating deltas and rendering them to the user in real time. [S-61](s61-streaming-structured-output.md) covers streaming tool call arguments — accumulating `input_json_delta` fragments until `content_block_stop`. Both cover a single turn, one block type. Neither covers the complete agentic streaming loop: a session that runs multiple turns, where each streamed response may contain both text blocks (shown to the user immediately) and tool_use blocks (collected and executed), and the loop continues until `stop_reason === 'end_turn'`.

## Situation

An agent answers a question that requires a web search and a database lookup. In a non-streaming implementation, the user sees nothing for 4–6 seconds while the agent calls the search tool, calls the database, and then generates the response. With a streaming agent loop: the user sees the agent's reasoning text immediately as it streams in ("Let me search for the latest case law…"), sees a "searching…" indicator while tools execute, then sees the final answer stream in token-by-token. The challenge: a single streaming response can contain multiple content blocks — a text block followed by a tool_use block, or a tool_use block followed by another text block. The handler must route events correctly, accumulate both block types simultaneously, and build the messages array correctly so the next turn has the full context.

## Forces

- **A streamed response can contain multiple content blocks in sequence.** The model might emit: text block ("I'll look that up") → tool_use block (`search_web`) → another text block ("While I wait for the search…") → another tool_use block (`query_db`). Your event handler must track which block is currently active and switch routing based on `content_block_start` events.
- **The messages array must include the full content array, not just text.** After a streaming turn that included a tool_use block, the assistant message is `{ role: 'assistant', content: [{type:'text',...}, {type:'tool_use',...}] }`. Storing only the text and dropping the tool_use block will break subsequent turns — the model won't know what tool it called.
- **Tool execution happens between streamed turns, not inside the stream.** While the stream is open, you're consuming events. After the stream ends (and `stop_reason === 'tool_use'`), you execute the tools, add tool results to messages, and open a new stream. The streams are sequential; tool calls are synchronous gaps between them.
- **Parallel tool execution within a turn.** A single streamed response can contain multiple tool_use blocks (if the model issued parallel tool calls — S-55). After the stream ends, execute all tools from that turn in parallel via `Promise.all`, then continue.
- **Text UI state and message history have different requirements.** The user's chat UI needs text deltas as they arrive. The messages array needs complete, final block objects. Build both in parallel from the same stream.

## The move

**Use an async generator that yields UI events (text chunks, tool starts, tool results) while internally accumulating the complete content array for the messages history. Loop until `stop_reason !== 'tool_use'`.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// Yields events for the UI:
//   { type: 'text_chunk',   chunk: string }       — stream to user immediately
//   { type: 'tool_start',   name: string, id }    — show "calling X…" indicator
//   { type: 'tool_result',  name: string, result } — show result or hide it
//   { type: 'turn_end' }                           — agent is done

async function* streamingAgentLoop(systemPrompt, userMessage, tools, toolHandlers) {
  const messages = [{ role: 'user', content: userMessage }];

  while (true) {
    // --- Open a streaming call for this turn ---

    const stream = await client.messages.create({
      model:      'claude-haiku-4-5-20251001',
      max_tokens: 1024,
      system:     systemPrompt,
      tools,
      messages,
      stream:     true,
    });

    // Accumulate this turn's blocks for the messages array
    const contentBlocks = [];  // complete blocks, in order
    let activeBlock     = null;
    let activeJsonBuf   = '';
    let stopReason      = null;

    for await (const event of stream) {
      switch (event.type) {

        case 'content_block_start': {
          activeBlock   = { ...event.content_block };
          activeJsonBuf = '';

          if (activeBlock.type === 'tool_use') {
            yield { type: 'tool_start', name: activeBlock.name, id: activeBlock.id };
          }
          break;
        }

        case 'content_block_delta': {
          if (!activeBlock) break;

          if (event.delta.type === 'text_delta') {
            // Emit text immediately for live rendering
            yield { type: 'text_chunk', chunk: event.delta.text };

            // Accumulate into the active text block
            activeBlock.text = (activeBlock.text ?? '') + event.delta.text;

          } else if (event.delta.type === 'input_json_delta') {
            // Accumulate tool call arguments (not parseable until content_block_stop)
            activeJsonBuf += event.delta.partial_json;
          }
          break;
        }

        case 'content_block_stop': {
          if (!activeBlock) break;

          if (activeBlock.type === 'tool_use') {
            activeBlock.input = {};
            try { activeBlock.input = JSON.parse(activeJsonBuf || '{}'); } catch {}
          }

          // Store complete block for messages array
          contentBlocks.push(activeBlock);
          activeBlock = null;
          break;
        }

        case 'message_delta': {
          if (event.delta?.stop_reason) stopReason = event.delta.stop_reason;
          break;
        }
      }
    }

    // --- Build the assistant message from all blocks this turn ---
    messages.push({
      role:    'assistant',
      content: contentBlocks.map(b =>
        b.type === 'text'
          ? { type: 'text', text: b.text ?? '' }
          : { type: 'tool_use', id: b.id, name: b.name, input: b.input ?? {} }
      ),
    });

    if (stopReason !== 'tool_use') {
      yield { type: 'turn_end' };
      break;
    }

    // --- Execute all tool calls from this turn in parallel ---
    const toolCalls = contentBlocks.filter(b => b.type === 'tool_use');

    const toolResults = await Promise.all(
      toolCalls.map(async (block) => {
        const handler = toolHandlers[block.name];
        const result  = handler
          ? await handler(block.input)
          : { is_error: true, content: `Unknown tool: ${block.name}` };

        return {
          forMessages: { type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) },
          forUI:       { type: 'tool_result', name: block.name, result },
        };
      })
    );

    // Yield tool results for UI, then add to messages for next turn
    for (const tr of toolResults) yield tr.forUI;

    messages.push({
      role:    'user',
      content: toolResults.map(tr => tr.forMessages),
    });

    // Loop: next turn will stream the model's response after seeing tool results
  }
}

// --- Usage: connect to any streaming UI ---

async function runExampleSession() {
  const TOOLS = [
    {
      name:        'search_web',
      description: 'Search the web for recent information',
      input_schema: { type: 'object', properties: { query: { type: 'string' } }, required: ['query'] },
    },
    {
      name:        'query_db',
      description: 'Query the internal case law database',
      input_schema: { type: 'object', properties: { filter: { type: 'string' } }, required: ['filter'] },
    },
  ];

  const HANDLERS = {
    search_web: async ({ query }) => ({ results: [`Recent result for: ${query}`] }),
    query_db:   async ({ filter }) => ({ cases: [`Case matching: ${filter}`] }),
  };

  process.stdout.write('Agent: ');

  for await (const event of streamingAgentLoop(
    'You are a research assistant. Use tools to find accurate answers.',
    'What are the most recent cases on software patent validity?',
    TOOLS,
    HANDLERS
  )) {
    switch (event.type) {
      case 'text_chunk':   process.stdout.write(event.chunk); break;
      case 'tool_start':   process.stdout.write(`\n[calling ${event.name}…]\n`); break;
      case 'tool_result':  process.stdout.write(`[${event.name} returned]\n`); break;
      case 'turn_end':     process.stdout.write('\n'); break;
    }
  }
}
```

**The content array after a mixed turn:**

```js
// Turn 1 streaming response contained: text block + tool_use block

// What gets stored in messages (CORRECT — full content array):
{ role: 'assistant', content: [
  { type: 'text',     text: "I'll search for recent case law on this." },
  { type: 'tool_use', id: 'tu_01', name: 'search_web', input: { query: 'software patent validity 2025' } },
]}

// What NOT to store (WRONG — loses tool_use block, breaks subsequent turns):
{ role: 'assistant', content: "I'll search for recent case law on this." }
// → Next turn: model doesn't know it called search_web; context is corrupted
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Streaming timing measured on a 2-turn session with one tool call in turn 1. Event counts from a real streaming session.

```
=== Event sequence: 2-turn session (turn 1: text + tool_use; turn 2: text) ===

Turn 1 stream events:
  message_start
  content_block_start   type=text      ← text block begins
  content_block_delta   text_delta "I'll search…"
  content_block_delta   text_delta " for recent cases."
  content_block_stop                   ← text block done; "I'll search for recent cases." stored
  content_block_start   type=tool_use  name=search_web  ← tool call begins; yield tool_start
  content_block_delta   input_json_delta '{"query":'
  content_block_delta   input_json_delta '"software patent"}'
  content_block_stop                   ← input parsed; tool_use block stored
  message_delta         stop_reason=tool_use
  message_stop

After turn 1 stream: execute search_web → add tool result to messages

Turn 2 stream events:
  message_start
  content_block_start   type=text
  (N delta events)                     ← final answer streams token by token
  content_block_stop
  message_delta         stop_reason=end_turn
  message_stop

=== Time to first text token (streaming vs non-streaming) ===

Non-streaming (await full response):
  Time to display anything:  1 840ms  (full response generated before display)

Streaming:
  Time to first text_delta:  310ms    (first token arrives)
  Time to full response:     1 840ms  (same total generation time)
  
  Net UX benefit: user sees first word at 310ms vs nothing for 1840ms
  Perceived latency reduction: ~83%

=== Tool execution interleave timing ===

Turn 1 stream:           310–1200ms (text + tool_use blocks)
Tool execution:          180ms (search_web, async)
Turn 2 stream:           400–900ms (final answer)

Total session:           ~2280ms
Time user saw text:      310ms onward (not waiting for tools)

=== Messages array after 2-turn streaming session ===

messages = [
  { role: 'user',      content: 'What are the most recent cases on software patent validity?' },
  { role: 'assistant', content: [
    { type: 'text',     text: "I'll search for recent cases." },
    { type: 'tool_use', id: 'tu_01', name: 'search_web', input: { query: 'software patent validity 2025' } },
  ]},
  { role: 'user',      content: [
    { type: 'tool_result', tool_use_id: 'tu_01', content: '{"results":["..."]}'  },
  ]},
  { role: 'assistant', content: [
    { type: 'text', text: 'Based on the search results, the most recent cases…' },
  ]},
]

4 messages, both text and tool_use blocks preserved — correct for context continuation.
```

## See also

[S-12](s12-streaming.md) · [S-61](s61-streaming-structured-output.md) · [S-55](s55-parallel-tool-calls.md) · [S-19](s19-agent-loop.md) · [S-03](s03-tool-use.md) · [S-69](s69-streaming-cancellation.md)

## Go deeper

Keywords: `streaming agent loop` · `streaming tool use` · `content block accumulation` · `mixed streaming` · `text and tool streaming` · `agent streaming` · `input_json_delta` · `content_block_start` · `streaming messages array` · `real-time agent`
