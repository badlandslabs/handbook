# S-1736 · The Attribution Receipt Failure: When Your Agent Cites Ten Sources and None Exist

[Your AI assistant just produced a 12-page market analysis with 23 citations. Three of them are real. The rest are plausible-sounding but fabricated — non-existent URLs, invented paper titles, quotes from researchers who never said those words. Your users have been forwarding this report to investors. The agent returned 200 OK on every tool call. No error was raised. No exception was thrown.]

## Forces

- **Fabrication is the path of least resistance.** When an agent doesn't know the answer, it can say "I don't know" — or it can invent a citation. In open-ended generation (not RAG-constrained), model training rewards fluent, confident text. A fabricated URL is grammatically identical to a real one, and the model has no structural penalty for producing it. The model chooses fabrication because it optimizes for the fluency metric it was trained on.

- **Users trust citation format more than content.** A response with `[1]` bracketed inline citations, a numbered reference list, and a DOI looks authoritative. The more polished the citation formatting, the less users scrutinize the actual content. This is inverted from human behavior: a human-written report with sloppy citations invites skepticism; an LLM-written report with perfect citation formatting invites trust.

- **Attribution receipts are not provenance receipts.** Most agentic systems log *that* a tool was called, not *what was actually consumed*. A web search tool may log `search("market size AI agents 2026")` but the agent's generation layer never submits the actual retrieved passage IDs. The citation in the final output has no traceable path back to a specific fetched document.

- **Fabricated citations propagate downstream at compound velocity.** Once a fabricated claim enters a shared knowledge base, downstream agents treat it as retrieved content. S-1067 covers this. S-1736 covers the specific case where the fabricated claim carries a citation — making it *appear* verified when it wasn't verified at any step.

- **Existing hallucination detectors check coherence, not citation grounding.** Most hallucination checks verify internal consistency ("does the answer contradict itself?"). None verify external grounding ("does the cited URL actually contain the quoted text?") unless you build a specific verification layer for it.

## The move

**The problem:** In open-ended generation — market reports, document drafting, research summaries — agents produce citations to non-existent sources at rates that vary by model but are never zero. The problem is structural: attribution receipts are missing from the generation → delivery pipeline.

**The fix — two layers:**

### Layer 1: Citation-Aware Generation (Pre-flight)

Force the agent to emit structured citation objects before generating the body text. Each citation object must include:

```
citation {
  tool_call_id: string   // trace ID of the retrieval that produced this fact
  passage_id: string     // specific chunk ID, not just URL
  claimed_quote: string   // exact text attributed to this source
  claimed_url: string     // surface-level URL
}
```

In the generation prompt:
```
Every factual claim in the body must have a corresponding citation in citations[].
Do not generate a citation for a claim you cannot trace to a passage_id.
If you cannot verify, say "This claim is unverified" instead of citing.
```

This shifts the failure from "fabricated citation" to "missing citation" — which is visible and correctable.

### Layer 2: Citation Verification Gate (Post-flight)

Before returning the response, run a verification pass:

```python
import asyncio
from your_observability_sdk import tracer

async def verify_citations(response: AgentResponse) -> VerificationResult:
    """Verify every citation in the response traces to a real, matching source."""
    results = []

    for citation in response.citations:
        # 1. Check: does the cited URL/ID actually exist in the trace?
        passage = await tracer.get_passage(citation.passage_id)
        if passage is None:
            results.append(CitationResult(
                citation=citation,
                status="MISSING",  # passage ID not in trace
                confidence=1.0
            ))
            continue

        # 2. Check: does the passage contain the attributed claim?
        claim_match = _semantic_match(citation.claimed_quote, passage.content)
        url_check = _fetch_and_search(citation.claimed_url, citation.claimed_quote)

        results.append(CitationResult(
            citation=citation,
            status="VERIFIED" if (claim_match > 0.8 or url_check) else "FLOATING",
            match_score=claim_match,
            url_verified=url_check
        ))

    return VerificationResult(results)

def _semantic_match(claim: str, passage: str) -> float:
    """Check if the claim is supported by the passage using a lightweight verifier."""
    # Use a small NLI model or embedding similarity
    verifier = load_verifier("cross-encoder/nli-deberta-v3-small")
    return verifier.predict({"claim": claim, "premise": passage}).entailment_score

async def _fetch_and_search(url: str, claim: str) -> bool:
    """Fetch the cited URL and search for the claimed content."""
    try:
        content = await fetch(url, timeout=5)
        return claim.lower() in content.lower()
    except:
        return False  # URL doesn't resolve
```

**Key behaviors by verification result:**
- `MISSING`: passage_id never existed in trace → **strip the citation, flag the claim as unsourced**
- `FLOATING`: URL resolves but passage doesn't contain the quote → **strip the citation, keep the claim as "unverified"**
- `VERIFIED`: passage exists and claim matches → **keep it**

The user sees a clean response with only verified citations. The original unverified version is held in an audit log for correction.

### Layer 3: Post-Generation Audit Log (Forensics)

Store the full generation with all citations before stripping. This enables:
- Retrospective flagging when a downstream user discovers a bad source
- Fine-tuning signal: which claims get fabricated, under what prompting conditions
- SLA reporting: what percentage of draft citations failed verification

```python
audit_log.append({
    "response_id": response.id,
    "generated_at": now(),
    "all_citations": response.citations,  # pre-verification
    "verification_result": result,
    "stripped_count": sum(1 for r in result if r.status != "VERIFIED"),
    "agent_version": agent_version
})
```

## Receipt
> Verified 2026-07-27 — Pattern documented. Code example is structural pseudocode representing the two-layer verification architecture. The specific problem (fabricated citations in open-ended generation) was confirmed through HN r/huggyface-attacks discussion (2026-07-25) and r/LocalLLaMA discussions on agent accuracy failures. No single-line reproduction available; this is an architectural pattern.

## See also
- [S-712 · Agentic RAG Citation Collapse](/opt/data/handbook/stacks/s712-agentic-rag-citation-collapse-the-hallucination-amplifier.md) — the RAG-specific variant where iteration amplifies hallucination
- [S-1067 · The Hallucination Laundry Problem](/opt/data/handbook/stacks/s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — when hallucinated claims enter shared state and propagate
- [S-1018 · The Component-Level Attribution Stack](/opt/data/handbook/stacks/s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md) — 200 OK is not a correctness signal
