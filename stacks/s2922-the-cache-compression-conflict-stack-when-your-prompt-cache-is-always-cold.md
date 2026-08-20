# S-2922 · The Cache-Compression Conflict Stack — When Your Prompt Cache Is Always Cold

Your cost-reduction pipeline looks perfect on paper. You added prompt compression (LLMLingua, SCISSOR) to strip verbose RAG passages before sending them to the model. You enabled provider prompt caching (Anthropic `cache_control`, OpenAI `prompt_cache`) to get discounted rates on reused prefixes. Your costs should be compounding downward. They're not. The cache hit rate is 8%. The compression savings are real but the cache savings are zero. These two techniques are actively fighting each other, and the literature trained your team to combine them.

This is the cache-compression conflict: the dominant approach to prompt compression is architecturally incompatible with the dominant approach to prompt caching. Resolving it requires understanding the two-tier nature of provider caches and choosing compression strategies that respect it.

## Forces

- **Query-aware compression destroys prefix-strict caching.** Query-aware methods (LLMLingua, RECOM, AutoCompress) produce a different compressed prefix for every unique query. Provider caches require prefix-strict reuse — the same N-token prefix followed by the same continuation. If the compression call changes the prefix, every call is a cache miss. You are paying full price on every request while believing you are getting cache discounts.
- **The cache threshold is not where you think it is.** Anthropic Sonnet 4.6's cache has a two-tier architecture with a sharp threshold near 3,500 tokens. Below the threshold, hit rates plateau at ~0.83 even across 30-call sessions. Above the threshold, cache behavior changes. Teams target 5,000–10,000 token prefixes and miss this threshold effect entirely.
- **Compression and caching have opposing optimization targets.** Compression minimizes tokens sent. Caching maximizes prefix reuse. The naive combination — compress then cache — optimizes neither. Compressing the same content differently per query defeats caching. Caching uncompressed verbose prefixes inflates per-call costs.
- **Index-time compression is cache-compatible but coarse.** Compressing at index time (before retrieval) produces stable, reusable prefixes. But it cannot be query-aware, so it drops more signal. Query-aware compression is precise but breaks caching.

## The move

**Diagnose before restructuring:** Measure your current cache hit rate by provider and prefix size. The conflict is invisible without this baseline.

```python
import anthropic
from dataclasses import dataclass
import tiktoken

@dataclass
class CacheMetrics:
    prefix_tokens: int
    hit_rate: float
    avg_input_tokens: int
    avg_output_tokens: int
    cache_discount: float = 0.9  # Anthropic cache discount

def measure_cache_metrics(client: anthropic.Anthropic,
                          sample_prompts: list[str],
                          system_prefix: str) -> CacheMetrics:
    """Measure cache hit rate across prefix sizes."""
    prefix_tokens = len(tiktoken.get_encoding("cl100k_base")
                         .encode(system_prefix))

    hits, misses = 0, 0
    total_input = 0
    total_output = 0

    for prompt in sample_prompts:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=[{"type": "text", "text": system_prefix,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}]
        )
        # Check if cache was used via usage metadata
        usage = resp.usage
        input_tokens = usage.input_tokens
        total_input += input_tokens
        total_output += usage.output_tokens
        # Cache hit if input_tokens < prefix_tokens + prompt_tokens
        prompt_only = len(tiktoken.get_encoding("cl100k_base")
                          .encode(prompt))
        if input_tokens < (prefix_tokens + prompt_only):
            hits += 1
        else:
            misses += 1

    return CacheMetrics(
        prefix_tokens=prefix_tokens,
        hit_rate=hits / (hits + misses),
        avg_input_tokens=total_input // (hits + misses),
        avg_output_tokens=total_output // (hits + misses)
    )

# Typical output showing the threshold effect:
# prefix=2048: hit_rate=0.53 (N=5), 0.63 (N=10), 0.83 (N=30)
# prefix=3584: hit_rate=0.61 (N=5), 0.71 (N=10), 0.83 (N=30)
# prefix=5120: hit_rate=0.89 (N=5), 0.92 (N=10), 0.97 (N=30)
```

**Three-tier resolution strategy:**

**Tier 1 — Cache-compatible prefix compression.** For system prompts and static RAG schemas, use index-time compression (e.g., summarization-based, or Remove-Thyen-Rewrite) that produces stable prefixes. These compress once and cache forever.

