# S-1430 · The Memory Quality-Gated Eviction Stack — When Your Memory Grows to Infinity and Your Agent Gets Dumber

Your agent has run 3,200 tasks. It has 18,400 vector-stored memory entries spanning two years of conversations, document retrievals, and learned preferences. The new hire just asked it to summarize the Q3 product roadmap. The agent spent 40 seconds retrieving 20 entries, filled half its context window with noise, and answered as if Q3 had launched six months ago. The memory isn't full. The memory is full of garbage. This is not a retrieval problem. It is a **garbage collection problem**.

## Forces

- **Append-only is the default but not the answer.** Every agent framework ships with a "store everything" memory system. Vector search is the only gatekeeper — if the query matches, the memory gets retrieved, regardless of whether the entry is stale, contradicted by later events, or only incidentally relevant. After 1,000+ sessions, the corpus is too large to audit and too noisy to trust.
- **Recency and frequency are terrible eviction signals.** LRU and LFU both miss the point: the memories most likely to be needed again aren't the most recently accessed or the most frequently accessed — they're the most *useful*. A memory entry about a cancelled project that was accessed last week keeps surfacing over the accurate replacement plan that was created this morning.
- **Quality degrades before quantity does.** Tian Pan (tianpan.co, April 2026) showed this starkly: agents using an add-all strategy accumulated 2,400 records with 13% accuracy on medical reasoning tasks; agents with active memory management kept 248 records and achieved 39% accuracy — 3× better performance from *less* memory. The signal-to-noise ratio of the memory corpus, not its size, determines agent quality.
- **Write-side quality gates are insufficient alone.** Most teams improve by adding importance scores at write time. But importance at write time is a prediction, not a measurement. A memory entry flagged "important" because it contains a project deadline doesn't account for the project being cancelled, renamed, or reassigned three weeks later. Eviction must re-evaluate quality at retrieval time or on a schedule.
- **Manual GC doesn't scale.** Engineering teams patch this by running periodic cleanup scripts or letting users "forget" specific facts. This is a whack-a-mole strategy. The memory corpus is growing faster than any manual process can track, and the failure mode (wrong answers) is silent — no exception fires, no alert pages anyone.

## The Move

Quality-gated eviction replaces recency and frequency with **retrieval success correlation** as the primary eviction signal. The core idea: a memory entry's value isn't whether it matched a query, but whether *using it in context produced a good outcome*. Track retrieval-to-outcome correlation per entry, and evict entries that correlate with failures more than successes.

### Signal Layer: What to Track Per Entry

Store these fields on every memory entry after the first retrieval cycle:

```
memory_entry {
  id: string
  content: string
  created_at: timestamp
  last_accessed: timestamp
  access_count: int
  retrieval_count: int          # times this entry appeared in top-k
  success_when_used: int        # task outcomes that used this entry and succeeded
  failure_when_used: int        # task outcomes that used this entry and failed
  stale_flag: bool              # set when contradicting evidence appears
  quality_score: float          # computed: success_when_used / (success_when_used + failure_when_used + ε)
}
```

### Eviction Trigger: The Quality Drain

Run eviction when `median(quality_score across corpus) < threshold`. This fires when the median entry in your memory corpus has a quality score below the threshold — meaning most of your memory is net-negative.

```python
def should_evict(memory_entries: list[MemoryEntry], threshold: float = 0.5) -> bool:
    scores = [e.quality_score for e in memory_entries if e.retrieval_count > 3]
    if len(scores) < 10:
        return False
    median_score = statistics.median(scores)
    return median_score < threshold
```

### Eviction Algorithm: Quality-Ranked Sweep

```python
def evict_low_quality(memory_entries: list[MemoryEntry], target_count: int = 500) -> list[str]:
    """Evict entries with lowest quality scores until corpus reaches target_count."""
    # Only consider entries with enough retrieval history to be meaningful
    candidates = [e for e in memory_entries if e.retrieval_count >= 3]
    
    # Sort by quality score ascending (worst first)
    ranked = sorted(candidates, key=lambda e: (
        e.quality_score,                    # lowest quality first
        -e.last_accessed.timestamp,         # break ties with older
        -e.retrieval_count                  # prefer evicting less-used
    ))
    
    evicted_ids = []
    for entry in ranked:
        if len(memory_entries) <= target_count:
            break
        memory_store.delete(entry.id)
        evicted_ids.append(entry.id)
    
    return evicted_ids
```

### The Staleness Signal: Cross-Entry Contradiction Detection

Quality scores alone can't catch factual staleness. Add a lightweight contradiction detector that runs on every new memory write:

```python
def check_staleness(new_entry: MemoryEntry, existing_entries: list[MemoryEntry]) -> list[str]:
    """Find entries that contradict the new entry, mark them stale."""
    stale_ids = []
    new_entities = extract_entities(new_entry.content)
    new_facts = extract_facts(new_entry.content)  # (subject, predicate, object) triples
    
    for existing in existing_entries:
        if existing.is_stale:
            continue
        existing_entities = extract_entities(existing.content)
        overlap = set(new_entities) & set(existing_entities)
        
        if len(overlap) < 2:  # need shared entities to check contradiction
            continue
        
        # Check if factual triples contradict
        new_facts_for_overlap = [(s,p,o) for (s,p,o) in new_facts if s in overlap]
        existing_facts_for_overlap = [(s,p,o) for (s,p,o) in extract_facts(existing.content) if s in overlap]
        
        for (s, p, o) in new_facts_for_overlap:
            for (se, pe, oe) in existing_facts_for_overlap:
                if s == se and p == pe and o != oe:
                    # Contradiction found — mark existing stale
                    existing.is_stale = True
                    stale_ids.append(existing.id)
                    break
    
    return stale_ids
```

Stale entries are evicted on the next GC sweep regardless of quality score.

### GC Cadence: When to Run

| Trigger | Frequency | Use When |
|---------|-----------|----------|
| Task-completion-triggered | Every N completions | Low-volume, high-stakes agents |
| Nightly batch | Every 24h | Most production agents |
| Context-pressure-triggered | When window >80% full | Memory-intensive pipelines |
| Quality-threshold-triggered | When median quality drops | Data-drift-prone domains |

## Receipt

> Verified 2026-07-21 — Tian Pan (tianpan.co, April 2026): 2,400-record add-all agents achieved 13% task accuracy; 248-record quality-managed agents achieved 39% — 3× improvement from fewer, higher-quality memories. Quality-gated eviction pattern implemented against this benchmark.

## See also

- [S-529 · Context Interference — Proactive Forgetting](/stacks/s529-context-interference-proactive-forgetting.md) — the write-path equivalent: what to store before eviction becomes necessary
- [S-1030 · The Forgetting Stack](/stacks/s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — retrieval crowding and extraction noise as the input-side failure
- [S-1221 · Importance-Weighted Starvation](/stacks/s1221-the-importance-weighted-starvation-stack-when-your-agent-has-a-full-window-but-nothing-that-matters.md) — the context-side consequence when importance isn't tracked at eviction
- [S-1020 · The Tiered Memory Stack](/stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — the architecture this pattern slots into
