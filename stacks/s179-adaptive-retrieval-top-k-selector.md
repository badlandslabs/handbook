# S-179 · Adaptive Retrieval Top-K Selector

[S-49](s49-retrieval-evaluation.md) measures Recall@K and Precision@K for a fixed K value — it tells you whether the K you chose is finding the right chunks. [S-66](s66-retrieval-score-thresholds.md) cuts results below a similarity score floor — a quality filter that removes low-confidence chunks regardless of rank. [S-176](s176-context-section-budget-enforcer.md) hard-caps the total tokens in a context section after retrieval, truncating if the retrieved set exceeds the budget.

None of these choose K before retrieval. Most systems fix K at deployment time: always top-5, always top-10. Fixed K is wasteful for simple queries and starving for complex ones. A factual lookup — "what is the contract value?" — needs one or two high-confidence chunks; retrieving ten wastes tokens and dilutes relevance. A comparative analysis across entities needs eight or ten chunks to cover the evidence. Fixed K gives the same budget to both.

The adaptive top-K selector computes K before each retrieval call from three inputs: the available token budget for the context section (from S-176), the average chunk size in this corpus, and per-query-type bounds that encode how much context different query types actually need. The result is the largest K that fits the budget, clamped between the minimum and preferred K for the query type. Query types with high preferred K (comparative: 10) fetch more when budget allows; query types with low preferred K (factual: 3) stop early even when budget is generous.

## Situation

A RAG pipeline routes queries across four types: factual (single-fact lookups), analytical (multi-evidence reasoning), comparative (cross-entity), and generative (drafting). Average chunk size is 300 tokens. Section budget varies by query depth: 800 tokens for quick lookups, 4 000 tokens for deep analysis.

With fixed K=5: a factual query with 800-token budget retrieves 5 chunks × 300 tokens = 1 500 tokens but only 800 are available — S-176 truncates the last two. Two chunks are fetched but immediately dropped. An analytical query with 4 000-token budget retrieves 5 chunks × 300 = 1 500 tokens but could fit 13 chunks and likely needs 8 for full coverage — 3 chunks of evidence are never fetched.

With adaptive K: the factual query gets K=2 (fits 800-token budget, above its min of 1). The analytical query gets K=8 (capped by its preferred ceiling, fits in 4 000 tokens). Neither wastes a fetch and neither is starved.

## Forces

- **Compute K before the retrieval call, not after.** Fetching 10 chunks then truncating at injection is double waste: you paid the vector search cost for chunks you will not use, and S-176 has to clean up the overflow. Setting K before the call is cheaper — one number computed in microseconds, saving one or more vector reads.
- **K bounds encode query-type knowledge, not just budget arithmetic.** A factual query with a 4 000-token budget does not need K=13 chunks. Its preferred ceiling is 3; retrieving 13 adds noise, not signal. Encode domain knowledge about how many sources each query type needs, independent of how much budget is available.
- **BUDGET_BELOW_MIN is a warning, not a hard stop.** When the section budget can't fit even the minimum K (budgetK < minK), return K=minK and let retrieval proceed. S-176 will enforce the truncation. An undersized budget is a configuration problem, not a retrieval error — raise it in telemetry but do not block the call.
- **avgChunkTokens is an estimate; profile your corpus.** The right value depends on your chunking strategy. Sentence-level chunks average 50–80 tokens. Paragraph-level chunks average 200–400 tokens. Document-level chunks are 800–2 000 tokens. Tune avgChunkTokens from your ingest pipeline; the selector is only as accurate as this estimate.
- **Compose with S-176 and S-66 in sequence.** S-179 selects K before retrieval. Retrieval returns up to K chunks. S-66 filters by score threshold, potentially dropping low-confidence chunks below K. S-176 enforces the final section token cap. Run in that order; do not skip S-66 or S-176 just because S-179 pre-selected K.

## The move

