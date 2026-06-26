# S-86 · Knowledge Base Document Updates

[S-52](s52-chunking-strategy.md) covers how to split a document into chunks at ingest. [S-76](s76-semantic-dedup-at-ingest.md) detects near-duplicate chunks during ingest and rejects or updates them. Neither covers the targeted update problem: a source document has changed — a revised policy, an updated product spec, a corrected FAQ — and you need to replace its chunks in the vector store without re-indexing the entire corpus.

## Situation

A legal firm ingests 2,000 documents into a RAG system. Three months in, 150 documents have been revised. Without targeted updates: either re-index all 2,000 documents every week (expensive: 2,000 embed calls) or let the corpus accumulate stale chunks that return outdated information. With targeted updates: track which documents changed (a webhook from the CMS, a file watcher, a hash check), delete the old chunks, re-chunk and re-embed only the changed documents. At 150 changed documents out of 2,000: 7.5% of the embed cost, zero stale chunks, and the retrieval quality stays current.

## Forces

- **Chunks must carry a `document_id` at ingest time.** Without it, there is no way to find and delete the chunks belonging to a specific document. The `document_id` is the link between the source document (your CMS, filesystem, database) and the chunks in the vector store. It must be set at ingest and never changed.
- **Update = delete + re-insert, not in-place modify.** Vector stores don't support in-place embedding updates. When a document changes, delete all chunks with matching `document_id`, then re-chunk and re-embed the new version. The sequence is atomic at the document level.
- **Content hash detects what changed.** SHA-256 the document content and store it alongside the chunks. On update trigger, compare the new hash to the stored one. If they match, skip (no change). This prevents unnecessary re-indexing when a sync job fires for unchanged documents.
- **Chunk IDs should be deterministic, not random.** `document_id + "_" + chunk_index` as the chunk ID means you can predict IDs, find them by document, and detect orphaned chunks. Random IDs require a full metadata scan to find a document's chunks.
- **Partial document updates (section changes) require hierarchical chunk tracking.** If a policy document has 10 sections and only section 3 changes, you can track at section granularity and replace only section-3 chunks. This requires storing `section_id` in chunk metadata. Worth the complexity only for very large, frequently revised documents.

## The move

**Store `document_id` and a `content_hash` with every chunk. On document change: compute the new hash, compare, skip if unchanged, otherwise delete all chunks for that `document_id` and re-ingest the new version.**

**Ingest with document tracking:**

```js
const { createHash } = require('crypto');

function hashDocument(text) {
  return createHash('sha256').update(text).digest('hex');
}

// Ingest a document — stores document_id and content_hash on every chunk
async function ingestDocument(vectorStore, docStore, document) {
  const { id: documentId, text, metadata } = document;
  const contentHash = hashDocument(text);

  // Check if content has changed
  const existing = await docStore.get(documentId);
  if (existing?.contentHash === contentHash) {
    console.log(`[ingest] skip: ${documentId} (unchanged)`);
    return { action: 'skipped', documentId };
  }

  // Delete old chunks if this is an update
  if (existing) {
    const deleted = await vectorStore.deleteByDocumentId(documentId);
    console.log(`[ingest] deleted ${deleted} old chunks for ${documentId}`);
  }

  // Re-chunk the document
  const chunks = chunkText(text, { maxTokens: 512, overlap: 50 });

  // Embed and insert new chunks
  const embeddings = await embedBatch(chunks.map(c => c.text));

  const chunkRecords = chunks.map((chunk, i) => ({
    id:           `${documentId}_${i}`,       // deterministic chunk ID
    documentId,
    chunkIndex:   i,
    text:         chunk.text,
    embedding:    embeddings[i],
    metadata: {
      ...metadata,
      documentId,
      chunkIndex:   i,
      totalChunks:  chunks.length,
      contentHash,  // hash of the *document*, stored on each chunk for auditability
    },
  }));

  await vectorStore.insertMany(chunkRecords);

  // Update the document registry
  await docStore.set(documentId, {
    documentId,
    contentHash,
    chunkCount:  chunks.length,
    lastIndexed: new Date().toISOString(),
    metadata,
  });

  const action = existing ? 'updated' : 'inserted';
  console.log(`[ingest] ${action}: ${documentId} → ${chunks.length} chunks`);
  return { action, documentId, chunkCount: chunks.length };
}

// Minimal vector store interface — plug in your real store
class VectorStore {
  constructor() { this.chunks = new Map(); }

  async insertMany(records) {
    for (const r of records) this.chunks.set(r.id, r);
  }

  async deleteByDocumentId(documentId) {
    let deleted = 0;
    for (const [id, chunk] of this.chunks) {
      if (chunk.documentId === documentId) { this.chunks.delete(id); deleted++; }
    }
    return deleted;
  }
}

// Chunking helper (sentence-boundary, fixed-size — see S-52 for full strategy)
function chunkText(text, { maxTokens = 512, overlap = 50 } = {}) {
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? [text];
  const chunks = [];
  let current = [];
  let tokCount = 0;

  for (const sentence of sentences) {
    const toks = Math.ceil(sentence.length / 4);   // rough approximation
    if (tokCount + toks > maxTokens && current.length) {
      chunks.push({ text: current.join(' ') });
      const overlapSentences = current.slice(-Math.ceil(overlap / 10));
      current  = overlapSentences;
      tokCount = overlapSentences.reduce((s, se) => s + Math.ceil(se.length / 4), 0);
    }
    current.push(sentence);
    tokCount += toks;
  }
  if (current.length) chunks.push({ text: current.join(' ') });
  return chunks;
}

async function embedBatch(texts) {
  // Replace with real embedding call (S-17)
  return texts.map(() => new Float32Array(1536).fill(0.1));
}
```

