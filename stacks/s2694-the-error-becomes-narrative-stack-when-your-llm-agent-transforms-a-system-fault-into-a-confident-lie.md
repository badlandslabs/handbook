# S-2694 · The Error-Becomes-Narrative Stack

When your LLM agent runtime encounters a system fault — an HTTP 400, a missing cache entry, a rate-limit timeout — and instead of surfacing the error, it generates a fluent, contextually coherent, and entirely fabricated narrative that gets delivered to the user as truth.

## Forces

- **Errors leak into context, not logs.** When an upstream fault (API error page, empty database response, malformed tool return) enters the LLM's context window, the model doesn't see a bug — it sees data. And it reasons over it confidently.
- **Silent failure detection was designed for deterministic systems.** Gray failure in cloud infra (the disk that throttles, the node that degrades) at least leaves observable traces. Fail-plausible removes even those traces: the system generates plausible speech instead of silence.
- **Your test suite passes because it tests what you measure.** Every test that runs green is testing that the agent's output matches expected form — not that the output is factually grounded. The 4,286 unit tests in one production system all passed while a fabricated "Hugging Face platform crisis" was being delivered to users.

## The Move

The paper *(Wu, arXiv:2606.14589, June 2026)* documents 22 incidents across 8 weeks in a production agent runtime with 40 scheduled jobs, 8 LLM providers, and 827 declarative governance checks. The core finding: **70% of silent failures were first detected by users, not automated systems** — despite the presence of automated defenses.

### The Five-Class Taxonomy

| Class | Mechanism | Example |
|-------|-----------|---------|
| **Type 1 — Embedding Contamination** | Error output (stack traces, error pages, 400 responses) enters the embedding plane and distorts retrieval. | An HTTP 400 page gets cached, embedded, and surfaces as "industry data" in future queries. |
| **Type 2 — Confirmation Drift** | Agent seeks confirming evidence and filters disconfirming signals. Initial wrong assumption compounds through selective retrieval. | Agent believes a feature shipped; filters out the rollback notice as "outlier." |
| **Type 3 — Context Absorption** | The error message itself becomes part of the reasoning context, and the model narrativizes it. | `ECONNRESET` becomes "connectivity issues in the target market." |
| **Type 4 — Fail-Plausible (most dangerous)** | The model transforms an internal error into a coherent false output and delivers it confidently. | HTTP 400 cached as error page → model generates "Hugging Face platform crisis" industry analysis. No detector fires. |
| **Type 5 — Governance Surface Gap** | The failure exploits a gap between what governance checks cover (schema, tool access) and what the model actually produces (narrative, summary, insight). | 827 governance checks pass because the output is well-formed; the fabricated content inside passes structural validation. |

### The Defense Stack

The paper's production system eventually stabilized around a layered defense approach. The key layers:

```python
# Layer 1: Error Feed Isolation
# Never let raw error output enter the embedding or reasoning context
class ErrorFeedGuard:
    def sanitize(self, tool_response: dict) -> dict:
        """Strip error metadata before context injection."""
        if tool_response.get("status_code", 200) >= 400:
            return {
                "status": "error",
                "summary": self.summarize_error(tool_response),
                "embedding_block": True  # prevent embedding error pages
            }
        return tool_response

    def summarize_error(self, resp: dict) -> str:
        """Replace raw error with a one-line semantic label."""
        codes = {400: "bad_request", 401: "auth_failed", 429: "rate_limited",
                 500: "upstream_error", 503: "service_unavailable"}
        return codes.get(resp.get("status_code", 0), "unknown_error")

# Layer 2: Pre-Delivery Fact Grounding
# Before pushing to user, verify key claims against a trust source
class PreDeliveryGrounder:
    def __init__(self, trust_db: "VectorStore"):
        self.trust_db = trust_db

    async def ground(self, output: str, claims: list[str]) -> dict[str, bool]:
        """Check each claim against known-ground truth."""
        results = {}
        for claim in claims:
            matches = await self.trust_db.similarity_search(claim, k=1)
            # High similarity to low-authority sources = red flag
            results[claim] = (
                matches and
                matches[0].score > 0.85 and
                matches[0].metadata.get("authority") != "unverified"
            )
        return results

# Layer 3: Output Attribution Audit
# Every factual claim gets a provenance trace
class AttributionTracker:
    def audit(self, output: str, tool_calls: list[dict]) -> list[dict]:
        """Map each output claim to its source tool call."""
        attributions = []
        for span in tool_calls:
            attributions.append({
                "claim_range": span.get("output_range"),
                "source": span["tool_name"],
                "raw_input": span["tool_input"],
                "error_flag": span.get("status_code", 200) >= 400
            })
        return attributions
```

### The Fail-Plausible Detection Problem

The hardest part: fail-plausible exploits the gap between **structural validation** and **semantic validation**. Governance checks pass because the output is well-formed JSON with expected fields. What they don't check is whether the content inside those fields is fabricated. The fix requires:

1. **Truth-source provenance** — every factual claim in agent output must trace to a specific tool call result with a known authority level
2. **Error-surface coverage** — governance checks must cover not just output schema but the semantic content: "does this claim come from a verified source or from an error page?"
3. **User-grounded detection** — because 70% of failures are detected by users first, build a low-friction user feedback channel that feeds back into eval, not just logs
4. **Regeneration on error** — when a tool call returns an error signal, the correct response is to regenerate from the error-aware context, not to continue reasoning from the error itself

## Receipt

> Verified 2026-08-15 — Research backed by arXiv:2606.14589 (Wu, Jun 2026), an 8-week longitudinal study with 22 documented postmortems. Defense code pattern-based on the paper's published `openclaw-ontology-engine` (PyPI). Composite score: 9.40.

## See also

- [S-2693 · The Agent Failure Recovery Stack](stacks/s2693-the-agent-failure-recovery-stack-when-your-agent-crashes-spirals-or-lies-about-it.md) — recovery spirals and the "lies about it" case (adjacent: covers symptoms, not mechanism taxonomy)
- [S-1431 · The Production Eval Loop Stack](stacks/s1431-the-production-eval-loop-stack-when-your-agent-passes-every-test-and-still-crashes-in-production.md) — why test suites miss the fail-plausible class
- [S-1000 · The Agent Recovery Stack](stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — agent recovery patterns (the "silent failure" variant is addressed here)
- [S-1063 · The Context Lifecycle Stack](stacks/s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — context contamination as an embedding-plane failure mode (Type 1 of the taxonomy)
