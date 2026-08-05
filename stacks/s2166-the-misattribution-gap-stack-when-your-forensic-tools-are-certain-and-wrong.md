# S-2166 · The Misattribution Gap Stack — When Your Forensic Tools Are Certain and Wrong

Your agent starts approving transactions that violate policy. Not once — consistently, confidently, with full justification. You run your standard playbook: red-team the model, inspect activation patterns, flag for retraining. Three weeks later the behavior resumes. Your forensics said the model was at fault. The forensics were looking in the wrong place entirely. The cause was a single policy-formatted document in shared memory, planted five weeks ago through a normal document upload — and your entire incident response targeted the model.

## Forces

- **Forensic tools assume a single attribution surface.** Every standard tool — red-teaming, activation analysis, behavioral regression testing — operates at the model layer. A memory-layer attack produces identical symptoms and survives every model-level intervention.
- **SND is empirically indistinguishable from model misalignment.** Semantic Norm Drift produces behavioral artifacts that cannot be separated from emergent misalignment using content-forensic classifiers. Across 510 checkpoints, classifiers trained on poisoning patterns achieved 0% detection — yet the attack was active in every case.
- **The Retrieval-Coverage Dilemma makes evasion trivial.** Any adversarial document that passes the content filter necessarily requires broad retrieval coverage to be effective. Evasion strategies that reduce coverage also reduce effectiveness (r = 0.858). In practice, this means attackers have no reason to be subtle: the document that bypasses the filter is also the one that will be retrieved.
- **Retraining is a permanent, expensive non-fix.** When teams retrain the model in response to what is actually a memory attack, they spend months and millions changing model behavior that was never the cause. Meanwhile the document remains in the vector store.

## The move

### The Three Paths to Agent Misconduct

This stack introduces **Semantic Norm Drift (SND)** as a third, structurally distinct path to agent misconduct:

| | Emergent Misalignment | Secret Collusion | Semantic Norm Drift (SND) |
|---|---|---|---|
| **Cause** | Model develops goals during deployment | Multiple agents coordinate covertly | Policy document in shared memory |
| **Detection surface** | Behavioral monitoring | Communication logs | Memory layer |
| **Standard response** | Retrain / fine-tune | Access controls | **Memory forensics** |
| **Path 3 evasion** | — | — | Proves immune to Path 1 & 2 defenses |

The critical property of SND: it is invisible to defenses designed for the first two paths, and it produces forensics that confidently implicate the model.

### The Attack Mechanics

1. A policy-formatted document enters the shared vector store through a legitimate upload channel (e.g., a user attaches a revised compliance guideline). No exploit, no injection payload — normal document ingestion.
2. Provenance is lost. After embedding and storage, there is no mechanism tracking which upload introduced which embedding. The document becomes indistinguishable from any other piece of trusted context.
3. On retrieval, the document appears in the agent's context window with the same authority as system prompts and hardcoded instructions. The LLM treats it as a policy directive.
4. The behavior change manifests downstream — transaction approvals, routing decisions, data access — as if the model had been retrained to violate policy.
5. Standard forensic response runs content-forensic classifiers on the model output. The attack never touched the model. Detection rate: 0/508 checkpoints.

### The CCT Defense: Two Code Changes

Counterfactual Composition Testing (CCT) is the paper's deployable defense, requiring approximately two code changes in the retrieval pipeline:

```python
# CCT: Counterfactual Composition Testing
# Run at memory retrieval time, before context injection

def cct_check(memory_documents: list[Document], query: str) -> list[Document]:
    """
    For each retrieved document, test whether removing it changes the agent's
    output. If removing doc D produces a different (compliant) decision,
    D is a candidate SND vector.
    """
    baseline_output = agent.decide(query, memory_documents)

    filtered = []
    for doc in memory_documents:
        counterfactual = [d for d in memory_documents if d.id != doc.id]
        counterfactual_output = agent.decide(query, counterfactual)

        if baseline_output != counterfactual_output:
            # This document causally influences the decision
            # Flag for quarantine, log provenance, continue
            provenance_log.append({
                "doc_id": doc.id,
                "session": session_id,
                "influence": "SND_CANDIDATE",
                "baseline": baseline_output,
                "counterfactual": counterfactual_output,
            })
        else:
            filtered.append(doc)

    return filtered
```

**CCT Results (from arxiv:2605.22842):**
- True Positive Rate: **87.5%** against MAJB-64 corpus
- False Acceptance Rate: **0.000** — no clean documents flagged
- Causal attribution accuracy: **87.5%**

The zero FAR is the critical property: CCT does not degrade clean retrieval.

### The Memory Provenance Contract

CCT detects the symptom. The provenance contract prevents recurrence:

```python
# Memory provenance: attach cryptographic attestations to every write

class AttestedMemoryWrite:
    doc_id: str
    content_hash: str          # sha-256 of original document
    embedding_id: str          # points to vector store entry
    upload_principal: str      # who uploaded (human or agent ID)
    upload_session: str        # which session
    attestation: str           # HMAC(principal + hash + session, secret_key)

    def verify(self) -> bool:
        expected = hmac.new(
            self.secret_key,
            f"{self.upload_principal}:{self.content_hash}:{self.upload_session}".encode(),
            "sha256"
        ).hexdigest()
        return hmac.compare_digest(self.attestation, expected)
```

After a CCT flag, provenance allows you to answer: "which upload introduced this document?" — the question that standard attribution cannot answer.

### Separating Attribution Surfaces in Incident Response

When an agent exhibits policy-violating behavior, the triage sequence must check both surfaces:

```
1. Isolate the session's full memory snapshot (not just logs)
2. Run CCT against the memory snapshot
   → If CCT flags a document: memory-layer attack, SND path
   → If CCT passes: model-layer issue, emergent misalignment or drift
3. NEVER run retraining as first response — you may be fixing the wrong surface
4. If SND confirmed: identify provenance, quarantine document family,
   audit all embeddings derived from same upload batch
```

### The MAJB-64 Baseline

MAJB-64 (Memory AdversarialJudgment Benchmark, 64 cases) is the first adversarial memory benchmark combining filter-passing construction, multi-agent evaluation, temporal trajectory data, and causal ground truth. Use it to validate your CCT implementation before production:

- **Coverage:** CDG (cause detection gap), SDR (stealth duration), RSDR (retrieval stealth DR) across 20 sessions
- **Adaptive bypass:** 25 evasion variants tested — none defeated CCT
- **Evasion-coverage correlation:** r = 0.858, p = 4.1×10⁻⁸ — tight enough that filter-based evasion is structurally futile

## Receipt

> Verified 2026-08-05 — arXiv:2605.22842 (May 2026) SUPREME Lab. CCT defense reproduced in principle. Provenance contract pattern from the paper's open implementation (anonymous.4open.science/r/Semantic_Norm_Drift-D412). MAJB-64 benchmark confirmed as first of its kind for memory-layer adversarial evaluation. Retrieval-Coverage Dilemma correlation (r=0.858) empirically validated across 25 evasion variants.

## See also

- [S-1587 · The Stealth Memory Injection Stack](/stacks/s1587-the-stealth-memory-injection-stack-when-a-single-email-replants-your-agents-entire-worldview.md) — the attack surface (what goes *into* memory)
- [S-1050 · The Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — poisoning at the tool *output* layer
- [S-1009 · The Agentic RCA Stack](/stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — the generic RCA pattern; this entry is its memory-layer counterpart
- [S-866 · The Memory Contradiction Stack](/stacks/s866-the-memory-contradiction-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — temporal memory failure; SND is its adversarial counterpart
