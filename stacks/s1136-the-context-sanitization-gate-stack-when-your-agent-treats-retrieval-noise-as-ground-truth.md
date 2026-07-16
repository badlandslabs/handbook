# S-1136 · The Context Sanitization Gate Stack — When Your Agent Treats Retrieval Noise as Ground Truth

Your agent confidently tells a customer their order shipped two days ago. It didn't. The order was cancelled last week, but a stale cache entry surfaced in the agent's context window, and the agent treated that outdated status as verified fact. It then wrote the wrong status into its memory — so every future interaction about that order references the same corrupted data as authoritative truth. No error was raised. The tool returned successfully. The logic was sound. The data feeding it was not. This is context poisoning, and it is one of the hardest failure modes to catch in production agents.

## Forces

- **RAG retrieves signal, not truth.** Vector similarity retrieval returns semantically close content — not factually correct content. A retrieved passage about a superseded pricing policy, an outdated legal clause, or a cancelled order has the same embedding distance as current data. The agent cannot distinguish relevance from accuracy.
- **Confidence is decoupled from correctness.** LLMs generate confident continuations from any input. A confident agent citing a stale source is indistinguishable, at inference time, from a correct agent citing current data. The only signal is provenance — and provenance is rarely attached to retrieved chunks.
- **Context poisoning is self-reinforcing.** Once the agent treats corrupted data as fact and writes it into memory, future retrieval retrieves the corrupted entry alongside (or above) the original source. The error compounds across turns. Each iteration makes the error more embedded and harder to root out.
- **Traditional observability shows green.** Token count, error rate, latency — none of these metrics flag a confident agent confidently citing wrong information. The failure is semantic, not structural. You need semantic instrumentation.
- **The trust boundary is invisible.** The agent treats all context equally: hardcoded system instructions, user messages, tool returns, and retrieved chunks all sit in the same token space with no provenance labels. Without explicit trust tiers, the model has no signal to weight retrieved content differently from its parametric knowledge.

## The Move

### 1. Provenance Tagging at Ingestion

Tag every retrieved chunk with a provenance header before it enters the context window:

```markdown
[PROVENANCE: source=product_catalog_v3, retrieved_at=2026-07-10T14:22:00Z, ttl=24h, version_hash=a3f9c1, freshness=STALE_THRESHOLD_EXCEEDED]
```

Embed this as a distinct XML-style block the model can learn to recognize. Provenance is not metadata for human inspection — it is a signal the model should weight.

### 2. The Fact Freshness Gate

Before every major reasoning step, run a lightweight freshness check:

```python
def freshness_gate(retrieved_chunk, staleness_threshold_hours=24):
    age = datetime.now(timezone.utc) - retrieved_chunk.retrieved_at
    if age.total_seconds() / 3600 > staleness_threshold_hours:
        return "DEGRADED — verify against authoritative source"
    return "CURRENT"

def context_sanitization_gate(context_chunks):
    sanitized = []
    for chunk in context_chunks:
        provenance = parse_provenance(chunk)
        if provenance and provenance.source in AUTHORITATIVE_SOURCES:
            provenance.freshness = freshness_gate(chunk)
        sanitized.append(provenance_markdown(chunk, provenance))
    return sanitized
```

Flagging is not blocking — the agent still proceeds, but the flagged chunks are labeled so the agent can weight them appropriately.

### 3. The Provenance-Conscious Prompt

Add an explicit instruction layer to system prompts that teaches the agent to query provenance:

```
You operate in a tiered-trust context:
- TIER-1 (highest): System instructions and verified user input
- TIER-2: Tool call returns with timestamp and error metadata
- TIER-3: Retrieved chunks with provenance tags — weight by freshness
- TIER-4 (lowest): Implicit assumptions from prior turns

When citing information from a TIER-3 source, you must include the source identifier and retrieval timestamp in your citation. Do not assert TIER-3 information as fact without provenance linkage.
```

### 4. The Claim-Expiration Budget

