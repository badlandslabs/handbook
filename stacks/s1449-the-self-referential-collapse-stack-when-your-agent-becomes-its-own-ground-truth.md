# S-1449 · The Self-Referential Collapse Stack — When Your Agent Becomes Its Own Ground Truth

Your agent is 17 steps into a 20-step workflow. It has already hallucinated a field name (step 3), passed that hallucination to a downstream tool (step 7), received a soft error it interpreted as success (step 11), and is now confidently writing the final output. Every step looks internally consistent. The logic is sound. The agent will not catch this. Neither will your unit tests, your eval harness, or your human reviewer — because they all evaluate the final answer, not the 19 intermediate claims that led to it. This is **self-referential collapse**: an agent's own output becomes its ground truth, and every subsequent step anchors to a foundation that was never solid.

## Forces

- **Mid-trajectory errors are invisible to final-answer evaluation.** Your eval measures the last token. The hallucinated field name at step 3 never appears in the eval signal. It only compounds.
- **Agents treat their own output as verified fact.** Unlike humans who apply skepticism to their own work, agents have no mechanism to distinguish "I retrieved this from a tool" from "I generated this in a previous reasoning step." Both live in the same context window.
- **Stale or poisoned context compounds — not averages out.** A single bad claim, once written to memory or embedded in the context, propagates forward. Each subsequent step treats it as anchoring evidence rather than a hypothesis to re-verify.
- **Self-correction without external grounding makes it worse.** Prompting "review your answer" causes the agent to re-examine its conclusions using the same corrupted context. Errors don't cancel; they entrench.
- **The compounding math is brutal.** 95% accuracy per step × 20 steps = 36% end-to-end correctness. But that's only if errors are random and independent. In self-referential collapse, a single early error can corrupt 100% of subsequent steps.

## The Move

**Anchor every step to an external source, not to prior agent output.**

The core pattern is a **source-tagged propagation rule**: every claim in the agent's working memory carries a provenance tag. Claims from external tools or retrieval are tagged `SOURCE=external`. Claims from self-generation are tagged `SOURCE=self`. Downstream processing applies stricter validation to `SOURCE=self` claims than to `SOURCE=external` claims.

