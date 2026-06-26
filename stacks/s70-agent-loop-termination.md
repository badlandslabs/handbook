# S-70 · Agent Loop Termination

[S-19](s19-agent-loop.md) says to "always bound the loop" with a max-iteration cap, token budget, no-progress detection, and a goal verifier. That's the principle. This entry is the implementation: four concrete termination conditions, how to wire them together, and what to return when each fires. An agent loop without explicit termination logic will eventually run to a limit you didn't set, at a cost you didn't expect.

## Situation

A research agent is supposed to gather information about a company, make three tool calls, and return a summary. In production, 0.3% of runs get stuck: the search tool returns no results, the agent retries the same query with minor variations, and the loop runs for 50 turns before the platform timeout kills it. Each stuck run costs 10× the expected $0.05 and, worse, returns nothing — the timeout is not a graceful exit. A max-turns guard at turn 10 would have saved $0.40 per stuck run and returned a partial result instead of a hard timeout error.

## Forces

- **The model cannot reliably detect its own stuck states.** A model looping on the same failed search does not know it's looping — it is reasoning forward from each tool result in isolation. No-progress detection is infrastructure, not intelligence.
- **Max-turns is a safety net, not a success condition.** Setting `MAX_TURNS = 15` does not mean the agent should run 15 turns — it means 15 turns is the budget. Most tasks should complete in 3–7 turns. When the guard fires, treat it as a signal something went wrong, not as normal completion.
- **Done signals must be explicit.** The model produces text; the loop keeps running until code says stop. An explicit done-signal tool call (or a structured terminal output) is cleaner and more reliable than asking the loop to infer completion from the model's output.
- **Goal verification is separate from done-detection.** The agent saying "DONE" proves it believes it is done, not that the goal was actually achieved. A verifier that checks the result against the original goal catches cases where the agent completed the wrong task or produced a partial output with misplaced confidence.
- **Partial results beat hard failures.** When a limit fires — max turns, token budget, no-progress — return whatever was accomplished, annotated with the termination reason. A partial result with context is more useful than an error message.

## The move

**Wire four termination checks in order: (1) done-signal, (2) no-progress detector, (3) token budget, (4) max-turns guard. Return partial results on limit; run a goal verifier before returning done.**

```js
const MAX_TURNS       = 15;
const TOKEN_BUDGET    = 20_000; // input + output tokens across the run
const NO_PROGRESS_N   = 3;      // same tool+args this many times → stuck

async function runAgentLoop(client, task, tools) {
  const messages    = [{ role: 'user', content: task }];
  const callHistory = [];    // {tool, argsKey} per turn
  let   totalTokens = 0;
  let   result      = null;

  for (let turn = 0; turn < MAX_TURNS; turn++) {

    // Check 3: token budget before calling the model
    if (totalTokens >= TOKEN_BUDGET) {
      return terminate('token_budget', result, messages);
    }

    const response = await client.messages.create({
      model:     'claude-sonnet-4-6',
      max_tokens: 1024,
      tools,
      messages,
    });

    totalTokens += response.usage.input_tokens + response.usage.output_tokens;
    messages.push({ role: 'assistant', content: response.content });

    // Check 1: done-signal tool call
    const doneCall = response.content.find(
      b => b.type === 'tool_use' && b.name === 'task_complete'
    );
    if (doneCall) {
      result = doneCall.input.result;
      const verified = await verifyGoal(client, task, result);
      if (verified.pass) return { status: 'done', result, turns: turn + 1, tokens: totalTokens };
      // Verifier failed — let the agent try again with feedback
      messages.push({ role: 'user', content: [{ type: 'tool_result', tool_use_id: doneCall.id,
        content: `Goal not yet met: ${verified.reason}. Continue.` }] });
      continue;
    }

    // Execute tool calls; record for no-progress detection
    if (response.stop_reason === 'tool_use') {
      const toolCalls = response.content.filter(b => b.type === 'tool_use');
      const toolResults = [];

      for (const call of toolCalls) {
        const argsKey = call.name + ':' + JSON.stringify(
          Object.keys(call.input).sort().reduce((o, k) => (o[k] = call.input[k], o), {})
        );
        callHistory.push(argsKey);

        // Check 2: no-progress detection
        const recentN = callHistory.slice(-NO_PROGRESS_N * 2);
        const counts  = recentN.reduce((m, k) => (m[k] = (m[k]||0)+1, m), {});
        if (Object.values(counts).some(c => c >= NO_PROGRESS_N)) {
          return terminate('no_progress', result, messages, call.name);
        }

        const toolResult = await executeTool(call.name, call.input);
        if (call.name !== 'task_complete') result = toolResult; // track last substantive result
        toolResults.push({ type: 'tool_result', tool_use_id: call.id, content: JSON.stringify(toolResult) });
      }
      messages.push({ role: 'user', content: toolResults });
      continue;
    }

    // end_turn without tool call — agent produced text; treat as done
    if (response.stop_reason === 'end_turn') {
      result = response.content.find(b => b.type === 'text')?.text ?? '';
      return { status: 'done', result, turns: turn + 1, tokens: totalTokens };
    }
  }

  // Check 4: max-turns guard (loop exhausted)
  return terminate('max_turns', result, messages);
}

function terminate(reason, partialResult, messages, detail = null) {
  console.warn(`[agent-loop] terminated: ${reason}${detail ? ` (${detail})` : ''}`);
  return { status: reason, result: partialResult, partial: true, messageCount: messages.length };
}

// Goal verifier — a separate, cheap model call
async function verifyGoal(client, originalTask, result) {
  const resp = await client.messages.create({
    model:     'claude-haiku-4-5-20251001', // cheap model for verification
    max_tokens: 60,
    messages:  [{ role: 'user', content:
      `Task: ${originalTask}\nResult: ${result}\nDoes this result fully complete the task? Reply JSON: {"pass": true/false, "reason": "..."}` }],
  });
  try   { return JSON.parse(resp.content[0].text); }
  catch { return { pass: true, reason: 'parse error — accepting result' }; } // fail open
}
```

