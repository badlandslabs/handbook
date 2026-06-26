# S-17 · Embeddings

A way to turn text into numbers that capture meaning, so a computer can tell which pieces of text are similar. The machinery underneath [RAG](s07-rag.md) and semantic [memory](s09-memory-systems.md).

## Forces
- Keyword search misses meaning ("car" ≠ "automobile"); embeddings catch it, but add a model and a vector store to run
- Higher dimensions capture more nuance but cost more storage and slower search — every dimension is bytes per vector, multiplied by millions of rows
- The best-on-leaderboard model is rarely the best on *your* data
- Truncation and quantization cut cost dramatically but quietly corrupt results if done wrong

## The move

- **Know what it is.** An embedding turns text into a vector (a list of numbers) where distance encodes meaning; you compare two with cosine similarity. Nearby vectors mean similar text. That's the whole basis of semantic search, RAG, and memory.
- **Shortlist from MTEB, then test on your data.** The MTEB leaderboard is a starting point, not a verdict. 2026 options: OpenAI `text-embedding-3-large` (safe API default), Qwen3-Embedding (top open-source), EmbeddingGemma-300M (on-device), Jina-embeddings-v3 (cheap), Cohere embed-v4 (multimodal). The rankings move monthly.
- **Budget dimensions against storage.** A 1024-dim float32 vector is ~4KB, so 10M documents is ~40GB. 768–1024 dims is the sweet spot for most RAG ([S-02](s02-context-budget.md) thinking, applied to vectors).
- **Truncate with Matryoshka, carefully.** MRL models front-load meaning into early dimensions, so you can truncate (e.g. 1024→256) for ~2–3% quality loss and ~4× less storage. It must be *trained in* — never truncate a non-MRL model and expect graceful decay — and renormalize after truncating manually.
- **Quantize, then tier your search.** Drop precision (float32→int8 or binary) *after* MRL truncation; the two stack. Production pattern: fast binary/int8 first-pass search, then rerank the top candidates with full-precision vectors or a cross-encoder ([S-07](s07-rag.md)).

## Receipt
> Mechanism (cosine similarity, MRL front-loading, quantization stacking, renormalize-after-truncation) is from HuggingFace's [embedding quantization](https://huggingface.co/blog/embedding-quantization) and [Matryoshka](https://huggingface.co/blog/matryoshka) writeups. A documented MRL result: OpenAI `text-embedding-3-large` truncated to 256 dims outperforms the older `ada-002` at 1536 dims on MTEB (OpenAI's own announcement). Specific model scores, prices, and rankings are monthly-moving snapshots — check the live [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard) and provider pricing before committing. Verified 2026-06-25; not independently benchmarked here.

## See also
[S-07](s07-rag.md) · [S-27](s27-reranking.md) · [S-09](s09-memory-systems.md) · [S-02](s02-context-budget.md) · [R-01](../frontier/r01-model-landscape.md)

## Go deeper
Keywords: `embeddings` · `cosine similarity` · `MTEB` · `Matryoshka representation learning` · `vector quantization` · `int8` · `binary quantization` · `cross-encoder reranking` · `vector database`
