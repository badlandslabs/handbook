# F-32 · Context Overflow Recovery

A 200K-token context window sounds unlimited. It isn't. A coding assistant that re-injects a 1 400-token file on every turn overflows a GPT-4o (128K) session at turn 87. A support agent accumulating long tool outputs hits the wall faster still. Pre-flight detection ([S-56](../stacks/s56-preflight-token-check.md)) catches overflow before the API call; this entry covers what to do when a running session approaches or hits the limit.

## Situation

An agent is mid-session on turn 20 of a code review. The user pastes another large file. The pre-flight check fires: adding this file would push the conversation to 130 000 tokens — over the model's 128K limit. Or, if pre-flight was skipped, the API returns `invalid_request_error: prompt is too long`. Either way, the agent can't call the model with the current context. The session needs to continue; the user isn't done.

## Forces

- **Re-injecting documents is the main culprit.** Conversation turn tokens grow linearly — 50–100 tokens per exchange — but injecting a 1 000-token file on every turn multiplies that by 10–20×. Naive implementations that keep the full history including all file injections overflow 10× faster than they need to.
- **The API error tells you what happened, but not how to fix it.** `invalid_request_error` with `prompt is too long` is the runtime signal. It fires after you've already paid for the tokenization pass on the input. Pre-flight ([S-56](../stacks/s56-preflight-token-check.md)) catches this before spending the call.
- **`stop_reason: max_tokens` is a different problem.** That's output truncation — the *response* was cut short. Context overflow is input truncation — the *prompt* was too large to send at all. The recovery strategy is different for each.
- **Recovery options have a quality–cost tradeoff.** Sliding window is cheapest but loses early context; summarization preserves key facts but requires a model call; routing to a larger-context model costs more per token. Cache the static content first — it's often the highest-leverage fix.
- **The conversation state needs to be separable from the token buffer.** If your agent stores conversation state only in the message history array, you can't recover without losing state. Maintain a structured state object alongside the history; it survives any history truncation strategy.

## The move

**Apply the recovery strategies in this order: first cache static content, then compress history, then route up. Have pre-flight running so you catch overflow before the call, not after.**

**Detection:**

```js
// Pre-flight (preferred — catches it before the API call)
const { fits, headroom } = preflightCheck(allMessages, MODEL_LIMIT);
if (!fits) { recoverContext(conversation); return callModel(conversation); }

// Runtime detection (if pre-flight was skipped)
try {
  response = await client.messages.create({ model, messages, max_tokens });
} catch (err) {
  if (err.status === 400 && err.message?.includes('too long')) {
    await recoverContext(conversation);
    response = await client.messages.create({ model, messages: conversation.messages, max_tokens });
  } else throw err;
}
```

**Recovery playbook (apply in order):**

```js
async function recoverContext(conversation, { targetFraction = 0.70 } = {}) {
  const targetTokens = MODEL_LIMIT * targetFraction;  // recover to 70% full

  // Strategy 1: cache static content (zero quality loss, works once per session)
  if (!conversation.staticContentCached) {
    moveStaticToCachedPrefix(conversation);  // move system docs/files to cache_control prefix (S-08)
    conversation.staticContentCached = true;
    if (countTokens(conversation) <= targetTokens) return;
  }

  // Strategy 2: sliding window — drop oldest turns (fast, loses early context)
  while (countTokens(conversation) > targetTokens && conversation.history.length > 3) {
    conversation.history.shift();  // drop oldest turn pair
    conversation.history.shift();
  }
  if (countTokens(conversation) <= targetTokens) return;

  // Strategy 3: summarize oldest N turns (preserves key facts; costs one model call)
  const toSummarize = conversation.history.splice(0, Math.floor(conversation.history.length / 2));
  const summary = await summarizeHistory(toSummarize);  // model call: ~200-400 tok output
  conversation.history.unshift({ role: 'user', content: `<prior_summary>${summary}</prior_summary>` });
  if (countTokens(conversation) <= targetTokens) return;

  // Strategy 4: route to larger-context model (same quality, higher price)
  conversation.model = LARGER_CONTEXT_MODEL;  // e.g. route to a 1M-context model (S-06)
}
```

**Carry-forward state design (what survives history truncation):**

```js
// Keep structured state separate from history — it survives any recovery strategy
const agentState = {
  taskDescription: string,    // original user goal
  completedSteps:  string[],  // what has been done
  pendingSteps:    string[],  // what remains
  keyFindings:     string[],  // facts that must survive context truncation
  openQuestions:   string[],  // unresolved items
};

// Inject state as a message at the top of every trimmed history
// This is cheaper than carrying N turns of history and preserves task continuity
function buildMessagesWithState(agentState, recentHistory) {
  return [
    { role: 'user', content: `<task_state>${JSON.stringify(agentState)}</task_state>` },
    ...recentHistory,
  ];
}
```

**Recovery strategy decision table:**

| Situation | Strategy | Quality | Cost |
|---|---|---|---|
| Static file re-injected every turn | Cache prefix (S-08) | No loss | Saves 90% on file tokens |
| Long conversation, early context dispensable | Sliding window (S-54) | Early context lost | Cheapest |
| Early context has key facts | Summarize oldest turns | Key facts preserved | +1 model call |
| Model window is genuinely too small | Route up (S-06) | No loss | Higher/token |
| Emergency: nothing else works | Hard truncate to 70% | Unpredictable loss | No extra cost |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Coding assistant scenario: 18-token system prompt; 1 403-token file injected each turn; 17-token user turns; 41-token agent turns. API error shape from Anthropic public API documentation.

```
=== Context overflow: document-heavy coding assistant ===

System prompt:          18 tokens
Injected file per turn: 1403 tokens
Avg user + agent turn:  58 tokens
Tokens per turn:        1461 tokens (naive: file re-injected every turn)

Context limits:
  gpt-4o   (128K) → overflow at turn ~87
  claude-sonnet (200K) → overflow at turn ~136

At turn 10 (14 628 tokens, naive re-injection):
  Full history + file each turn:           14 628 tok  ($43.88/k)
  Cache file (S-08) + full turn history:    2 001 tok  (file at cache-read price: $0.30/M)
  Summarize turns 1-7 + file + last 3:      1 813 tok  ($5.44/k)

→ Caching the static file is a 7.3× cost reduction, zero quality loss

=== API error on context overflow ===

{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "prompt is too long: 205117 tokens > 200000 maximum"
  }
}
Detection: err.status === 400 && err.message?.includes('too long')
Note: pre-flight (S-56) catches this before the API call — prefer that path
```

The dominant fix is usually caching the static content: move documents and system prompts to a `cache_control` prefix ([S-08](../stacks/s08-prompt-caching.md)) and they stop counting against the turn accumulation. In the receipt scenario, this alone reduces turn-10 cost by 7.3× and pushes overflow out from turn 87 to a point where the conversation history alone won't fill the window within any realistic session length.

## See also

[S-56](../stacks/s56-preflight-token-check.md) · [S-21](../stacks/s21-context-compaction.md) · [S-54](../stacks/s54-multi-turn-conversation-design.md) · [S-08](../stacks/s08-prompt-caching.md) · [S-06](../stacks/s06-model-routing.md) · [S-38](../stacks/s38-agent-state-design.md)

## Go deeper

Keywords: `context overflow` · `context window limit` · `prompt too long` · `context recovery` · `history compaction` · `sliding window` · `summarize history` · `model routing` · `token accumulation` · `invalid_request_error`
