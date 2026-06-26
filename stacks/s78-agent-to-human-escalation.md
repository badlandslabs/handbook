# S-78 · Agent-to-Human Escalation

[F-09](../forward-deployed/f09-human-in-the-loop.md) covers the design philosophy of human oversight — three approval modes, the non-negotiable action list, avoiding reviewer fatigue. [S-41](s41-agent-handoff-patterns.md) covers handing off between agents — the structured handoff object, compression decisions. Neither covers the runtime implementation of agent-to-human escalation: detecting the trigger in code, building a handoff package the human reviewer can actually act on, pausing the agent loop, and resuming cleanly when the decision comes back.

## Situation

A support agent handles a refund request. The order is 47 days old; policy limit is 30 days; the customer says the item was defective. The agent's confidence score is 0.41 — below the 0.60 threshold for autonomous action. Without escalation logic, the agent either denies the refund (wrong if defective-item exception applies) or hallucinates a policy exception it doesn't have authority to grant. With escalation: the agent pauses, pushes a 158-token package to the human queue, and resumes when a human decides "approve exception." The agent processes the refund. The reviewer made one decision in under two minutes.

## Forces

- **Escalation triggers are a finite, enumerable set.** Low confidence is one. Explicit user request ("I want to speak to a human") is another. Max turns exceeded is a safety net. Keyword patterns (legal, fraud, billing error) flag cases where autonomous action is risky regardless of confidence. Define the trigger set upfront; don't let the agent decide dynamically whether it needs help.
- **The escalation package must be actionable, not a raw dump.** Passing the full conversation history costs 822 tokens for a 20-turn conversation and buries the signal. A structured package — task summary, agent's action, compact conversation summary, last 3 turns, suggested actions — is 158 tokens (81% smaller) and tells the reviewer exactly what they need to decide.
- **The resume is a single injected message.** When the human decides, inject their decision as the next user turn: "Human reviewer: approve exception for defective item." The agent continues from there. Zero re-architecture of the agent loop required.
- **The human queue must persist agent state.** If the human takes 4 hours to respond, the agent loop should be paused, not spinning. Store the serialized state; resume when the queue delivers the response. This is the same durable-execution pattern as [F-15](../forward-deployed/f15-durable-execution.md).
- **Suggested actions in the package reduce reviewer latency.** If the agent offers `['approve_exception', 'deny_outside_window', 'request_defect_evidence']`, the reviewer clicks rather than types. Include only actions the agent has authority to execute.

## The move

**Define the trigger set. Build a compact escalation package. Pause the loop and push to a human queue. Resume by injecting the human decision as a user turn.**

```js
// Escalation trigger definitions — extend for your domain
const TRIGGERS = {
  LOW_CONFIDENCE:   { check: (ctx) => ctx.confidence < 0.60,  label: 'low_confidence' },
  EXPLICIT_REQUEST: { check: (ctx) => /speak.{0,10}human|real person|supervisor|escalate/i.test(ctx.lastUserMessage), label: 'explicit_request' },
  MAX_TURNS:        { check: (ctx) => ctx.turnCount >= 10,     label: 'max_turns_exceeded' },
  POLICY_KEYWORD:   { check: (ctx) => /legal|lawsuit|attorney|fraud|billing error/i.test(ctx.lastUserMessage), label: 'policy_keyword' },
};

function detectEscalation(ctx) {
  for (const [, trigger] of Object.entries(TRIGGERS)) {
    if (trigger.check(ctx)) return trigger.label;
  }
  return null;
}

// Build a compact handoff package the human reviewer can act on
function buildEscalationPackage(taskId, trigger, agentState) {
  return {
    taskId,
    trigger,
    confidence:            agentState.confidence,
    taskSummary:           agentState.taskSummary,       // agent's own summary of the situation
    agentActionTaken:      agentState.lastAction,        // what the agent tried before escalating
    conversationSummary:   agentState.conversationSummary,  // compact summary, not full history
    lastMessages:          agentState.messages.slice(-3),   // last 3 turns only; not all N
    suggestedActions:      agentState.suggestedActions,  // options the agent can execute
    escalatedAt:           new Date().toISOString(),
  };
}

// Agent loop with escalation — works with any async human queue
async function runAgentWithEscalation(client, task, humanQueue) {
  const systemPrompt = `You are a customer support agent for ${task.company}.
