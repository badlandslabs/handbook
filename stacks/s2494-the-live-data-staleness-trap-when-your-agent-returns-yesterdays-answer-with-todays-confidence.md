# S-2494 · The Live-Data Staleness Trap — When Your Agent Returns Yesterday's Answer with Today's Confidence

Your customer asks "is my order shipped?" The agent checks a cached query result from 12 minutes ago, confirms shipment, and closes the ticket. The order was returned to sender 8 minutes ago. The agent was fast, confident, and wrong — and nothing in its world told it that the cached answer had become a lie.

This is the live-data staleness trap: agents that cache results over mutable data, serve them with full model confidence, and have no signal that the ground truth changed underneath them.

## Forces

- **Cached = trusted.** When a query result comes from cache, the agent treats it identically to a fresh result. There's no metadata in the context that says "this answer is N minutes stale" — so the model doesn't know to hedge.
- **Mutable data is the default in production.** Account balances, inventory counts, order statuses, user permissions, pricing, availability — most data an agent reads changes over time. Caching any of it risks serving stale answers.
- **Semantic caching widens the blast radius.** Unlike exact-match caching, semantic cache hit criteria are loose. "Has my package shipped?" and "where is my order?" hit the same cache entry even if shipment status changed between them.
- **Latency hides the problem.** The cached answer returns faster than a fresh one — speed signals correctness, not staleness. The agent has no latency-based hedge.
- **The agent has no invalidation channel.** Most cache invalidation is TTL-based. TTL doesn't know when data actually changed — it only knows elapsed time. A 5-minute TTL that fires 30 seconds before a data change is just as broken as no TTL at all.

## The move

**1. Annotate every cached tool result with an explicit staleness bound.**

Do not let tool results enter the context as raw strings. Wrap them:

```
cached_result = semantic_cache.get(query_embedding)
if cached_result:
    response_text = cached_result.value
    context_note = (
        f"[Cache hit — source '{cached_result.source}' was written "
        f"{cached_result.age_seconds}s ago. Data may have changed since then.]"
    )
    # Inject as explicit context, not raw tool output
```

The model will hedge more when it sees the age. This is not elegant — it's necessary because the model cannot observe cache metadata.

**2. Track staleness tolerance per data type.**

Not all cached data ages equally. Define tolerance thresholds:

| Data type | Max acceptable age | Action if stale |
|---|---|---|
| Product catalog description | 4 hours | Use cached, flag in output |
| Account balance | 0 | Bypass cache, read live |
| Order status | 2 minutes | Use cached if age < 2min, else refresh |
| Inventory count | 30 seconds | Never cache, always fresh |
| User permissions | 1 minute | Use cached if age < 1min |

Inventory and financial data get near-zero TTL. Static reference data gets generous TTL. The key is making the TTL policy explicit per data class, not global.

**3. Wire data-source change events into cache invalidation.**

TTL-only invalidation is a proxy for data change. When you can detect actual changes, use them:

- Subscribe to database change streams (PostgreSQL logical replication, MongoDB change streams, DynamoDB Streams)
- Use webhooks from external APIs (shipping providers, payment systems)
- Invalidate the cache entry on write to the authoritative source — don't wait for TTL to expire

This is the difference between "cache entry is 5 minutes old" and "the order status record was last modified 5 minutes ago." The former tells you time elapsed; the latter tells you data changed.

**4. Add a freshness assertion to every staleness-sensitive tool call.**

When the agent calls a tool whose result will be used for a consequential decision, the orchestrator injects a constraint:

```
You are answering about data that may be cached.
If you see a cache age annotation, treat it as an explicit warning.
For shipping status, inventory, pricing, account balances, or permissions:
  — do not answer with full confidence if the cache age > 60 seconds
  — say "I see this data is N seconds old — [the current status is / let me check fresh]"
```

The model can hedge correctly if it knows it has stale data. It cannot hedge if it doesn't know.

**5. Monitor cache-to-truth divergence in production.**

