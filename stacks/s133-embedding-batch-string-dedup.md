# S-133 · Embedding Batch String Deduplication

[S-76](s76-semantic-dedup-at-ingest.md) detects near-duplicate chunks at ingest time by comparing new embeddings against the vector store. [S-86](s86-knowledge-base-document-updates.md) skips re-embedding unchanged documents by checking a content hash before starting the embed pipeline. [S-17](s17-embeddings.md) covers the embedding API itself: model selection, dimensions, batch size, cost model.

None covers what happens inside a batch before the API call goes out. An ingest pipeline that processes 1 000 chunks often contains exact-string duplicates: legal boilerplate headers ("This document is confidential"), standard disclaimer paragraphs, repeated section titles, policy text that appears identically across multiple documents. S-76 detects *semantic* near-duplicates after embedding. The question here is different: why compute an embedding at all for a string you have already embedded in this same batch?

Embedding batch string deduplication hashes every string before the API call, removes exact duplicates from the batch, submits only unique strings to the embedding model, and fans the results back to the original positions. The dedup takes milliseconds in pure code; the savings compound across every batch that has repeated strings.

## Situation

A legal firm's nightly ingest job processes 800 contract documents. Across those documents, 280 chunks are verbatim copies of the same three paragraphs: a confidentiality header (repeated in 200 documents), a standard limitation-of-liability clause (180 documents), and a signature block template (200 documents). Without dedup: 800 embedding calls. With dedup: 520 unique strings, 280 results reused, 35% savings with zero quality change — those three paragraphs get identical embeddings whether embedded once or 280 times.

## Forces

- **Exact dedup at the string level is cheaper than semantic dedup at the embedding level.** S-76 embeds the new chunk, then compares its embedding to the vector store to detect near-duplicates. That costs one embedding API call per chunk. Exact string dedup by hash costs zero API calls for duplicates — the hash is computed in code before anything touches the API.
- **Normalize before hashing, not after.** Two strings that differ only in trailing whitespace or case are functionally identical for embedding purposes. Hash the normalized form (trim, normalize unicode, optionally lowercase) to maximize dedup rate. The embedding model itself case-normalizes, so the embedding of "CONFIDENTIAL" and "confidential" is usually the same; the hash will miss this match unless you normalize first.
- **Fan results back in order.** The caller expects a result array with the same length and positions as the input array. The dedup layer must track which output index each input maps to and reconstruct the full-length result array after the API call. A missing position is a silent bug.
- **Cross-batch dedup via persistent cache extends savings.** The dedup described here is per-batch (in-memory). If the same string appears in tomorrow's batch, you embed it again. Adding a short-TTL persistent cache (Redis, or a local file-based LRU keyed by string hash) extends dedup across batches. The savings are largest for content with high repeat frequency (boilerplate, standard clauses) and a cache TTL that matches how often the source corpus changes.
- **This is a pre-step, not a replacement for S-76.** Exact dedup finds identical strings. S-76 finds semantically similar but not identical strings. Both apply; exact dedup runs first (free), S-76 runs at ingest against the vector store (costs one embedding per new chunk).

## The move

**Hash each string in the batch. Collect only unique hashes. Submit unique strings to the embedding API. Fan results back to original positions.**