**Compute K = max(minK, min(preferredK, floor(sectionBudget / avgChunkTokens))) before each retrieval call. Route K into the vector search; never retrieve more than K.**

```js
// --- Adaptive retrieval top-K selector ---
// Computes K before each retrieval call from:
//   (1) available section token budget
//   (2) average chunk size in this corpus
//   (3) per-query-type min/preferred bounds
// Distinct from S-49 (evaluation), S-66 (score threshold), S-176 (post-retrieval budget cap).
// Compose: S-179 selects K → retrieval returns K → S-66 filters → S-176 enforces cap.

const K_BOUNDS = {
  factual:     { min: 1, preferred: 3  },  // single fact; 1–3 chunks
  analytical:  { min: 3, preferred: 8  },  // reasoning across evidence; 3–8 chunks
  comparative: { min: 3, preferred: 10 },  // cross-entity comparison; 3–10 chunks
  generative:  { min: 2, preferred: 5  },  // drafting with supporting context; 2–5 chunks
};

function adaptiveK(queryType, sectionBudgetTokens, avgChunkTokens) {
  const bounds  = K_BOUNDS[queryType] || { min: 1, preferred: 5 };
  const budgetK = Math.floor(sectionBudgetTokens / avgChunkTokens);
  const k       = Math.max(bounds.min, Math.min(bounds.preferred, budgetK));

  let limitedBy;
  if (budgetK < bounds.min)             limitedBy = 'BUDGET_BELOW_MIN';  // budget < min K
  else if (budgetK >= bounds.preferred) limitedBy = 'TYPE_CEILING';      // type cap is binding
  else                                  limitedBy = 'BUDGET';            // budget is binding

  return {
    k,
    budgetK,
    minK:          bounds.min,
    preferredK:    bounds.preferred,
    tokenEstimate: k * avgChunkTokens,
    limitedBy,
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Six query-type × budget combinations. Cost model: 10 000 calls/day mixed workload. `adaptiveK()` timed over 1 000 000 iterations. Zero API calls.

```
=== Adaptive Retrieval Top-K Selector ===

avg chunk size: 300 tok

Query type     Budget   budgetK   K→   limitedBy            tok used   scenario
------------------------------------------------------------------------------------------
factual        800      2         2    BUDGET               600        tight budget
factual        200      0         1    BUDGET_BELOW_MIN     300        very tight budget (below min)
analytical     4000     13        8    TYPE_CEILING         2400       full budget (type ceiling applies)
analytical     1500     5         5    BUDGET               1500       medium budget (budget-limited)
comparative    4000     13        10   TYPE_CEILING         3000       full budget
generative     900      3         3    BUDGET               900        medium budget

=== Cost model: 10 000 calls/day mixed workload ===
(40% factual/800tok, 30% analytical/4000tok, 20% generative/900tok, 10% factual/200tok)

Fixed K=5:    15.00M tokens/day   $12.00/day
Adaptive K:   11.70M tokens/day    $9.36/day
Savings:       3.30M tokens/day    $2.64/day  ($964/year)
(savings are retrieval input tokens — chunks not fetched and not injected)

=== Compose chain ===
S-179 selects K → retrieval returns K chunks → S-66 filters by score → S-176 enforces cap

=== Timing (1 000 000 iterations) ===
adaptiveK():  < 0.0001 ms  (pure arithmetic — no I/O, no allocation)
```

## See also

[S-49](s49-retrieval-evaluation.md) · [S-66](s66-retrieval-score-thresholds.md) · [S-176](s176-context-section-budget-enforcer.md) · [S-83](s83-cross-encoder-reranking.md) · [S-79](s79-hybrid-search-rrf.md)

## Go deeper

Keywords: `adaptive retrieval top-K` · `dynamic K retrieval RAG` · `retrieval K budget adaptation` · `query-type K bounds` · `retrieval chunk count optimization` · `RAG context budget` · `token-aware retrieval K` · `retrieval K selector` · `adaptive chunk retrieval` · `RAG cost optimization K`
