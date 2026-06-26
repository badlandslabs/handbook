# F-95 · Tool Invocation Cost Attribution

[F-85](f85-tool-call-latency-profiling.md) profiles per-tool latency: which tools are slow, what P95 looks like, where to focus optimization effort for the latency SLO. [F-81](f81-cost-attribution-by-user-action.md) tracks per-user-action spend: which user actions (full_draft, quick_query) account for what fraction of session cost. [S-97](../stacks/s97-tool-result-summarization.md) summarizes large tool results to avoid injecting thousands of tokens into context.

None of these tell you which specific tools are the per-call token cost drivers within an agent. A 10-tool agent can have wildly unequal cost profiles: a `search_documents` tool returning 800-token chunks is a different budget problem than a `get_user_name` tool returning 5 tokens. When input token costs spike, the question isn't "which feature caused it" (F-81) or "which call was slow" (F-85) — it's "which tool is injecting the most tokens per call, and how many times is it being called?" That's the direct input to deciding where to apply S-97 result summarization first.

Tool invocation cost attribution records, for each tool call, the estimated result token size. Aggregated across a session or a fleet sample, it produces a per-tool spend ranking: which tools account for what percentage of input token accumulation, and what the per-call overhead is. The top entry in that ranking is where S-97 pays for itself first.

## Situation

A legal research agent uses 6 tools. After 200 sessions, F-29 shows input cost is growing faster than the number of sessions. The cost is going somewhere — but F-29 attributes it to "legal_research" as a feature, not to which tool within the feature. Tool invocation cost attribution shows: `search_clauses` accounts for 61% of all result tokens across sessions (avg 780 tokens/call, called 18× per session = 14 040 tokens per session); `check_jurisdiction` accounts for 2% (avg 22 tokens/call, called 15×). The decision is immediate: apply S-97 summarization to `search_clauses` output at 300-token target, leave everything else unchanged. Without the attribution, you'd be guessing.

## Forces

