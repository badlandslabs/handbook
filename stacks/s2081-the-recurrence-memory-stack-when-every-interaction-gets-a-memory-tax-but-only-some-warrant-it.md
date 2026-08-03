# S-2081 · The Recurrence Memory Stack

When your long-running agent burns 87% more tokens than it needs to on memory consolidation — processing chit-chat and one-off remarks with the same LLM depth as mission-critical context — the fix is not a smarter model. It is a smarter *gate*.

## Situation

Your customer-support agent has been running for 60 days. It handles 200 interactions daily. Every interaction — a greeting, a complaint, a refund request — gets stored, embedded, and fed to an LLM for memory extraction. The token bill is $3,200/month. You profile it and find that 73% of consolidation tokens process interactions that never recur: casual pleasantries, one-time questions, ephemeral context. The agent wastes more tokens on memory than on the actual conversations. RecMem (ACL 2026 Findings, Dai et al.) calls this **eager consolidation** — invoking an LLM on every interaction regardless of whether the content warrants long-term storage. The fix is recurrence-based gating: LLM consolidation only triggers when semantically similar interactions recur with sustained frequency.

## Forces

- **Every interaction pays the same LLM tax.** Eager systems invoke an LLM to process chit-chat and billing disputes with identical depth — wasteful.
- **Retrieval quality degrades under noise.** More stored memory means more irrelevant hits in retrieval — the retriever pulls casual turns alongside task-critical ones.
- **Context windows are finite but knowledge is unbounded.** Agents accumulate experience faster than they integrate it; the gap compounds silently.
- **Token cost compounds on long-running agents.** Monthly cost is a function of daily interaction volume × consolidation cost per interaction × 30 days — the math gets ugly fast.
- **Not all interactions are worth remembering.** The distinction between "someone said hello" and "the billing dispute was escalated to tier 2" is semantic, not structural — the system cannot know which is which without a gate.

## The move

**The recurrence-based memory gate.** Instead of eager LLM consolidation on every interaction, route through a three-layer architecture:

### Layer 1 — Subconscious buffer (no LLM cost)
Store incoming interactions verbatim in a lightweight buffer. Encode them with a small embedding model (e.g., a 7B sentence transformer, not the frontier model). This layer is cheap, fast, and lossy — it holds raw traces without semantic commitment.

### Layer 2 — Recurrence detector (lightweight check)
Periodically run similarity search against the buffer. Track recurrence counts: how many semantically similar interactions have appeared across a sliding window? Use embedding similarity (cosine > 0.85) as the signal. Interactions with low recurrence pass through without further processing — they are noise.

### Layer 3 — LLM consolidation gate (only on threshold)
Only invoke the LLM for episodic and semantic extraction when:
- Recurrence count exceeds a threshold (e.g., 3+ similar interactions in 7 days), AND
- The interaction cluster has not been consolidated recently (anti-duplication window)

This converts LLM consolidation from a continuous cost into a triggered, amortized cost.

### Episodic vs. semantic extraction
When Layer 3 fires, extract two representations:
- **Episodic memory** — narrative summary that preserves the sequence and intent of the interaction cluster (what happened, in what order, with what outcome)
- **Semantic memory** — compressed atomic facts stripped of narrative (entities, preferences, commitments, constraints)

Use these as dual retrieval targets: episodic for reconstructing context, semantic for fast factual lookup.

