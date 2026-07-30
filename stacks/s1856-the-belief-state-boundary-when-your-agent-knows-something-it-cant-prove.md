# S-1856 · The Belief State Boundary

When your agent reaches a conclusion, acts on it, and passes that conclusion downstream — without ever flagging it as unverified.

## Forces

- Agents naturally accumulate working beliefs as they process context — this is reasoning
- Context windows are finite; agents must treat some information as durable fact rather than re-checking
- Downstream agents, tools, and humans all assume incoming facts are verified
- No structural boundary exists in most frameworks between "I inferred this" and "I confirmed this"
- The cost of verification is often higher than the perceived risk, so agents skip it

## The move

**Separate three epistemic tiers explicitly in your agent's state model:**

1. **Verified facts** — retrieved from authoritative sources with citation. These can be passed downstream without flag.
2. **Working inferences** — the agent's reasoned conclusions from context. These must be tagged as `inference: {confidence, source_span, verification_required: bool}`.
3. **Assumptions** — values the agent filled in when data was absent. These must be surfaced to the caller, not propagated silently.

**The key structural change:** add an **epistemic checkpoint** before every cross-boundary handoff (tool call, agent handoff, response to user). The checkpoint walks the agent's belief state and flags any working inference or assumption that would alter the output if wrong.

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class EpistemicEntry:
    tier: Literal["verified", "inference", "assumption"]
    content: str
    confidence: float  # 0.0–1.0
    source_span: str | None = None  # where in context this came from
    downstream_impact: bool = False  # would wrongness break downstream?

@dataclass
class BeliefState:
    """Tracks what the agent 'knows' across the run."""
    entries: list[EpistemicEntry] = field(default_factory=list)

    def add(self, tier: str, content: str, confidence: float,
            source_span: str | None = None):
        entry = EpistemicEntry(
            tier=tier,
            content=content,
            confidence=confidence,
            source_span=source_span,
        )
        self.entries.append(entry)
        return entry

    def checkpoint(self, threshold: float = 0.85) -> list[EpistemicEntry]:
        """
        Run before every cross-boundary handoff.
        Returns entries that need verification or surfacing.
        """
        blockers = []
        for e in self.entries:
            if e.tier == "assumption":
                blockers.append(e)
            elif e.tier == "inference" and e.confidence < threshold:
                blockers.append(e)
        return blockers

    def format_for_downstream(self) -> dict:
        """Format belief state for safe handoff."""
        verified = [e for e in self.entries if e.tier == "verified"]
        working = [e for e in self.entries if e.tier in ("inference", "assumption")]

        return {
            "verified_facts": [e.content for e in verified],
            "working_beliefs": [
                {"content": e.content, "confidence": e.confidence,
                 "type": e.tier}
                for e in working
            ],
            "epistemic_note": (
                f"{len(working)} unverified belief(s) embedded. "
                "Do not treat working_beliefs as verified."
            )
        }


# --- Example usage ---

state = BeliefState()

# Tier 1: Verified fact (retrieved from DB with citation)
state.add("verified",
          "Acme Corp Q3 revenue = $4.2M",
          confidence=1.0,
          source_span="DB:financials.q3_revenue row=1")

# Tier 2: Inference (reasoned from context)
state.add("inference",
          "Revenue dropped 15% YoY → likely due to enterprise churn",
          confidence=0.78,
          source_span="context:llm_reasoning_step_7")

# Tier 3: Assumption (filled in, no data available)
state.add("assumption",
          "Competitor pricing change happened in Q2 (no data, estimating)",
          confidence=0.5)

# Before sending to downstream agent
blockers = state.checkpoint(threshold=0.85)
if blockers:
    print(f"⚠ Epistemic checkpoint: {len(blockers)} item(s) need surfacing")
    for b in blockers:
        print(f"  [{b.tier}] {b.content} (conf={b.confidence})")
        # Surface to caller, inject warning into response, or halt
else:
    print("✓ Belief state cleared for handoff")

# Downstream receives safe format
safe = state.format_for_downstream()
# {"verified_facts": ["Acme Corp Q3 revenue = $4.2M"],
#  "working_beliefs": [{"content": "...", "confidence": 0.78, "type": "inference"},
#                      {"content": "...", "confidence": 0.5, "type": "assumption"}],
#  "epistemic_note": "2 unverified belief(s) embedded..."}
```

**Verification strategy by tier:**

| Tier | Verify how | Cost |
|------|-----------|------|
| Verified | Citation trace, DB lookup | Low (already done) |
| Inference | LLM-as-judge against source span, re-retrieve | Medium |
| Assumption | Explicit retrieval, prompt for "I don't know" | High |

**The meta-pattern:** most agent failures aren't "the agent was wrong" — they're "the agent was wrong and passed the wrongness downstream without anyone noticing until the output mattered." The Belief State Boundary makes the epistemic quality of every piece of information visible at every handoff point.

## Receipt

> Verified 2026-07-30 — Pattern identified from Tianpan.co "Cascading Context Corruption" (April 14, 2026), Claude Skills discussion #406 on agent memory frontier (July 2026), paperclipped.de production failure analysis (2026). Code example is structural pseudocode demonstrating the epistemic tier model. Pattern confirmed against three production failure reports: schema entropy → cascading wrong conclusion → wrong action → undetected failure chain.

## See also

- [S-1853 · The Handoff Contract Stack](stacks/s1853-the-handoff-contract-stack-when-your-agent-hands-off-confidence-without-evidence.md) — structural framing of inter-agent handoff quality
- [S-1854 · The Entropy Guardian Stack](stacks/s1854-the-entropy-guardian-stack-when-your-agent-fails-silently-and-you-wont-know-until-its-too-late.md) — silent failure detection
- [S-1847 · The Silent-Signal Stack](stacks/s1847-the-silent-signal-stack-when-your-dashboard-says-green-and-your-users-say-nothing-happened.md) — observability gap
- [S-1855 · The Sequence Authorization Gap](stacks/s1855-the-sequence-authorization-gap-when-each-tool-call-is-authorized-but-the-chain-is-an-attack.md) — cross-boundary safety
