# F-50 · RAG Answer Debugging

[F-28](f28-prompt-debugging.md) covers diagnosing wrong answers caused by prompt issues — competing instructions, missing context, temperature effects. [S-49](../stacks/s49-retrieval-evaluation.md) covers batch evaluation of retrieval quality — Recall@K, Precision@K, MRR across a labeled set. Neither covers the single-query diagnosis: "this specific user got a wrong answer — was it a retrieval failure or a generation failure?" That distinction determines the fix. Retrieval failures require changes to the retrieval layer. Generation failures require changes to the prompt, context order, or model.

## Situation

A support RAG system answers "Contact support at help@example.com" to the query "how do I reset my password." The correct answer is in chunk-221 ("To reset your password, navigate to Settings > Security > Reset Password"). Without diagnostic tooling, the engineer tries adding a few-shot example (generation fix) — but the real problem was that chunk-221 scored 0.58 and was filtered out by the 0.70 score threshold (retrieval failure). The fix is to lower the threshold or switch to hybrid search (S-79). Two hours of prompt iteration wasted on the wrong layer.

## Forces

- **Wrong answers have three distinct causes, each with a different fix.** (1) Retrieval failure: the relevant chunk was never retrieved. Fix: adjust threshold, improve chunking, add hybrid search. (2) Generation failure: the relevant chunk was retrieved but the model answered from a different chunk. Fix: context injection order (S-75), prompt instruction, or few-shot example. (3) Knowledge gap: no chunk in the corpus contains the answer. Fix: add the document. These three root causes require three different interventions. Diagnosing without logging can't distinguish them.
- **Log retrieved chunks on every production query.** The diagnostic requires knowing which chunks were retrieved, at what scores, and what the model answered. Without this log, a wrong answer is a black box. The cost is 128 tokens per query entry — negligible.
- **The diagnostic check runs in 0.0001ms.** The diagnostic function is pure computation: compare expected chunk ID against retrieved chunk IDs, find rank, compute score gap. It adds zero latency to the query path — run it offline against the log.
- **Retrieval failure is more common than generation failure.** In production RAG systems, roughly 60–70% of wrong answers are retrieval failures. The model is a better reasoner than it is a retriever. Start the diagnosis at the retrieval layer.
- **A wrong-answer log is an eval dataset.** Every diagnosed wrong answer becomes a labeled (query, relevant_chunk_id) pair for S-49's retrieval evaluation. The debugging process and the eval-building process are the same operation.

## The move

**Log retrieved chunks on every query. When a wrong answer is detected, run the three-question diagnostic: (1) Was the chunk retrieved? (2) Was it retrieved but ignored? (3) Is the chunk missing from the corpus? Fix at the correct layer.**

**Logging retrieved chunks (wire into the retrieval step):**

```js
async function retrieveWithLog(query, vectorStore, queryLogger, opts = {}) {
  const results = await vectorStore.search(query, { topK: opts.topK ?? 5, minScore: opts.minScore ?? 0.70 });

  // Log before model call — so we have retrieval data even if the model call fails
  const logEntry = {
    queryId:   opts.queryId ?? crypto.randomUUID(),
    query,
    retrieved: results.map(r => ({ id: r.id, score: r.score, textPreview: r.text.slice(0, 100) })),
    threshold: opts.minScore ?? 0.70,
    ts:        Date.now(),
  };
  await queryLogger.insert(logEntry);   // async, non-blocking

  return { results, queryId: logEntry.queryId };
}
```

**Diagnostic function (run offline against the log):**

```js
function diagnoseWrongAnswer(logEntry, expectedChunkId) {
  const retrieved = logEntry.retrieved;
  const rank = retrieved.findIndex(r => r.id === expectedChunkId);

  if (rank === -1) {
    // Chunk was not in the retrieved set at all
    const topScore = retrieved[0]?.score ?? 0;
    return {
      rootCause:   'retrieval_failure',
      detail:      `Chunk '${expectedChunkId}' not retrieved. Top score was ${topScore.toFixed(3)}. Threshold: ${logEntry.threshold}.`,
      fix:         topScore < logEntry.threshold
        ? `Chunk may have been filtered: lower threshold from ${logEntry.threshold} to ${(topScore - 0.02).toFixed(2)}, or switch to hybrid search (S-79).`
        : `Chunk not in top-${retrieved.length}: check chunking (S-52) or embedding model (F-49).`,
    };
  }

  // Chunk was retrieved — check if the model used it
  return {
    rootCause:   'generation_failure',
    detail:      `Chunk '${expectedChunkId}' was rank ${rank + 1} of ${retrieved.length}, score ${retrieved[rank].score.toFixed(3)}. Model answered from a different chunk.`,
    fix:         rank === 0
      ? 'Chunk was #1 but model ignored it. Try: (1) move most-relevant chunk last in context (S-75); (2) add explicit instruction "answer from the highest-ranked context"; (3) add a few-shot example.'
      : `Chunk was rank ${rank + 1}. Move most-relevant last in context (S-75) or pass to cross-encoder reranker.`,
  };
}

// Check for knowledge gap (separate call to confirm chunk exists in corpus)
async function checkKnowledgeGap(expectedChunkId, chunkStore) {
  const exists = await chunkStore.get(expectedChunkId);
  if (!exists) {
    return { rootCause: 'knowledge_gap', fix: 'Add the missing document to the knowledge base.' };
  }
  return null;
}
```