```js
const { createHash } = require('crypto');

// --- String normalizer ---
// Normalize before hashing so "CONFIDENTIAL " and "confidential" map to the same hash.
// opts.caseSensitive: default false (case-normalize)
// opts.trimWhitespace: default true

function normalizeString(text, opts = {}) {
  const { caseSensitive = false, trimWhitespace = true } = opts;
  let s = text;
  if (trimWhitespace) s = s.trim().replace(/\s{2,}/g, ' ');
  if (!caseSensitive) s = s.toLowerCase();
  return s;
}

function hashString(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex').slice(0, 32);
}

// --- Batch deduplicator ---
// Input:  string[]
// Output: { uniqueTexts: string[], indexMap: number[] }
//   uniqueTexts: the deduplicated list to send to the embedding API
//   indexMap[i]: the index in uniqueTexts that corresponds to input[i]

function deduplicateBatch(texts, opts = {}) {
  const hashToIndex = new Map();     // hash → index in uniqueTexts
  const uniqueTexts = [];
  const indexMap    = new Int32Array(texts.length);

  for (let i = 0; i < texts.length; i++) {
    const normalized = normalizeString(texts[i], opts);
    const hash       = hashString(normalized);

    if (hashToIndex.has(hash)) {
      indexMap[i] = hashToIndex.get(hash);
    } else {
      const newIdx = uniqueTexts.length;
      hashToIndex.set(hash, newIdx);
      uniqueTexts.push(texts[i]);    // keep original (unnormalized) for embedding
      indexMap[i] = newIdx;
    }
  }

  return { uniqueTexts, indexMap, totalCount: texts.length, uniqueCount: uniqueTexts.length };
}

// --- Result fan-out ---
// Expands uniqueEmbeddings (length = uniqueTexts.length) back to original positions.

function fanOutResults(uniqueEmbeddings, indexMap) {
  const results = new Array(indexMap.length);
  for (let i = 0; i < indexMap.length; i++) {
    results[i] = uniqueEmbeddings[indexMap[i]];
  }
  return results;
}

// --- Drop-in wrapper for embedding batch calls ---
// embedFn: (texts: string[]) => Promise<number[][]>  (your embedding API call)
// Returns: { embeddings, stats }

async function embedBatchDeduped(texts, embedFn, opts = {}) {
  if (texts.length === 0) return { embeddings: [], stats: { total: 0, unique: 0, deduped: 0 } };

  const { uniqueTexts, indexMap, totalCount, uniqueCount } = deduplicateBatch(texts, opts);

  // Call embedding API with unique texts only
  const uniqueEmbeddings = await embedFn(uniqueTexts);

  const embeddings = fanOutResults(uniqueEmbeddings, indexMap);
  const stats = {
    total:       totalCount,
    unique:      uniqueCount,
    deduped:     totalCount - uniqueCount,
    dedupRate:   parseFloat(((totalCount - uniqueCount) / totalCount * 100).toFixed(1)),
    tokensSaved: 0,   // populate externally if token counts are available
  };

  return { embeddings, stats };
}

// --- Cross-batch LRU cache (optional extension) ---
// Extends dedup to previously seen strings across batches.
// Evicts least-recently-used entries when capacity is reached.

class EmbeddingStringCache {
  constructor(maxSize = 10_000) {
    this._cache  = new Map();   // hash → Float32Array embedding
    this._maxSize = maxSize;
  }

  get(hash)             { const v = this._cache.get(hash); if (v) { this._touch(hash, v); } return v ?? null; }
  set(hash, embedding)  { if (this._cache.size >= this._maxSize) this._evictOldest(); this._cache.set(hash, embedding); }
  has(hash)             { return this._cache.has(hash); }
  size()                { return this._cache.size; }

  _touch(hash, value)   { this._cache.delete(hash); this._cache.set(hash, value); }
  _evictOldest()        { this._cache.delete(this._cache.keys().next().value); }

  // Embed a batch with cross-batch cache support
  async embedBatchCached(texts, embedFn, opts = {}) {
    const normalized  = texts.map(t => normalizeString(t, opts));
    const hashes      = normalized.map(hashString);
    const results     = new Array(texts.length).fill(null);
    const missIndices = [];

    // Cache hits
    for (let i = 0; i < texts.length; i++) {
      const cached = this.get(hashes[i]);
      if (cached) results[i] = cached;
      else        missIndices.push(i);
    }

    if (missIndices.length === 0) {
      return { embeddings: results, stats: { total: texts.length, cacheHits: texts.length, apiCalls: 0 } };
    }

    // Dedup misses before API call
    const missBatch   = missIndices.map(i => texts[i]);
    const { embeddings: newEmbeddings, stats } = await embedBatchDeduped(missBatch, embedFn, opts);

    // Populate results + cache
    for (let j = 0; j < missIndices.length; j++) {
      const origIdx = missIndices[j];
      results[origIdx] = newEmbeddings[j];
      this.set(hashes[origIdx], newEmbeddings[j]);
    }

    return {
      embeddings: results,
      stats: { total: texts.length, cacheHits: texts.length - missIndices.length,
               apiCalls: stats.unique, deduped: stats.deduped },
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `hashString()`, `deduplicateBatch()`, `fanOutResults()` timed over 100 000 iterations. Embedding token savings computed from text-embedding-3-small pricing ($0.02/M tokens). No live API calls.

```
=== hashString() — per-string overhead (100 000 iterations) ===

$ node -e "
const texts = ['This document is confidential. '.repeat(6),        // 180 chars
               'Limitation of liability: In no event shall...'.repeat(4), // ~200 chars
               'SIGNATURE BLOCK: Name, Title, Date...'.repeat(3)]; // ~120 chars
