# S-765 · Memory Staleness: When Your Agent's Cache Develops False Beliefs

An agent successfully works around a broken API for three weeks. It learns to multiply timestamps by 1000, retry on certain error codes, skip a flaky endpoint. Then the API is fixed. The agent's workaround persists — because the fix generated no invalidation signal. The agent now corrupts data with double-conversions, and there's no error, no log, no crash. Just wrong behavior, confidently executed.

## Forces

- Agent memory is a **cache of derived state**, not ground truth — it's built from observations and inferences, not from authoritative sources
- **Workarounds become beliefs.** When an agent successfully compensates for a broken behavior, it encodes that compensation in memory. The memory doesn't distinguish "I observed this" from "this is how the world works"
- **Software fixes don't broadcast invalidation events.** A bug fix, a config change, a new deployment, a dependency upgrade — none of these signal to the agent's memory layer that its learned rules are now stale
- **Implicit conflict is genuinely hard.** The STALE benchmark (May 2026) tests exactly this: when new evidence *implies* an old belief is wrong without *stating* it. Across 400 expert-validated conflict scenarios, even frontier models resolve these correctly ~55% of the time — a coin flip on whether your agent notices its memory has expired
- **Traditional cache invalidation doesn't translate directly.** A model's weights and context aren't a database. There's no TTL, no version key, no cache tag. The memory lives in embeddings and weights; you can't `DELETE FROM memory WHERE cause = 'timestamp_bug'`

## The move

Treat **every code change as a potential memory-invalidation event**, and build the invalidation path before you need it. Three interlocking mechanisms:

### 1. Provenance-tagged memory entries

Every memory write captures the conditions under which it was formed, not just the content:

```json
{
  "content": "Multiply timestamp fields by 1000 before sending to downstream",
  "provenance": {
    "trigger": "API returned timestamps in seconds instead of milliseconds",
    "first_observed": "2026-04-01",
    "artifact_id": "api_client.py:142",
    "confidence": "derived",
    "tags": ["workaround", "timestamp", "api_contract"]
  }
}
```

This distinguishes a workaround (confidence: derived, should be invalidated on fix) from a fact (confidence: verified, stable). At retrieval time, the agent sees which memories are derived — and acts accordingly.

### 2. Event-triggered invalidation

Map your engineering events to memory layers:

| Event | Invalidates | Action |
|-------|-----------|--------|
| Bug fix merged | Memories tagged with the bug's trigger | Re-validate before applying |
| API contract change | Memories about that endpoint | Treat as new environment |
| Config/infra deployment | Memories dependent on that config | Full memory re-check |
| Version upgrade | All workaround-tagged memories | Graduated re-validation |

```python
# During deployment pipeline
def on_bug_fix_merged(bug_id: str, fixed_components: list[str]):
    for component in fixed_components:
        # Mark memories for re-validation, don't delete
        memory_store.flag_for_revalidation(
            tags=["workaround"],
            related_to=component
        )
    # Next agent invocation runs re-validation loop
```

The key: **flag for re-validation, don't auto-delete.** Deletion loses information that might be right in a different context. Re-validation lets the agent confirm or update.

### 3. Proactive re-validation at retrieval

Before acting on a high-confidence derived memory, run a re-check:

```python
def retrieve_with_revalidation(memory, context):
    if memory.provenance.confidence == "derived":
        # Re-verify the triggering condition is still true
        still_holds = verify_condition(
            condition=memory.provenance.trigger,
            current_state=context.current_environment
        )
        if not still_holds:
            memory.status = "invalidated"
            return None  # Agent must re-derive
    return memory
```

This is the self-healing circuit breaker for memory. It's not free — it costs a verification call — but it prevents the silent corruption case where the agent confidently does the wrong thing with no error signal.

### The minimal viable version

If you can't implement all three, start with this: **tag every workaround memory, and run a re-check on startup after deployments.** Even this much catches the common case where an agent resumes after a deploy and applies pre-fix logic to a post-fix world.

## Receipt

> Verified 2026-07-07 — Research synthesis from: STALE benchmark (May 2026, implicit conflict resolution ~55% accuracy), MemGym (May 2026, long-horizon memory evaluation), Tian Pan "Agent That Memorized Your Bug" (May 2026, production case study), Anna Jey "Long-Term Memory That Does Not Rot" (Towards AI, May 2026). Key benchmark figures are from cited sources; the production case is from the Tian Pan post. Composite scoring: Urgency 8, Gap 9 (S-09 covers memory types/tiers, not staleness), Specificity 9, Timeliness 9 (May 2026 benchmarks make this urgent NOW), Density 8.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — Episodic, semantic, and procedural memory types; the foundation this builds on
- [S-21 · Context Compaction](s21-context-compaction.md) — How context eviction interacts with memory; constraint pinning is the governance analog of this problem
- [S-760 · Agent Flight Recorder](s760-agent-flight-recorder-the-tamper-evident-audit-log-for-autonomous-systems.md) — Provenance tracking at the system level; applies to memory provenance too