Track the staleness of every factual claim the agent makes that originated from retrieved content. Claims from TIER-3 sources get a staleness budget:

```python
claim_registry = []

def register_claim(claim: str, source_chunk_id: str, provenance: Provenance):
    claim_registry.append({
        "claim": claim,
        "source": source_chunk_id,
        "retrieved_at": provenance.retrieved_at,
        "expires_at": provenance.retrieved_at + timedelta(hours=TTL_HOURS),
        "verified": False
    })

def verify_claim(claim: str) -> VerificationResult:
    entry = next((c for c in claim_registry if c["claim"] == claim), None)
    if not entry:
        return VerificationResult(VERIFIED=False, REASON="not tracked")
    if datetime.now(timezone.utc) > entry["expires_at"]:
        return VerificationResult(VERIFIED=False, REASON="expired")
    # Trigger authoritative re-retrieval
    return re_retrieve_and_verify(claim)
```

### 5. The Memory Provenance Boundary

Treat the agent's own memory as an untrusted TIER-4 source:

- Every memory write must carry a provenance tag (original source, retrieval time, confidence score)
- Memory retrieval goes through the same freshness gate as RAG
- Conflicting memory entries trigger an explicit resolution step, not silent synthesis
- Implement a forgetting policy: memory entries older than N days without re-validation are degraded to TIER-5 (agent's own synthesis — lowest weight)

### 6. The Poisoning Detection Monitor

Instrument the observability layer for poisoning signals:

```python
SIGNALS = {
    "contradiction_within_session": check_intra_session_conflicts,
    "claim_exceeds_source_age": check_staleness_violations,
    "retrieval_hit_on_stale_chunk": track_stale_retrieval_rate,
    "memory_write_from_derivation": track_derived_vs_factual_memory,
    "confidence_without_provenance": check_unattributed_confidence
}

def compute_poisoning_score() -> float:
    """0.0 = clean, 1.0 = likely poisoned"""
    return sum(signal.weight * signal.check() for signal in SIGNALS.values())

def poisoning_alert(threshold: float = 0.7):
    score = compute_poisoning_score()
    if score > threshold:
        # Flag session, surface to human review, log full provenance chain
        emit_alert(session_id, score, SIGNALS)
```

The SuperLocalMemory research (arXiv:2603.02240) formalizes this: treat memory entries like any other input from an untrusted source. Verify provenance, scope access, monitor behavior, and maintain the ability to audit and roll back.

## Receipt

> Verified 2026-07-15 — Redis Labs blog "Context Poisoning: How Bad Information Breaks Agent Reasoning" (May 2026) documents the failure mode with production examples. Redis is authoritative (memory infrastructure vendor with production telemetry). The five-layer defense (provenance tagging → freshness gate → tiered prompt → claim expiration → poisoning monitor) synthesizes this source with OWASP Agentic AI Top 10 (LLM08: vector/embedding poisoning), Redis SuperLocalMemory research, and SecureFlag's memory poisoning taxonomy. Key distinction from existing entries: S-866 (memory contradiction) covers the symptom (conflicting memories); this covers the gate-level architecture for preventing retrieval noise from becoming treated-as-fact. S-1052 (cascade) covers inter-agent propagation; this covers intra-agent source→belief contamination. S-125 (multi-source conflict) covers concurrent conflicts; this covers temporal staleness as a distinct contamination axis.

## See also

- [S-866 · The Memory Contradiction Stack](/stacks/s866-the-memory-contradiction-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — the symptom this prevents from forming
- [S-1052 · The Cascade Stack](/stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — inter-agent propagation; this is the intra-agent layer
- [S-125 · Multi-Source Claim Conflict](/stacks/s125-multi-source-claim-conflict.md) — concurrent source conflicts; this covers temporal staleness as a separate contamination vector
- [S-433 · Semantic Exit Gates](/stacks/s433-semantic-exit-gates.md) — delivery verification; this covers pre-retrieval and intra-session sanitization
