# S-2666 · The Obsolescence Blind Spot — When Your Agent Remembers Correctly But Acts Wrong

Your agent retrieves a memory: the pricing contract with Acme Corp was last updated on 2024-03-15, rate $0.042/kWh. The retrieval score is 0.94 — near perfect. The agent uses it to calculate a quote. Acme switched providers eight months ago. The memory is historically accurate. The decision is catastrophically wrong.

This is the obsolescence blind spot: vector similarity ranking is blind to temporal decay, domain drift, and schema evolution. Retrieval finds what matches your query; it does not find what is still true.

## Forces

- **Vector similarity ≠ relevance.** A 0.95 similarity score tells you the retrieved text resembles the query — not that the retrieved fact applies to the current context. Similarity is syntactic; relevance is pragmatic.
- **Temporal proximity and semantic similarity are orthogonal signals.** High similarity can coexist with complete staleness. The vector has no timestamp awareness unless explicitly injected.
- **Forgetting is invisible.** Agents are tested on retrieval accuracy — did it find the right document? — not on retrieval validity — is this document still the right one? This split means the blind spot passes every evaluation.
- **Staleness compounds across layers.** A stale memory feeds a stale reasoning chain. By the time the output is obviously wrong, the root cause (forgetting to check "is this still true?") is buried under layers of correct-looking logic.
- **What "fresh" means is domain-dependent.** A pricing contract going stale in August 2026 means "no longer the governing rate." A regulatory code going stale means "this law was repealed." A product spec going stale means "this feature was cut." Generic TTLs can't capture these distinctions.

## The move

**Layer 1 — Timestamp every memory with action-level precision.**

Every memory record carries an `effective_from` and `effective_until` field. Not `created_at` — `effective_until`, the time after which this fact should not drive a consequential action without re-verification.

```python
class TimestampedMemory:
    content: str
    effective_from: datetime    # when this became true
    effective_until: Optional[datetime]  # when this stopped being true; None = still valid
    verified_at: datetime       # last human/automated confirmation
    staleness_threshold: timedelta  # domain-specific, not a global TTL

    def is_live(self, now: datetime) -> bool:
        if self.effective_until and self.effective_until < now:
            return False
        if (now - self.verified_at) > self.staleness_threshold:
            return False
        return True
```

**Layer 2 — Separate retrieval from action qualification.**

Vector retrieval returns candidates. A separate `qualification layer` scores them for action-readiness: temporal validity, source recency, schema compatibility.

```python
def retrieve_for_action(query: str, action_type: str, context: dict) -> list[Memory]:
    candidates = vector_store.similarity_search(query, k=10)

    qualified = []
    for mem in candidates:
        # Layer 1: still temporally live?
        if not mem.is_live(now=datetime.utcnow()):
            continue
        # Layer 2: schema-compatible with current context?
        if not mem.schema_version.is_compatible(context["schema_version"]):
            continue
        # Layer 3: action-type-aware staleness
        threshold = staleness_thresholds[action_type]
        if (datetime.utcnow() - mem.verified_at) > threshold:
            # Downscore but don't discard — flag for re-verification
            mem.qualification_score = 0.3
            mem.flag = "REVERIFY"
        else:
            mem.qualification_score = mem.similarity_score
        qualified.append(mem)

    return qualified
```

**Layer 3 — Tag action types with staleness thresholds.**

```
QUERY          → 7 days (read operations, low blast radius)
PRICE          → 24 hours (financial impact)
REGULATORY     → 24 hours (compliance risk)
PERSONNEL      → 7 days (org structure changes slowly but matters)
CONFIG         → 1 hour (runtime config, fast drift)
```

**Layer 4 — Surface staleness at the decision point.**

When a retrieved memory is flagged, the agent's prompt gets a mandatory annotation:

```
RETRIEVED: "Pricing contract rate = $0.042/kWh" [REVERIFY — verified 43 days ago, action_type=PRICE, threshold=24h]
```

The agent is not forbidden from using it — it is informed. The move gives the agent the option to re-verify before committing.

**Layer 5 — Verifier-as-sidecar.**

For high-stakes actions, spawn a lightweight verification agent alongside the primary:

```python
def quote_with_verification(customer_id: str, retrieved_memories: list[Memory]) -> Quote:
    stale = [m for m in retrieved_memories if m.flag == "REVERIFY"]
    if stale and action_is_high_stakes(quote_action):
        verification = verifier_agent.run(
            prompt=f"Verify these facts are still current: {stale}. "
                   f"Return CONFIRMED / CONTRADICTED / UNKNOWN for each."
        )
        # Block if any verification returns CONTRADICTED
        if any(r.status == "CONTRADICTED" for r in verification.results):
            raise StaleMemoryError("Quoted from stale data — re-fetch required")
    return build_quote(retrieved_memories)
```

## Receipt

> Verified 2026-08-15 — Pattern verified against arXiv:2607.07118 "MemFree: Open-Source Memory-Augmented LLM Systems" (Jul 2026): the MemFree architecture explicitly separates retrieval (semantic match) from memory qualification (temporal validity), using a `time_decay_score = relevance * exp(-λ * age)` formula. Production memory systems at mnemoverse.com document reranking as a mandatory production requirement: "vector similarity returns the right candidates but often in the wrong order — age and verification recency must rerank before delivery." ACL 2026 (AgeMem, Yu et al.) shows that memory management quality — not just retrieval quality — determines long-horizon task performance. The gap between these two dimensions (retrieval vs. qualification) is the obsolescence blind spot.

## See also

- [S-178](s178-context-freshness-watermark.md) — Context Freshness Watermark: individual source TTLs, not cross-source action qualification
- [S-1035](s1035-the-context-capacity-gap-when-your-agent-remembers-a-conversation-that-was-never-meant-to-last.md) — Context Capacity Gap: effective vs. advertised context windows
- [S-2665](s2665-the-causal-trace-stack-when-your-tracer-captures-the-trip-but-not-the-cause.md) — Causal Trace: attaching why-this-was-retrieved to what-was-retrieved
