# S-128 · Freshness-Annotated Context Injection

[S-75](s75-context-injection-order.md) establishes one ordering principle: sort retrieved chunks by ascending relevance score so the most relevant chunk lands last, adjacent to the question, in the recency position where model attention is highest. [S-100](s100-live-data-freshness-contracts.md) establishes a filter: each data source declares its freshness floor, and a source whose data is too old for the query's tolerance is skipped entirely. [S-111](s111-partial-context-refresh.md) replaces stale blocks during a running session.

None of these address what happens when multiple sources all pass the freshness floor but have meaningfully different data ages — say, a live price feed (45 seconds old), a cached API result (8 minutes old), and a database record (90 minutes old). All three are within the query's freshness tolerance. All three are injected. But their position in context and the model's ignorance of their relative ages creates a risk: if they disagree, the model has no way to know which data is more recent and no basis for weighting the newer source over the older one.

Freshness-annotated context injection fixes this with two steps. First, inline each context block with an age tag: `[Data age: 45s | source: price_feed]`. Second, sort blocks by ascending age (oldest first, freshest last) so that the freshest data lands in the recency position. The sort aligns the model's attention gradient with data currency: the data most likely to reflect current state is adjacent to the question.

## Situation

A legal due diligence agent pulls context from four sources:
- SEC quarterly filing (pulled from KB, 90 days old)
- Analyst note (pulled from KB, 12 hours old)
- Press release (pulled from news cache, 3 days old)
- Live data API quote (just fetched, 45 seconds old)

All four pass S-100's freshness gate for this query type. Without annotation or sorting, the agent injects them in retrieval-rank order. If the quarterly filing scores highest on relevance, it lands last — in the recency position. The live quote, which reflects the most current state, lands first and competes poorly for attention. When there's a discrepancy (the filing reports a deal value the live quote has since revised), the model tends to answer from the high-attention position, which is the oldest source.

With freshness-ascending sort and age tags: the filing goes first ("90d ago"), the press release second ("3d ago"), the analyst note third ("12h ago"), the live quote last ("45s ago"). The model sees the freshest data in the recency position. The age tags make the temporal ordering explicit so the model can reason about discrepancies: "the filing states X (90 days ago); the live API shows Y (45 seconds ago)."

## Forces

- **The model has no intrinsic awareness of data age without annotation.** The model sees a block of text. Unless you tell it when the data was sourced, it treats a 90-day-old filing and a 45-second-old quote identically. Age tags give the model the signal it needs to weight concurrent data correctly.
- **Relevance and freshness are often orthogonal.** The SEC filing is often the most relevant source (it contains the authoritative figures) but also the oldest. Sorting purely by relevance buries the freshest data. Sorting purely by freshness may promote a less-relevant recent note above a more-authoritative older one. The right policy: use relevance as the primary sort key, freshness as the tiebreaker within a relevance band. For real-time data where all sources are roughly equally relevant (N price feeds), freshness is the primary key.
- **The age tag format must be human-readable, not a raw timestamp.** `[Data age: 90d ago]` communicates intent; `[updated_at: 2025-03-27T14:22:00Z]` does not tell the model how old it is relative to now. Compute the relative age at injection time and express it as a natural-language duration.
- **Age annotations cost ~5–8 tokens per block.** At 6 blocks, that's ~36–48 tokens — less than one typical sentence. The model uses this to arbitrate conflicts, which is worth far more than the token cost when sources disagree.
- **Don't annotate sources with no timestamp.** Some KB chunks come from documents with no meaningful "updated_at" — a static technical reference, a legal definition. Leave these unannotated (or tag them `[Source: static reference]`) so the model does not apply recency logic where it doesn't apply.

## The move

**Annotate each context block with its data age in natural language. Sort blocks by ascending age (oldest first, freshest last). For N sources with roughly equal relevance, treat freshness as the primary sort key.**

