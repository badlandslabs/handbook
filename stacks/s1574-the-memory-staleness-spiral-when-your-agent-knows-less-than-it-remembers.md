# S-1574 · The Memory Staleness Spiral — When Your Agent Knows Less Than It Remembers

Your agent correctly recalls that User A prefers reports in PDF format, that the API endpoint is `v2.1`, and that the last sprint goal was shipped March 3rd. All three memories were true when stored. None are true now — the format changed, the API is on `v3.0`, and the sprint goal was revised. The agent retrieves all three, acts on all three as current facts, and nobody notices until the wrong output lands. This is not a memory retrieval failure. This is the Memory Staleness Spiral: correct storage + correct retrieval + zero staleness awareness = silently wrong behavior.

## Forces

- **Memories are stored as facts, not as time-stamped beliefs.** Most memory systems write `fact: "User prefers PDF reports"` into a vector store. The retrieval pipeline fetches it correctly. Nobody records when it became true, when it might expire, or whether the world has since changed. The fact looks current because it *is* a fact — just a stale one.
- **Retrieval similarity scores are blind to temporal validity.** Semantic similarity doesn't encode time. A memory about "Q4 2024 strategy" and a memory about "Q2 2026 strategy" can score identically relevant to a query about "current strategy" — the embedding knows nothing about validity windows.
- **Agents have no epistemic uncertainty about their own memory.** Humans caveat memories ("I think the deadline is Friday — or was it moved?"). Agents that retrieve a memory treat it as a grounded fact, often with high confidence, because they have no signal that the memory might be outdated relative to the current world state.
- **Staleness compounds silently in long-running sessions.** A session that runs for 30 days accumulates memories that are progressively more likely to be stale. The agent's confidence in retrieved memories grows over time (more retrieval = more reinforcement), while the actual accuracy of those memories degrades. This is the spiral: the agent becomes *more* confident in *less* accurate beliefs.

## The move

### 1. Stamp every memory with a temporal metadata envelope

Store not just the fact but its provenance and validity window:

```python
# Memory store entry — never write raw facts without metadata
memory_entry = {
    "fact": "User prefers PDF report format",
    "stored_at": datetime.utcnow().isoformat(),
    "valid_from": "2026-01-15T00:00:00Z",     # when this became true
    "valid_until": "2026-07-31T23:59:59Z",     # hard TTL (optional)
    "soft_staleness_days": 7,                   # advisory refresh window
    "source": "user_explicit_preference",       # how it was learned
    "version": 1,
    "superseded_by": None,                      # link to newer version if updated
}
```

This applies to every memory layer: L1 (working context), L2 (conversation/session store), and L3 (persistent profiles).

### 2. Compute staleness at retrieval, not at storage

At retrieval time, compute how old the memory is and surface that as a signal:

```python
from datetime import datetime, timedelta

def retrieve_memory_with_freshness(user_id: str, query: str, memory_store) -> list[dict]:
    """Retrieve memories and annotate each with staleness signal."""
    memories = memory_store.search(user_id=user_id, query=query, top_k=5)

    now = datetime.utcnow()
    enriched = []
    for mem in memories:
        age = now - datetime.fromisoformat(mem["stored_at"])
        days_old = age.total_seconds() / 86400

        # Staleness tiers
        if mem.get("valid_until") and now > datetime.fromisoformat(mem["valid_until"]):
            staleness_tier = "EXPIRED"
        elif days_old > mem.get("soft_staleness_days", 30):
            staleness_tier = "STALE"
        elif days_old > mem.get("soft_staleness_days", 30) / 2:
            staleness_tier = "AGING"
        else:
            staleness_tier = "FRESH"

        mem["staleness_tier"] = staleness_tier
        mem["days_old"] = round(days_old, 1)
        enriched.append(mem)

    return enriched

# In the agent's system prompt or retrieval context, include:
# "MEMORY [{tier}] {days_old}d: {fact}"
# Agents that see "[STALE] 47d: API endpoint is v2.1" are more likely to verify
```

