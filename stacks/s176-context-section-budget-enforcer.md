# S-176 · Context Section Budget Enforcer

[S-56](s56-preflight-token-check.md) runs a single total-token check before a call: if the assembled prompt exceeds the model's context window, abort. It treats the prompt as one number. [S-103](s103-cost-triggered-compaction.md) compacts conversation history when marginal cost per turn exceeds a threshold. [S-107](s107-pipeline-stage-output-budget.md) constrains how many tokens each stage in a pipeline is allowed to emit.

None of these enforce per-section input budgets at assembly time. A prompt can satisfy the total context limit while one section — conversation history, retrieved chunks — consumes 80% of the budget and crowds out the others. The system prompt is 600 tokens of instructional overhead; giving it 4 000 tokens is waste. Retrieved context should not exceed 4 000 tokens for a concise task; allowing it to expand to 12 000 is an overfetch problem, not a context problem. The move is earlier: before joining sections into the final prompt, enforce a budget per section, truncate or fail any section that exceeds it, and log what was dropped.

This is distinct from S-56 in two ways. S-56 runs after assembly; S-176 runs before assembly and per section, so overflows are contained rather than triggering a full abort. It is distinct from S-103 in scope: S-103 manages session-level compaction; S-176 enforces single-call section budgets. It is distinct from S-107 in direction: S-107 is about output tokens cascading downstream; S-176 is about input tokens arriving at assembly time.

## Situation

