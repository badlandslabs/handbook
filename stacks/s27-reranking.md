# S-27 · Reranking

First-stage retrieval ([S-07](s07-rag.md)) is tuned for *recall* — cast a wide, cheap net. But "topically similar" isn't "answers the question." Reranking is the second stage: re-score the shortlist for *precision* and keep only the best few. One of the highest-ROI upgrades over naive vector-only RAG.

## Forces
- A bi-encoder embeds query and document *separately* — fast enough to scan a whole corpus, but it never sees them together, so it ranks by vague topical overlap
- Keyword search ranks by term frequency — a doc that says "password" five times outranks the one that actually explains the reset, even though the latter answers the query
- A cross-encoder reads query + candidate *jointly* and captures their interaction — far more accurate, but too slow to run over millions of docs
- Retrieval, not generation, is where naive RAG fails most often — fixing rank order is cheaper than a better model

## The move
- **Two stages: recall, then precision.**
  1. **Recall (wide + cheap).** Retrieve top 20–50 with **hybrid search**: BM25 keyword + dense vector, fused by Reciprocal Rank Fusion (RRF). Hybrid beats either alone — keyword catches exact matches, vectors catch paraphrase.
  2. **Precision (narrow + accurate).** Run a **cross-encoder reranker** over only that shortlist; keep the top 3–5 for the LLM.
- **Only rerank the shortlist.** Cross-encoders cost ~tens of ms per pair — fine on 50 candidates, impossible on the whole corpus. That's why it's stage two.
- **Pre-filter on metadata first** (tenant, date, doc type) — never rerank candidates the user isn't allowed to see, and shrink the shortlist before paying for it.
- **Models:** `bge-reranker-v2-m3` (self-host, ~free marginal cost) or Cohere Rerank (managed). **ColBERT late-interaction** is a middle ground: token-level scoring, more accurate than a bi-encoder, cheaper than a full cross-encoder.
- **Gate on retrieval metrics** (Recall@K, MRR, nDCG), not vibes — reranking quality drifts as your corpus grows.

## Receipt
> Verified 2026-06-25 — recall-then-precision on a 5-doc corpus, query "How do I reset my password?". Stage 1 = literal keyword overlap; stage 2 = llama3.2 (Ollama, localhost:11435) scoring each candidate on *does it answer the question* (an LLM reranker standing in for a cross-encoder; embeddings/dedicated reranker not available here).

```
STAGE 1 (keyword recall):  D1(3) > D3(1) > D5(1) > D2(0) > D4(0)
  top-1 = D1  ("password policy: 12 chars, expires every 90 days")  <- says "password" most, answers nothing
  D3 (the actual how-to-reset steps) recalled but stuck at rank 2

STAGE 2 (rerank: "does it answer?"):  D3(7) > D1(2) > D2(2) > D5(0)
  top-1 = D3  <- the answer-bearing doc promoted over the keyword-heavy one
```

The keyword stage ranked the password-*policy* doc first because it repeats the query's word most — exactly the "topically similar, not answer-bearing" failure. The reranker read query and passage together and scored the actual reset instructions 7 vs the policy doc's 2, promoting the right doc to #1. Reordering the *same* candidates — no new retrieval, no bigger model — fixed the answer. (A real cross-encoder over hybrid-search candidates does this far better than this LLM-reranker stand-in; the principle is what the run shows.)

## See also
[S-07](s07-rag.md) · [S-17](s17-embeddings.md) · [S-22](s22-tool-selection-at-scale.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [S-13](s13-context-engineering.md)

## Go deeper
Keywords: `reranking` · `cross-encoder` · `bi-encoder` · `hybrid search` · `BM25` · `reciprocal rank fusion` · `ColBERT` · `late interaction` · `bge-reranker` · `Cohere Rerank` · `nDCG` · `MRR`
