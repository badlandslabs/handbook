# S-1915 · The Tiered Forgetting Stack — When Your Agent Remembers Everything and Knows Nothing

Your agent has a 200K-token context window and a vector store with every document your company has ever produced. Three months in production, it greets your largest enterprise client by asking for their company name. It remembers every single tool call from the last 90 days. It forgot the one fact that actually mattered. The problem is not that your agent has a bad memory. The problem is that it has no forgetting policy.

Storage is cheap. Retrieval is expensive. An agent with a flat memory architecture — everything stored equally, everything retrieved equally — produces retrieval noise that buries signal. The retriever returns 20 semi-relevant chunks, the model spends tokens disambiguating them, and the correct answer gets crowded out by plausible alternatives. The fix is not more context. The fix is a forgetting policy that treats memory like a product, not a database.

The production pattern that solves this is **tiered forgetting**: an explicit eviction hierarchy that prioritizes memories by a composite score (semantic importance × recency × temporal validity), enforced through a three-tier memory architecture. This is not the same as "the agent decides what to forget." Tiered forgetting is a systems design decision, made by engineers, enforced by infrastructure.

## Forces

- **Flat memory is a retrieval antipattern.** Every memory stored with equal weight means retrieval is dominated by keyword similarity, not actual utility. The document you cited last week outranks the policy that governs this entire workflow.
- **Context rot erodes governance before it erases facts.** A policy constraint from step 1 competes equally with a tool call result from step 37. S-1221 shows importance-weighted starvation: the agent's most critical information gets silently displaced by accumulated noise. Compounding this, S-360 (Governance Decay) shows that compaction optimises for task continuity, not constraint preservation — standing policies are treated as low-salience and evicted first.
- **Recency is the wrong eviction signal.** LRU works for caches because older entries are less likely to be needed. For agents, a fact about a client's legal structure from six months ago is more important than last Tuesday's weather. Importance does not decay like recency.
- **Tiered forgetting is already field-proven.** Anthropic's "Dreaming" (May 2026) is a between-session consolidation cycle that distils raw experience into durable, retrievable memory. Mem0's tiered architecture (hot/warm/cold tiers), Ivezaj's three-tier pattern (Jun 2026), and IDFS AI's tiered forgetting research (May 2026) all converge on the same conclusion: the production-ready agent forgets on purpose.
- **Forgetting policies must be explicit and tunable.** A hardcoded "drop anything older than 30 days" is fragile. Forgetting policy is a product decision that should reflect business impact, not just storage constraints.

## The move

### 1. Define three memory tiers

```
TIER 1 — HOT (always in context)
  Scope: Current task context, active policy constraints, 
         user preferences from last session, in-flight tool results.
  Eviction: Never automatic. Explicit task-end flush.
  Size: ~5-15% of context window, hard-capped.

TIER 2 — WARM (retrievable on query)
  Scope: Facts about the current user/project, 
         recent decisions and their rationale, 
         relevant policies (not just the active one), 
         session history condensed to key outcomes.
  Eviction: Composite score < threshold → compress or evict.
  Size: Vector store, unlimited, scored and ranked.

TIER 3 — COLD (reconstructable on demand)
  Scope: Archive of past session summaries, 
         historical decisions, completed task logs.
  Eviction: Age-based + importance-weighted.
  Access: Regenerated from Tier 2 summaries when context permits.
```

### 2. Score every memory with a composite importance function

Do not rely on recency alone. Weight three signals:

```
Score = (semantic_importance × 0.45) + (recency × 0.25) + (temporal_validity × 0.30)

semantic_importance: how critical is this fact to current or foreseeable tasks?
  → Policy constraints, user preferences, active project facts: high
  → Incidental context, tangential references: low

recency: when was this memory last accessed or confirmed?
  → Decays on a per-tier schedule (faster for hot, slower for cold)

temporal_validity: how likely is this fact to still be true?
  → A client's legal entity name: valid for years
  → A support ticket status: valid for hours
  → A pricing tier: valid until next contract renewal
  → Assign TTLs by fact category, not by memory age
```

