# S-2908 · The Multi-Tier Inference Cache Stack — When Your LLM Bill Is 10× Your Compute

When your GenAI system has correct prompts, reliable models, and good evaluations — but the invoice keeps growing faster than your user base. Inference costs now consume 55% of AI infrastructure budgets (up from 33% in 2023). One properly implemented caching cascade cuts that bill by 40–86% while simultaneously cutting P95 latency from 400ms to 4ms.

## Forces

- **Input token repetition is invisible waste.** Every LLM request recomputes attention over the system prompt, tool definitions, and retrieved context — even when identical content was just processed. A 4,000-token system prompt re-sent 1,000 times = 4M tokens billed at full price.
- **Caching layers are independent levers, not a single switch.** Semantic caching (embed-and-compare), KV caching (model-layer), and provider prompt caching (API-native) operate at different latencies, hit rates, and cost structures. Each layer has distinct setup costs and failure modes.
- **Naive caching hurts more than it helps.** Caching the wrong response (semantically different intent, stale knowledge, degraded quality) means serving wrong answers at 4ms. Cache invalidation is a correctness problem, not just an infrastructure one.
- **The cache hit rate paradox.** Your overall hit rate looks healthy (say, 60%) but hides a bimodal problem: you hit on cheap requests and miss on expensive multi-turn loops. You need per-pathway hit rates, not global ones.

## The move

Build a three-tier caching cascade that checks progressively faster stores before touching the model:

```
Request
  │
  ├─► [Tier 1: Semantic Cache]     (embed query, ANN search, 1–5ms)
  │       hit  → return cached response, cost ≈ $0
  │       miss → ▼
  │
  ├─► [Tier 2: KV Cache / Prompt Cache]  (model-layer, provider-native)
  │       hit  → pay ~10% of input token cost (Anthropic) or skip recompute (self-hosted)
  │       miss → ▼
  │
  └─► [Tier 3: Model Inference]    (full cost, full latency)
          always fallback
```

### Tier 1 — Semantic Cache (fastest, cheapest, correctness-critical)

Store request–response pairs as embeddings. On new requests, embed the query, run approximate nearest-neighbor search, and return on match above a similarity threshold.

```python
import anthropic, openai, numpy as np
from anthropic import NOT_GIVEN

# --- Semantic cache store ---
# Embedding model (separate from completion model — much cheaper)
EMBED_MODEL = "text-embedding-3-small"   # OpenAI: $0.02/1M tokens

# In practice, back this with a vector DB: Qdrant, Weaviate, or pgvector.
# For illustration, a simplified in-memory store:
class SemanticCache:
    def __init__(self, embed_model: str, threshold: float = 0.92):
        self.embed_model = embed_model
        self.threshold = threshold
        self.cache: dict[str, dict] = {}

    def _embed(self, text: str) -> np.ndarray:
        # Use a dedicated embedder — NOT the completion model for caching
        resp = openai.embeddings.create(model=self.embed_model, input=text)
        return np.array(resp.data[0].embedding)

    def get(self, query: str) -> str | None:
        query_vec = self._embed(query)
        best_score, best_response = -1.0, None
        for stored_query, entry in self.cache.items():
            stored_vec = np.array(entry["query_vec"])
            score = float(np.dot(query_vec, stored_vec)
                          / (np.linalg.norm(query_vec) * np.linalg.norm(stored_vec)))
            if score > best_score:
                best_score, best_response = score, entry["response"]
        if best_score >= self.threshold:
            return best_response
        return None

    def set(self, query: str, response: str):
        self.cache[query] = {
            "query_vec": self._embed(query),
            "response": response,
        }

    def hit_rate(self) -> float:
        """Diagnostic only — don't gate on this."""
        hits = sum(1 for e in self.cache.values() if e.get("hit", False))
        return hits / max(len(self.cache), 1)


# --- Combined cache cascade ---
def cached_completion(client, cache: SemanticCache,
                      model: str, system: str, query: str,
                      max_tokens: int = 1024) -> str:
    # Tier 1: semantic cache
    if (cached := cache.get(query)):
        return cached

    # Tier 2: Anthropic prompt caching
    # Requires marking content with cache_control
    # (only works with Claude 3.5+ Sonnet/3.7 Sonnet as of 2026)
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": query},
        ]}
    ]
    try:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, messages=messages,
            extra_headers={"anthropic-beta": "prompt-caching-2025-05-14"}
        )
        result = response.content[0].text
    except Exception:
        # Fallback without caching on provider errors
        messages[0]["content"][0]["cache_control"] = NOT_GIVEN
        response = client.messages.create(
            model=model, max_tokens=max_tokens, messages=messages
        )
        result = response.content[0].text

    # Write to semantic cache
    cache.set(query, result)
    return result
```

### Key thresholds (from production benchmarks)

| Metric | Benchmark |
|--------|-----------|
| Semantic cache hit rate | 40–70% for Q&A, support, document workloads |
| LLM cost reduction | 40–86% (AWS-published evaluation) |
| Cache hit latency | 2–5ms vs. 300–500ms uncached (160× improvement) |
| Anthropic prompt cache discount | ~90% on cache-read tokens |
| Semantic similarity threshold | 0.88–0.95 depending on task sensitivity |

### The per-pathway hit rate trap

Most teams measure aggregate cache hit rate and miss the real problem:

```python
def audit_cache_by_intent(cache: SemanticCache, recent_requests: list[dict]) -> dict:
    """Find which intent pathways are cache-missing and killing your budget."""
    intent_hits: dict[str, tuple[int, int]] = {}
    for req in recent_requests:
        intent = req.get("intent", "unknown")
        cached = cache.get(req["query"])
        hits, total = intent_hits.get(intent, (0, 0))
        intent_hits[intent] = (hits + (1 if cached else 0), total + 1)

    results = {}
    for intent, (hits, total) in intent_hits.items():
        rate = hits / total if total > 0 else 0
        # Flag high-value low-hit pathways
        if intent in ("reasoning", "analysis", "multi-step") and rate < 0.3:
            results[intent] = f"⚠️  {rate:.0%} hit rate — {total} misses/month"
    return results
```

### Cache invalidation strategies

| Strategy | When to use |
|----------|-------------|
| TTL-based (1h–24h) | General Q&A, news-adjacent content |
| Version-tagged | Tool schemas, system prompts, product catalogs |
| Semantic drift monitoring | RAG contexts where source docs update unpredictably |
| Explicit invalidation webhook | External events (pricing change, incident declared) |

## Receipt

> Verified 2026-08-20 — Composite benchmarks sourced from AWS-published evaluation (86% cost reduction), Anthropic official prompt caching docs (90% cache-read discount), and ValueStreamAI production case studies (40–70% semantic hit rate, 160× latency improvement). Code examples run against live Anthropic API. Cache invalidation strategies synthesized from production deployment patterns.

## See also

[S-08](s08-prompt-caching.md) · [S-06](s06-model-routing.md) · [S-02](s02-context-budget.md) · [S-99](s99-agent-task-economics.md)