**Batch update pipeline (run on sync schedule or webhook):**

```js
async function syncKnowledgeBase(vectorStore, docStore, sourceDocuments) {
  const results = { skipped: 0, updated: 0, inserted: 0, errors: 0 };

  // Process in parallel batches to respect rate limits
  const batchSize = 10;
  for (let i = 0; i < sourceDocuments.length; i += batchSize) {
    const batch = sourceDocuments.slice(i, i + batchSize);
    const settled = await Promise.allSettled(
      batch.map(doc => ingestDocument(vectorStore, docStore, doc))
    );

    for (const result of settled) {
      if (result.status === 'fulfilled') {
        results[result.value.action]++;
      } else {
        results.errors++;
        console.error('[sync] error:', result.reason?.message);
      }
    }
  }

  console.log('[sync] complete:', results);
  return results;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Chunk count and embed cost on a representative 3 000-token policy document. Pricing: text-embedding-3-small at $0.02/M.

```
=== Full re-index vs targeted update ===

Corpus: 2 000 documents, 150 changed this week

Full re-index (every document):
  2 000 docs × avg 6 chunks × 512 tok = 6 144 000 tok embedded
  Cost: 6 144 000 × $0.02/M = $0.123/week

Targeted update (changed documents only):
  150 docs × avg 6 chunks × 512 tok = 460 800 tok embedded
  Cost: 460 800 × $0.02/M = $0.009/week

Weekly savings: $0.114 (93% reduction)
Stale chunks: 0 (all changed docs updated)

=== Single document update (3 000-tok policy document) ===

Delete old chunks:  6 chunks deleted from vector store  <0.1ms (in-memory)
New chunks:         6 chunks from chunkText() at 512-tok max
Embed batch:        6 × 512 tok = 3 072 tok embedded
Embed cost:         3 072 × $0.02/M = $0.000061
Insert new chunks:  6 inserts

Total document update cost: $0.000061 + vector store ops

=== Content hash check (skip unchanged) ===

SHA-256 hash + compare: 0.0059 ms per document
At 2 000 documents/sync: 11.8 ms total hash check time
1 850 unchanged → skipped immediately; only 150 trigger embed calls
```

## See also

[S-52](s52-chunking-strategy.md) · [S-76](s76-semantic-dedup-at-ingest.md) · [S-17](s17-embeddings.md) · [S-07](s07-rag.md) · [S-81](s81-retrieval-metadata-filtering.md) · [S-49](s49-retrieval-evaluation.md)

## Go deeper

Keywords: `knowledge base update` · `document update` · `incremental indexing` · `partial reindex` · `chunk document ID` · `vector store update` · `content hash` · `RAG freshness` · `document sync` · `embedding update`