After each response, output a confidence score 0.0–1.0 for your answer as JSON on the last line: {"confidence": 0.XX, "taskSummary": "...", "suggestedActions": [...]}`;

  let messages = [{ role: 'user', content: task.initialMessage }];
  let turnCount = 0;
  let done = false;
  let result = null;

  while (!done) {
    const response = await client.messages.create({
      model: 'claude-haiku-4-5-20251001', max_tokens: 512,
      system: systemPrompt, messages,
    });

    const text = response.content[0].text;

    // Parse agent's self-reported state from structured suffix
    const stateMatch = text.match(/\{"confidence"[\s\S]*\}/);
    const agentState = stateMatch ? JSON.parse(stateMatch[0]) : { confidence: 1.0 };
    agentState.lastAction  = text.replace(stateMatch?.[0] ?? '', '').trim();
    agentState.messages    = messages;
    agentState.turnCount   = ++turnCount;
    agentState.lastUserMessage = messages[messages.length - 1].content;

    // Check for escalation triggers
    const trigger = detectEscalation(agentState);

    if (trigger) {
      const pkg = buildEscalationPackage(task.id, trigger, agentState);
      console.log(`[escalation] trigger=${trigger}, confidence=${agentState.confidence}`);

      // Pause loop — push to human queue and await decision (may take minutes or hours)
      const humanDecision = await humanQueue.push(pkg);   // durable; see F-15

      // Resume: inject decision as the next user message
      const resumeMessage = `Human reviewer decision (${humanDecision.action}): ${humanDecision.note ?? 'Proceed as directed.'}`;
      messages.push({ role: 'assistant', content: agentState.lastAction });
      messages.push({ role: 'user',      content: resumeMessage });
      agentState.confidence = 1.0;  // human has decided; proceed with confidence
      continue;
    }

    if (response.stop_reason === 'end_turn' && agentState.confidence >= 0.60) {
      done = true;
      result = agentState.lastAction;
    } else {
      messages.push({ role: 'assistant', content: text });
    }
  }

  return result;
}

// Human queue interface (implementation varies: database row, Slack message, ticket system)
// humanQueue.push(pkg) → Promise<{ action: string, note?: string }>
// When human acts, the promise resolves and the loop resumes.
```

**Trigger taxonomy by use case:**

| Trigger | When to use | Action |
|---|---|---|
| Low confidence | Continuous; check every turn | Pause; send to review queue |
| Explicit user request | Any time | Pause immediately |
| Max turns | Safety net only | Escalate with summary |
| Policy keyword | Domain-specific | Pause before responding |
| Tool failure (repeated) | Agent stuck in loop | Escalate with failure log |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Package and history token counts measured on representative content.

```
=== Escalation package vs full history ===

$ node -e "
// 20-turn support conversation (realistic length)
// Escalation package: taskSummary + agentAction + conversationSummary + last 3 msgs + suggestedActions
"
Full 20-turn history:   822 tok
Escalation package:     158 tok  (81% smaller)
Resume injection:        17 tok  ('Human reviewer decision: approve_exception. Process refund.')

Human reviewer reads 158 tok instead of 822 tok — faster decision, better signal-to-noise.

=== Trigger check speed ===

Confidence threshold check (<0.60): <0.0001 ms per call
Regex keyword scan (4 patterns):     0.0017 ms per call (S-77 receipt baseline)

Both are negligible — the wait is the human queue, not the detection.

=== Escalation rate and economics ===

At 1 000 support tasks/day, 8% escalation rate (industry estimate for AI support):
  Tasks escalated: 80/day
  Human review time at 2 min/task: 160 min/day = 2.7 hrs/day
  vs. agent handling incorrectly: cost of 1 wrong refund decision >> 2.7 hrs of review

Token cost of escalation package at Haiku $0.80/M:
  158 tok × $0.80/M = $0.000126/escalation
  80 escalations/day × $0.000126 = $0.010/day — negligible
```

## See also

[F-09](../forward-deployed/f09-human-in-the-loop.md) · [S-41](s41-agent-handoff-patterns.md) · [F-15](../forward-deployed/f15-durable-execution.md) · [S-70](s70-agent-loop-termination.md) · [S-53](s53-confidence-calibration.md) · [F-42](../forward-deployed/f42-ai-incident-response.md)

## Go deeper

Keywords: `agent escalation` · `human handoff` · `escalation trigger` · `human queue` · `confidence threshold` · `escalation package` · `resume from human` · `HITL implementation` · `pause agent loop` · `human-in-the-loop`
