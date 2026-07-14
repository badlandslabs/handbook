# S-1086 · The Cascading Hallucination Spill Stack

[You run a multi-hop RAG agent. Hop 1 retrieves a confidently-wrong document chunk — a mis-parsed PDF, a stale record, a retrieval artifact. Hop 2 treats it as confirmed and builds on it. Hop 3 cites it as evidence. By hop 5, the agent presents a factually incorrect answer with perfect internal coherence, 95% confidence, and no error code anywhere in the pipeline.]

## Forces

- **Hallucination detectors evaluate outputs, not trajectories.** SelfCheckGPT checks the final answer. RAGAS checks retrieved documents. Neither watches how a corrupted intermediate conclusion propagates through a multi-step reasoning chain.
- **Cascaded errors are self-consistent.** Once a hallucinated fact is established in the reasoning chain, subsequent steps are consistent with it — making consistency-based detectors blind to the error.
- **Confidence is not fidelity.** Models report high confidence on hallucinated outputs. In agentic RAG, that confidence compounds across hops, not just within a single response.
- **Retrieval quality gates the entire pipeline.** A bad retrieval at hop 1 doesn't produce a bad retrieval at hop 1. It produces a bad answer at hop N.
- **Cross-stage monitoring is absent in most stacks.** Standard observability captures per-step inputs and outputs; it rarely tracks whether the *conclusion* of step N+1 depends on the *premise* established in step N.

## The move

**1. Trace provenance at the claim level, not the turn level.**

Annotate every factual claim made in each reasoning step with its source retrieval. Build a claim graph: `claim_id → agent_turn → retrieved_chunk_id → chunk_content → confidence_score`. When the final answer cites "fact X," you can trace it back through the hops that established it.

```
claim_graph = {}

def add_claim(step_id, claim, source_chunk, confidence):
    claim_id = f"c{len(claim_graph)}"
    claim_graph[claim_id] = {
        "step": step_id,
        "text": claim,
        "source": source_chunk,
        "confidence": confidence,
        "children": []   # claims that cite this one
    }
    return claim_id

def link_claims(parent_id, child_id):
    claim_graph[parent_id]["children"].append(child_id)
```

**2. Run a cross-stage verifier between hops, not just after the final answer.**

Insert a lightweight consistency check: given the claim graph so far, does the next retrieved chunk *contradict*, *support*, or *expand* the established claims? Route contradictions to human review or escalate with a flag — do not let contradicted claims become premises.

```python
def cross_stage_check(claim_graph, new_chunk, threshold=0.6):
    """Between hops: does new_chunk contradict any high-confidence claims?"""
    contradictions = []
    for cid, claim in claim_graph.items():
        if claim["confidence"] < threshold:
            continue
        if chunk_contradicts(new_chunk, claim["source"]):
            contradictions.append(cid)
    return contradictions  # non-empty = escalate

# Usage between reasoning hops:
contradictions = cross_stage_check(claim_graph, retrieved_chunk)
if contradictions:
    log.warning(f"Hop {step} contradicted claims: {contradictions}")
    escalate_to_human(claim_graph, contradictions)
    # OR: rerun retrieval with corrected query
```

**3. Use a different model or verifier family at each hop.**

Same-model hallucination is self-reinforcing. A frontier model that hallucinated in hop 1 will confidently defend that hallucination in hop 3. Use a smaller, more literal verifier model (e.g., a fact-checking model or a fine-tuned small model on your domain's ground truth) for cross-stage consistency checks — it won't share the same priors.

**4. Anchor conclusions to retrievable ground truth, not to intermediate outputs.**

Prefer retrieval strategies that link each reasoning step to a *verifiable external source*, not just to the previous agent turn's output. GraphRAG with entity grounding, or a structured knowledge graph with provenance triples (`subject, predicate, object, source_doc`), makes each claim auditable.

```
# GraphRAG-style grounded triple
triple = {
    "subject": "Q3 revenue",
    "predicate": "increased by",
    "object": "23%",
    "source_doc": "earnings_2026_q3.pdf",
    "page": 4,
    "provenance": "direct_quote"
}
```

**5. Treat low-confidence retrievals as circuit-breakers.**

If a retrieval step produces low-similarity or low-confidence chunks, treat the entire trajectory as unreliable rather than trying to recover downstream. A 0.31 similarity score on a critical business question is not "good enough" — it is a signal that the pipeline should halt and re-query with a reformulated question.

## Receipt

> Verified 2026-07-14 — Source: CHARM Framework (arXiv:2606.04435, Saroj Mishra, June 3, 2026): output-level hallucination detectors catch <20% of cascaded errors in multi-hop agentic RAG. Datadog State of AI Engineering 2026 (April 2026): ~1-in-20 production AI requests fail; ~60% are capacity-caused and detectable. The harder category — confident-but-wrong outputs returning HTTP 200 — is where cascading hallucination lives. Microsoft GraphRAG study: multi-hop reasoning accuracy 16.7% → 56.2% (3.4x) with knowledge graph grounding. Cross-encoder reranking adds 33–40% retrieval accuracy at ~120ms latency.

## See also

- [S-100 · Agentic RAG](s100-agentic-rag.md) — routing and chaining patterns for multi-step retrieval
- [S-1028 · Synthetic Trajectory Degeneration](s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — when self-reinforcing training corrupts capability
- [S-459 · Cross-Session Memory Poisoning](s459-cross-session-memory-poisoning.md) — how corrupted memory becomes persistent false belief
- [S-914 · The Observability Trap](s914-the-observability-trap-stack-when-your-dashboard-watches-your-agent-burn-47k.md) — when your monitoring watches without catching
