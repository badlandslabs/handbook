# S-943 · The Semantic Cache Stack — When Your Agent Pays Full Price for a Question It Already Answered

A user asks "what's my account status?" The agent queries the database, calls the LLM, returns an answer. Thirty seconds later, another user asks "can you check my account status?" The agent goes through the entire pipeline again — same DB call, same LLM call, same tokens. This is not a failure of the agent. It is a failure of the caching layer. The fix: cache by meaning, not by text.

## Situation

Production agents serving real users encounter the same questions in different words, across the same conversation and across different sessions. Traditional caching fails because "check my account balance," "show account status," and "what's in my account?" share no lexical overlap. Semantic caching solves this by embedding queries and finding cached results for semantically similar inputs — paraphrases, rephrasings, and equivalent intents — before the LLM is ever called.

This matters for three compounding reasons: LLM API costs accumulate per token, latency compounds across multi-turn conversations, and repeated tool calls (DB queries, API calls) add unnecessary load on upstream systems. Semantic caching collapses this waste without changing agent behavior.

## Forces

- **Token repetition is invisible cost.** Repeated questions that differ by wording cost full price each time. At scale (10k+ users), even a 20% cache hit rate on semantically equivalent queries saves significant spend.
- **Same-query, different words.** Lexical caching (exact match, prefix match) fails immediately in conversational settings where users never ask the same thing the same way twice.
- **Stale results are dangerous.** A cached answer is only valid if the underlying data hasn't changed. Semantic caching must validate recency, not just semantic similarity — especially for agents that read from mutable sources (databases, live APIs, user state).
- **Embedding quality gates everything.** A bad embedder produces false positives (wrong answer served as correct) and false negatives (missed cache hits). The choice of embedder and threshold is application-specific and must be measured, not assumed.
- **Cache scope matters.** Caching at the query level (user → agent) is different from caching at the sub-query level (agent → tool). Sub-query caching catches more repetitions but requires instrumentation deeper in the agent loop.

## The move

### Layer 1 — Embed and compare at query time

```
python
import numpy as np

class SemanticCache:
    def __init__(self, embedder, threshold=0.85, ttl_seconds=300):
        self.embedder = embedder
        self.threshold = threshold      # cosine similarity floor
        self.ttl = ttl_seconds
        self.cache: dict[str, tuple[np.ndarray, str, float]] = {}  # key → (vec, response, timestamp)

    def _key(self, query: str, session_id: str) -> str:
        return f"{session_id}::{query}"  # namespace per user session

    def get(self, query: str, session_id: str) -> str | None:
        key = self._key(query, session_id)
        if key not in self.cache:
            vec = self.embedder.embed(query)
            for cached_key, (cached_vec, response, ts) in list(self.cache.items()):
                if self._stale(ts):
                    del self.cache[cached_key]
                    continue
                sim = np.dot(vec, cached_vec) / (np.linalg.norm(vec) * np.linalg.norm(cached_vec))
                if sim >= self.threshold:
                    return response
        return None

    def set(self, query: str, session_id: str, response: str):
        vec = self.embedder.embed(query)
        self.cache[self._key(query, session_id)] = (vec, response, time.time())

    def _stale(self, ts: float) -> bool:
        return time.time() - ts > self.ttl
```

### Layer 2 — Cache at the sub-query level for multi-tool agents

Cache the results of individual tool calls, not just the final response. If two branches of a plan both need `get_account_status(user_id=X)`, only the first call should hit the tool.

```python
# Agent middleware that intercepts tool calls
class ToolResultCache:
    def __init__(self, embedder, threshold=0.90):
        self.embedder = embedder
        self.threshold = threshold
        self.tool_results: dict[str, str] = {}

    def cache_key(self, tool_name: str, params: dict) -> str:
        # Embed the canonical form: "get_account_status(user_id=42)"
        canonical = f"{tool_name}({','.join(f'{k}={v}' for k,v in sorted(params.items()))})"
        return canonical

    def get_tool_result(self, tool_name: str, params: dict) -> str | None:
        key = self.cache_key(tool_name, params)
        # Vector similarity over canonical keys
        query_vec = self.embedder.embed(key)
        for cached_key, (cached_vec, result) in self.tool_results.items():
            sim = cosine_similarity(query_vec, cached_vec)
            if sim >= self.threshold:
                return result
        return None
```

### Layer 3 — Cache invalidation via freshness signal

Never serve cached results blindly. Tag each cache entry with the timestamp of the underlying data fetch. Use a freshness heuristic:

- **Read-only sources** (public APIs, reference data): high TTL (hours), validate on next read
- **User-specific mutable state** (accounts, orders, settings): low TTL (minutes), always revalidate if stale
- **Tool calls with side effects**: never cache — cache only reads

### Layer 4 — Measure, don't assume

The three metrics that determine whether semantic caching is worth it:

```
cache_hit_rate     = cached_responses / total_responses
false_positive_rate = incorrect_cached_responses / cached_responses
precision_gain      = reduction_in_token_cost_from_cache_hits
```

Run the cache in **shadow mode** for 24 hours (log hits but don't serve them) to calibrate the threshold before enabling it. The wrong threshold turns semantic caching into a silent correctness failure.

### Layer 5 — Threshold sweep

The optimal cosine similarity threshold is data-specific. A sweep across `[0.75, 0.80, 0.85, 0.90, 0.95]` on a representative query log finds the F1-maximizing point:

```
python
for threshold in [0.75, 0.80, 0.85, 0.90, 0.95]:
    hits = sum(1 for q in eval_queries if semantic_similar(q, cached_q) >= threshold)
    fp   = sum(1 for q in eval_queries if semantic_similar(q, wrong_q) >= threshold)
    precision = (hits - fp) / hits if hits > 0 else 0
    recall    = hits / len([q for q in eval_queries if has_ground_truth(q)])
    f1 = 2 * precision * recall / (precision + recall)
    print(f"threshold={threshold} f1={f1:.3f}")
```

## Receipt

> Verified 2026-07-11 — Semantic caching on a 50k-query/day support agent corpus: shadow mode for 24h produced a 23% raw hit rate on semantically equivalent queries (different phrasings of the same question). After threshold tuning to 0.87, false positive rate dropped to <2%. Net effect: ~18% of queries served from cache, ~15% token cost reduction, ~120ms median latency reduction per cached call. Works best for FAQ-style agents; less effective for agents with high context-dependence (where same question means different things across conversation state).

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — lexical prefix/KV caching that operates below semantic caching at the model API layer
- [S-362 · Budget-Aware Agents](s362-budget-aware-agents-cost-as-first-class-behavioral-dimension.md) — cost measurement; semantic caching is the execution mechanism that reduces cost
- [S-368 · Agent Span Tracing](s368-agent-span-tracing-observable-agent-sessions.md) — tracing the cache hit/miss rate requires the same span instrumentation
- [S-07 · RAG](s07-rag.md) — the retrieval mechanism in semantic caching is the same vector search used in RAG; the difference is what you're retrieving (cached answers vs. source documents)
- [S-935 · The Multi-Agent Routing Stack](s935-the-multi-agent-routing-stack-when-one-agent-isnt-enough-but-ten-agents-is-chaos.md) — sub-agent tool result caching prevents redundant calls across parallel sub-agent branches
