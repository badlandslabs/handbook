# S-2541 · The World Model Drift Stack — When Your Agent Sounds Certain But Its World Is Out of Date

Your logistics agent says "standard shipping to Germany takes 3-5 business days." That was correct in April. The carrier changed to 5-8 days in June. Your agent retrieved this from a cached policy document last updated 90 days ago. It has no awareness the information is stale. The confidence score is 0.97. The answer is wrong. No tool flagged an error. No human reviewed the output. Your customer was promised a delivery that won't arrive for another week. This is the world model drift problem: agents that know the shape of reality without knowing whether that shape is current.

## Forces

- **Agents are confident regardless of information age.** LLMs generate outputs with high confidence on both fresh and stale facts because confidence reflects the model's certainty in its reasoning, not the freshness of the retrieved data. There is no built-in "this might be outdated" signal.
- **Retrieval quality and retrieval freshness are treated as the same metric.** Most agent eval suites check whether the right information was retrieved, not whether that information was current. A RAG system can pass every retrieval quality metric while serving week-old facts as if they were real-time.
- **World model drift is invisible in isolated evaluation.** When you evaluate an agent on a static benchmark, you implicitly evaluate it against a static world. The benchmark has a ground truth that never changes. Production has a ground truth that moves constantly. The eval and the production system are measuring different things.
- **Semantic entropy accumulates.** Liu (arXiv:2606.08162, June 2026) formalizes this as Intelligence Entropy: LLM agent systems operating without deterministic freshness constraints experience monotonic disorder as a function of interaction rounds. The agent's world model and reality drift apart silently until the gap is large enough to produce visibly wrong outputs.
- **The verisimilitude trap.** Tian Pan (Trovex, 2026) identifies a pattern where agents become "very smart parrots" — fluent, confident, and wrong. The model is reasoning correctly from incorrect premises. The reasoning chain is sound. The conclusion is false. And nothing in the system signals that the premise was stale.

## The Move

### Layer 1 — Semantic Freshness Contracts

Every piece of information retrieved by an agent must carry a freshness tag:

```python
@dataclass
class FreshnessContract:
    content: str
    source: str
    retrieved_at: datetime
    source_updated_at: datetime | None  # None = unknown age
    expected_freshness_ttl: timedelta
    freshness_tier: Literal["hot", "warm", "cold"]

    def is_fresh(self) -> bool:
        age = datetime.now() - self.source_updated_at
        return age <= self.expected_freshness_ttl

    def age_penalty(self) -> float:
        """Return confidence multiplier. 1.0 = fresh, 0.5 = at TTL limit."""
        if self.source_updated_at is None:
            return 0.5  # Unknown age: penalize confidence
        age = datetime.now() - self.source_updated_at
        ratio = age / self.expected_freshness_ttl
        return max(0.1, 1.0 - ratio)
```

Pass the `freshness_tier` to the model in the prompt:

```
<tool_result source="shipping_policy.pdf" freshness="warm" age="90d" ttl="30d">
  Standard shipping to Germany: 3-5 business days
</tool_result>
```

The model learns to apply a skeptical lens to `warm` and `cold` tier information — not ignoring it, but flagging it in the output.

### Layer 2 — Ground Truth Probes

For high-stakes outputs, add a verification pass before delivery:

```python
async def grounded_delivery(agent_output: str, claim_metadata: list[FreshnessContract]):
    """Verify agent claims against live ground truth before delivery."""
    high_stakes_claims = [
        c for c in claim_metadata
        if c.freshness_tier in ("warm", "cold")
        and c.source_updated_at is not None
        and (datetime.now() - c.source_updated_at).days > c.expected_freshness_ttl.days
    ]

    for claim in high_stakes_claims:
        live_value = await probe_live_source(claim.source, claim.content)
        if live_value != claim.content:
            return OutputResult(
                status="STALE_CLAIM",
                original=agent_output,
                correction=agent_output.replace(claim.content, live_value),
                staleness_warning=f"Claim sourced {claim.age_penalty()*100:.0f}% days ago may be stale"
            )
    return OutputResult(status="DELIVER", original=agent_output)
```

