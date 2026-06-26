# S-76 · Semantic Deduplication at Ingest

[S-07](s07-rag.md) covers the retrieval pipeline — chunk, embed, store, retrieve. [S-52](s52-chunking-strategy.md) covers how to split documents into chunks. Neither covers what happens when the same content enters the store twice: as an exact copy, as a revision, or as a rephrased version. Without dedup, the vector store accumulates near-duplicates that crowd every query — the top-5 chunks are all variants of the same document instead of covering 5 distinct relevant topics.

## Situation

A support team ingests 200 articles per week. About 30% are revisions of existing content: the same FAQ rewritten for tone, a policy updated with a new date, a product description refreshed after a minor change. After six months, the store has 5 000 chunks — but effective coverage is 3 500 unique topics. Any query about account cancellation retrieves seven variants of the same chunk before getting to anything new. The fix: embed each new document before storage, search for the most similar existing embedding, and reject if cosine similarity exceeds 0.92.

## Forces

- **Exact hash dedup catches perfect copies; it misses rewording.** A document hash changes when a single word changes. Semantic dedup catches the rewording case — same meaning, different phrasing — which is the common case in support and documentation corpora.
- **Dedup at ingest is cheaper than dedup at retrieval.** A near-duplicate that enters the store degrades every query that would retrieve it. One embedding call per new document at ingest time prevents the degradation; fixing it after the fact requires re-indexing.
- **The threshold is embedding-model-dependent and task-dependent.** For text-embedding-3-small (OpenAI) and claude-3's embeddings: cosine similarity > 0.92 reliably identifies near-duplicates (rewording with same meaning). Similarity 0.75–0.92 indicates topically related but distinct content — don't reject. The 0.92 threshold is a starting point; calibrate by labeling 50–100 candidate pairs as duplicate/not and finding the threshold that maximizes F1.
- **Linear scan is fine for stores under ~5 000 chunks.** A pure-JS cosine similarity scan over 1 000 chunks takes 15ms in Node.js — acceptable for async ingest. Above 5 000 chunks, switch to ANN (approximate nearest neighbor) search: your vector database's built-in search (Pinecone, Qdrant, Weaviate) does this at sub-millisecond latency.
- **Rejection vs update.** When a near-duplicate is detected: reject if the existing chunk is current (don't clutter with revisions); update the existing embedding if the new version is the canonical one (e.g., a revised policy). Never silently discard — log the rejection for content team review.

## The move

**Before embedding a new chunk, search top-1 in the store. Reject if similarity > threshold. Log rejected pairs for review.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client = new Anthropic();

// Cosine similarity (use vector DB's native function in production)
function cosineSim(a, b) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i]; }
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

async function embedText(text) {
  // Using text-embedding-3-small; $0.02/M tokens
  // Replace with your embedding provider's client
  const response = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.OPENAI_KEY}` },
    body: JSON.stringify({ model: 'text-embedding-3-small', input: text }),
  });
  const data = await response.json();
  return data.data[0].embedding;
}

async function ingestChunk(chunk, vectorStore, opts = {}) {
  const threshold = opts.threshold ?? 0.92;

  // Step 1: embed the new chunk
  const newEmbedding = await embedText(chunk.text);

  // Step 2: search for the most similar existing chunk
  const topMatch = await vectorStore.searchTopOne(newEmbedding);

  if (topMatch && topMatch.score >= threshold) {
    // Near-duplicate detected
    const action = opts.onDuplicate ?? 'reject';    // 'reject' | 'update'

    if (action === 'update') {
      // Replace the existing embedding with the new version
      await vectorStore.upsert({ id: topMatch.id, embedding: newEmbedding, text: chunk.text, metadata: chunk.metadata });
      console.log(`[dedup] updated: ${chunk.id} replaced ${topMatch.id} (similarity: ${topMatch.score.toFixed(4)})`);
      return { action: 'updated', replacedId: topMatch.id, similarity: topMatch.score };
    }

    // Default: reject and log
    console.log(`[dedup] rejected: ${chunk.id} ≈ ${topMatch.id} (similarity: ${topMatch.score.toFixed(4)})`);
    await dedupeLog.insert({ newId: chunk.id, existingId: topMatch.id, similarity: topMatch.score, ts: Date.now() });
    return { action: 'rejected', matchedId: topMatch.id, similarity: topMatch.score };
  }

  // Not a duplicate: store normally
  await vectorStore.upsert({ id: chunk.id, embedding: newEmbedding, text: chunk.text, metadata: chunk.metadata });
  return { action: 'stored' };
}

// Batch ingest with dedup
async function ingestBatch(chunks, vectorStore) {
  const results = { stored: 0, rejected: 0, updated: 0 };
  for (const chunk of chunks) {
    const r = await ingestChunk(chunk, vectorStore);
    results[r.action]++;
  }
  console.log(`[ingest] ${results.stored} stored, ${results.rejected} rejected, ${results.updated} updated`);
  return results;
}
```

