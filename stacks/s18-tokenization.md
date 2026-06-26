# S-18 · Tokenization

How text becomes the units a model actually reads and bills in. [Law 2](../laws.md) says tokens are the budget — this is what a token is.

## Forces
- The model never sees your letters — only integer IDs for subword pieces, so "how long is this?" has a non-obvious answer
- Token count drives both cost and whether your input fits the context window
- Every provider tokenizes differently, so a single estimate misprices the others
- The rule-of-thumb conversions break exactly where it matters most: code and non-English text

## The move

- **Know what a token is.** A tokenizer splits text into subword pieces, each mapped to an integer ID; the model only ever sees IDs. Common words stay whole; rare ones fragment ("hamburger" → `ham` + `bur` + `ger`). Most models use byte-pair encoding; Gemini uses SentencePiece.
- **Use the rule of thumb only for rough sizing.** English runs ~4 characters per token, ~750 words per 1,000 tokens. Code, JSON, and non-English are less efficient (Chinese ~2× the tokens). For anything that hits a bill or a limit, count the actual text.
- **Count per provider, don't extrapolate.** The same text yields different counts across vendors — single-digit % on English prose, 10–20% on code. Use each vendor's count-tokens endpoint (Anthropic and Gemini both expose one — see [S-02](s02-context-budget.md)) rather than scaling one tokenizer's number.
- **Read the bill correctly.** Cost = input tokens + output tokens, priced separately, and output usually runs 2–4× the input rate. The prompt-to-response ratio, not just total size, drives the cost.
- **Cut the bill with existing levers.** Prompt caching ([S-08](s08-prompt-caching.md)), fewer RAG chunks ([S-07](s07-rag.md)), tiering to a smaller model ([S-06](s06-model-routing.md)), and trimming the prompt ([S-13](s13-context-engineering.md)) — attack your largest line item first.

## Receipt
> Mechanism (subword BPE / SentencePiece, integer IDs, the ~4-chars-per-token and ~750-words-per-1,000-tokens rules, output priced 2–4× input) is standard and consistent across provider docs and tokenization writeups. Cross-provider count differences (e.g. "Hello, world!" ≈ 4 tokens on GPT vs 3 on Claude; ~250/280/320 tokens per 1,000 English chars on GPT/Claude/Gemini) are source-reported and encoder-version-dependent — directional, not exact; run the real tokenizer for billing. Verified 2026-06-25; specific counts not independently reproduced here.

## See also
[S-02](s02-context-budget.md) · [S-08](s08-prompt-caching.md) · [S-06](s06-model-routing.md) · [S-16](s16-prompting.md) · [S-17](s17-embeddings.md)

## Go deeper
Keywords: `tokenization` · `BPE` · `byte-pair encoding` · `SentencePiece` · `tiktoken` · `subword` · `vocabulary` · `count_tokens` · `input vs output pricing`
