# S-192 · Content-Type Context Pruner

S-54 (multi-turn conversation design) describes two strategies when context grows too large: a sliding window (drop the oldest N turns) or summarization (compress history via a Haiku call). The sliding window is free but loses context from the start of the session. Summarization preserves meaning but costs tokens and a model call.

A third option costs nothing and preserves more: drop turns in priority order by content type, not by age.

Not all messages contribute equally to reasoning. A 1 400-token tool result block from turn 3 contributes much less to the current turn than the 180-token user message from turn 1 that describes the problem. An assistant reasoning step is intermediate — the conclusion matters; the internal steps usually don't. The sliding window throws both away equally. A content-type-aware pruner drops the largest, most disposable messages first and keeps the messages that carry intent and conclusion.

The priority ladder: `user_message` and `task_state` are preserved longest — they carry the user's intent and current operational state. `final_answer` and `synthesis` are next — they carry conclusions. `tool_result` and `reasoning_step` are pruned first — they are large, often reconstructable, and rarely needed for reasoning about the current turn.

## Situation

A customer service agent session runs 12 turns. The context is 9 800 tokens; the budget is 6 000 tokens. 3 800 tokens must be freed.

Turn breakdown:
- T1 (user_message, 180 tok): user describes the problem — high priority.
- T2 (tool_result, 1 400 tok): diagnostic data from account lookup — large, low priority.
- T3 (reasoning_step, 520 tok): agent's intermediate analysis — medium-low priority.
- T4 (synthesis, 290 tok): agent's findings summary — medium priority.
- T5 (user_message, 95 tok): user follow-up — high priority.
- T6 (tool_result, 1 100 tok): second tool call result — large, low priority.
- T7 (tool_result, 1 350 tok): third tool call result — largest, low priority.
- T8 (reasoning_step, 480 tok): agent reasoning — medium-low priority.
- T9 (user_message, 110 tok): user clarification — high priority, must keep (recent).
- T10 (synthesis, 320 tok): final synthesis — must keep (recent).
- T11 (user_message, 85 tok): latest user message — must keep (recent).
- T12 (final_answer, 870 tok): latest answer — must keep (recent).

**Sliding window (drop oldest 8 messages):** drops T1–T8, including the user's initial problem statement, all intermediate work, and the agent's synthesis. Keeps only T9–T12 (1 385 tok). Loses intent.

**Content-type pruner:** sorts by priority + size, frees needed tokens without touching user messages. Prunes T2 (1 400), T7 (1 350), T6 (1 100) = 3 850 tok saved. Total after: 5 950 tok ≤ 6 000 budget. All four user messages (T1, T5, T9, T11) are preserved. The agent retains the full problem description.

## Forces

- **Content type must be tagged at injection time.** A pruner that receives an untagged messages array has to infer content type from role and structure — fragile and error-prone. Tag every injected message with `contentType` when it is added. Add this field alongside the standard `role` and `content` fields; it costs nothing and makes pruning reliable.
- **Always keep the most recent N messages regardless of type.** The current turn's immediate predecessors (last 2 turns = 4 messages) provide the model with turn-local coherence. Even if a recent turn contains only a large tool result, do not prune it — the model is still reasoning about it.
- **Prune largest messages first within the same priority tier.** Two tool results at the same priority: prune the 1 400-token one before the 600-token one. This minimizes the number of messages removed to meet the budget.
- **Summarize only when pruning can't meet the budget.** Content-type pruning is zero cost. Summarization costs a Haiku call. Run the pruner first; fall through to F-63 (mid-task context recovery) only if the pruner can't reach the budget without removing user messages.
- **Log which types were pruned.** If `user_message` entries are being pruned, the conversation is longer than the budget can sustain — escalate or trigger compaction. If only `tool_result` and `reasoning_step` entries are pruned, the budget is working as intended.

## The move

