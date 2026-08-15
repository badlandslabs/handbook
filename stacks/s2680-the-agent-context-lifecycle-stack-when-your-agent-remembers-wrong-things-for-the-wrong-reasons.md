# [S-2680] · The Agent Context Lifecycle Stack

When your agent gives confident wrong answers because it remembered the right things at the wrong time, in the wrong scope, with the wrong identity.

## Situation

Your customer-support agent has been running for three months. Last week it told a customer their order was shipped. It wasn't — the agent was reading from a memory entry written by a different agent instance six weeks ago, before the order was cancelled. The agent wasn't hallucinating. It was confidently retrieving a stale, scope-bleeding fact that was accurate once but should have been archived, adjusted, or scoped away.

This is not a memory storage problem. It is a **context lifecycle failure** — the agent never decided *when* to remember, *how long* to keep the fact, *who* it belonged to, or *when* to forget it.

## Forces

- Agents get memory right at the write moment, then treat retrieval as read-only — no lifecycle discipline between write and read
- Every agent team independently decides what to store, how long to keep it, and when to compact it — producing a fleet of agents with inconsistent memory hygiene
- Long-running agents accumulate context without any pruning or re-architecting — the context window grows, the agent gets slower, and the quality degrades silently
- Multi-agent systems face identity fragmentation: the same entity appears as "Sarah," "Sarah Chen," and "SC" across different agents' memories, splitting history and producing contradictory answers
- Cross-session amnesia: agents that *should* remember from last week don't, because there's no mechanism for surfacing episodic knowledge at the right moment in the right scope
- Retrieval is often on the critical path — every turn blocks on a synchronous round-trip to the memory store, adding latency and cost at inference time

## The move

Treat agent memory as a **lifecycle problem**, not a storage problem. The arXiv:2607.21503v1 (Maximem, July 2026) framework defines five lifecycle primitives that must all be present for production-grade context management:

### The Five Primitives

**1. Architect** — Before storing anything, decide the memory shape: what categories exist, what extraction methods apply, what storage locations to use, what the retention policy is, and how retrieval and compaction work. Most agent teams skip this and just dump embeddings into a vector store. Architects fail by over-engineering schemas upfront or under-engineering and letting memory become a pile of undifferentiated chunks.

**2. Author** — Extract, structure, and write facts into memory. Authoring is not just "store the chat summary." It means deciding which facts are worth storing, under which entity, with what provenance. A failure here produces identity fragmentation: the same real-world entity gets authored under multiple names and never gets resolved into one canonical record.

**3. Augment** — Add to existing memories without overwriting them. New facts should update, not replace. Augmentation failure leads to context staleness: the agent acts on a fact that was true last month but has since changed. The fix is versioning or timestamped overlays, not blind appends.

**4. Adjust** — Revise or compact memories over time. This is the most-neglected primitive. Without adjustment, memory grows unbounded, retrieval degrades, and the agent's effective context window shrinks. Techniques: summarization-based compaction, forgetful embedding updates, episodic consolidation on a schedule. The OpenClaw Heartbeat system (2026) lets agents autonomously summarize and prune their own memories on a cron — the agent wakes up, reviews its memory state, and optimizes it without human intervention.

**5. Archive** — Move old or irrelevant memories out of the active context window, not delete them. Archive enables future retrieval when a long-running conversation requires historical grounding. Archive without a retrieval path is the same as deletion.

### Scope Isolation — The Missing Boundary

Scope bleeding is the failure where memory from one context leaks into another. One user's preferences surface in another user's session. The agent misses organizational context entirely. The fix is **per-agent memory isolation at the infrastructure level** — each agent instance maintains its own isolated memory namespace. In multi-tenant deployments, there is no cross-contamination between users, departments, or organizations. This must be enforced by the infrastructure layer, not by prompting.

### Cross-Session Persistence

Agents need episodic memory that survives individual sessions. Semantic Memory stores facts about the world. Episodic Memory stores facts about the user — their preferences, past frustrations, and recurring issues. Without episodic surfacing, every new session requires the user to re-establish context they've already provided. The agent repeats itself. The user repeats themselves.

### Retrieval Off the Critical Path

