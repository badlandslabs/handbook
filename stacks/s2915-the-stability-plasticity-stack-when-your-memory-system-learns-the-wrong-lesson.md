# S-2915 · The Stability-Plasticity Stack: When Your Memory System Learns the Wrong Lesson

You gave your agent a memory system so it could learn from past interactions. Six months later, it has "learned" that every user prefers brief responses (one summarization stripped the word "comprehensive" from a preference), that the Q3 report is from 2024 (repeated summarization degraded the date), and that it should never ask follow-up questions (a single anomalous session was consolidated as "standard behavior"). The memory system is working. It is also quietly distorting everything it touches. This is the stability-plasticity dilemma: every design choice that makes memory more adaptive makes it more dangerous.

## Forces

- **Memory consolidation is lossy by design.** Every summarization step discards nuance. Do it ten times and "user prefers detailed explanations with examples when the topic is complex" becomes "user prefers brief responses." The model can't tell the difference between useful compression and corruption.
- **More plasticity = more drift risk.** Agents with autonomous memory write/update/delete (Mem0, Memory-R1) adapt faster but accumulate drift faster. Agents with rigid write-once memory stay accurate but become stale. There's no free lunch.
- **Read and write failures are asymmetric.** A memory that fails to retrieve correct facts produces wrong output immediately. A memory that stores corrupted facts produces wrong output consistently, every time, until manually corrected — and you may not notice.
- **The SSGM insight: memory integrity > retrieval accuracy.** Static RAG errors are isolated to one turn. Evolving memory errors become permanent ground truth. One hallucinated fact written to memory becomes a cited reference for every future session.

## The Move

**Govern memory at two layers: architecture and policy.**

### Architecture: Source + Summary Separation

Never summarize away from raw entries. Keep two tiers:

```
Raw Event Store (append-only)
  └── verbatim: "user said: 'I want comprehensive reports with data tables'"
  └── verbatim: "user said: 'make it concise'"
  └── verbatim: "user said: 'detailed is better, really'"
  └── timestamp, session_id

Consolidated Summary (mutable, versioned)
  └── current: "User prefers detailed, data-driven reports"
  └── v3, last_updated: 2026-08-15
  └── v2, last_updated: 2026-06-01  ← can audit drift between versions
  └── v1, last_updated: 2026-03-01  ← original signal preserved
```

Reconcile from raw, not from summary. When raw and summary conflict, raw wins. Summary is a view, not the source.

### Policy: Staleness Gates and Drift Detection

Define explicit consolidation policies per memory category:

| Memory Type | Consolidation Allowed | Max Summarization Passes | Drift Threshold |
|---|---|---|---|
| User preferences | Yes | 3 | Flag if summary changes valence (positive→negative) |
| Factual project data | No (mark immutable) | — | Any change triggers re-verification |
| Session summaries | Yes | 5 | Flag if key entities disappear |
| Procedural "how we do X" | Yes, with version | 3 | Flag if procedure contradicts raw event |

### Policy: The Immutability Signal

Tag memory entries at write time:

- **`persistent=true`**: Consolidatable. User preferences, project context.
- **`immutable=true`**: Never summarized. Dates, numbers, names, decisions.
- **`ephemeral=true`**: Session-only, not stored. Scratch calculations, mid-task notes.

Immutability is a flag the retrieval layer respects, not a hard constraint — an admin can override, but it requires explicit action and audit log entry.

### Policy: Drift Detection

Run a lightweight contradiction check at consolidation time:

```
Before writing new summary version:
  1. Retrieve previous summary version
  2. Generate: "Does the new summary contradict the previous one?"
  3. If contradiction detected → flag for human review or preserve both with annotation
  4. If contradiction propagates to raw event → reject consolidation, keep raw
```

From SSGM (Lam et al., arXiv:2603.11768, May 2026): "Through formal analysis, we show how SSGM can help prevent semantic drift where knowledge degrades through iterative summarization."

### Architecture: Checkpoint + Replay on Memory Corruption

When corruption is detected, replay from raw:

```
Corruption detected in "user_preference" memory
  → Retrieve all raw events for user_preference
  → Discard current summary
  → Re-consolidate from raw (with stricter pass limit)
  → Write new summary version with "reconstructed=true" flag
  → Notify: "Memory integrity check ran; preference summary rebuilt from raw events"
```

## Evidence

- **Research paper:** SSGM: Governing Evolving Memory in LLM Agents — identifies semantic drift, memory poisoning, and conflict/hallucination as the three critical failure points unique to evolving memory. Proposes separation of execution from governance. — [arXiv:2603.11768](https://arxiv.org/abs/2603.11768)

- **Production case (Letta agents, 2025):** Letta agents running on a simple file-based conversation history achieved 74.0% accuracy on LoCoMo — better than many specialized memory systems. This suggests the baseline is raw storage; complexity added above it introduces drift risk. — [Letta benchmark report, August 2025](https://agentstack.ghost.io/state-of-ai-agent-memory-2026/)

- **Framework:** Mem0 (63,667 stars) and AtomMem introduce atomic consolidation mechanisms, but practitioners in production report that autonomous write/delete access without staleness policies causes persistent drift in user-facing agents. The recommended mitigation: immutable tags on factual entries, consolidation policies per category. — [Mem0 GitHub](https://github.com/mem0ai/mem0), cited in [Letta "State of AI Agent Memory 2026"](https://agentstack.ghost.io/state-of-ai-agent-memory-2026/)

## Gotchas

- **Trusting the summary as ground truth.** Most teams debug a wrong agent response by checking what the agent "remembered" — which is the summary, not the raw events. Start debugging from raw.
- **Setting consolidation too aggressive.** "Compress everything older than 7 days" is a drift accelerator on high-frequency interactions. Use per-category limits, not global ones.
- **Missing the contamination path.** If a single malicious prompt injection reaches the memory write path, it can corrupt the raw store, not just the summary. Treat memory write as a tool call with dangerous permissions — validate before write.
- **Treating memory integrity as a solved problem.** BEAM (2025) and LongMemEval (ICLR 2025) are benchmarks, not solutions. They measure the problem; you still have to design around it.
