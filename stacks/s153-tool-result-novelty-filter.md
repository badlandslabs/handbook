# S-153 · Tool Result Novelty Filter

[S-43](s43-tool-result-caching.md) caches tool call responses: when the model calls `get_customer(id=123)` a second time with the same arguments, the cached response is returned without hitting the API and without counting new input tokens. [S-150](s150-prompt-context-block-deduplication.md) deduplicates blocks at prompt assembly time: if the same content appears in both the system prompt and a tool result, the lower-priority copy is dropped before the prompt is built.

Both miss a different failure mode. S-43 requires identical arguments — if the model calls `get_customer(id=123, fields=['name','status'])` on turn 1 and `get_customer(id=123)` on turn 5, the arguments differ, the cache misses, the call goes through, the result arrives, and it is added to the messages array. The result's content may be 87% overlapping with what turn 1's result already injected. S-150 checks within one prompt assembly; it does not check the new result against the running messages history accumulated across prior turns.

The cost is real. Each block added to the messages array costs input tokens on every subsequent turn. A 127-token customer profile injected at turn 3 in a 10-turn session costs 127 × 7 = 889 tokens of accumulated input cost before the session ends. If the content was already known from turn 1, those 889 tokens are waste.

A tool result novelty filter runs a Jaccard similarity check after each tool call returns, before the result is added to the messages array. It compares the incoming result against prior content blocks already present in the messages array. If similarity exceeds a threshold (default 0.85), the result is marked REDUNDANT and skipped. The model's messages array stays shorter; subsequent turn costs fall.

## Situation

A CRM support agent runs a 10-turn session. On turn 1, `get_customer(id=AC-2291)` returns:

```
Customer ID: AC-2291. Company: Acme Corp. Plan: enterprise. Status: active.
Billing cycle: monthly. Renewal: January. Contact: billing@acme.com.
```

This block is added to messages (127 tokens).

On turn 5, the model decides to re-fetch the customer. It calls `get_customer(id=AC-2291, include=['plan','status'])` — different arguments, cache miss. The result arrives:

```
Customer account Acme Corp, ID AC-2291. Plan: enterprise. Status: active.
Billing cycle: monthly. Renewal: January. Contact: billing@acme.com.
```

Without the filter: this is added to messages. Two copies of essentially the same facts now ride in context for turns 6–10 (5 turns × 127 tokens = 635 tokens of waste on top of the original).

With the filter: `check(result, priorContent)` → Jaccard similarity against the turn-1 block = 0.875 > 0.85 threshold → REDUNDANT → skipped. A short acknowledgment note is injected instead: `[get_customer(AC-2291): no new data]`. The model sees the note and continues without re-reading the full profile.

## Forces

- **The check runs at a different hook than S-43 and S-150.** S-43 fires before the tool call (cache hit → return cached value). S-150 fires at prompt assembly time (comparing N blocks in one pass). This filter fires after the tool call returns, before deciding whether to append the result to messages. These three hooks compose without conflict: S-43 eliminates redundant calls; this filter catches the cases S-43 misses (different args, same content).
- **Jaccard is lexical, not semantic.** Two responses with different wording that mean the same thing will not be detected as redundant. The filter catches structural near-copies: the same database record returned in slightly different field order or with minor wording differences. For semantic deduplication across paraphrases, use embedding cosine similarity — but that is 10–50× slower and rarely justified at this hook.
- **Threshold 0.85 is deliberately high.** At 0.85, a result must share 85% of its non-trivial words with a prior block before being blocked. A partial update (status changed, new overdue flag) will typically fall to 0.65 similarity — injected as expected. The threshold is a precision dial: lower it to catch more overlaps (risk: blocking genuinely useful updates); raise it to block only near-copies (risk: missing some).
- **Short results are exempt.** Results under `minWords: 10` pass through without checking. A tool that returns `{"status": "ok"}` (3 content words) would produce meaningless Jaccard comparisons against long prior blocks. Exempt short results unconditionally.
- **The check is O(words) per prior block.** At 0.06ms for a 20-word result vs. 3 prior 20-word strings, a 10-turn session with 8 tool calls incurs ~0.5ms total filter overhead. That is negligible against the 500–1200ms per model call. If the prior content array grows large (50+ blocks), the check will grow proportionally — consider only comparing against recent N blocks or tool results of the same tool type.
- **Skipping is never silent.** When REDUNDANT, inject a stub note rather than nothing. A completely absent tool result in the messages array confuses the model's sense of what happened on that turn. A stub (`[tool_name: no new data]`) maintains the tool-use/tool-result message pair structure required by the API without adding content tokens.