```python
from datetime import datetime, timedelta
from collections import defaultdict

class RecurrenceGate:
    def __init__(self, embedder, llm, recurrence_threshold=3, window_days=7):
        self.buffer = []          # Layer 1: subconscious
        self.recurrence = defaultdict(int)  # Layer 2: recurrence tracker
        self.consolidated = {}    # LLM-extracted memories
        self.embedder = embedder
        self.llm = llm
        self.recurrence_threshold = recurrence_threshold
        self.window_days = window_days

    def ingest(self, interaction: dict):
        """Layer 1: buffer the interaction."""
        embedding = self.embedder.encode(interaction["text"])
        entry = {
            "embedding": embedding,
            "text": interaction["text"],
            "timestamp": interaction.get("timestamp", datetime.utcnow()),
        }
        self.buffer.append(entry)
        self._update_recurrence(embedding)

    def _update_recurrence(self, embedding):
        """Layer 2: update recurrence counts for similar past interactions."""
        window = datetime.utcnow() - timedelta(days=self.window_days)
        for past in self.buffer:
            if past["timestamp"] < window:
                continue
            sim = self._cosine(embedding, past["embedding"])
            if sim > 0.85:
                key = self._cluster_key(past["embedding"])
                self.recurrence[key] += 1

    def should_consolidate(self, embedding) -> bool:
        """Layer 3: gating decision."""
        key = self._cluster_key(embedding)
        return (
            self.recurrence[key] >= self.recurrence_threshold
            and key not in self.consolidated
        )

    def consolidate(self, cluster_id: str, cluster_interactions: list):
        """Layer 3: LLM extraction — only on gate trigger."""
        # Episodic: preserve sequence and narrative
        episodic_prompt = (
            "Summarize these interactions as an episodic memory. "
            "Preserve the sequence, intent, and outcome of each turn.\n\n"
            + "\n".join(t["text"] for t in cluster_interactions)
        )
        episodic = self.llm.generate(episodic_prompt)

        # Semantic: compress to atomic facts
        semantic_prompt = (
            "Extract atomic facts from these interactions: entities, "
            "preferences, commitments, and constraints. No narrative.\n\n"
            + "\n".join(t["text"] for t in cluster_interactions)
        )
        semantic = self.llm.generate(semantic_prompt)

        self.consolidated[cluster_id] = {
            "episodic": episodic,
            "semantic": semantic,
        }
        self.consolidated[key] = datetime.utcnow()

    def _cluster_key(self, embedding) -> str:
        # Deterministic cluster ID from embedding bucket
        return str(int.from_bytes(
            bytes(embedding[:8].round().astype(int)),
            "big"
        ))

    @staticmethod
    def _cosine(a, b):
        import numpy as np
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
```

### The numbers
RecMem (ACL 2026, LoCoMo + LongMemEval-S benchmarks) shows:
- **87% reduction** in consolidation tokens vs. eager systems (Mem0, A-Mem, MemoryOS)
- **Higher accuracy** than eager baselines — less noise in retrieval means cleaner recall
- At 200 interactions/day: ~43 consolidations/month instead of 6,000; ~193K vs ~1,500K construction tokens

## Tradeoffs

- **Latency on first occurrence.** Fresh interactions sit in the buffer unconsolidated until recurrence is observed — cold start retrieval will not surface them.
- **Threshold tuning is non-trivial.** Too low → eager consolidation returns; too high → you miss transient but important patterns. Start at 3 and adjust by retrieval hit rate.
- **Embedding model quality matters.** The subconscious layer is only as good as the similarity signal. A poor embedder will miscount recurrence and corrupt the gate.
- **Episodic/semantic tension.** Episodic is high-fidelity but verbose; semantic is compact but lossy. Use both — they serve different retrieval paths.

## Receipt

> Receipt pending — 2026-08-03. Architecture drawn from RecMem (Dai et al., arXiv:2605.16045, ACL 2026 Findings). Benchmarks: LoCoMo, LongMemEval-S. Token reduction figures cited from paper's reported comparison against Mem0, A-Mem, MemoryOS. Code example is the RecMem pattern in plain Python — not run against a live system.

## See also
- [S-1002 · The Memory Consolidation Debt Stack](stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — the problem this optimizes; debt is what happens when consolidation never happens at all
- [S-1043 · The Dreaming Pattern](stacks/s1043-the-dreaming-pattern-when-your-agent-runs-a-memory-consolidation-cycle-between-sessions.md) — the consolidation *mechanism*; this entry is the *when-to-consolidate* gate that decides which sessions get dreaming cycles
- [S-02 · Context Budget](stacks/s02-context-budget.md) — token cost is a first-class concern; the recurrence gate is a specific mechanism for keeping the budget lean