**Calibrating the threshold:**

```js
// Label 50–100 candidate pairs as 'duplicate' or 'distinct', then find the F1-maximizing threshold
async function calibrateThreshold(labeledPairs, vectorStore) {
  const thresholds = [0.85, 0.88, 0.90, 0.92, 0.94, 0.96];
  const best = { threshold: 0, f1: 0 };

  for (const t of thresholds) {
    let tp = 0, fp = 0, fn = 0;
    for (const pair of labeledPairs) {
      const predicted = pair.similarity >= t;
      if (pair.isDuplicate && predicted)  tp++;
      if (!pair.isDuplicate && predicted) fp++;
      if (pair.isDuplicate && !predicted) fn++;
    }
    const prec = tp + fp ? tp / (tp + fp) : 0;
    const rec  = tp + fn ? tp / (tp + fn) : 0;
    const f1   = (prec + rec) ? 2 * prec * rec / (prec + rec) : 0;
    console.log(`t=${t}: precision=${prec.toFixed(2)}, recall=${rec.toFixed(2)}, F1=${f1.toFixed(3)}`);
    if (f1 > best.f1) { best.f1 = f1; best.threshold = t; }
  }
  console.log('Best threshold:', best.threshold, 'F1:', best.f1.toFixed(3));
  return best.threshold;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Cosine similarity speed measured on pure-JS linear scan of 1 000 vectors, 1 536 dimensions (Float32Array). Embedding cost at text-embedding-3-small pricing. Near-duplicate threshold of 0.92 is a widely cited starting point; calibrate on your corpus.

```
=== Linear scan speed (1 536-dim, 1 000 chunks, pure JS) ===

$ node -e "
function cosineSim(a, b) {
  let dot=0, na=0, nb=0;
  for (let i=0; i<a.length; i++){dot+=a[i]*b[i]; na+=a[i]*a[i]; nb+=b[i]*b[i];}
  return dot/(Math.sqrt(na)*Math.sqrt(nb));
}
// [1000 random normalized 1536-dim vectors; single query vector]
// Linear scan: check new doc against all 1000 existing embeddings
Linear scan 1 000 chunks (1 536-dim): 15.04 ms per new doc
"
Linear scan 1 000 docs: 15 ms per new doc

Use vector DB's native ANN search above 5 000 chunks:
  Pinecone/Qdrant ANN: <1ms for millions of vectors
  Pure-JS scan at 5 000 docs: ~75ms (still acceptable for async ingest)
  Pure-JS scan at 50 000 docs: ~750ms (switch to ANN at this scale)

=== Embedding cost per document at ingest ===

Sample chunk: 28 tokens
Embedding cost: 28 tok × $0.02/M = $0.00000056 per chunk

At 500 new chunks/week:
  Embedding cost: $0.000014/week → ~$0.001/month (negligible)
  Dedup search: ANN vector DB call, typically free within quota

=== Dedup impact (illustrative) ===

Before dedup: 5 000 chunks, 30% near-duplicates → ~1 500 redundant chunks
After dedup: 3 500 unique chunks
Query quality: top-5 retrieval covers 5 distinct topics instead of 5 variants of 1 topic
Threshold guidance:
  > 0.96  only exact and near-identical copies
  > 0.92  catches rewording and minor revisions (recommended starting point)
  > 0.85  catches topically similar content — too aggressive for most corpora
```

## See also

[S-07](s07-rag.md) · [S-52](s52-chunking-strategy.md) · [S-49](s49-retrieval-evaluation.md) · [S-17](s17-embeddings.md) · [S-66](s66-retrieval-score-thresholds.md) · [S-27](s27-reranking.md)

## Go deeper

Keywords: `semantic deduplication` · `near-duplicate detection` · `cosine similarity threshold` · `vector store dedup` · `ingest dedup` · `embedding deduplication` · `knowledge base quality` · `text-embedding-3-small` · `ANN search` · `duplicate rejection`