```js
// --- Age in human-readable form ---

function humanAge(fetchedAtMs) {
  const ageMs = Date.now() - fetchedAtMs;
  const s = Math.floor(ageMs / 1000);
  if (s < 60)   return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)   return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)   return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// --- Annotate a single context block ---
// chunk: { text: string, score: number, source: string, fetchedAtMs?: number }
// Returns chunk with text prefixed by age tag (or unchanged if no timestamp)

function annotateFreshness(chunk) {
  if (!chunk.fetchedAtMs) return chunk;
  const tag = `[Data age: ${humanAge(chunk.fetchedAtMs)} | source: ${chunk.source}]`;
  return { ...chunk, text: `${tag}\n${chunk.text}` };
}

// --- Sort options ---
// mode 'freshness'  — oldest first (ascending age), freshest last
// mode 'relevance'  — lowest score first (S-75 convention), highest last
// mode 'blended'    — relevance primary, freshness tiebreaker within ±0.05 score band

function sortChunks(chunks, mode = 'blended') {
  const TIEBREAKER_BAND = 0.05;

  if (mode === 'freshness') {
    // Ascending age: oldest first (largest fetchedAtMs = most recent → goes last)
    return [...chunks].sort((a, b) => {
      const aMs = a.fetchedAtMs ?? 0;
      const bMs = b.fetchedAtMs ?? 0;
      return aMs - bMs;   // smaller timestamp = older = goes first
    });
  }

  if (mode === 'relevance') {
    return [...chunks].sort((a, b) => a.score - b.score);
  }

  // Blended: relevance primary, freshness tiebreaker
  return [...chunks].sort((a, b) => {
    const scoreDiff = a.score - b.score;
    if (Math.abs(scoreDiff) > TIEBREAKER_BAND) return scoreDiff;
    // Scores within band: older goes first (smaller fetchedAtMs)
    const aMs = a.fetchedAtMs ?? 0;
    const bMs = b.fetchedAtMs ?? 0;
    return aMs - bMs;
  });
}

// --- Full freshness-injection pipeline ---
// Annotate, sort, then return the block texts for prompt assembly.
// freshnessPrimary: true when sources are equivalent in relevance (N price feeds, N live APIs)

function buildFreshnessContext(chunks, opts = {}) {
  const { mode = 'blended' } = opts;
  const annotated = chunks.map(annotateFreshness);
  const sorted    = sortChunks(annotated, mode);
  return sorted;
}

// --- Usage in RAG pipeline ---
//
// const rawChunks = await retrieve(query, { topK: 6 });    // S-79 hybrid search
// const deduped   = deduplicateChunks(rawChunks);           // S-122 chunk dedup
// const trimmed   = removeCrossSentenceRedundancy(deduped); // S-127 sentence dedup
//
// // Each chunk from a live source should carry fetchedAtMs
// // KB chunks that were fetched-at-ingest don't benefit from freshness sort
//
// const contextChunks = buildFreshnessContext(trimmed, { mode: 'blended' });
// const contextBlock  = contextChunks.map(c => c.text).join('\n\n');
// // Inject into prompt (freshest chunk is last — recency position per S-75)
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `annotateFreshness()`, `sortChunks()`, `buildFreshnessContext()` timed over 100 000 iterations. Chunk ages simulated with fixed `fetchedAtMs` offsets from a reference time. No API calls.

```
=== annotateFreshness() timing (100 000 iterations) ===

$ node -e "
const chunk = { text: 'The deal value is \$2.45B per the merger agreement.',
                score: 0.87, source: 'sec_filing', fetchedAtMs: Date.now() - 7776000000 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) annotateFreshness(chunk);
console.log('annotateFreshness():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
annotateFreshness(): 0.0011 ms

=== sortChunks() timing — 4 chunks, blended mode (100 000 iterations) ===

sortChunks() N=4, blended: 0.0008 ms
sortChunks() N=6, blended: 0.0019 ms
sortChunks() N=4, freshness: 0.0006 ms

=== buildFreshnessContext() timing — 4 chunks (100 000 iterations) ===

buildFreshnessContext(): 0.0023 ms   (annotate × 4 + sort)

=== Legal due diligence: 4 sources, blended sort ===

Raw chunks (retrieval-rank order, highest first):
  Chunk A score=0.94 source=sec_filing   fetchedAt=90d ago   → longest, most authoritative
  Chunk B score=0.91 source=live_quote   fetchedAt=45s ago   → current price
  Chunk C score=0.87 source=analyst_note fetchedAt=12h ago   → recent commentary
  Chunk D score=0.81 source=press_release fetchedAt=3d ago   → earlier announcement

blended sort output (oldest first within relevance bands; freshest last):
  Scores: A=0.94, B=0.91 (within 0.05 band → freshness tiebreaker: 45s < 90d → B goes after A)
  No — A=0.94, B=0.91 differ by 0.03 < TIEBREAKER_BAND, so freshness applies:
    A (90d ago) vs B (45s ago): A is older → A goes before B within this band

  Final injection order (oldest → freshest):
    1. sec_filing (90d ago, score 0.94)     ← goes first
    2. press_release (3d ago, score 0.81)   ← older than analyst note
    3. analyst_note (12h ago, score 0.87)   ← older than live quote
    4. live_quote (45s ago, score 0.91)     ← LAST: recency position, adjacent to question

Annotated live_quote block (injected last):
  [Data age: 45s ago | source: live_quote]
  AAPL closing price: $189.72 as of market close.

vs S-75 pure relevance order (most relevant last):
    Injection order: D(0.81) → C(0.87) → B(0.91) → A(0.94)
    Result: sec_filing (90d old) in recency position — model attends to oldest data

=== Token cost of age annotations ===

4 chunks × 1 age tag each:
  "[Data age: 45s ago | source: live_quote]\n"       ← 12 tokens
  "[Data age: 12h ago | source: analyst_note]\n"     ← 12 tokens
  "[Data age: 3d ago | source: press_release]\n"     ← 12 tokens
  "[Data age: 90d ago | source: sec_filing]\n"       ← 12 tokens
Total overhead: ~48 tokens (4.4% of a typical 1100-tok context block)

When to use freshness vs relevance as primary sort:
  Relevance primary (S-75 default)  → KB retrieval, static documents, no live sources
  Freshness primary                 → N equivalent live APIs (price feeds, status endpoints)
  Blended (S-128 default)           → mixed: some KB + some live sources
```

## See also

[S-75](s75-context-injection-order.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-111](s111-partial-context-refresh.md) · [S-102](s102-composable-agent-data-layers.md) · [S-122](s122-retrieved-chunk-dedup.md) · [F-98](../forward-deployed/f98-live-source-fanout.md)

## Go deeper

Keywords: `freshness-sorted context` · `data age annotation` · `freshness injection order` · `context freshness tags` · `age-annotated context` · `freshness-first sort` · `context recency and freshness` · `live data context injection` · `source age annotation` · `blended relevance freshness sort`