Synchronous retrieval on every turn adds latency and cost to every inference. Production patterns:
- Prefetch likely memories on session start (amortize the round-trip)
- Embedding-asynchronously: compute embeddings in the background, write to the store, don't block the next token
- Cache frequently-retrieved facts in the agent's working memory, refresh on a schedule

```python
# Minimal heartbeat-driven memory lifecycle
from datetime import datetime, timedelta
import json

class AgentMemoryLifecycle:
    def __init__(self, memory_store, heartbeat_interval_hours=6):
        self.store = memory_store
        self.interval = timedelta(hours=heartbeat_interval_hours)
        self.last_heartbeat = None

    def should_heartbeat(self):
        if self.last_heartbeat is None:
            return True
        return datetime.now() - self.last_heartbeat >= self.interval

    def heartbeat(self, agent_id: str):
        """
        Autonomous memory maintenance cycle:
        1. Compact: summarize chunks older than 30 days
        2. Prune: remove entries flagged as stale (TTL expired)
        3. Resolve: merge duplicate entity names (identity fragmentation fix)
        4. Archive: move compacted/pruned entries to cold storage
        """
        # Step 1: compact old episodic entries
        old_entries = self.store.query(
            agent_id=agent_id,
            type="episodic",
            age_days_gt=30,
            archived=False
        )
        for entry in old_entries:
            summary = self._summarize(entry["content"])
            self.store.update(entry["id"], {
                "content": summary,
                "compacted": True,
                "original_age_days": entry["age_days"]
            })

        # Step 2: prune stale semantic entries (TTL expired)
        self.store.delete_where(
            agent_id=agent_id,
            type="semantic",
            ttl_expired=True
        )

        # Step 3: resolve identity fragmentation
        # Group by entity fingerprint, merge if > 3 aliases exist
        fragments = self.store.get_identity_fragments(agent_id=agent_id)
        for fragment_group in fragments:
            if fragment_group["alias_count"] > 3:
                canonical = self.store.merge_aliases(
                    fragment_group["aliases"],
                    agent_id=agent_id
                )
                # Invalidate conflicting embeddings, re-embed the canonical
                self.store.invalidate_embeddings(fragment_group["aliases"])
                self.store.reindex(canonical)

        # Step 4: archive compacted/pruned entries
        self.store.archive_where(
            agent_id=agent_id,
            type__in=["episodic", "semantic"],
            compacted_or_pruned=True
        )

        self.last_heartbeat = datetime.now()

    def _summarize(self, content: str) -> str:
        # In production: call an LLM with a compacting prompt
        # or use a local SLM for speed/cost
        return f"[COMPACTED from {len(content)} chars] {content[:200]}..."
```

## Receipt
> Verified 2026-08-15 — Pattern distilled from arXiv:2607.21503v1 (Gaurav Dadhich, Maximem, 23 Jul 2026). The five primitives (architect, author, augment, adjust, archive) provide the canonical taxonomy for context lifecycle management. Scope bleeding, identity fragmentation, cross-session amnesia, and retrieval-on-critical-path are documented as the four primary failure modes. OpenClaw Heartbeat pattern confirmed as a production implementation of the adjust primitive. No existing handbook entry covers the lifecycle framing — S-827 covers multi-agent consistency (a downstream symptom of scope bleeding), S-02 covers token budgeting (a storage constraint, not a lifecycle discipline). The identity fragmentation problem connects to S-827's canonical entity registry as a partial solution, but S-827 treats it as a multi-agent consistency problem while S-2680 frames it as a memory authoring defect.

## See also
- [S-827 · The Context Sprawl Pattern](s827-the-context-sprawl-pattern-when-agents-forgot-to-agree.md) — downstream symptom of scope bleeding and identity fragmentation
- [S-02 · Context Budget](s02-context-budget.md) — storage constraint, not lifecycle discipline; context budget is a prerequisite, not a substitute for lifecycle management
- [S-646 · Agent Drift in Multi-Agent Systems](s646-the-agent-drift-in-multi-agent-systems.md) — behavioral drift over time; the lifecycle stack addresses the memory substrate that drift detection depends on
