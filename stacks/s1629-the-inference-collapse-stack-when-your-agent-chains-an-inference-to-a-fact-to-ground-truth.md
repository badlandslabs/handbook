# S-1629 · The Inference Collapse Stack — When Your Agent Chains an Inference to a Fact to Ground Truth

Your research agent analyzed 40 documents and concluded "likely outdated" as a cautious hedge. Your drafter agent received it as "confirmed outdated." Your reviewer agent saw it as "outdated." Your approval agent stamped it. Three hours later, the document is flagged in an audit as having been used as authoritative — nobody can trace where the certainty originated because every agent was acting rationally on what it received. This is inference collapse: the transformation of probabilistic inference into declared fact as it propagates through multi-agent pipelines, with no error raised at any step.

## Forces

- **LLMs conflate inference confidence with ground truth.** When a model says "X is the case," the surface form is identical whether X is an extracted fact, a high-probability inference, or a wild guess. Agents downstream treat all three as equally authoritative. The epistemic status — how the information was derived — is discarded by every agent in the chain.
- **Agents optimize for coherence, not provenance.** Given a claim to work with, agents naturally build on it rather than interrogate it. Asking "is this actually verified or was this inferred?" requires deliberate meta-cognition the model was not prompted to perform. The path of least resistance is to treat received claims as given.
- **Standard evaluation cannot track uncertainty across boundaries.** Eval suites score outputs — they don't annotate the provenance chain within them. A pipeline that produces correct-looking output from corrupted inference will score well on task completion. Metacognitive poisoning is invisible to every standard evaluation framework.
- **The failure is retroactively invisible.** Once the claim has propagated, the system has no mechanism to trace "where did this certainty come from?" The signal that would identify the collapse — provenance metadata — was never attached in the first place.

## The move

Build three architectural controls that track and gate epistemic status across agent boundaries:

### 1. Tag every assertion with its provenance tier

Annotate every extracted or inferred claim with an explicit epistemic tag before handoff. Tags are not natural language hedging — they are structured metadata that downstream agents must respect:

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class ProvenanceTier(Enum):
    EXTRACTED_VERIFIED = "extracted_verified"    # Pulled from authoritative source
    EXTRACTED_UNVERIFIED = "extracted_unverified"  # Pulled from non-authoritative source
    INFERRED_HIGH = "inferred_high"               # High-confidence inference (>0.85)
    INFERRED_MEDIUM = "inferred_medium"           # Medium-confidence inference (0.6-0.85)
    INFERRED_LOW = "inferred_low"                 # Low-confidence inference (<0.60)
    UNKNOWN = "unknown"                           # Source unclear

@dataclass
class TaggedClaim:
    content: str
    tier: ProvenanceTier
    source: Optional[str] = None
    confidence: Optional[float] = None
    reasoning_trace: str = field(default="")

    def can_escalate_to(self, target_tier: ProvenanceTier) -> bool:
        """Can this claim be treated as the target tier downstream?"""
        tier_rank = {
            ProvenanceTier.EXTRACTED_VERIFIED: 5,
            ProvenanceTier.EXTRACTED_UNVERIFIED: 4,
            ProvenanceTier.INFERRED_HIGH: 3,
            ProvenanceTier.INFERRED_MEDIUM: 2,
            ProvenanceTier.INFERRED_LOW: 1,
            ProvenanceTier.UNKNOWN: 0,
        }
        return tier_rank[self.tier] >= tier_rank[target_tier]
```

### 2. Gate escalation with explicit provenance checks

Downstream agents must not upgrade provenance tier without independent verification. Implement this as a gating layer on every agent entry point:

```python
from typing import List