**Termination outcome table:**

| Trigger | Status returned | What the caller should do |
|---|---|---|
| `task_complete` + verifier passes | `done` | Use the result |
| `task_complete` + verifier fails | loop continues | Verifier feedback injected |
| `end_turn` (no tool call) | `done` | Use the text result |
| No-progress detected | `no_progress` | Log; surface partial; alert if frequent |
| Token budget hit | `token_budget` | Surface partial; escalate to larger budget |
| Max turns hit | `max_turns` | Log as anomaly; surface partial; investigate |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Costs estimated at $3.00/M input, $15.00/M output (Sonnet); $0.80/M input (Haiku verifier). No-progress check measured at 0.0038ms per call.

```
=== No-progress check overhead ===

$ node -e "
const kv = {};
const N = 100000;
const t0 = performance.now();
for (let i = 0; i < N; i++) {
  const k = 'search:query=test';
  kv[k] = (kv[k]||0) + 1;
  Object.values(kv).some(c => c >= 3);
}
console.log('Per check:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Per check: 0.0038 ms

=== Runaway loop cost (no termination guard) ===

Expected: 5 calls/task × $0.01/call × 1 000 tasks/day = $50/day
Runaway:  50 calls/task × $0.01/call × 1 000 tasks/day = $500/day
Monthly extra cost: $13 500/month

Max-turn guard at turn 10 saves 40 turns per stuck run → $0.40 per stuck task

=== Goal verifier cost ===

Verifier prompt: ~80 tok input + 20 tok output = ~100 tok total
At Haiku pricing ($0.80/M in, $4.00/M out): $0.000144/verification
At 1 000 tasks/day: $4.32/month — negligible vs $13 500 runaway risk

=== Termination reason distribution (healthy system) ===

done (task_complete):   ~90%  ← this should dominate
done (end_turn):        ~7%
no_progress:            ~2%   ← alert if > 3%
token_budget:           ~0.5% ← alert; check context growth
max_turns:              ~0.5% ← alert; investigate prompt
```

## See also

[S-19](s19-agent-loop.md) · [F-05](../forward-deployed/f05-agent-failure-taxonomy.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [F-11](../forward-deployed/f11-agent-reliability.md) · [S-38](s38-agent-state-design.md) · [S-26](s26-planning.md)

## Go deeper

Keywords: `agent loop termination` · `max turns` · `no-progress detection` · `done signal` · `goal verifier` · `token budget` · `loop guard` · `stuck detection` · `task_complete` · `runaway agent`