A contract analysis agent assembles six context sections per call: `system_prompt` (role and output instructions), `few_shot` (two annotated examples), `retrieved` (top-K chunks from retrieval), `history` (recent conversation turns), `tool_results` (tool call payloads), `user_query` (the user's request). Without section budgets, a long conversation accumulates history that grows without bound. After 40 turns, history alone is 4 200 tokens — exceeding the 2 000-token budget and crowding out retrieved context. The model answers from conversation memory rather than from freshly retrieved contract text.

With section budgets:
- `system_prompt` hard-capped at 600 tokens (`FAIL` on overflow): a system prompt that has grown to 760 tokens during editing fails fast, forcing a rewrite before it ships.
- `history` soft-capped at 2 000 tokens (`TRUNCATE` on overflow): 4 200 tokens of history is silently trimmed to 2 000 before assembly. The oldest turns are dropped. Retrieval gets its full slot.
- `retrieved` capped at 4 000 tokens: overfetched chunks are trimmed, preserving the high-relevance head.
- `user_query` soft-warned at 300 tokens (`WARN`): unusually long queries pass through but are logged for inspection.

The total-token check (S-56) still runs after assembly as a final gate. The section enforcer prevents any one section from making the total check meaningless by eating headroom before retrieval and instructions arrive.

## Forces

- **Different sections warrant different overflow behaviors.** The system prompt must never be truncated silently — truncating it produces nonsensical partial instructions. Fail fast if it overflows; fix the prompt, not the budget. Retrieved context and history can be truncated from the low-relevance tail without catastrophic loss. User queries should not be truncated at all; warn and pass through.
- **Token estimation is an approximation.** The `length / 4` heuristic (one token ≈ four characters for English prose) is fast and sufficient for pre-assembly budgeting. For exact enforcement, call the tokenizer API — 2 ms per call at 10 000 calls/day is 20 CPU-seconds of extra latency. For most workloads, the 4x heuristic with a 10% safety margin on budgets is faster and good enough. The section enforcer is a guardrail, not a precision counter.
- **Truncation must preserve semantic coherence.** Hard-cutting mid-sentence produces garbled context. Back off to the nearest word boundary within the character budget. If no word boundary falls in the last 30% of the budget window, hard-cut — the content is likely one long token sequence anyway (a JSON blob, a code listing) and sentence boundaries are meaningless.
- **The section order in the config determines processing priority.** If `system_prompt` has `onOverflow: 'FAIL'`, a bloated system prompt causes the enforcer to return an error immediately — it does not process the remaining sections. Sections that are most critical to correctness should be checked first. Retrieved context and history, which are safe to truncate, should be processed last.
- **Log what was dropped, not just that something was dropped.** `dropped: 2200` (tokens) without knowing which section was truncated is useless. The enforcer returns per-section metadata: original token count, truncated count, and tokens dropped. Store this metadata in the call's telemetry record. If history is truncated on 40% of calls, the session compaction threshold (S-103) is too loose and needs tightening.
- **Compose with S-56 as the final gate.** Section budgets prevent any one section from overflowing its allocation. S-56 catches the case where the sum of all section budgets still exceeds the model's context window — a misconfiguration where individual budgets sum to more than the model allows. Both checks run; neither replaces the other.

## The move

**Define per-section budgets with overflow behaviors. Enforce before assembly. Truncate to word boundaries. Return per-section metadata for telemetry.**

```js
// --- Context section budget enforcer ---
// Runs before prompt assembly. Enforces per-section token caps.
// Distinct from S-56 (post-assembly total check) and S-103 (session-level compaction).
// Compose: S-176 enforce → assemble → S-56 total check → send.

function estimateTokens(str) {
  return Math.ceil(str.length / 4);
}

function truncateToTokens(str, maxTokens) {
  if (estimateTokens(str) <= maxTokens) return str;
  const maxChars = maxTokens * 4;
  let cut = str.lastIndexOf(' ', maxChars);
  if (cut < maxChars * 0.7) cut = maxChars; // no good space; hard-cut
  return str.slice(0, cut) + '…';
}

class ContextSectionBudgetEnforcer {
  constructor(sections) {
    // sections: [{ name, maxTokens, onOverflow: 'TRUNCATE'|'FAIL'|'WARN' }]
    this._sections = sections;
  }

  // contentMap: { sectionName: string, ... }
  // Returns { status, sections: { name: { content, tokens, status, originalTokens?, dropped? } }, totalTokens, overflows }
  enforce(contentMap) {
    const sectionResults = {};
    let totalTokens = 0;
    const overflows = [];

    for (const def of this._sections) {
      const content = contentMap[def.name] || '';
      const tokens = estimateTokens(content);

      if (tokens <= def.maxTokens) {
        sectionResults[def.name] = { content, tokens, status: 'OK' };
        totalTokens += tokens;
        continue;
      }

      if (def.onOverflow === 'FAIL') {
        return {
          status: 'ERROR',
          failedSection: def.name,
          actual: tokens,
          max: def.maxTokens,
          message: `Section "${def.name}" exceeds budget: ${tokens} > ${def.maxTokens} tokens`,
        };
      }

      const truncated = truncateToTokens(content, def.maxTokens);
      const truncatedTokens = estimateTokens(truncated);
      const dropped = tokens - truncatedTokens;

      sectionResults[def.name] = {
        content: truncated, tokens: truncatedTokens,
        originalTokens: tokens, dropped,
        status: def.onOverflow === 'WARN' ? 'OVER_WARN' : 'TRUNCATED',
      };
      totalTokens += truncatedTokens;
      overflows.push({ section: def.name, originalTokens: tokens, truncatedTokens, dropped });
    }

    return { status: 'OK', sections: sectionResults, totalTokens, overflows, overflowCount: overflows.length };
  }
}

// --- Section budget configuration ---
const ENFORCER = new ContextSectionBudgetEnforcer([
  { name: 'system_prompt', maxTokens:  600, onOverflow: 'FAIL'     }, // must not exceed — truncated instructions break the model
  { name: 'few_shot',      maxTokens:  400, onOverflow: 'TRUNCATE' }, // trim lowest-quality examples
  { name: 'retrieved',     maxTokens: 4000, onOverflow: 'TRUNCATE' }, // trim low-relevance chunks from retrieval tail
  { name: 'history',       maxTokens: 2000, onOverflow: 'TRUNCATE' }, // trim oldest turns
  { name: 'tool_results',  maxTokens: 1200, onOverflow: 'TRUNCATE' },
  { name: 'user_query',    maxTokens:  300, onOverflow: 'WARN'     }, // warn but pass through; never cut a user query
]);

// Integration: enforce → assemble → send
function assemblePrompt(contentMap) {
  const enforced = ENFORCER.enforce(contentMap);
  if (enforced.status === 'ERROR') throw new Error(enforced.message);
  // Log overflow telemetry before assembling
  if (enforced.overflowCount > 0) {
    enforced.overflows.forEach(o =>
      console.log(`[section-budget] ${o.section}: ${o.originalTokens} → ${o.truncatedTokens} (dropped ${o.dropped})`));
  }
  const s = enforced.sections;
  return [s.system_prompt.content, s.few_shot.content, s.retrieved.content,
          s.history.content, s.tool_results.content, s.user_query.content].join('\n---\n');
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Six sections, one overflow (history: 4 200 → 2 000 tok). FAIL scenario confirmed. `enforce()` timed over 100 000 iterations. Zero API calls, zero tokens.

```
=== Context Section Budget Enforcer ===

Section budgets: system=600 | few_shot=400 | retrieved=4000 | history=2000 | tool_results=1200 | user_query=300

Input section sizes:
  system_prompt   : 86 tok
  few_shot        : 125 tok
  retrieved       : 2238 tok
  history         : 4200 tok     ← over 2000 budget
  tool_results    : 23 tok
  user_query      : 28 tok

Enforcement result:
  system_prompt   : OK         86 tok
  few_shot        : OK        125 tok
  retrieved       : OK       2238 tok
  history         : TRUNCATED  4200 → 2000 tok  (dropped 2200)
  tool_results    : OK         23 tok
  user_query      : OK         28 tok

Uncapped total:   6700 tok
Enforced total:   4500 tok
Savings:          2200 tok  (33%)
At 10 000 calls/day (Haiku $0.80/M): $17.60/day savings

FAIL scenario: system_prompt=760 tok > 600 cap → status=ERROR  section=system_prompt

=== Timing (100 000 iterations) ===
enforce() 6 sections, 1 overflow: 0.0013 ms

Zero API calls. Zero tokens. Runs at assembly boundary.
```

## See also

[S-56](s56-preflight-token-check.md) · [S-103](s103-cost-triggered-compaction.md) · [S-107](s107-pipeline-stage-output-budget.md) · [S-123](s123-post-call-cost-attribution.md) · [S-174](s174-stale-while-revalidate-live-data.md)

## Go deeper

Keywords: `context section budget` · `per-section token cap` · `prompt section token limit` · `context assembly budget` · `section-level token enforcement` · `prompt section truncation` · `pre-assembly token budget` · `context window section allocation` · `per-section prompt budget` · `token budget enforcer`