## The move

**After each tool call, check similarity against prior content in messages. Skip injection on REDUNDANT; inject a stub note instead.**

```js
// --- Tool result novelty filter ---
// Compares incoming tool result against prior message content blocks.
// If similarity >= threshold, skips injection and adds a stub note instead.
// Threshold 0.85: blocks near-copies, passes updates (status changes, new fields).

class ToolResultNoveltyFilter {
  constructor(opts = {}) {
    this._threshold = opts.threshold ?? 0.85;
    this._minWords  = opts.minWords  ?? 10;
  }

  _wordSet(text) {
    return new Set(
      text.toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).filter(w => w.length > 2)
    );
  }

  _jaccard(a, b) {
    const setA = this._wordSet(a);
    const setB = this._wordSet(b);
    let inter = 0;
    for (const w of setA) if (setB.has(w)) inter++;
    const union = setA.size + setB.size - inter;
    return union === 0 ? 0 : inter / union;
  }

  // toolResultText: raw text content of the tool result
  // priorContent:   array of text strings already in the messages array
  // Returns: { inject: bool, reason: string, similarity?: number, mostSimilarIndex?: number }
  check(toolResultText, priorContent) {
    const words = toolResultText.split(/\s+/).filter(Boolean).length;
    if (words < this._minWords) {
      return { inject: true, reason: 'TOO_SHORT_TO_FILTER', words };
    }
    let maxSim = 0;
    let mostSimilarIdx = -1;
    for (let i = 0; i < priorContent.length; i++) {
      const sim = this._jaccard(toolResultText, priorContent[i]);
      if (sim > maxSim) { maxSim = sim; mostSimilarIdx = i; }
    }
    if (maxSim >= this._threshold) {
      return {
        inject:           false,
        reason:           'REDUNDANT',
        similarity:       parseFloat(maxSim.toFixed(3)),
        mostSimilarIndex: mostSimilarIdx,
      };
    }
    return {
      inject:     true,
      reason:     'NOVEL',
      similarity: parseFloat(maxSim.toFixed(3)),
    };
  }
}

// --- Integration pattern ---
// Collect prior tool result content from the messages array.
// After each tool call, run the filter and choose inject vs stub.

const NOVELTY_FILTER = new ToolResultNoveltyFilter({ threshold: 0.85, minWords: 10 });

function extractPriorContent(messages) {
  // Pull text from prior tool_result content blocks
  return messages
    .filter(m => m.role === 'user')
    .flatMap(m => m.content ?? [])
    .filter(b => b.type === 'tool_result')
    .map(b => (Array.isArray(b.content) ? b.content : [b.content])
              .filter(c => c.type === 'text').map(c => c.text).join(' '))
    .filter(t => t.length > 0);
}

async function callToolWithNoveltyFilter(messages, toolName, toolArgs, executor) {
  const rawResult = await executor(toolName, toolArgs);
  const rawText   = typeof rawResult === 'string' ? rawResult : JSON.stringify(rawResult);

  const prior  = extractPriorContent(messages);
  const verdict = NOVELTY_FILTER.check(rawText, prior);

  if (!verdict.inject) {
    // Stub: maintain tool_result message pair without injecting full content
    return {
      type:       'tool_result',
      content:    [{ type: 'text', text: `[${toolName}: no new data — ${rawText.length} chars, similarity ${verdict.similarity} to turn-${verdict.mostSimilarIndex + 1} result]` }],
      _filtered:  true,
      _similarity: verdict.similarity,
    };
  }

  return {
    type:    'tool_result',
    content: [{ type: 'text', text: rawText }],
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` timed over 100 000 iterations against 3 prior content strings (20 words each). Tool result strings are representative CRM record outputs.

