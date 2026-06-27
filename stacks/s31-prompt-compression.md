# S-31 · Prompt Compression

Retrieved documents injected into prompts are written for humans — they repeat themselves, hedge their claims, and bury the key facts in prose. A 450-token RAG passage can contain 200 tokens of actual signal. Sending the rest to the model costs tokens on every query and degrades attention on the parts that matter.

## Forces

- Retrieved content is the biggest variable cost in a RAG agent's context: system prompt and instructions are fixed; retrieved passages grow with the query
- Dense documents improve answer quality; verbose documents dilute attention and inflate cost without improving answers
- Compressing at query time costs a call — that call must be amortized across enough queries to be worth it
- Question-aware compression is more precise (drop only facts irrelevant to *this* query) but requires a compression call per query; index-time compression is coarser but runs once
- Abstractive compression (rewrite denser) vs. token pruning (drop individual tokens by perplexity score): abstractive is portable and requires no extra model; token pruning (LLMLingua) achieves higher ratios at the cost of a separate scorer

## The move

**Compress the retrieval, not the instructions.** Instructions and few-shot examples are already dense. Retrieved passages are where the bloat lives.

**Abstractive compression (portable, no extra model):**
```
You are a document compressor. Extract only the technical facts needed to
answer questions about [topic]. Remove filler, hedging, and repetition.
Return a dense fact list, no prose.

Passage: {retrieved_text}
```

Run at temperature 0.0. The compressed output becomes the injection, not the original.

**Token pruning (higher ratios, requires separate scorer):** LLMLingua uses a small model (GPT-2 or LLaMA-7B) to score each token's perplexity. Low perplexity = predictable = removable. Removes individual tokens rather than rewriting; per published benchmarks (EMNLP '23, ACL '24), achieves 4–10× compression in production (20× is achievable on math benchmarks but degrades on open-domain tasks).

**Compress at index time when possible.** If the same document will be retrieved across many queries, compress once during indexing and cache the result. Break-even on the compression call is ~12 queries; after that, every query is pure savings.

**For query-specific needs:** use question-aware compression — pass both the question and the document, ask the compressor to keep only facts relevant to *this* query. Higher precision, higher per-query cost.

## Receipt

> Verified 2026-06-26 — llama3.2 via Ollama (localhost:11435). Abstractive compression of a ~450-token transformer self-attention document; same question answered from full and compressed versions.

```
Step 1 — Full document query
  in=3,033 tokens
  Answer: correct (scaling prevents softmax saturation)

Step 2 — Abstractive compression call
  in=3,050  out=200 tokens
  Document: ~450 tokens → 200 tokens (55% document compression)

Step 3 — Compressed document query
  in=2,761 tokens
  Answer: correct, identical precision

Token reduction:    272 tokens (9% end-to-end)
Document reduction: ~55% (450 → 200 tokens)
Break-even:         12 queries (compression call = 3,250 tokens / 272 saved per query)
```

**What the receipt shows:**

- The 9% end-to-end savings looks modest because the prompt frame (instructions + question) dominates at small scale. The document itself compressed 55%. At larger documents or multiple passages, the absolute savings grow faster than the fixed frame cost.
- Both answers were correct and comparably precise — compression didn't lose the key fact.
- Break-even at 12 queries makes index-time compression the obvious choice for any document retrieved repeatedly (e.g., a product FAQ, an API reference).

## See also

[S-07](s07-rag.md) · [S-02](s02-context-budget.md) · [S-21](s21-context-compaction.md) · [S-13](s13-context-engineering.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `LLMLingua` · `LongLLMLingua` · `prompt compression` · `token pruning` · `abstractive compression` · `index-time compression` · `RAG cost optimization` · `perplexity scoring`