@dataclass
class ProvenanceGate:
    def verify_for_handoff(
        self,
        claims: List[TaggedClaim],
        min_tier: ProvenanceTier = ProvenanceTier.EXTRACTED_UNVERIFIED
    ) -> List[TaggedClaim]:
        """
        Filter and annotate claims before downstream handoff.
        - Claims below minimum tier are flagged for review.
        - No automatic tier escalation: low-confidence inferences
          cannot become 'extracted_verified' through repetition.
        """
        verified = []
        for claim in claims:
            if not claim.can_escalate_to(min_tier):
                # Tag as requiring verification; don't suppress
                # Downstream agents must see this but treat as unverified
                claim.tier = ProvenanceTier.UNKNOWN
            verified.append(claim)
        return verified

    def detect_inference_collapse(
        self,
        claims: List[TaggedClaim],
        tolerance: float = 0.15
    ) -> List[TaggedClaim]:
        """
        Detect when a claim's confidence drops significantly
        between agents — a symptom of inference collapse.
        Detects: same content, tier degraded beyond tolerance.
        """
        seen = {}
        collapsed = []
        for claim in claims:
            key = claim.content[:80]  # Normalize by content prefix
            if key in seen:
                prior = seen[key]
                if prior.tier != claim.tier:
                    collapsed.append(claim)
            else:
                seen[key] = claim
        return collapsed
```

### 3. Wrap claims with provenance audit trail

Every claim that enters a pipeline gets a cryptographically signed provenance record. This is the audit trail that lets you answer "where did this certainty come from?" retroactively:

```python
import hashlib
import time

@dataclass
class ProvenanceRecord:
    claim_hash: str
    tier: ProvenanceTier
    agent_id: str
    timestamp: float
    parent_hashes: List[str] = field(default_factory=list)

    @classmethod
    def from_claim(cls, claim: TaggedClaim, agent_id: str,
                   parent_hashes: List[str]) -> "ProvenanceRecord":
        content_hash = hashlib.sha256(
            claim.content.encode()
        ).hexdigest()[:16]
        return cls(
            claim_hash=content_hash,
            tier=claim.tier,
            agent_id=agent_id,
            timestamp=time.time(),
            parent_hashes=parent_hashes,
        )

# Usage in pipeline:
# Before Agent A processes: attach ProvenanceRecord to every claim
# After Agent B receives: check ProvenanceRecord.tier before treating as fact
# On audit: traverse parent_hashes to trace the inference chain
```

### Evaluation: detecting inference collapse in your eval suite

Add a provenance-adversarial test case to your eval pipeline:

```
Test: Cascade Inference Collapse
Input: Document D where claim C is stated with 60% confidence.
       Drafter agent is told "C is confirmed."
       Reviewer agent receives drafter output.
Expect: Provenance tag on C degrades from inferred_low → unknown
        after Reviewer receives it without independent verification.
        Claim must not appear in final output as VERIFIED
        unless a second agent independently confirmed it.
Metric: provenance_tier_escalation_rate (should be 0)
        claim_accuracy_without_verification (should track tier, not surface form)
```

## Receipt

> Verified 2026-07-25 — Research confirmed inference collapse mechanics from: (1) Label Studio "Ground Truth in the Age of AI Agents" (April 2026, metacognitive poisoning as named failure class, "guess becomes ground truth" pattern from production HN discussion), (2) OWASP ASI Top 10 for Agentic Applications 2026 (ASI08: Cascading Failures — small errors propagate, ASI07: Insecure Inter-Agent Communication — spoofing and tampering), (3) Humaneeti AI Agent Evaluation Guide (April 2026, drift and hallucination as primary silent failure mode), (4) AllAboutTesting OWASP T5 analysis (cascading hallucination as deliberate attack vector), (5) QASkills Multi-Agent Testing Guide (June 2026, "one agent hallucinating a value, then a second acting on it, then a third reporting it as fact" as dominant multi-agent failure class). Pattern distinct from S-1052 (cascade of factual errors) and S-1065 (inter-agent trust escalation) — this entry covers epistemic/uncertainty propagation across agent boundaries, not factual errors or credential abuse.

## See also

- [S-1052 · The Cascade Stack](/stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — the cascade of factual errors; this entry covers the epistemic propagation that precedes factual errors
- [S-1622 · The Confidence Calibration Stack](/stacks/s1622-the-confidence-calibration-stack-when-your-agent-is-wrong-but-sounds-certain.md) — single-agent overconfidence; this entry covers multi-agent propagation of epistemic uncertainty
- [S-1286 · The Handoff Contract](/stacks/s1286-the-handoff-contract-when-your-agent-hands-off-work-and-the-context-goes-missing.md) — context loss in handoffs; this entry covers the specific problem of provenance/signal loss in handoffs