```
=== ToolResultNoveltyFilter timing (100 000 iterations) ===

check() — NOVEL     (3 prior strings):  0.0593 ms
check() — REDUNDANT (3 prior strings):  0.0605 ms

Note: Jaccard is O(words in both strings). 3 prior × 20-word strings
at 0.06ms is negligible vs 500–1200ms model call latency.
A session with 8 tool calls incurs ~0.5ms total filter overhead.

=== Prior content in messages array (3 prior tool results) ===

Block 0 (turn 1, get_customer): "Customer ID AC-2291 Acme Corp status active plan enterprise billing monthly renewal January contact billing@acme.com"
Block 1 (turn 2, get_orders):   "Recent orders ORD-001 amount 12000 date 2026-01-15 status shipped ORD-002 amount 8500 status pending"
Block 2 (turn 3, get_tickets):  "Support tickets open tickets none closed tickets 3 last contact 2026-03-10 category billing resolved"

=== Scenario A: Novel tool result (invoice, not in prior) ===

get_invoice(id=INV-4421):
  "Invoice INV-4421 amount 23500 due date 2026-07-01 status unpaid line items consulting 15000 software 8500"

check(): similarity=0.208 → NOVEL → inject full result

=== Scenario B: Redundant customer re-fetch (same data, different arg format) ===

get_customer(id=AC-2291, fields=['name','plan','status']):
  "Customer account Acme Corp ID AC-2291 plan enterprise status active billing cycle monthly renewal January contact billing@acme.com"

check(): similarity=0.875 ≥ 0.85 → REDUNDANT → skip
Stub injected: "[get_customer: no new data — 128 chars, similarity 0.875 to turn-1 result]"

Turn-5 cost: 12 tokens (stub) vs 127 tokens (full result).
Remaining turns 6-10 (5 turns) save: (127-12) × 5 = 575 input tokens.
At Sonnet $3.00/M: $0.000173/skip.

=== Scenario C: Partially new result (status changed + overdue note added) ===

get_customer(id=AC-2291):
  "Customer account Acme Corp ID AC-2291 plan enterprise status SUSPENDED billing cycle monthly renewal January contact billing@acme.com payment overdue 45 days"

check(): similarity=0.650 < 0.85 → NOVEL → inject full result
Status change ("active"→"SUSPENDED") and new overdue field are preserved.

=== Cost projection ===

Model:                  Sonnet ($3.00/M input)
Sessions/day:           10 000
Skip rate:              12% (1 redundant tool call per ~8 session tool calls)
Avg blocked tokens:     127 (one typical CRM record)
Avg remaining turns:    7  (blocked at turn 3 in 10-turn session)
Tokens saved per skip:  127 × 7 = 889

Daily savings:  10 000 × 0.12 × 889 tokens × $3.00/M = $3.20/day

Filter overhead: 0.06ms/check × 8 tool calls/session × 10 000 sessions = 4.8s total CPU/day — negligible.

=== S-43 vs S-150 vs S-153 ===

              │ S-43 (tool result cache)        │ S-150 (block dedup at assembly)  │ S-153 (novelty filter)
──────────────┼─────────────────────────────────┼──────────────────────────────────┼─────────────────────────────────
Hook          │ Before tool call (cache check)  │ Prompt assembly (cross-source)   │ After tool call, before inject
Dedup basis   │ Exact arg match                 │ FNV-1a hash (exact content)      │ Jaccard (lexical similarity)
Misses        │ Different args, same content    │ Multi-turn prior history         │ Semantic paraphrases
Catches       │ Identical repeat calls          │ System prompt ↔ tool result      │ Approximate re-fetches
Result        │ Returns cached, still injects   │ Drops lower-priority copy        │ Replaces with stub note
```

## See also

[S-43](s43-tool-result-caching.md) · [S-150](s150-prompt-context-block-deduplication.md) · [S-122](s122-retrieved-chunk-dedup.md) · [S-103](s103-cost-aware-context-management.md) · [S-97](s97-tool-result-summarization.md) · [S-130](s130-structured-tool-result-compression.md)

## Go deeper

Keywords: `tool result novelty filter` · `redundant tool result detection` · `tool call deduplication messages` · `jaccard tool result similarity` · `skip tool result injection` · `tool result context accumulation` · `redundant agent tool call` · `tool result overlap detection` · `agent context deduplication` · `tool result injection filter`