Track how often cached answers diverge from live answers when you do a refresh:

```
fresh = live_query()
cached = cached_query()
divergence = semantic_distance(fresh, cached)
if divergence > threshold:
    alert("Cache divergence on", source, "age:", cache_age, "divergence:", divergence)
    invalidate(source)
```

High divergence + old cache = your TTL is too loose for that data type. Tune it.

```python
import hashlib, time
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class StalenessAnnotatedResult:
    value: Any
    source: str
    cached_at: float
    ttl_seconds: int
    invalidated_by: Optional[str] = None  # event source that triggered invalidation

    @property
    def age(self) -> float:
        return time.time() - self.cached_at

    @property
    def is_fresh(self) -> bool:
        return self.age < self.ttl_seconds

    @property
    def staleness_note(self) -> str:
        if self.is_fresh:
            return f"[{self.source}: {self.age:.0f}s old — within TTL]"
        return (
            f"[⚠ {self.source}: {self.age:.0f}s old — EXCEEDS TTL of {self.ttl_seconds}s. "
            f"Data may have changed. Verify before acting on this result.]"
        )


class LiveDataCache:
    """Cache that enforces staleness tolerance per data type and annotates results."""

    def __init__(self, ttl_by_type: dict[str, int], change_event_subscribers: list[callable] = None):
        self._store: dict[str, StalenessAnnotatedResult] = {}
        self._ttl_by_type = ttl_by_type
        self._change_subscribers = change_event_subscribers or []
        for source, ttl in ttl_by_type.items():
            if hasattr(source, 'subscribe'):
                source.subscribe(lambda e, s=source: self._on_change_event(s, e))

    def get(self, key: str) -> Optional[StalenessAnnotatedResult]:
        return self._store.get(key)

    def set(self, key: str, value: Any, source: str, ttl_seconds: Optional[int] = None):
        ttl = ttl_seconds or self._ttl_by_type.get(source, 300)
        self._store[key] = StalenessAnnotatedResult(
            value=value,
            source=source,
            cached_at=time.time(),
            ttl_seconds=ttl,
        )

    def _on_change_event(self, source: str, event: Any):
        """Invalidate all entries whose source matches the change event."""
        for key, result in list(self._store.items()):
            if result.source == source:
                result.invalidated_by = f"change_event:{event}"
                del self._store[key]

    def inject_into_context(self, key: str, llm) -> str:
        """Return annotated text suitable for injection into agent context."""
        result = self.get(key)
        if not result:
            return ""
        return f"{result.value}\n\n{result.staleness_note}"
```

## Receipt

> Verified 2026-08-11 — Semantic caching with Redis (redis.io/blog/what-is-prompt-caching) reports 70-90% cost reduction, but Redis documentation explicitly notes: "For tasks where data freshness is critical (e.g., financial data, inventory levels), you may not want to use caching at all, or you need a very short TTL." The Belsoft analysis (belsoftsolutions.com/blog/llm-prompt-caching-enterprise-production-2026) quantifies that a customer-support agent can drop from $4,200/month to $680/month with prompt caching — but neither source addresses the correctness problem when cached results reference mutable state. The pattern is validated in principle; the implementation code above is representative of the staleness-annotation pattern described across the Redis and Belsoft guides. Receipt pending — production runtime demonstration.

## See also

- [S-1654 · The Stale Amplification Stack](/stacks/s1654-the-stale-amplification-stack-when-caching-makes-wrong-answers-faster.md) — static policy document staleness; this entry covers mutable live-data staleness
- [S-943 · The Semantic Cache Stack](/stacks/s943-the-semantic-cache-stack-when-your-agent-pays-full-price-for-a-question-it-already-answered.md) — semantic cache mechanics; this entry covers freshness control on top of semantic cache
- [S-100 · Live Data Freshness Contracts](/stacks/s100-live-data-freshness-contracts.md) — data freshness as a contract; this entry applies the concept to agentic cache invalidation