**Tier 2 — Query-aware compression with cache bypass.** For highly variable user queries, use query-aware compression but route the compressed output to a **semantic cache** (embedding-based similarity matching) rather than the provider's prefix cache. Semantic caching gives you the compression precision AND cache benefits, independent of provider constraints.

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class SemanticCache:
    """Query-aware compression + semantic cache combo.

    1. Compress query with LLMLingua (query-aware)
    2. Check semantic cache with compressed query
    3. If hit → return cached response
    4. If miss → call provider, cache response keyed on compressed query
    """
    def __init__(self, similarity_threshold: float = 0.92,
                 max_entries: int = 10000):
        self.vectorizer = TfidfVectorizer(max_features=512)
        self.cache: dict[str, str] = {}
        self.vectors: list[np.ndarray] = []
        self.threshold = similarity_threshold

    def _embed(self, text: str) -> np.ndarray:
        if not self.vectors:
            vec = self.vectorizer.fit_transform([text]).toarray()[0]
        else:
            vec = self.vectorizer.transform([text]).toarray()[0]
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def get_or_call(self, compressed_query: str,
                    llm_fn, call_kwargs: dict) -> str:
        # Check semantic cache
        q_vec = self._embed(compressed_query)
        for idx, cached_vec in enumerate(self.vectors):
            sim = cosine_similarity([q_vec], [cached_vec])[0][0]
            if sim >= self.threshold:
                # Use cached response for semantically equivalent query
                return self.cache[list(self.cache.keys())[idx]]

        # Cache miss → call provider
        response = llm_fn(**call_kwargs)
        if len(self.cache) >= self.max_entries:
            # Evict oldest
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            self.vectors.pop(0)

        self.cache[compressed_query] = response
        self.vectors.append(q_vec)
        return response
```

**Tier 3 — Two-tier provider cache sizing.** If you must use provider prefix caching, size your system prefix to exploit the threshold. Anthropic Sonnet 4.6 hits plateau (ρ≈0.83) above 3,500 tokens. Target 4,000–6,000 token stable prefixes. Below 3,500 tokens, the hit rate is poor enough that the cache discount may not justify the complexity — measure before committing.

```python
def optimal_prefix_size(metrics: CacheMetrics) -> int:
    """Decide whether provider prefix cache is worth it.

    Returns the recommended prefix size based on measured hit rates.
    Below threshold, semantic cache (Tier 2) is more cost-effective.
    """
    THRESHOLD = 3500  # Anthropic Sonnet 4.6 cache plateau
    WORTH_IT_HIT_RATE = 0.70

    if metrics.prefix_tokens < THRESHOLD:
        # Below threshold: hit rate plateaus at ~0.83
        # Use semantic cache instead — it's provider-agnostic
        return 0  # Signal: don't use provider prefix cache

    if metrics.hit_rate >= WORTH_IT_HIT_RATE:
        # Above threshold with good hit rate: worth it
        return metrics.prefix_tokens

    # Above threshold but poor hit rate → investigate why
    # Possible causes: session fragmentation, multi-user interference
    return metrics.prefix_tokens
```

## Receipt

> Verified 2026-08-20 — arXiv:2607.15516v1 (Yan Song, PayPal, July 2026) provides the empirical foundation. Three production workload validations confirm the cache-compression conflict. Anthropic Sonnet 4.6 two-tier cache architecture confirmed via API measurement: sharp threshold near 3,500 tokens, plateau hit rate ρ≈0.83 across 30-call sessions. CAPC framework validated on PayPal workloads. Semantic cache approach (Tier 2) is a direct application of CAPC recommendations.

## See also

- [S-2908 · The Multi-Tier Inference Cache Stack](stacks/s2908-the-multi-tier-inference-cache-stack-when-your-llm-bill-is-10x-your-compute.md) — the broader multi-tier caching architecture (KV / semantic / provider)
- [S-31 · Prompt Compression](stacks/s31-prompt-compression.md) — compression techniques for RAG passages; this entry explains why naive combination with caching fails
- [S-11 · LLM Gateway and Fallback](stacks/s11-llm-gateway-fallback.md) — provider-level fallback chains; cache-compression conflict is a pre-gateway optimization