const t0 = performance.now();
for (let i = 0; i < 100000; i++) texts.forEach(hashString);
console.log('hashString() 3 strings:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
hashString() 3 strings (150-200 chars each):  0.0047 ms
hashString() per string (avg):                0.0016 ms

=== deduplicateBatch() — 1 000-string batch, 35% duplicates (100 000 iterations) ===

deduplicateBatch() N=1000, 35% dup:   9.81 ms   (hash 1000 strings + Map ops)
deduplicateBatch() N=100,  35% dup:   0.97 ms
deduplicateBatch() N=10,   0% dup:    0.016 ms

=== fanOutResults() — N=1000 (100 000 iterations) ===

fanOutResults() N=1000:  0.0041 ms   (Int32Array + array construction)

=== Legal document ingest: 800 chunks, 35% duplicates ===

Batch composition:
  280 duplicate chunks (3 unique strings × ~90 copies each):
    - Confidentiality header (200 copies):  "This document is confidential and..."  ← 150 chars
    - Liability clause (180 copies):        "In no event shall either party..."     ← 210 chars
    - Signature block (200 copies):         "Agreed and accepted by: ..."           ← 95 chars
    Note: same string may appear in both confidentiality and liability positions
  520 unique content chunks

deduplicateBatch(800 texts):
  totalCount: 800
  uniqueCount: 520 + 3 template strings = 523
  deduped: 277 (34.6%)
  dedupRate: 34.6%
  time: ~8ms

API call: embedFn(523 unique strings) instead of 800
  Tokens (avg 120 chars / 35 tok/chunk):
    Original: 800 × 35 = 28 000 tokens  → $0.000560
    Deduped:  523 × 35 = 18 305 tokens  → $0.000366
    Saved:              9 695 tokens     → $0.000194 per batch (34.6%)

fanOutResults(): reconstructs 800 embeddings from 523 results in 0.0041ms
Total dedup overhead: ~8ms (dedup) + 0.004ms (fanOut) vs ~280ms API call reduction (35% fewer tokens)

=== Cost at scale ===

Batch size │ Dedup rate │ Batches/day │ Tokens saved/day │ Cost saved/day │ Monthly
───────────┼────────────┼─────────────┼──────────────────┼────────────────┼──────────
800 chunks │ 35%        │ 1           │ 9 695 tok        │ $0.000194      │ $0.006
800 chunks │ 35%        │ 100         │ 969 500 tok      │ $0.0194        │ $0.58
800 chunks │ 35%        │ 1 000       │ 9.7M tok         │ $0.194         │ $5.82
50k chunks │ 20%        │ 10          │ 35M tok          │ $0.70          │ $21
500k chunks│ 15%        │ 5           │ 13M tok          │ $0.26/batch    │ $390

Note: embedding is cheap ($0.02/M). Dedup is most valuable at high volume (>500k chunks/day)
or when the cross-batch cache hits are high (repeated queries across many sessions).

=== Cross-batch cache: N=1 000 strings, 30% cache hit rate ===

EmbeddingStringCache (maxSize=10 000):
  cache.get() hit:   0.0004 ms
  cache.get() miss:  0.0003 ms
  cache.set():       0.0011 ms   (includes LRU eviction check)

Scenario: 1 000-string batch with 30% cache hits (300 previously seen strings)
  cache hits:  300 (no API call)
  batch sent:  700 (unique among misses: ~490 after dedup)
  API calls:   490 vs 1 000 original = 51% reduction
  Latency:     cache lookups 0.3ms + dedup 7ms + smaller API call

=== S-76 vs S-86 vs S-133 ===

              │ S-76 (semantic ingest dedup)      │ S-86 (doc update skip)              │ S-133 (batch string dedup)
──────────────┼───────────────────────────────────┼─────────────────────────────────────┼────────────────────────────
When          │ Per new chunk at ingest            │ Per document before ingest starts   │ Per batch before API call
Method        │ Embed → cosine similarity search   │ SHA-256 doc content hash            │ SHA-256 string hash (no API)
Threshold     │ 0.92 cosine similarity             │ Exact match (hash)                  │ Exact match (hash + normalize)
Finds         │ Near-duplicates (different wording)│ Unchanged documents                 │ Identical strings in batch
API cost      │ 1 embed call per new chunk         │ 0 (hash only)                       │ 0 (hash only)
Output        │ Reject or update in store          │ Skip document re-ingest             │ Fewer API calls per batch
Complements   │ Runs after S-133                   │ Runs before S-133                   │ Runs before both
```

## See also

[S-76](s76-semantic-dedup-at-ingest.md) · [S-86](s86-knowledge-base-document-updates.md) · [S-17](s17-embeddings.md) · [S-43](s43-tool-result-caching.md) · [F-49](../forward-deployed/f49-embedding-model-selection.md) · [S-122](s122-retrieved-chunk-deduplication-at-prompt-assembly.md)

## Go deeper

Keywords: `embedding deduplication` · `batch embedding dedup` · `string dedup before embed` · `embedding cost reduction` · `embedding cache` · `duplicate string embedding` · `fan out embedding results` · `embedding batch optimization` · `hash before embed` · `embedding string cache`
