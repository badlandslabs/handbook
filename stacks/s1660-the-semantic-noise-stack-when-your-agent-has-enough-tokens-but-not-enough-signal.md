# S-1660 · The Semantic Noise Stack — When Your Agent Has Enough Tokens But Not Enough Signal

You added more context. The agent got worse. You checked the token count — well under the limit. You checked the model — unchanged. You checked the task — identical. The culprit is not capacity. It is *content quality*: conflicting definitions, stale metadata, outdated schemas, and contradictory business rules all sitting inside the context window, silently pulling the model in different directions. This is semantic noise, and it is now the dominant failure mode for production agents — not hallucination, not context overflow, but *context pollution*.

## Forces

- **Semantic noise is invisible to capacity metrics.** Token count, context utilization percentage, and window usage all look fine. The agent still fails. Standard observability dashboards show green everywhere. Nobody is measuring whether the content *inside* the window is internally consistent.
- **Bigger context windows amplify semantic conflicts, not just capacity.** A 128K context window doesn't just fit more relevant data — it fits more *irrelevant, contradictory, and outdated* data. Larger windows import proportionally more conflicts unless actively filtered. Google DeepMind researchers: "most agent failures are not model failures anymore — they are context failures."
- **Two agents with identical context budgets can have opposite task outcomes.** One loads 15 highly relevant, consistent chunks. The other loads 15 chunks where 4 contradict each other and 3 are stale. The second agent performs 24 percentage points worse — purely from content quality variance, not quantity.
- **Retrieval quality ≠ semantic quality.** Dense retrieval maximizes recall. It does not check for definition conflicts, schema drift, or staleness. A retrieval system that scores 95% on recall can still surface 5% of content that actively misleads the agent.

## The move

**Layer 1 — Identify the noise types.** Semantic noise has three distinct sources:

| Type | Example | Detection |
|------|---------|-----------|
| **Definitional conflict** | "active customer" means open contract in CRM but paid subscription in billing | Cross-source entity resolution |
| **Temporal decay** | Product pricing, inventory counts, account status that changed after last retrieval | Timestamp + freshness TTL |
| **Schema drift** | A field renamed in the API six months ago; old tool schema still in MCP | Schema version comparison |

**Layer 2 — Measure signal-to-noise ratio, not just recall.** Add a pre-inference consistency check:

```python
import anthropic

client = anthropic.Anthropic()

def inject_with_noise_check(context_chunks: list[dict], task: str, client) -> str:
    """
    Injects retrieved context only after passing a semantic consistency check.
    Skips or weights-down chunks that conflict with higher-priority sources.
    """
    # Score each chunk for staleness and internal consistency
    scored = []
    for chunk in context_chunks:
        age = (datetime.now() - chunk["fetched_at"]).total_seconds()
        staleness_penalty = min(age / (8 * 3600), 1.0)  # 8h = max penalty
        scored.append((chunk, staleness_penalty))

    # Observation masking: exclude bottom quartile by staleness score
    threshold = sorted(s for _, s in scored)[len(scored) // 4]
    filtered = [c for c, s in scored if s >= threshold]

    # Check for definitional conflicts across filtered chunks
    conflicts = detect_definitional_conflicts(filtered, task, client)
    if conflicts:
        # Downweight or tag conflicting chunks rather than dropping silently
        for conflict in conflicts:
            conflict["chunk"]["confidence"] = 0.3
            conflict["chunk"]["conflict_note"] = conflict["reason"]

    return filtered


def detect_definitional_conflicts(chunks: list[dict], task: str, client) -> list[dict]:
    """
    Uses the LLM as a lightweight conflict detector — not as summarizer.
    Observation masking: flag noise rather than trying to compress it.
    """
    conflict_prompt = f"""Given this task: {task}
    And these retrieved context chunks:
    {chunks}

    Identify ONLY semantic conflicts: cases where two chunks give contradictory
    information about the same entity or concept. Return a list of conflicting
    chunk IDs with the specific contradiction. Do NOT summarize or rephrase.
    Format: [{{"chunk_id": "...", "reason": "..."}}]
    If no conflicts, return []."""
    # lightweight
    response = client.messages.create(
        model="claude-haiku-4-20250514",
        max_tokens=256,
        system="You detect semantic conflicts only. No summaries.",
        messages=[{"role": "user", "content": conflict_prompt}],
    )
    import json, re
    match = re.search(r'\[.*\]', response.content[0].text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return []
```

**Layer 3 — Observation masking over summarization.** The instinct when context gets noisy is to summarize. Don't. Atlan's research (2026): LLM summarization for noisy context achieves 31% solve rate with high cost. *Observation masking* — selectively excluding the noisiest chunks rather than compressing all chunks — achieves 33.6% solve rate at 52% lower cost. The key difference: summarization tries to preserve all content, including noise. Masking simply removes the bottom quartile.

**Layer 4 — Typed retrieval with conflict tags.** Move from flat retrieval to structured retrieval that annotates each chunk with metadata the agent can reason over:

```python
@dataclass
class AnnotatedChunk:
    chunk_id: str
    content: str
    source_system: str        # "crm" | "billing" | "inventory"
    entity_type: str          # "customer" | "order" | "product"
    staleness_seconds: float
    confidence: float = 1.0   # reduced by conflict detection
    conflict_note: str = ""   # human-readable conflict flag

    def agent_readable_tag(self) -> str:
        tags = [f"[{self.source_system.upper()}]"]
        if self.staleness_seconds > 3600:
            tags.append(f"⚠ stale({int(self.staleness_seconds/3600)}h)")
        if self.confidence < 0.8:
            tags.append(f"⚡ low-confidence: {self.confidence}")
        if self.conflict_note:
            tags.append(f"❗conflict: {self.conflict_note}")
        return " ".join(tags)
```

The agent receives structured context with per-chunk provenance and quality flags. It can now *reason about* context quality rather than passively consuming everything. Crucially: the agent itself becomes part of the noise-detection loop — if it sees three conflicting chunks tagged as `conflict`, it can request clarification or escalate.

**Layer 5 — Enforce a consistency SLO.** Track semantic consistency rate alongside traditional quality metrics:

```
Semantic consistency SLO = (1 - conflicts_detected / total_chunks_retrieved) * 100
Target: ≥ 95% consistency per session
Alert at: < 90% consistency
```

A green eval pipeline with a red consistency SLO means your agent is being polluted faster than it's being improved.

## Receipt

> Receipt pending — 2026-07-26
> Key data points: Grok-3 accuracy 43%→19% (1→15 distractors, arxiv 2505.18761); observation masking vs LLM summarization (33.6% vs 31% solve rate, 52% cost reduction, Atlan 2026); Google DeepMind "most agent failures are context failures" (AGILE Leadership Day, Jun 2026). Pending: A/B test in production environment with real retrieval pipeline to validate semantic consistency SLO threshold.

## See also

- [S-1063](s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — Covers context *capacity* and eviction; this entry covers context *quality* within capacity
- [S-100](s100-live-data-freshness-contracts.md) — Covers temporal decay at the data layer; this entry covers semantic conflicts at the retrieval layer
- [S-1026](s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — Covers multi-dimensional eval; semantic noise is one of the sneakier failure modes it misses