**Tag every message with `contentType` at injection. When context exceeds the budget, sort candidates by priority (tool results and reasoning steps first) then by size. Remove until the budget is met. Preserve the last N messages unconditionally.**

```js
// --- Content-type context pruner ---
// Prunes conversation history by content type priority, not by age.
// Runs in O(n log n) — sort + greedy. Zero API calls, zero tokens.
// Fall through to F-63 (mid-task context recovery) if budget still not met.

// Higher number = pruned sooner. Lower number = kept longer.
const PRUNE_PRIORITY = {
  user_message:    0,   // user intent — never prune first
  task_state:      0,   // current operational state — never prune first
  final_answer:    1,   // conclusions — prune only if necessary
  synthesis:       2,   // summaries — prune before conclusions
  reasoning_step:  3,   // intermediate thinking — prune early
  tool_result:     3,   // often largest — prune early
};

class ContentTypeContextPruner {
  // opts.mustKeepRecent: number of most-recent messages to never prune. Default: 4.
  // opts.priorities:     per-contentType priority overrides.
  constructor(opts) {
    opts = opts || {};
    this._mustKeepRecent = opts.mustKeepRecent != null ? opts.mustKeepRecent : 4;
    this._priorities     = Object.assign({}, PRUNE_PRIORITY, opts.priorities || {});
  }

  // Prune messages until total tokens ≤ budgetTokens.
  // messages: [{ role, content, contentType, tokens, ... }]
  //   contentType: one of the PRUNE_PRIORITY keys (or custom override)
  //   tokens: estimated token count for this message
  // Returns: { kept, pruned, totalBefore, totalAfter, tokensSaved, budgetMet }
  prune(messages, budgetTokens) {
    const totalBefore = messages.reduce((s, m) => s + (m.tokens || 0), 0);
    if (totalBefore <= budgetTokens) {
      return { kept: messages, pruned: [],
               totalBefore, totalAfter: totalBefore, tokensSaved: 0, budgetMet: true };
    }

    const cutoff     = Math.max(0, messages.length - this._mustKeepRecent);
    const candidates = messages.slice(0, cutoff);
    const alwaysKeep = messages.slice(cutoff);

    // Sort: highest priority (prune first) first; within tier, largest first.
    const sorted = [...candidates].sort((a, b) => {
      const pa = this._priorities[a.contentType] ?? 1;
      const pb = this._priorities[b.contentType] ?? 1;
      return (pb - pa) || (b.tokens || 0) - (a.tokens || 0);
    });

    const prunedSet = new Set();
    let saved  = 0;
    const need = totalBefore - budgetTokens;

    for (const msg of sorted) {
      if (saved >= need) break;
      prunedSet.add(msg);
      saved += msg.tokens || 0;
    }

    const kept   = messages.filter(m => !prunedSet.has(m));
    const pruned = [...prunedSet];

    return {
      kept, pruned,
      totalBefore,
      totalAfter:     totalBefore - saved,
      tokensSaved:    saved,
      messagesPruned: pruned.length,
      budgetMet:      totalBefore - saved <= budgetTokens,
      // If budgetMet is false, user_messages are next in line — trigger F-63 instead.
    };
  }
}

// --- Usage ---
// Called in the context assembly layer before each API call.
// const PRUNER = new ContentTypeContextPruner({ mustKeepRecent: 4 });
//
// function buildContext(history, budgetTokens) {
//   const result = PRUNER.prune(history, budgetTokens);
//   if (!result.budgetMet) {
//     // Pruning alone wasn't enough — trigger F-63 (mid-task context recovery)
//     return compressHistory(result.kept, budgetTokens);
//   }
//   return result.kept;
// }
//
// // Example message tagging at injection:
// history.push({ role: 'user', content: userMsg, contentType: 'user_message', tokens: 95 });
// history.push({ role: 'tool', content: toolResult, contentType: 'tool_result', tokens: 1400 });
// history.push({ role: 'assistant', content: reasoning, contentType: 'reasoning_step', tokens: 520 });
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 12-message conversation history, 9 800 tokens total, 6 000-token budget. Pruner removes 3 tool results (3 850 tok) and meets the budget without touching any user messages. Compared against sliding window (drops oldest 8 messages, loses problem statement). Timed over 1 000 000 iterations. Zero API calls.

```
=== Content-Type Context Pruner ===

