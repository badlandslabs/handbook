# S-1043 · The Dreaming Pattern — When Your Agent Runs a Memory Consolidation Cycle Between Sessions

Your agent works perfectly within a session. Between sessions, it forgets what it learned. You stuff more context in, then more, until the token bill doubles and the agent starts forgetting the oldest facts. The real fix is not more context — it is a consolidation cycle that runs between sessions, distilling raw experience into durable, retrievable memory. Anthropic shipped this as "Dreaming" for Claude Managed Agents on May 6, 2026. Harvey reported a 6× task-completion lift after enabling it (vendor-reported). The pattern is now field-proven.

## Forces

- **Raw session data is not memory.** Storing every turn verbatim creates noise that drowns signal — the retriever pulls irrelevant old turns and the agent wastes tokens re-reading them.
- **Memory write-path and read-path must be decoupled.** Writing every turn directly to semantic storage at inference time adds latency, increases cost, and produces duplicate or contradictory entries. Consolidation decouples this into a batch process.
- **Forgetting is as important as remembering.** Without a consolidation pass that prunes, merges, and elevates facts, memory stores grow unbounded and retrieval quality degrades.
- **Long-context is now a competitor to consolidation for small fleets.** Claude Opus 4.7's 1M-token flat-priced context undercuts Mem0 + Pinecone at under ~500K accumulated tokens. Consolidation is the right investment above that threshold.
- **Vendor-default memory models are now API-shaped.** Anthropic uses filesystem-mounted `/mnt/memory/`. Google uses identity-scoped Memory Bank. OpenAI uses vector-store via `file_search`. Each implies a different consolidation strategy.

## The move

Design the consolidation pipeline as a first-class architectural concern, separate from the inference loop.

### 1. Capture session transcripts in raw form

During active sessions, write every turn (user input, agent reasoning, tool calls, final output) to an immutable session log. Do not attempt semantic processing at write time. The log is append-only and cheap to store.

```
session_store/
  2026-07-13/
    session_001.log   # raw turn-by-turn transcript
    session_002.log
```

### 2. Trigger consolidation on session boundary

After a session ends (or on a schedule for long-running sessions), invoke the consolidation pipeline. The trigger must be event-driven, not polling — tie it to session-close events from your orchestrator.

```
ConsolidationTrigger(session_id) → consolidation_job.enqueue()
```

### 3. Run the three-stage consolidation pass

The pipeline operates in three stages, each increasingly expensive:

**Stage 1 — Episodic extraction.** Read the session log. Extract discrete facts: what the user asked, what the agent did, what the outcome was, what the user corrected. Output as structured episodic records. Discard verbatim turns.

```
# Pseudo: episodic extraction
extracted = llm.extract_episodes(
    transcript=session_log,
    schema={"event": str, "action": str, "outcome": str, "correction": str}
)
```

**Stage 2 — Semantic upsert.** For each extracted episodic fact, check for existing semantic entries. Merge duplicates, update stale facts, discard contradictions (flag for human review instead of silent overwrite). Write merged results to the semantic memory store.

```
# Pseudo: semantic upsert with deduplication
for episode in extracted:
    existing = semantic_retriever.search(episode.key_fact, top_k=3)
    if existing and semantic_overlap(episode, existing):
        episode = merge(episode, existing)
    else:
        semantic_store.upsert(episode)
```

**Stage 3 — Procedural abstraction (optional, highest cost).** For recurring action sequences across multiple sessions, abstract a reusable procedure. E.g., "every time the user asks for a report, the agent queries X, aggregates Y, formats Z." Store this as a procedural skill or system-prompt fragment.

### 4. Validate consolidation quality before promoting

Before promoted memories enter the active retrieval pool, run a recall check: inject the new semantic entries into a probe prompt and verify the agent can retrieve and use them correctly. If recall fails, the entry was too abstract or too specific — revise the extraction prompt.

### 5. Tune consolidation frequency by memory type

| Memory type | Consolidation frequency | Reason |
|-------------|------------------------|--------|
| Episodic | Every session | Preserves unique events; no aggregation needed |
| Semantic | Daily or per-N-sessions | Patterns emerge from volume; too-frequent is wasteful |
| Procedural | Weekly | Requires cross-session pattern detection; expensive |

### The dreaming control plane

```
┌─────────────────────────────────────┐
│           SESSION LOOP              │
│  (agent inference + raw log write) │
└────────────────┬────────────────────┘
                 │ session_close
                 ▼
┌─────────────────────────────────────┐
│     CONSOLIDATION TRIGGER           │
│  (event-driven, not scheduled)      │
└────────────────┬────────────────────┘
                 │
     ┌───────────┼───────────┐
     ▼           ▼           ▼
  Episodic   Semantic   Procedural
  extract    upsert     abstract
     │           │           │
     └───────────┼───────────┘
                 ▼
         Recall validation
                 │
                 ▼
       Active retrieval pool
```

## When to build vs. buy

- **Build** when you need cross-vendor memory portability or fine-grained control over consolidation logic.
- **Use Mem0** for cross-vendor memory (41K GitHub stars, integrates with Anthropic SDK, OpenAI Agents SDK, Google ADK).
- **Use Anthropic Dreaming** (Claude Managed Agents) when you are fully on Anthropic and want zero-ops consolidation.
- **Use Google Memory Bank** when running on Vertex AI with Gemini agents.
- **Use long-context as memory** when accumulated history is under ~500K tokens — flat per-request pricing makes consolidation unnecessary overhead.

## Common failure modes

- **Consolidation blocking the session boundary.** If consolidation runs synchronously before the next session can start, you introduce latency on session resume. Always run consolidation asynchronously.
- **Over-consolidation.** Extracting too many semantic facts from a single session floods the store with noise. Apply a salience filter — only promote facts that were verified, corrected, or explicitly important.
- **Stale consolidation prompts.** The extraction and merge prompts drift as your domain changes. Re-run eval on historical sessions quarterly.
- **Missing the right-to-be-forgotten.** Consolidation must also delete or redact on user request — append-only logs need a parallel deletion log processed during consolidation.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — the three-tier storage model that dreaming populates
- [S-999 · The Orchestration and Memory Stack](s999-the-orchestration-and-memory-stack-when-your-agent-needs-to-know-what-it-already-knew.md) — orchestration patterns that depend on durable memory
- [S-100 · Agentic RAG](s100-agentic-rag.md) — retrieval patterns that consume consolidated memory
- [S-1024 · The Kappa Deflation Problem](s1024-the-kappa-deflation-problem-when-your-llm-judge-reports-85-but-has.md) — eval for consolidation quality
