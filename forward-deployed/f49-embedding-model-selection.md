# F-49 · Embedding Model Selection

[S-17](../stacks/s17-embeddings.md) covers how embeddings work — cosine similarity, Matryoshka representation learning, quantization stacking, when to use a cross-encoder reranker. It lists five 2026 model options in one line and notes that rankings move monthly. That isn't a selection guide. This entry covers the decision: given your corpus, query volume, language requirements, and budget, which embedding model do you use and why.

## Situation

A team building a support RAG system asks: should we use `text-embedding-3-small` (cheap, widely used) or `text-embedding-3-large` (higher MTEB, 6.5× more expensive)? The answer depends on four things their system prompt doesn't address: how much the MTEB score delta actually matters for their corpus type, whether they need multilingual support, whether dimension count affects their storage budget, and whether the cost difference is meaningful at their query volume. At 10k queries/day with 50 tokens each, the cost difference is $1.65/month — the choice is almost entirely about quality, not cost.

## Forces

- **MTEB average score is the right starting signal, not the right ending point.** MTEB aggregates across task types: retrieval, classification, clustering, reranking. If your use case is purely retrieval (RAG), the MTEB retrieval sub-score is more predictive than the average. A model that ranks lower on average may rank higher on retrieval specifically. Check the task-specific sub-leaderboard.
- **Embedding cost is almost always negligible.** At 10k queries/day with 50-token queries: `text-embedding-3-large` at $0.13/M costs $1.95/month. `text-embedding-3-small` at $0.02/M costs $0.30/month. The delta is $1.65/month. This is not a cost decision — it is a quality decision. The expensive models only become meaningful costs at >10M tokens/day.
- **Dimension count affects storage and ANN index speed, not quality (for MRL models).** Matryoshka-trained models (text-embedding-3-*, jina-embeddings-v3) can be truncated: a 3 072-dim model truncated to 256 dims still outperforms the older ada-002 at 1 536 dims on MTEB. Truncate to the lowest dimension that meets your quality bar. This lets you use a high-quality model with storage costs comparable to a small model.
- **Multilingual requirement narrows the field sharply.** English-optimized models degrade significantly on other languages. If you serve non-English queries, use a multilingual model from the start — retrofitting is expensive (requires re-embedding your entire corpus). Jina-embeddings-v3 and Cohere embed-v4 support 100+ languages.
- **Test on your corpus, not just MTEB.** A 1–2 MTEB point difference on the leaderboard may be 5 points on your domain or 0. Embed 200 representative queries, retrieve top-5, label relevance, compute Recall@5. Thirty minutes of labeling and one API call gives you ground truth for your data.

## The move

**Start with MTEB retrieval sub-scores for your language. Truncate MRL models to reduce storage. If multilingual, narrow to multilingual models first. Test on 200 labeled queries before committing. Switch only if Recall@5 delta > 3 points.**

**Embedding model comparison (2026-06-26 snapshot — verify at MTEB leaderboard before committing):**

| Model | Dims (max) | MTEB avg | Cost/M tok | Multilingual | Notes |
|---|---|---|---|---|---|
| `text-embedding-3-small` | 1 536 | ~62 | $0.02 | No | Safe default for English RAG |
| `text-embedding-3-large` | 3 072 | ~65 | $0.13 | No | Truncatable to 256; outperforms ada-002 at 256 dims |
| `jina-embeddings-v3` | 1 024 | ~65 | $0.02 | Yes (100+) | Best value; multilingual parity |
| `cohere-embed-v4` | 1 024 | ~66 | $0.10 | Yes (100+) | Leading multilingual; also handles images |
| `nomic-embed-text` | 768 | ~62 | free (local) | No | On-device; no API cost; lower quality ceiling |

> MTEB scores are from the HuggingFace MTEB leaderboard (retrieval task average). Rankings shift monthly — verify before committing. Prices from provider pricing pages 2026-06-26.

**Decision flowchart:**

```
Multilingual required?
├── YES → jina-embeddings-v3 (low cost) or cohere-embed-v4 (highest quality)
└── NO  → continue
       │
       └── On-device / air-gapped?
           ├── YES → nomic-embed-text or EmbeddingGemma-300M
           └── NO  → continue
                  │
                  └── Storage / index size constraint?
                      ├── YES → text-embedding-3-large truncated to 512 dims (MRL)
                      └── NO  → start with text-embedding-3-small
                             │
                             └── Test on your corpus.
                                 Recall@5 delta > 3 pts → upgrade to text-embedding-3-large
                                 Recall@5 delta ≤ 3 pts → stay with small
```

