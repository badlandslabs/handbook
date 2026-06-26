# S-54 · Multi-Turn Conversation Design

Every turn in a conversation adds tokens. In a 10-turn session with full history injection, the agent's input at turn 10 is nearly 5× the input at turn 1 — and every turn after that costs more than the last. Most agents don't need the full history at every turn; they need the current task state, the last few turns for coherence, and the current message. Designing what gets injected at each turn — and when to summarize what came before — is the difference between a session that degrades gracefully and one that collapses under its own history.

## Situation

A support agent handles sessions that run 8–15 turns. By turn 10, it's injecting the full conversation history: 970 tokens of context where most of the value is in the last 3 turns and the structured state. The agent begins losing coherence around turn 12 — earlier user preferences mentioned in turn 2 aren't being honored. The cause: turn 2 content is buried 800 tokens back in the history, and the model attends most strongly to recent tokens. A sliding window (last 5 turns) fixes the cost; a structured state object ([S-38](s38-agent-state-design.md)) fixes the coherence loss by extracting preferences into an explicit field.

## Forces

- Full history grows linearly with turns; structured state grows with completed work. At turn 10, full history is 970 tokens; sliding window is 545; summary + last 3 turns is 583. The gap widens at longer sessions. Full history is the most expensive strategy and provides decreasing marginal value after turn 5.
- Context position determines what the model attends to. Information at the top and bottom of the context window receives higher attention than content in the middle. A preference stated in turn 2 but buried 8 turns later may as well not be there. The fix is not to carry more history — it's to extract important information into a structured state object at the top of the prompt.
- Summarization breaks even in 5 turns. A single summary call compresses 7 turns (595 tokens) into 208 tokens, costing $5.03/k. The savings start at turn 8 and compound from there. For sessions expected to run 10+ turns, summarization pays for itself.
- Retrieved chunks are turn-local. RAG chunks injected for one turn's answer have no value in subsequent turns — the model has already used them. Drop retrieved chunks after each response; never carry them into the next turn's context.
- Intermediate CoT reasoning should never cross turn boundaries. If a turn uses chain-of-thought ([S-46](s46-chain-of-thought.md)), only the answer carries forward — not the scratchpad. Carrying reasoning chains across turns multiplies token cost with no benefit.

## The move

**Inject: system prompt + structured state + last N turns + current message. Drop: retrieved chunks, old tool results, CoT. Summarize at turn N or when context exceeds 50% of the context limit.**

**Turn injection template:**

```js
function buildTurnContext(state, history, currentMessage, retrievedChunks, { windowSize = 5 } = {}) {
  const recentHistory = history.slice(-windowSize);  // last N turns only

  return [
    { role: 'system', content: systemPrompt },       // cached static prefix (S-08)
    { role: 'user',   content: `<state>${JSON.stringify(state)}</state>` },  // always at top
    ...recentHistory,                                 // last N turns for coherence
    ...(retrievedChunks.length
        ? [{ role: 'user', content: `<context>${retrievedChunks.join('\n')}</context>` }]
        : []),                                        // this turn only; will not be in next turn
    { role: 'user',   content: currentMessage },
  ];
}
```

**What to carry vs. drop:**

| Content | Carry | Why |
|---|---|---|
| System prompt | Always | Cacheable static prefix |
| Structured state ([S-38](s38-agent-state-design.md)) | Always | Compact; explicit; position-salient |
| Last N turns (N=3–5) | Always | Recent coherence; sliding window |
| Current user message | Always | The question |
| Retrieved RAG chunks | This turn only | Drop immediately after response |
| Old tool results (>2 turns ago) | Never | Move decision to state; drop raw result |
| CoT / reasoning scratchpad | Never | Only the answer crosses turn boundaries |
| Pleasantries ("thanks!", "sure!") | Optional drop | Zero signal; compress in summary |

**Summarization trigger and prompt:**

```js
function shouldSummarize(history, contextLimit, currentContextSize) {
  if (history.length > 7) return true;                          // turn-count trigger
  if (currentContextSize > contextLimit * 0.50) return true;   // budget trigger
  return false;
}

async function summarizeHistory(history, model) {
  const historyText = history.map(m => `${m.role}: ${m.content}`).join('\n');
  const summary = await model.call(`
Summarize this conversation in 3–5 bullet points.
Focus on: decisions made, user preferences stated, open questions.
Drop pleasantries. Output only the bullets.

${historyText}`);
  return summary; // replaces history in next turn's context
}
```

**Three strategies compared — choose by session length:**

| Session length | Strategy | Why |
|---|---|---|
| 1–5 turns | Full history | Short enough; no overhead |
| 5–10 turns | Sliding window N=5 | Simplest fix; reliable coherence |
| 10+ turns | Summary + last 3 turns | Compounds savings; preserves arc |

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Token counts at each turn derived from a 120-token system prompt + 85 tok/turn pairs (realistic support chat length). Summary compression ratio (35%) from typical bullet-point summarization of conversational content. Break-even is calculated exactly: summary call cost ÷ savings per turn.

```
=== Context size by strategy across 10 turns ===

Strategy                       T1    T2    T3    T5    T7   T10
Full history                  205   290   375   545   715   970
Sliding window (N=5)          205   290   375   545   545   545
Summary + last 3 turns        205   290   375   434   494   583

=== Cost at turn 10 (per 1k calls) ===
Full history:         970 input tokens  →  $4.26/k
Sliding window (N=5): 545 input tokens  →  $2.98/k   (30% cheaper)
Summary + 3 turns:    583 input tokens  →  $3.10/k   (27% cheaper)

=== Summary call economics (triggered at turn 7) ===
Summary prompt:   41 tokens
History input:   595 tokens (7 turns × 85 tok)
Summary output:  208 tokens (35% compression)
Summary call:    $5.03/k
Savings per subsequent turn: 387 tokens = $1.16/k
Break-even: 5 turns after summarization
```

The sliding window is the practical default — it cuts turn-10 cost by 30% with one line of code. Add summarization for sessions expected to run 10+ turns; it breaks even by turn 12 and compounds from there. Structured state is orthogonal to both: it addresses coherence loss, not token count.

## See also

[S-38](s38-agent-state-design.md) · [S-09](s09-memory-systems.md) · [S-13](s13-context-engineering.md) · [S-08](s08-prompt-caching.md) · [S-21](s21-context-compaction.md)

## Go deeper

Keywords: `multi-turn conversation` · `conversation design` · `sliding window` · `context injection` · `turn history` · `conversation summarization` · `context management` · `chat agent` · `session design` · `history truncation`