### 3. Enforce eviction at write time, not read time

The most common mistake is storing everything and trying to filter at retrieval. Instead, enforce the forgetting policy when the memory write happens:

```python
class TieredMemory:
    def write(self, fact: MemoryEntry) -> None:
        score = self.compute_score(fact)
        if score < self.tier3_threshold:
            # Discard: not important enough to reconstruct
            return
        elif score < self.tier2_threshold:
            self.cold_store.append(self.summarize(fact))
        else:
            self.warm_store.upsert(fact, score=score)

        # Enforce hot tier cap: evict by score, not recency
        if self.hot_size() > HOT_CAP:
            lowest = min(self.hot_store, key=lambda f: f.score)
            self.hot_store.remove(lowest)
            self.warm_store.upsert(lowest, score=lowest.score)
```

### 4. Anchor governance constraints to Tier 1 explicitly

This is the bridge to S-360 (Governance Decay). Policy constraints must be pinned to hot memory, not passed as part of the general context that compaction can reach:

```python
def enforce_governance(agent, policy_constraints: list[Policy]) -> None:
    """Pin policy constraints to Tier 1 — outside compaction reach."""
    for policy in policy_constraints:
        agent.memory.hot_store.pin(
            key=f"POLICY:{policy.id}",
            value=policy.text,
            importance=10.0,   # highest possible score
            temporal_validity=policy.ttl  # expires when policy changes
        )
    # Compaction harness: NEVER touch hot_store
    # (S-360 proves compaction drops these when treated as normal context)
```

### 5. Test the forgetting policy, not just the memory system

The failure mode is getting the tier thresholds wrong. Write evals that verify correct eviction behaviour:

```python
def test_forgetting_policy():
    agent = TieredAgent()
    
    # After 90 days, client preferences should survive
    agent.memory.write(older_fact("client_prefers_senior_engineer", age=90))
    agent.memory.write(older_fact("weather_yesterday", age=1))
    
    agent.load_context()
    assert "client_prefers_senior_engineer" in agent.context
    assert "weather_yesterday" not in agent.context  # evicted
    
    # Governance policy must never be evicted
    agent.enforce_policy(no_email_external)
    agent.run_task(100_steps_with_compaction())
    agent.attempt_violation()  # must still refuse
```

## Receipt

> Verified 2026-07-31 — Pattern synthesized from: Mem0 tiered memory architecture (mem0.ai/blog, Jul 2026); Ivezaj three-tier memory pattern (ilirivezaj.com, Jun 2026); IDFS tiered forgetting research (idfs.ai, May 2026); SSGM governance framework (arXiv:2603.11768, Mar 2026); Anthropic Dreaming (May 2026, vendor-reported 6× task-completion lift); S-1221 importance-weighted starvation (handbook, 2026); S-360 Governance Decay (handbook, Chen arXiv:2606.22528, Jun 2026). Code examples are realistic Python structures based on documented Mem0 and LangMem API patterns.

## See also

- [S-1221 · Importance-Weighted Starvation](s1221-the-importance-weighted-starvation-stack-when-your-agent-has-a-full-window-but-nothing-that-matters.md) — the starvation problem this stack solves at the architecture level
- [S-360 · Governance Decay](s360-governance-decay-the-silent-safety-erosion-pattern.md) — why compaction kills policy constraints; pin to hot tier is the fix
- [S-1030 · The Forgetting Stack](s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — earlier treatment of the forgetting problem; this entry adds tier architecture and composite scoring
- [S-1043 · The Dreaming Pattern](s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — between-session consolidation as forgetting policy enforcement
- [S-681 · Context Depletion Rate Monitoring](s681-context-depletion-rate-monitoring.md) — monitoring the signal that eviction is needed