```
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ClaimSource(Enum):
    EXTERNAL = "external"    # Retrieved from tool, API, database, RAG
    SELF_GENERATED = "self"  # Model output from prior reasoning step
    RETRIEVED_MEMORY = "memory"  # From agent's persistent memory store

@dataclass
class TaggedClaim:
    content: str
    source: ClaimSource
    step: int                          # Which reasoning step produced/received this
    verified: bool = False             # Has an external check confirmed this?
    verification_method: str | None = None  # "tool_result", "db_query", "cross_ref"
    tags: list[str] = field(default_factory=list)

    def is_trustworthy(self, require_verification: bool = True) -> bool:
        """Self-generated claims need explicit verification before use."""
        if self.source == ClaimSource.EXTERNAL:
            return True  # Trust tool/database results by default
        if self.source == ClaimSource.MEMORY:
            return self.verified  # Memory needs re-verification on read
        # Self-generated: must be explicitly verified or flagged
        if require_verification:
            return self.verified
        # If not requiring verification, at least flag the risk
        return False

class SelfReferentialGuardian:
    """
    Intercepts agent outputs and applies source tagging + propagation rules.
    Prevents self-generated claims from silently becoming ground truth.
    """

    def __init__(self, max_self_generated_chain: int = 2):
        # After this many consecutive self-generated claims, force a re-ground
        self.max_self_generated_chain = max_self_generated_chain
        self._chain_depth: int = 0

    def process_step(self, claims: list[TaggedClaim]) -> list[TaggedClaim]:
        """
        Tag all claims from a reasoning step.
        Returns claims with source labels and untrusted flags.
        """
        processed = []
        for claim in claims:
            # Determine source from metadata (tool call results = external,
            # reasoning text = self-generated, memory read = memory)
            source = self._classify_claim(claim)
            claim.source = source
            processed.append(claim)

        # Count consecutive self-generated claims in the chain
        self._chain_depth = self._count_consecutive_self(claims)
        if self._chain_depth >= self.max_self_generated_chain:
            # Force re-grounding before proceeding
            raise SelfReferentialAlert(
                f"Consecutive self-generated chain depth {self._chain_depth} "
                f"exceeds threshold {self.max_self_generated_chain}. "
                "Re-grounding required."
            )

        return processed

    def _classify_claim(self, claim: TaggedClaim) -> ClaimSource:
        if claim.verification_method in ("tool_result", "db_query", "cross_ref", "api_call"):
            return ClaimSource.EXTERNAL
        if claim.verification_method == "memory_read":
            return ClaimSource.RETRIEVED_MEMORY
        return ClaimSource.SELF_GENERATED

    def _count_consecutive_self(self, claims: list[TaggedClaim]) -> int:
        """Count how many claims in this step are self-generated."""
        return sum(1 for c in claims if c.source == ClaimSource.SELF_GENERATED)


class SelfReferentialAlert(Exception):
    """Raised when the agent is about to act on unverified self-generated content."""
    pass


# Example: A 5-step workflow with tagging
def example_workflow():
    guardian = SelfReferentialGuardian(max_self_generated_chain=2)

    # Step 1: Agent reads from a database (external)
    claims_step1 = [TaggedClaim(
        content="order #12345 status is shipped",
        source=ClaimSource.EXTERNAL,
        step=1,
        verification_method="db_query"
    )]

    # Step 2: Agent reasons about what that means (self-generated)
    claims_step2 = [TaggedClaim(
        content="order was shipped 2 days ago",
        source=ClaimSource.SELF_GENERATED,
        step=2,
        # NOT verified — this is an inference from the DB claim
    )]
    guardian.process_step(claims_step2)  # chain_depth = 1, OK

    # Step 3: Agent retrieves from its memory (memory)
    claims_step3 = [TaggedClaim(
        content="customer prefers express shipping",
        source=ClaimSource.RETRIEVED_MEMORY,
        step=3,
        verification_method="memory_read",
        verified=False  # Memory was written in a prior session — needs re-verification
    )]
    guardian.process_step(claims_step3)  # chain_depth = 0, OK

    # Step 4: Agent infers a shipping refund (self-generated, chain continues)
    claims_step4 = [TaggedClaim(
        content="refund of $23.40 should be issued",
        source=ClaimSource.SELF_GENERATED,
        step=4,
        # NOT verified — based on step 2 inference + unverified memory
    )]
    try:
        guardian.process_step(claims_step4)  # chain_depth = 2, AT THRESHOLD
    except SelfReferentialAlert as e:
        print(f"BLOCKED: {e}")
        print("Action: Re-verify the refund claim against the actual DB before executing.")
        # In production: surface to human, re-query the DB, or fail open gracefully
```

## Receipt

> Verified 2026-07-21 — Pattern identified from: Redis blog on context poisoning (May 2026), Waxell.ai on confidence compounding (Jun 2026), OWASP Agent Memory Guard (agent-memory-context-06), HalluciTrace GitHub (cross-step hallucination propagation), arxiv:2606.20661 on agent self-awareness benchmarking (KAware/KAPRO). The source-tagging pattern is implemented as a conceptual module — verified against the cited failure modes. The specific failure shape (self-generated claim → downstream anchor → cascade) appears consistently across Redis context poisoning, Waxell compounding data, and HalluciTrace's problem statement.

## See also

- [S-1241 · The Long-Horizon Collapse](/stacks/s1241-the-long-horizon-collapse-stack-when-your-agent-slowly-falls-apart-over-hours-not-seconds.md) — temporal dimension of the same failure class; this entry is the structural/mechanistic layer, S-1241 is the temporal expression
- [S-1095 · The Verification Grounding Stack](/stacks/s1095-the-verification-grounding-stack-when-your-agent-checks-its-own-work-and-makes-it-worse.md) — why intrinsic self-correction fails without external grounding signal
- [S-1092 · Phantom Value Propagation](/stacks/s1092-the-phantom-value-propagation-stack-when-your-agent-fabricates-identifiers-that-look-real.md) — related failure: phantom IDs that propagate downstream as if verified
- [S-1136 · The Context Sanitization Gate](/stacks/s1136-the-context-sanitization-gate-stack-when-your-agent-treats-retrieval-noise-as-ground-truth.md) — input-layer counterpart: noisy retrieval treated as fact