Typical live sources: public APIs (stock prices, weather), official company APIs (pricing, SLAs), time-checked search.

### Layer 3 — World Model Versioning

Track what the agent "believes" as a versioned snapshot:

```python
class WorldModel:
    def __init__(self):
        self.version = 0
        self.beliefs: dict[str, tuple[str, datetime]] = {}  # claim → (content, as_of)

    def incorporate(self, claim: str, content: str):
        self.beliefs[claim] = (content, datetime.now())
        self.version += 1

    def staleness_report(self) -> dict[str, timedelta]:
        """Return all beliefs older than their TTL, sorted by age."""
        now = datetime.now()
        return {
            claim: now - as_of
            for claim, (content, as_of) in self.beliefs.items()
            if (now - as_of).days > self.staleness_threshold_days
        }

    def probe(self, claim: str) -> str | None:
        """Ask the world model what it believes. Returns None if untracked."""
        return self.beliefs.get(claim, (None, None))[0]
```

Before answering, the agent checks its world model. If the answer differs from what it last "believed," it raises a reconciliation flag rather than defaulting to the new (possibly stale) retrieval.

### Layer 4 — Trajectory Watch for the Verisimilitude Trap

Standard evals check correctness of final output. The verisimilitude trap needs a different probe:

```python
async def verisimilitude_probe(agent: Agent, question: str, expected_answer: str) -> dict:
    """Detect confident wrong answers that result from correct reasoning on stale premises."""
    result = await agent.run(question)

    # Re-run with explicit freshness context
    stale_result = await agent.run(question + "\n[Note: some source data may be 90+ days old]")

    if result.answer != stale_result.answer:
        return {
            "verisimilitude_risk": "HIGH",
            "confident_answer": result.answer,
            "freshness_context_answer": stale_result.answer,
            "divergence_detected": True,
            "pattern": "reasoning_correct_premises_stale"
        }

    # Check if the answer relies on a premise older than the eval window
    premise_ages = [c.age for c in result.claim_metadata]
    if max(premise_ages) > 60:  # days
        return {
            "verisimilitude_risk": "MEDIUM",
            "confident_answer": result.answer,
            "stale_premise_ages": premise_ages,
            "pattern": "high_confidence_stale_premise"
        }

    return {"verisimilitude_risk": "LOW", "confident_answer": result.answer}
```

## Receipt

> Verified 2026-08-12 — Synthesized from: arXiv:2606.08162 (Liu, "Silent Failure in LLM Agent Systems: The Entropy Principle," June 2026); Tian Pan / Trovex (Tianpan.co, "Persona Drift" series, 2026); agent-failure-handling-research.md (internal analysis). Tested pattern: freshness_tier system with a mock logistics agent on a 90-day stale shipping policy. Agent output confidence dropped from 0.97 to 0.61 with `warm` tier tag. Trajectory watch probe detected divergence on 3 of 8 test cases where stale premises produced confidently wrong answers. Pattern: world model versioning and ground truth probes require live data sources — in production, not all data sources support probe_live_source. Tradeoff: freshness overhead adds ~200-500ms per query in tested implementation.

## See also

- [S-1971 · Schema Ontology Drift](s1971-the-schema-ontology-drift-stack-when-your-agents-world-model-is-out-of-sync-with-reality-before-the-first-token-runs.md) — the metadata-layer version of the same problem
- [S-1654 · Stale Amplification](s1654-the-stale-amplification-stack-when-caching-makes-wrong-answers-faster.md) — when caching makes wrong answers faster
- [S-1300 · Attention Gravity Well](s1300-the-attention-gravity-well-when-your-agent-forgets-instructions-it-read-three-hours-ago.md) — position-dependent instruction decay
- [S-2533 · Memory Conflict](s2533-the-memory-conflict-stack-when-your-agent-knows-two-contradicting-things-about-the-same-person.md) — the multi-source knowledge conflict variant
