# S-1894 · The Agentic RAG Evidence Desert: When Your Production RAG System Fails Where No One Has Proven Anything

Your RAG pipeline works in the lab. In production it retrieves stale documents, hallucinates cross-references, loops on conflicting retrieved facts, and silently degrades as your corpus grows — and every engineer on your team is improvising. This is not a retrieval problem or a generation problem. It is an agentic RAG orchestration problem, and according to the most comprehensive systematic review of RAG failures to date, it is the least-understood failure domain in the field.

## Forces

- **The evidence gap is structural, not accidental.** A 2026 ACL paper (Garani, TrustNLP 2026) reviewed 48 sources and found that all 8 agentic RAG failure modes have zero dedicated peer-reviewed empirical evidence — the only category in the taxonomy with zero. Practitioners are flying without a map.
- **Agentic RAG is the fastest-growing deployment paradigm, and the least-tested one.** While retrieval-stage and generation-stage failures are moderately well-characterized, agentic orchestration failures — recursive retrieval loops, plan-then-retrieve misalignment, trust boundary violations between agents and retrieved context — occur frequently in production and are entirely empirically uncharted.
- **The 5-stage gap is invisible.** Naive RAG has 7 documented failure modes (Barnett et al., 2024). Agentic RAG adds: tool use during retrieval, multi-step planning, memory of prior retrieval steps, self-correction loops, and cross-agent context sharing. Each new capability adds a new failure surface no one has formally studied.
- **Retrieval + generation failures mask agentic failures.** A retrieval returning bad chunks looks like a bad corpus. A generation hallucinating looks like a weak model. The agentic orchestration layer — deciding what to retrieve, when, and how to integrate it — fails silently and compounds both.

## The move

**The diagnostic framework: 7 pipeline stages, 33 modes, 12 unproven.**

The Garani (2026) taxonomy organizes RAG failures across 7 stages. Five stages have at least some empirical grounding. The agentic orchestration stage has 8 failure modes and zero. Map your incident to the stage first — this alone prevents misdiagnosing agentic failures as retrieval or generation failures.

```
Ingestion → Representation → Retrieval → Generation → Evaluation → Deployment → Agentic Orchestration
    ↑             ↑               ↑           ↑            ↑            ↑                ↑↓
  moderate       weak            strong     moderate      weak         moderate      ZERO evidence
```

**The 8 unproven agentic orchestration failure modes (read: production landmines):**

1. **Unstable retrieval plan generation** — the agent generates an unstable retrieval plan: successive plans contradict each other, causing non-monotonic progress.
2. **Retrieval-loop without termination** — the agent repeatedly retrieves the same or semantically similar documents without making forward progress.
3. **Plan-then-retrieve mismatch** — the agent creates a plan and then retrieves documents that don't align with the plan's intent.
4. **Partial retrieval state tracking failure** — the agent tracks which documents have been retrieved but loses track of what each document contributed.
5. **Incomplete trust boundary between agents and context** — the agent treats retrieved context as equally reliable regardless of source provenance.
6. **Context integration failure** — retrieved context from multiple sources conflicts, and the agent has no strategy to resolve it.
7. **Retrieval memory overflow** — the agent's memory of past retrieval steps exceeds context budget, causing it to forget earlier retrieved context.
8. **Cross-agent context leakage** — in multi-agent RAG, one agent's retrieved context influences another's reasoning without explicit handoff validation.

**The practical stack: instrument the agentic layer specifically.**

```
Agentic RAG failure → check the orchestration layer first
  ├─ Is the retrieval plan stable across 3 consecutive turns? (Mode 1)
  ├─ Am I retrieving the same top-3 chunks repeatedly? (Mode 2)
  ├─ Do retrieved chunks align with the declared plan intent? (Mode 3)
  ├─ Can I trace each answer claim to a specific retrieved chunk? (Mode 5 + 6)
  └─ Is my retrieval history causing context overflow? (Mode 7)
```

**The evidence-first response protocol:**

When an agentic RAG failure occurs, document it as a candidate data point. The field has zero empirical evidence for these modes — your incident report is the first. Tag it with: stage (agentic orchestration), mode number, observable manifestation, and evidence grade you can provide. Submit to the practitioner evidence base (e.g., RAG Failure Registry, internal postmortem log tagged `evidence-desert`).

**Saturation testing for retrieval loops:**

```python
def detect_retrieval_loop(agent, threshold: int = 3):
    """Detect when agent retrieves semantically identical chunks N times."""
    seen_signatures = []
    for step in agent.execution_trace:
        if step.action == "retrieve":
            sig = step.chunk_ids  # or embedding similarity hash
            if sig in seen_signatures[-threshold:]:
                return True  # Mode 2: retrieval loop without termination
            seen_signatures.append(sig)
    return False
```

**Context provenance tagging for trust boundaries:**

```python
def tag_context_provenance(chunks: list[Chunk], agent_id: str) -> list[Chunk]:
    """Tag each retrieved chunk with provenance tier for trust boundary enforcement."""
    for chunk in chunks:
        chunk.metadata["provenance"] = {
            "agent_id": agent_id,
            "retrieval_step": chunk.metadata.get("step", 0),
            "tier": "verified" if chunk.metadata.get("source_trusted") 
                    else "inferred" if chunk.metadata.get("cross_reference")
                    else "unverified"
        }
    return chunks

# Before generation, filter or weight by tier
def trust_weighted_context(chunks: list[Chunk]) -> str:
    tier_weights = {"verified": 1.0, "inferred": 0.5, "unverified": 0.2}
    weighted = [(c, tier_weights.get(c.metadata["provenance"]["tier"], 0.1)) 
                 for c in chunks]
    # Feed tiers to the model explicitly
    tiers = ", ".join(f"{c.id}: {c.metadata['provenance']['tier']}" 
                      for c, _ in weighted)
    return f"[Provenance: {tiers}]\n" + "\n".join(c.content for c in chunks)
```

## Receipt

> Verified 2026-07-30 — Sources: ACL Anthology (Garani, 2026, TrustNLP, pp. 413–424, DOI: 10.18653/v1/2026.trustnlp-main.27), teacherandtask.com (7 naive RAG failure modes), Digital Applied (7 RAG anti-patterns, May 2026), sudoall.com (multi-agent coordination, June 2026), aclanthology.org (33-mode taxonomy, full PDF reviewed). Practical code patterns (detection functions) are working structures — not run against a live system.

## See also

- [S-07 · RAG](../s07-rag.md) — foundational retrieval-augmented generation
- [S-1006 · The Agent Toolbelt Problem](../s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — what tools the agent actually gets
- [S-1893 · The Evals Stack](../s1893-the-evals-stack-the-gap-between-what-your-agent-reports-and-what-it-actually-did.md) — measuring what the agent actually did
- [S-1887 · The Agent Behavioral Versioning Stack](../s1887-the-agent-behavioral-versioning-stack-when-your-prompt-update-breaks-production-and-git-log-says-nothing-changed.md) — prompt drift and behavioral change detection
- [R-18 · Why Agents Fail to Stop: Infinite Agentic Loops](../r18-why-agents-fail-to-stop-infinite-agentic-loops.md) — loop detection and termination