### 3. Inject staleness into the agent's context — not as metadata, as instruction

Don't just append staleness as invisible metadata. Convert it to a prompt signal the agent acts on:

```
## Retrieved Memories (with freshness advisory)
- [STALE — 47 days old] "API endpoint is v2.1" — verify before using
- [AGING — 12 days old] "User prefers PDF reports" — confirm still current
- [FRESH — 2 hours old] "Sprint 24 goals: [list]"
- [EXPIRED] "Q4 2024 strategy" — discard; superseded
```

The `[STALE]` and `[EXPIRED]` markers are not decorative — the agent's instruction set should tell it to re-query or verify before acting on memories above the freshness threshold.

### 4. Build a background re-validation pipeline

For high-value memories (user preferences, system configurations, policy rules), run async refresh:

```python
async def revalidate_memory(mem: dict, agent_client) -> dict:
    """Periodically re-check high-value memories against live sources."""
    if mem["staleness_tier"] not in ("STALE", "AGING"):
        return mem

    # Trigger verification based on memory type
    if mem["source"] == "user_explicit_preference":
        # Don't auto-change preferences; flag for confirmation
        mem["needs_confirmation"] = True
        mem["confirmed"] = False
    elif mem["source"] in ("api_knowledge", "system_config"):
        # Re-query the source; update in place
        fresh = await live_source_query(mem["fact"])
        if fresh != mem["fact"]:
            mem["superseded_by"] = fresh["id"]
            mem["valid_until"] = datetime.utcnow().isoformat()
            mem["version"] += 1
            # Write new version; don't overwrite old
            memory_store.upsert(fresh, superseded_from=mem["id"])

    return mem
```

### 5. Partition memories by expected volatility

Not all memories age equally. Assign volatility tiers at write time:

| Volatility | Expected Lifetime | Example | Refresh Strategy |
|---|---|---|---|
| **Static** | Months–years | User name, role | Manual or on-demand |
| **Slow** | Weeks | Preferences, team structure | Periodic re-confirm |
| **Dynamic** | Days | Ticket status, API versions | Live re-query preferred |
| **Temporal** | Hours or less | Stock prices, availability | Never cache; always fetch |

Dynamic and temporal memories should be retrieved live at query time, not from the memory store — the memory store is a cache of beliefs, not a live data source. S-100 (Live Data Freshness Contracts) covers this distinction at the tool-call layer; this entry covers it at the memory retrieval layer.

## Receipt

> Verified 2026-07-24 — Pattern identified from production analysis across Mem0 AI Agent Memory 2026 report (LoCoMo/LongMemEval benchmarks, temporal reasoning gaps), Mem0.io State of AI Agent Memory (cross-session identity and staleness as open problems), linesNcircles Tiered Memory Architecture guide (L1/L2/L3 tier staleness differentiation), Cloudflare Agent Memory (selective deletion for stale memories), and LangChain State of Agent Engineering survey (57% in production, quality as #1 barrier — quality includes stale knowledge acting as valid facts). No single existing handbook entry covers the specific failure mode of memory-level temporal staleness. Closest related entries: S-991 (memory architecture), S-100 (data freshness at tool layer), S-1127 (cross-user contamination), S-1063 (context lifecycle). This entry occupies the gap between "how memory is stored" and "when the stored memory is wrong."

## See also

- [S-991 · Agent Memory Stack](s991-the-agent-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — memory architecture foundations
- [S-100 · Live Data Freshness Contracts](s100-live-data-freshness-contracts.md) — staleness at the tool-call layer
- [S-1063 · Context Lifecycle Stack](s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — active curation of context over time
- [S-1127 · Cross-User Memory Contamination](s1127-the-cross-user-memory-contamination-stack-when-user-b-sees-user-as-private-notes.md) — memory leakage between users
- [S-1002 · Memory Consolidation Debt](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — related memory quality debt