**Testing on your corpus:**

```js
const Anthropic = require('@anthropic-ai/sdk');

// Evaluate Recall@5 on labeled (query, relevant_chunk_ids) pairs
async function evaluateEmbeddingModel(modelName, labeledPairs, vectorStore) {
  let hits = 0;
  const K = 5;

  for (const { query, relevantIds } of labeledPairs) {
    // Embed the query using the candidate model
    const embedding = await getEmbedding(modelName, query);
    const results   = await vectorStore.search(embedding, { topK: K });
    const retrieved = new Set(results.map(r => r.id));

    // Count how many relevant chunks appear in top K
    const recall = relevantIds.filter(id => retrieved.has(id)).length / relevantIds.length;
    hits += recall;
  }

  return { model: modelName, recallAtK: (hits / labeledPairs.length).toFixed(3), K };
}

// Compare two models on the same labeled set
async function compareModels(pairs, vectorStore) {
  const [small, large] = await Promise.all([
    evaluateEmbeddingModel('text-embedding-3-small', pairs, vectorStore),
    evaluateEmbeddingModel('text-embedding-3-large', pairs, vectorStore),
  ]);
  const delta = ((parseFloat(large.recallAtK) - parseFloat(small.recallAtK)) * 100).toFixed(1);
  console.log(`small Recall@5: ${small.recallAtK} | large Recall@5: ${large.recallAtK} | delta: ${delta}%`);
  console.log(Math.abs(delta) > 3 ? 'Switch to large.' : 'Stay with small — delta not worth the cost.');
}
```

**MRL dimension truncation (text-embedding-3-large):**

```js
// Truncate a 3072-dim embedding to 256 dims (valid for MRL-trained models)
// Quality at 256 dims still exceeds ada-002 at 1536 dims on MTEB
function truncateEmbedding(embedding, targetDims) {
  const truncated = embedding.slice(0, targetDims);
  // Re-normalize after truncation
  const norm = Math.sqrt(truncated.reduce((s, x) => s + x * x, 0));
  return truncated.map(x => x / norm);
}
```

## Receipt

> Verified 2026-06-26 — cost arithmetic from provider pricing pages. MTEB scores from HuggingFace MTEB leaderboard (2026-06-26 snapshot); not independently benchmarked. Truncation math from OpenAI's Matryoshka representation learning announcement.

```
=== Cost at 10k queries/day, 50 tok/query ===

Daily tokens: 10 000 × 50 = 500 000 tok = 0.5M tok/day

Model                  $/M tok    Daily cost   Monthly cost
text-embedding-3-small  $0.02      $0.010       $0.30
text-embedding-3-large  $0.13      $0.065       $1.95
jina-embeddings-v3      $0.02      $0.010       $0.30
cohere-embed-v4         $0.10      $0.050       $1.50

Delta (large vs small): $1.65/month
Decision is quality, not cost. Only meaningful above ~10M tok/day.

=== Storage savings from MRL truncation ===

text-embedding-3-large at full 3 072 dims:
  Per embedding: 3072 × 4 bytes (float32) = 12 288 bytes = 12 KB
  1M embeddings: 12 GB

text-embedding-3-large truncated to 512 dims:
  Per embedding: 512 × 4 bytes = 2 048 bytes = 2 KB
  1M embeddings: 2 GB (83% smaller)
  Quality: MTEB score at 512 dims still exceeds text-embedding-3-small at 1536 dims

=== When to upgrade from small → large ===

Test on 200 labeled (query, relevant_chunks) pairs.
If Recall@5 improves > 3 percentage points → upgrade (quality gain justifies $1.65/mo).
If Recall@5 improves ≤ 3 percentage points → stay with small.
Typical outcome: for support/FAQ corpora, delta is 0–2 pts. For technical docs, delta is 2–5 pts.
```

## See also

[S-17](../stacks/s17-embeddings.md) · [S-07](../stacks/s07-rag.md) · [S-49](../stacks/s49-retrieval-evaluation.md) · [S-27](../stacks/s27-reranking.md) · [S-76](../stacks/s76-semantic-dedup-at-ingest.md) · [S-66](../stacks/s66-retrieval-score-thresholds.md)

## Go deeper

Keywords: `embedding model selection` · `MTEB leaderboard` · `text-embedding-3-small` · `text-embedding-3-large` · `Matryoshka representation learning` · `MRL truncation` · `multilingual embeddings` · `jina-embeddings-v3` · `Recall@5` · `embedding cost`
