# S-52 · Chunking Strategy

How you split documents into chunks determines what the retriever can find and what the model can use. The embedding that represents a chunk must carry enough signal to match a query; the chunk that gets injected must carry enough context for the model to answer. These two requirements pull in opposite directions, and the right chunk design sits between them.

## Situation

A support bot returns "I don't have enough information" for questions whose answers are clearly in the knowledge base. Inspection reveals the answers span two adjacent chunks — neither chunk alone is sufficient. The chunking used 256-token fixed boundaries with no overlap, so the answer got split. Increasing to 512 tokens with 10% overlap resolves it. Separately, a question about refund policy fails to retrieve the right chunk because the chunk text begins mid-paragraph and the embedding has no signal that this is about "billing" — adding a `[Help Center > Billing > Refund Policy]` prefix to each chunk fixes the retrieval miss.

## Forces

- Retrieval and generation have different optimal chunk sizes. Small chunks (128–256 tokens) embed cleanly and retrieve with high precision — the query embedding matches a tight, specific passage. Large chunks (1024–2048 tokens) give the model more context to reason from. These two needs are genuinely in tension; the answer is to separate them.
- Fixed-boundary splitting is dangerous. Splitting at character count or token count cuts through sentences, mid-concept boundaries, and mid-table rows. The embedding of an incomplete sentence or half a table is semantically weak. Split at sentence or paragraph boundaries whenever possible.
- Overlap is cheap insurance. A 10% overlap on a 512-token chunk is 51 tokens — negligible embedding cost, but it ensures that an answer spanning a boundary appears in at least one complete chunk. Answers that straddle zero-overlap boundaries are the most common retrieval failure mode.
- Chunk metadata is part of the embedding signal. A chunk that begins "customers may request a full refund within 30 days" has no signal for queries about "billing policy." Prefixing with `[Acme Help > Billing > Refund Policy]` adds 12 tokens and dramatically improves retrieval for semantic queries that use document-level vocabulary.
- Large chunks are not free. K=3 chunks at 1024 tokens each inject 3072 tokens per query — four times the context of K=3 at 256 tokens. At 1,000 queries/day that costs $9.22/k vs $2.30/k. Context cost is not the primary driver, but at scale it matters.

## The move

**Start with 512 tokens, 10% overlap, sentence boundary splitting, and document-section metadata prefixes. Use hierarchical chunking when retrieval precision and context completeness are both requirements.**

**Default recipe:**

```js
function chunkDocument(text, { chunkSize = 512, overlapPct = 0.10, docMeta = '' } = {}) {
  // 1. Split at sentence boundaries first
  const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];

  const chunks = [];
  let current  = [];
  let count    = 0;
  const overlap = Math.floor(chunkSize * overlapPct);

  for (const sentence of sentences) {
    const sentToks = sentence.split(/\s+/).length; // approximate
    if (count + sentToks > chunkSize && current.length > 0) {
      const chunkText = current.join(' ');
      // Prepend metadata for embedding signal
      chunks.push(docMeta ? `[${docMeta}]\n${chunkText}` : chunkText);
      // Carry overlap: last N tokens of current chunk into next
      const overlapWords = current.join(' ').split(/\s+/).slice(-overlap);
      current = overlapWords;
      count   = overlapWords.length;
    }
    current.push(sentence.trim());
    count += sentToks;
  }
  if (current.length) chunks.push(docMeta ? `[${docMeta}]\n${current.join(' ')}` : current.join(' '));
  return chunks;
}

// Usage
const chunks = chunkDocument(articleText, {
  chunkSize: 512,
  overlapPct: 0.10,
  docMeta: 'Acme Help Center > Billing > Refund Policy',
});
```

**Chunk size decision table:**

| Document type | Recommended size | Reasoning |
|---|---|---|
| Short FAQ answers (50–100 words) | 256 tok, no overlap | Answer fits in one chunk; no boundary risk |
| Long prose (articles, docs) | 512 tok, 10% overlap | Standard; balances signal and context |
| Technical reference (tables, code) | 1024 tok, 20% overlap | Tables/code break badly at small sizes |
| Book chapters / PDFs | Hierarchical (below) | Large variation in section length |

**Hierarchical chunking (for large corpora):**

```
Embed:    child chunks — 128–256 tokens (tight retrieval signal)
Retrieve: parent chunks — 512–1024 tokens (broad model context)

At query time:
  1. Embed query → cosine similarity against child chunk embeddings
  2. Retrieve top-K child chunk IDs
  3. Inject corresponding parent chunks into context (not the child chunks)

Result: precision of small chunks + context completeness of large chunks
```

**Failure mode checklist — run before tuning the retriever:**

- [ ] Does the answer span more than one chunk? → Increase overlap or chunk size
- [ ] Does the chunk start or end mid-sentence? → Switch to sentence-boundary splitting
- [ ] Does the query vocabulary differ from chunk vocabulary? → Add metadata prefix
- [ ] Are large tables or code blocks split? → Use 1024-token chunks for those documents
- [ ] Is Recall@5 below 0.85 for specific query types? → Diagnose per chunk type ([S-49](s49-retrieval-evaluation.md))

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Chunk counts and embed/inject costs computed on a 3,000-token document across four strategies. Metadata prefix cost measured on a real sentence. Hierarchical pattern costs derived from child-chunk embedding + parent-chunk injection model.

```
=== Chunking strategy comparison (3,000-token document, K=3) ===

Strategy                               chunks   injected/query   embed cost   ctx cost/k queries
Fixed 256 tok, no overlap              12       768  tokens      $0.000061    $2.30/k
Fixed 512 tok, 10% overlap              7       1536 tokens      $0.000072    $4.61/k
Fixed 1024 tok, 10% overlap             4       3072 tokens      $0.000082    $9.22/k
Fixed 2048 tok, 10% overlap             2       6144 tokens      $0.000082    $18.43/k

=== Metadata prefix ===
Raw chunk:    23 tokens (no document signal)
Prefixed:     35 tokens (+12 tokens = +$0.00/k at embedding prices)
Benefit: query "refund policy" now matches "[Billing > Refund Policy]" in embedding space

=== Hierarchical chunking (same 3,000-token doc) ===
Child chunks embedded:   15 × 200 tok  (tight retrieval signal)
Parent chunks injected:   3 × 800 tok  (broad model context)
Embed cost:   $0.000060    Inject cost: $7.20/k queries
```

The key insight: embedding cost is nearly the same across all strategies ($0.000060–$0.000082). The variable is context injection cost — that's where large chunks bite. For most corpora, 512 tokens with 10% overlap and sentence-boundary splitting is the right default; add metadata prefixes before tuning anything else.

## See also

[S-07](s07-rag.md) · [S-49](s49-retrieval-evaluation.md) · [S-17](s17-embeddings.md) · [S-27](s27-reranking.md) · [S-13](s13-context-engineering.md)

## Go deeper

Keywords: `chunking` · `chunk size` · `chunk overlap` · `sentence boundary splitting` · `hierarchical chunking` · `parent-child chunking` · `metadata prefix` · `RAG chunking` · `text splitting` · `document processing`