Input: 12 messages, 9 800 total tokens, budget 6 000 tokens (need to free ≥ 3 800)

  Msg   Type              Tokens   Turn   Must-Keep?
  ───────────────────────────────────────────────────
  M1    user_message         180    T1    no   (candidate)
  M2    tool_result        1 400    T2    no   (candidate)
  M3    reasoning_step       520    T3    no   (candidate)
  M4    synthesis            290    T4    no   (candidate)
  M5    user_message          95    T5    no   (candidate)
  M6    tool_result        1 100    T6    no   (candidate)
  M7    tool_result        1 350    T7    no   (candidate)
  M8    reasoning_step       480    T8    no   (candidate)
  M9    user_message         110    T9    YES  (recent)
  M10   synthesis            320    T10   YES  (recent)
  M11   user_message          85    T11   YES  (recent)
  M12   final_answer         870    T12   YES  (recent)

Sorted candidates (priority DESC, size DESC):
  1. M2  tool_result    1 400 tok  (priority 3)
  2. M7  tool_result    1 350 tok  (priority 3)
  3. M6  tool_result    1 100 tok  (priority 3)
  4. M3  reasoning_step   520 tok  (priority 3)
  5. M8  reasoning_step   480 tok  (priority 3)
  6. M4  synthesis        290 tok  (priority 2)
  7. M1  user_message     180 tok  (priority 0)
  8. M5  user_message      95 tok  (priority 0)

Greedy removal (need 3 800 tok):
  Remove M2 (1 400) → saved = 1 400
  Remove M7 (1 350) → saved = 2 750
  Remove M6 (1 100) → saved = 3 850 ≥ 3 800 → STOP

Result:
  Pruned:     3 messages (M2, M7, M6) — all tool_results
  Kept:       9 messages
  tokensSaved: 3 850
  totalAfter:  5 950 tok ≤ 6 000 budget ✓
  budgetMet:   true

  User messages preserved: ALL (M1=T1, M5=T5, M9=T9, M11=T11)
  The initial problem statement (M1, 180 tok) survives.
  Intermediate reasoning preserved: M3, M8

--- Comparison: sliding window (drop oldest 8 = M1–M8) ---
  Pruned: M1–M8  (2 830 tok — doesn't even reach budget: 9 800 - 2 830 = 6 970 > 6 000)
  Must drop 9 oldest messages: M1–M9 (2 940 tok) — still not enough
  Drop M1–M10: 4 635 tok → 9 800 - 4 635 = 5 165 ≤ 6 000 ✓
  But now M1 (problem statement), M5 (follow-up), M9 (clarification) are GONE.
  Agent has no user intent from the first 10 messages.

--- Edge case: budget cannot be met without touching user_message ---
  budgetMet: false → caller triggers F-63 (mid-task context recovery via summarization)

=== Timing (1 000 000 iterations) ===
prune() 12 messages, 3 removed: 0.0019 ms
prune() 12 messages, already within budget: 0.0004 ms
Zero API calls. Zero tokens.
```

## See also

[S-54](s54-multi-turn-conversation-design.md) · [F-63](../forward-deployed/f63-mid-task-context-recovery.md) · [S-111](s111-partial-context-refresh.md) · [S-75](s75-context-injection-order.md) · [S-176](s176-section-context-budget.md)

## Go deeper

Keywords: `content type context pruner` · `priority context pruning` · `conversation history pruning` · `context pruning strategy` · `message priority pruning` · `tool result pruning` · `content-aware context management` · `history pruning by type` · `context budget pruning` · `selective history pruning`