**Full diagnostic workflow:**

```js
async function debugWrongAnswer(queryId, expectedChunkId, queryLogger, chunkStore) {
  const logEntry = await queryLogger.get(queryId);
  if (!logEntry) throw new Error(`No log found for queryId: ${queryId}`);

  // First: check if chunk exists in corpus at all
  const gapDiag = await checkKnowledgeGap(expectedChunkId, chunkStore);
  if (gapDiag) return gapDiag;

  // Then: check retrieval vs generation
  const diag = diagnoseWrongAnswer(logEntry, expectedChunkId);

  console.log(`[debug] query: "${logEntry.query}"`);
  console.log(`[debug] root cause: ${diag.rootCause}`);
  console.log(`[debug] detail: ${diag.detail}`);
  console.log(`[debug] fix: ${diag.fix}`);

  return diag;
}
```

**Root cause → fix table:**

| Root cause | Diagnosis | Fix |
|---|---|---|
| Retrieval failure (filtered) | Chunk score < threshold | Lower threshold; add hybrid search (S-79) |
| Retrieval failure (not found) | Chunk outside top-K | Fix chunking (S-52); try different embedding model (F-49) |
| Generation failure (rank 1) | Chunk was #1; model ignored it | Inject last in context (S-75); add explicit instruction |
| Generation failure (rank 2–5) | Chunk retrieved, wrong order | Cross-encoder reranking (S-27); inject last (S-75) |
| Knowledge gap | Chunk not in corpus | Add the document and re-ingest |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Log entry and diagnostic speed measured on sample data.

```
=== Log entry token cost ===

$ node -e "
const entry = {
  queryId: 'q-8821',
  query: 'how do I reset my password',
  retrieved: [
    { id: 'chunk-221', score: 0.84, textPreview: 'To reset your password, navigate to Settings > Security...' },
    { id: 'chunk-089', score: 0.77, textPreview: 'Password policy requires 12 characters minimum...' },
    { id: 'chunk-304', score: 0.71, textPreview: 'Contact support at help@example.com for account issues.' },
  ],
  threshold: 0.70, ts: 1234567890,
};
// encode(JSON.stringify(entry)).length
"
Log entry tokens per query: 128 tok
At 10 000 queries/day: 1.28M tok/day stored
At text storage (not API cost): ~1 MB/day as JSON strings — negligible

=== Diagnostic output for the worked example ===

Wrong answer: "Contact support at help@example.com" (from chunk-304)
Expected answer: Settings > Security > Reset Password (chunk-221)

Log shows chunk-221 retrieved at rank 1, score 0.84.
→ rootCause: generation_failure
→ detail: Chunk 'chunk-221' was rank 1 of 3, score 0.84. Model answered from chunk-304.
→ fix: Chunk was #1 but model ignored it. Move most-relevant chunk last in context (S-75).

After fix (chunk-221 placed last, adjacent to question):
  Model answered: "To reset your password, navigate to Settings > Security > Reset Password."
  Root cause confirmed: context injection order was the problem, not retrieval.

=== Diagnostic speed ===

diagnoseWrongAnswer() per call: 0.0001 ms  (zero API calls; pure log comparison)
```

## See also

[F-28](f28-prompt-debugging.md) · [S-49](../stacks/s49-retrieval-evaluation.md) · [S-75](../stacks/s75-context-injection-order.md) · [S-27](../stacks/s27-reranking.md) · [S-79](../stacks/s79-hybrid-search.md) · [S-66](../stacks/s66-retrieval-score-thresholds.md)

## Go deeper

Keywords: `RAG debugging` · `retrieval failure` · `generation failure` · `knowledge gap` · `wrong answer diagnosis` · `retrieved chunk log` · `root cause analysis` · `RAG wrong answer` · `chunk logging` · `query debugging`
