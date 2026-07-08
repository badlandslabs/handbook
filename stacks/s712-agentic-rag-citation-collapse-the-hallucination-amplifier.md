# S-712 · Agentic RAG Citation Collapse: The Hallucination Amplifier

[Agentic RAG iterates retrieval → generation cycles to self-correct. The same self-correction loop silently amplifies hallucination — each pass makes confident-but-wrong answers more elaborate, more cited, and harder to catch. The problem isn't the model. It's the architectural assumption that generated text becomes safe context for the next generation.]

## Forces

- **Iteration compounds error, not just reasoning.** Each agentic RAG cycle takes prior generation as input context. If a passage was missed on cycle N, the generator fills it plausibly. On cycle N+1, that plausible fill looks like a retrieved source — it appears in the citation list, it was "in context," so it feels grounded.
- **Citation checks test coherence, not grounding.** Most hallucination checkers verify "does this answer sound consistent?" rather than "can every factual claim trace to a specific retrieved passage ID?" Internal coherence is necessary but not sufficient — a confident narrative can be entirely internally consistent and entirely unsourced.
- **The retriever inherits the generator's mistakes.** Modern retrievers score passages against the current query + generation context. Generated text that appeared confident and well-cited gets boosted in subsequent retrieval scores, propagating the hallucination forward through the retrieval graph.
- **Multi-hop queries are the highest-risk case.** A 3-hop question ("what caused the delay, what was the downstream impact, and what was the root cause?") requires 3+ retrieval cycles. Each cycle adds one more opportunity for a missed passage to be filled and propagated. Hallucination probability compounds multiplicatively with cycle count.

## The move

**Citation gating: every factual claim must cite a passage by ID, not just by paragraph.**

The fix has three layers:

1. **Passage-level citation enforcement.** During generation, the prompt requires every factual claim to carry a `[source: passage_ID]` tag. The LLM must name the specific passage it drew from — not paraphrase it. Claims without tags are rejected at generation time, not post-hoc checked.

2. **Passage-trust scoring.** Each retrieved passage carries a retrieval-time trust score (based on embedding similarity, freshness, and source authority). Generated claims sourced from low-trust passages are flagged for human review before delivery, regardless of internal coherence.

3. **Amplification circuit breaker.** Track per-session hallucination signal. If the same factual gap reappears across N consecutive generations (detected via claim fingerprinting), halt iteration and escalate — the retriever is systematically missing this passage class.

```python
from dataclasses import dataclass
from typing import Optional
import hashlib

@dataclass
class Passage:
    id: str
    content: str
    trust_score: float  # 0.0–1.0
    source: str

@dataclass
class CitationClaim:
    claim: str
    passage_id: str
    passage_trust: float
    fingerprint: str  # hash of the factual claim

class CitationGate:
    """
    Enforces passage-level citation on every factual claim.
    Breaks the hallucination amplification loop in agentic RAG.
    """
    def __init__(self, trust_threshold: float = 0.6, max_cycles: int = 4):
        self.trust_threshold = trust_threshold
        self.max_cycles = max_cycles
        self._seen_gaps: dict[str, int] = {}  # fingerprint → cycle count

    def enforce(self, claims: list[CitationClaim]) -> tuple[list, list]:
        """
        Split claims into accepted and rejected.
        Accepted: cited + above trust threshold.
        Rejected: uncited OR below trust threshold.
        """
        accepted, rejected = [], []
        for claim in claims:
            if not claim.passage_id:
                rejected.append(claim)
                self._track_gap(claim, "uncited")
            elif claim.passage_trust < self.trust_threshold:
                rejected.append(claim)
                self._track_gap(claim, "low_trust")
            else:
                accepted.append(claim)
        return accepted, rejected

    def _track_gap(self, claim: CitationClaim, reason: str):
        fp = claim.fingerprint
        self._seen_gaps[fp] = self._seen_gaps.get(fp, 0) + 1
        if self._seen_gaps[fp] >= self.max_cycles:
            raise AmplificationHalt(
                f"Claim '{claim.claim[:50]}' appeared {self._seen_gaps[fp]} cycles "
                f"without passage grounding. Retriever is systematically missing this class. "
                f"Halt iteration, flag for retrieval audit."
            )

    def generate_with_citation(
        self,
        query: str,
        retrieved_passages: list[Passage],
        llm_client,
    ) -> tuple[str, list[CitationClaim]]:
        """
        Generate with citation enforcement. Returns answer + validated claims.
        """
        passage_context = "\n".join(
            f"[PASSAGE:{p.id}] (trust={p.trust_score:.2f}) {p.content}"
            for p in retrieved_passages
        )

        prompt = f"""Answer the query using ONLY the provided passages.
For EVERY factual claim, cite it as [PASSAGE:<id>].
If you cannot source a claim from a passage, say you don't know.

Query: {query}

Passages:
{passage_context}"""

        response = llm_client.generate(prompt)
        claims = self._extract_claims(response, retrieved_passages)
        accepted, rejected = self.enforce(claims)

        if rejected:
            # Re-generate excluding the hallucinated claims
            filtered_passages = [p for p in retrieved_passages
                                 if p.id not in {c.passage_id for c in rejected}]
            return self.generate_with_citation(query, filtered_passages, llm_client)

        return response, accepted

    def _extract_claims(
        self, response: str, passages: list[Passage]
    ) -> list[CitationClaim]:
        """Parse [PASSAGE:<id>] citations from response."""
        import re
        claims = []
        # Simple sentence-level extraction; production would use an NER model
        for sent in response.split(". "):
            match = re.search(r"\[PASSAGE:(\w+)\]", sent)
            passage_id = match.group(1) if match else None
            passage = next((p for p in passages if p.id == passage_id), None)
            fingerprint = hashlib.md5(sent.encode()).hexdigest()
            claims.append(CitationClaim(
                claim=sent.strip(),
                passage_id=passage_id or "",
                passage_trust=passage.trust_score if passage else 0.0,
                fingerprint=fingerprint,
            ))
        return claims

class AmplificationHalt(Exception):
    """Raised when a claim keeps re-appearing without grounding."""
    pass
```

## Receipt

> Verified 2026-07-06 — Devinity Solutions (May 2026): "Internal benchmarks across our client base match what the broader industry is reporting: naive RAG pipelines fail silently in production." Tianpan.co (Feb 2026): "Citation gating fixes this: the generator must source every factual claim to a specific retrieved passage. This is non-negotiable for legal, medical, or compliance use cases." Noveum.ai (2026): "Faithfulness hallucinations contradict the given context; citation hallucinations point to a source that does not back the claim. Agents often invent IDs and arguments." Citation gating is documented in Tianpan's agentic RAG post as the primary mitigation. Passage-trust scoring and amplification circuit breakers are design patterns synthesized from these sources — not yet observed as a combined production implementation.

## See also

- [S-100 · Agentic RAG](s100-agentic-rag.md) — covers the self-correcting retrieval loop; this entry covers its failure mode
- [S-284 · Silent RAG Failures Are Chunking Failures](s284-silent-rag-failures-are-chunking-failures.md) — upstream chunking errors that make retrieval systematically miss passages
- [S-125 · Multi-Source Claim Conflict](s125-multi-source-claim-conflict.md) — when competing sources produce contradictory answers across retrieval cycles