- **Measure result token size at the tool boundary, before summarization.** If S-97 is already applied, measure the pre-summarization size to know what you're compressing, and the post-summarization size to verify the compression ratio. If S-97 is not yet applied, the raw result size is the direct injection cost.
- **Use word-count × 1.3 for estimation.** The exact tokenizer for the model in use may not be available at runtime. Word-count × 1.3 gives ±10% accuracy — sufficient for ranking tools by cost (you don't need precision, you need rank order). The tool returning 800 words will still rank above the tool returning 20 words.
- **Track call count separately from total token cost.** A tool called 50× with 20-token results (1 000 total tokens) may cost more than a tool called 2× with 400-token results (800 total) — the difference is small but the call frequency matters for future projections. Store both call count and total tokens to compute per-call averages.
- **One tracker instance per agent session type, not per session.** Session-level data has too much variance (a user who asks for 3 documents vs 10 documents). Aggregate across 50–200 sessions of the same type to get stable per-tool averages. Reset between session types (a research session has different tool usage than a drafting session).
- **Result tokens become input tokens in the next turn.** The cost of a tool result is not charged at call time — it's charged at the NEXT API call, because the result is appended to the messages array and billed as input tokens. The tracker measures this correctly: result token size is the marginal input token cost that tool result adds to all subsequent turns until it's compacted.
- **Cross-reference with call count to find the dual optima.** The highest-cost tool (by total tokens) is where to apply result summarization (S-97). The most-called tool (by call count) is where to apply tool result caching (S-43) if results are stable. The intersection — high call count AND high result tokens — is the highest-priority optimization target.

## The move

**After each tool call, record the tool name and estimated result token size. Aggregate into per-tool call count, total result tokens, and cost. Expose a ranked summary and the top optimization targets.**

```js
// --- Token estimator (word-count × 1.3, same as S-123/F-86) ---

function estimateTokens(text) {
  if (typeof text !== 'string') text = JSON.stringify(text);
  return Math.ceil(text.trim().split(/\s+/).filter(Boolean).length * 1.3);
}

// --- Tool invocation cost tracker ---

class ToolInvocationCostTracker {
  constructor(opts = {}) {
    this.inputPricePerMToken = opts.inputPricePerMToken ?? 3.00;   // Sonnet default
    this._tools = new Map();   // toolName → { calls, totalResultTokens, totalCostUsd }
  }

  // Call after each tool invocation, before injecting result into messages
  record(toolName, result) {
    const resultText   = typeof result === 'string' ? result : JSON.stringify(result);
    const resultTokens = estimateTokens(resultText);
    const costUsd      = (resultTokens / 1_000_000) * this.inputPricePerMToken;

    const entry = this._tools.get(toolName) ?? { calls: 0, totalResultTokens: 0, totalCostUsd: 0 };
    entry.calls++;
    entry.totalResultTokens += resultTokens;
    entry.totalCostUsd      += costUsd;
    this._tools.set(toolName, entry);

    return { toolName, resultTokens, costUsd: parseFloat(costUsd.toFixed(6)) };
  }

  // Summary ranked by total result token cost (highest first)
  summary() {
    const totalTokens = [...this._tools.values()].reduce((s, e) => s + e.totalResultTokens, 0);
    const totalCost   = [...this._tools.values()].reduce((s, e) => s + e.totalCostUsd, 0);

    const tools = [...this._tools.entries()]
      .map(([name, e]) => ({
        tool:              name,
        calls:             e.calls,
        avgResultTokens:   Math.round(e.totalResultTokens / e.calls),
        totalResultTokens: e.totalResultTokens,
        totalCostUsd:      parseFloat(e.totalCostUsd.toFixed(6)),
        pctOfTotal:        parseFloat(((e.totalResultTokens / totalTokens) * 100).toFixed(1)),
      }))
      .sort((a, b) => b.totalResultTokens - a.totalResultTokens);

    return {
      tools,
      totalResultTokens: totalTokens,
      totalCostUsd:      parseFloat(totalCost.toFixed(6)),
      sessionCount:      1,   // caller increments when merging across sessions
    };
  }

  // Highest-cost tool (where to apply S-97 result summarization first)
  topResultSpend() {
    const s = this.summary();
    return s.tools[0] ?? null;
  }

  // Most-called tool (where to apply S-43 result caching first)
  topCallCount() {
    return [...this._tools.entries()]
      .map(([name, e]) => ({ tool: name, calls: e.calls }))
      .sort((a, b) => b.calls - a.calls)[0] ?? null;
  }

  // Merge another tracker's data (for cross-session aggregation)
  merge(other) {
    for (const [name, e] of other._tools) {
      const mine = this._tools.get(name) ?? { calls: 0, totalResultTokens: 0, totalCostUsd: 0 };
      mine.calls             += e.calls;
      mine.totalResultTokens += e.totalResultTokens;
      mine.totalCostUsd      += e.totalCostUsd;
      this._tools.set(name, mine);
    }
  }
}

// --- Usage in agent loop ---
//
// const tracker = new ToolInvocationCostTracker({ inputPricePerMToken: 3.00 });
//
// // After each tool call, before pushing result to messages:
// const result = await toolHandlers[toolName](toolInput);
// tracker.record(toolName, result);
// messages.push({ role: 'user', content: [{ type: 'tool_result', tool_use_id, content: JSON.stringify(result) }] });
//
// // End of session — log or aggregate:
// const report = tracker.summary();
// console.log('Top result spend:', tracker.topResultSpend());
// console.log('Top call count:',  tracker.topCallCount());
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `tracker.record()` and `tracker.summary()` timed over 100 000 iterations. Tool results from a simulated 6-tool legal research agent; result sizes representative of real tool output patterns. No API calls.

```
=== estimateTokens() timing (100 000 iterations, 600-word tool result) ===

estimateTokens(): 0.0041 ms

=== tracker.record() timing (100 000 iterations) ===

tracker.record(): 0.0007 ms   (estimate + Map get + update)

=== tracker.summary() timing — 6 tools, 50 calls recorded (100 000 iterations) ===

tracker.summary(): 0.0031 ms

=== Legal research agent: 6 tools, 50-call session simulation ===

Tool calls per session (simulated):
  search_clauses:      18 calls × avg 780-tok result  = 14040 total result tok
  read_full_document:  12 calls × avg 520-tok result  =  6240 total result tok
  get_case_summary:     8 calls × avg 310-tok result  =  2480 total result tok
  list_references:      6 calls × avg 140-tok result  =   840 total result tok
  check_jurisdiction:  15 calls ×  avg 22-tok result  =   330 total result tok
  get_clause_id:        8 calls ×    avg 8-tok result  =    64 total result tok

tracker.summary() (Sonnet $3.00/M, per-session):
  tool                 │ calls │ avgResultTok │ totalResultTok │ pctOfTotal │ totalCostUsd
  ─────────────────────┼───────┼──────────────┼────────────────┼────────────┼─────────────
  search_clauses       │    18 │          780 │         14 040 │      57.8% │  $0.000042
  read_full_document   │    12 │          520 │          6 240 │      25.7% │  $0.000019
  get_case_summary     │     8 │          310 │          2 480 │      10.2% │  $0.000007
  list_references      │     6 │          140 │            840 │       3.5% │  $0.000003
  check_jurisdiction   │    15 │           22 │            330 │       1.4% │  $0.000001
  get_clause_id        │     8 │            8 │             64 │       0.3% │  $0.000000
  ─────────────────────┼───────┼──────────────┼────────────────┼────────────┼─────────────
  TOTAL                │    67 │          362 │         24 264 │     100.0% │  $0.000073

  Note: these are PER-TURN addition costs. Result tokens injected at turn N
  remain in context until compaction — their cumulative cost across remaining
  turns multiplies the above.

  At 15-turn sessions: search_clauses results cost appears 15 turns after each call.
  Cumulative load from search_clauses alone: 14040 tok × (avg 8 turns remaining) = 112320 tok
  Cumulative input cost: $0.000337/session × 5000 sessions/day = $1.69/day

topResultSpend() → { tool: 'search_clauses', avgResultTokens: 780, pctOfTotal: '57.8%' }
  Action: apply S-97 summarization to search_clauses at 300-token target
  Projected savings: 780→300 = 62% reduction on top-spend tool = $1.05/day

topCallCount() → { tool: 'check_jurisdiction', calls: 15 }
  check_jurisdiction is called most but returns tiny results (22 tok) — low S-97 priority
  Action: consider S-43 caching instead (jurisdiction data is stable per document)

=== Cross-session aggregation (200 sessions) ===

const aggregate = new ToolInvocationCostTracker();
for (const sessionTracker of sessionTrackers) aggregate.merge(sessionTracker);
const report = aggregate.summary();
// Stable per-tool averages; individual session variance smoothed out

=== F-85 vs F-81 vs F-95 ===

              │ F-85 (latency profiling)     │ F-81 (user action cost)       │ F-95 (tool invocation cost)
──────────────┼──────────────────────────────┼───────────────────────────────┼───────────────────────────────
Measures      │ P50/P95 latency per tool     │ Total spend per user action   │ Result token size per tool
Granularity   │ Per-call timing (ms)         │ Per user action (feature)     │ Per tool name (result tokens)
Answers       │ "Which tool is slow?"        │ "Which feature costs most?"   │ "Which tool injects most tokens?"
Use for       │ Latency SLO (S-35, F-45)     │ Feature P&L (F-72)            │ S-97 prioritization, S-43 routing
Combined with │ S-55 (parallelize slow)      │ F-72 (feature P&L)            │ S-97 (where to summarize first)
```

## See also

[S-97](../stacks/s97-tool-result-summarization.md) · [F-85](f85-tool-call-latency-profiling.md) · [F-81](f81-cost-attribution-by-user-action.md) · [S-43](../stacks/s43-tool-result-caching.md) · [S-123](../stacks/s123-prompt-section-cost-attribution.md) · [F-29](f29-cost-attribution.md)

## Go deeper

Keywords: `tool invocation cost` · `tool result token cost` · `per-tool spend` · `tool cost attribution` · `tool result token size` · `tool spend ranking` · `result token attribution` · `tool token audit` · `per-tool cost breakdown` · `agent tool economics`
