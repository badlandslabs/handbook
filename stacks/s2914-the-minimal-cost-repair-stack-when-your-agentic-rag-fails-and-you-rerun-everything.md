# S-2914 · The Minimal-Cost Repair Stack — When Your Agentic RAG Fails and You Rerun Everything

Your agentic RAG pipeline failed a query. You re-run the whole trajectory: fresh retrieval, fresh reasoning, fresh tokens. It works. You do it again on the next failure. And the next. You are spending 3–5× the compute of a targeted fix because no one told you the failure was localizable — the rest of the trajectory was fine. This is the Minimal-Cost Repair Stack: diagnose once, repair exactly where it hurts, reuse everything else.

## Forces

- **Rerun is the default but the most expensive response.** Agentic RAG (ReAct, Search-o1, Search-RAG) interleaves retrieval and reasoning over long trajectories. When the trajectory fails at step 7 of 12, steps 1–6 were correct — but a full rerun discards them all. A naive retry strategy wastes 50–80% of compute on regenerating valid work.

- **Diagnosis without repair is half a solution.** The field has built failure taxonomies (Garani, TrustNLP 2026: 33 failure modes across 7 stages), detection frameworks, and control loops. But none of them tell you *what to do after you know what's wrong*. Stopping at diagnosis is an aircraft that knows it's stalling but doesn't move the yoke.

- **Failures in agentic RAG are systematic and multi-modal, not random.** HotpotQA trajectories fail in diverse, structured ways: wrong retrieved evidence, incomplete evidence, tool-call errors, off-topic reasoning. The diversity means a single repair strategy (rerun) is always over-engineered — you're fixing every possible failure class when only one is active.

- **Prefix reuse is the compounding asset.** Validated reasoning steps and retrieved documents from a failed run are not waste — they're expensive signals. The more of the original trajectory you preserve, the less recomputation the repair requires. The gap between "rerun everything" and "repair locally" is measured in tokens, latency, and cost.

## The Move

Doctor-RAG (Jiao et al., arXiv:2604.00865, HIT/Macquarie/UNSW/Meituan, April 2026) formalizes the repair gap and closes it with a two-stage pipeline.

### Stage 1 — Taxonomy-Constrained Diagnosis + Localization

A distilled diagnosis model reads the failed trajectory and outputs:

1. **Evidence sufficiency score**: Is the retrieved evidence adequate for the claim?
2. **Failure type classification**: Maps to a coverage-gated taxonomy:
   - **Evidence-insufficient**: retrieved docs don't cover the needed claim
   - **Evidence-wrong**: retrieved docs exist but are incorrect or off-topic  
   - **Evidence-superseded**: retrieved docs were correct when indexed, stale now
   - **Tool-call-error**: the retrieval tool returned malformed/nil output
   - **Reasoning-error**: the model mis-connected valid evidence
3. **Earliest failure point k†**: the index in the trajectory where the first error occurred

The diagnosis model is fine-tuned specifically for this task (not a general-purpose judge). Coverage gating means it only flags failures when the model's claimed coverage exceeds the actual evidence support — avoiding false positives on queries with genuinely sufficient evidence.

### Stage 2 — Tool-Conditioned Local Repair

Given `(failure_type, k†)`, the repair module selects a targeted operator:

- **Truncate** at k†, reuse all prior actions and retrieved evidence as conditionally valid
- **Re-retrieve** or **revise** only the failing step, not the whole trajectory
- **Reuse validated prefixes** — every step before k† is preserved and re-fed to the reasoning model

The repair is minimal: it intervenes exactly where the failure lives and leaves the rest intact.

### The Contrast

| Strategy | What it does | Token cost | Retrieval cost |
|----------|-------------|------------|----------------|
| Full rerun | Discard trajectory, re-execute everything | ~3–5× baseline | Full re-retrieval |
| Generic retry | Same prompt, hope for luck | Same as rerun | Same as rerun |
| DR-RAG local repair | Truncate + repair at k† only | ~1× + Δk tokens | ~39–45% fewer calls |

Experiments across HotpotQA, 2WikiMultiHopQA, MuSiQue, and PopQA show DR-RAG substantially improves exact match while reducing retrieval calls 39–45% and cutting ~1,000 tokens per repair (w/o Localization ablation confirms: without localization, trajectories regenerate more of the chain, confirming the value of pinpointing k†).

```python
# Minimal conceptual implementation
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class FailureType(Enum):
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    EVIDENCE_WRONG = "evidence_wrong"
    EVIDENCE_SUPERSEDED = "evidence_superseded"
    TOOL_CALL_ERROR = "tool_call_error"
    REASONING_ERROR = "reasoning_error"

@dataclass
class TrajectoryFailure:
    failure_type: FailureType
    earliest_point: int  # k†
    evidence_sufficiency: float  # 0.0 – 1.0
    coverage_claim: float  # model's claimed coverage

def diagnose_and_repair(trajectory: list, query: str, model) -> list:
    # Stage 1: Diagnose
    diagnosis_prompt = f"""Given failed trajectory for query: {query}
    Trajectory steps: {trajectory}
    Classify failure type, identify earliest failure point k†, 
    and assess evidence sufficiency.
    Return: failure_type, k†, sufficiency_score"""
    
    diagnosis = model.complete(diagnosis_prompt)
    failure: TrajectoryFailure = parse_diagnosis(diagnosis)
    
    # Stage 2: Repair locally — truncate at k†, reuse prefix
    if failure.failure_type == FailureType.EVIDENCE_INSUFFICIENT:
        repaired = trajectory[:failure.earliest_point]
        # Re-retrieve with expanded query
        retrieved = retrieve_with_expansion(query, expanded=True)
        repaired.append({"action": "retrieve", "evidence": retrieved})
        # Resume reasoning from repaired step
        suffix = model.reason_from(repaired, query)
        return repaired + suffix
    
    elif failure.failure_type == FailureType.TOOL_CALL_ERROR:
        # Re-execute only the failed tool call
        repaired = trajectory[:failure.earliest_point]
        tool_result = retry_tool(trajectory[failure.earliest_point]["tool"])
        repaired.append(tool_result)
        suffix = model.continue_reasoning(repaired, query)
        return repaired + suffix
    
    elif failure.failure_type == FailureType.REASONING_ERROR:
        # Truncate to before the reasoning error, 
        # re-derive from the last valid evidence
        repaired = trajectory[:failure.earliest_point]
        suffix = model.redo_reasoning_step(repaired, query)
        return repaired + suffix
    
    # Fallback: local repair failed, conservative rerun
    return full_rerun(query)
```

## Receipt

> Verified 2026-08-20 — arXiv:2604.00865v1 (April 2026), CC BY 4.0. Authors: Jiao, Huang, Qi, Wang, Li, Weng, Liu, Cai, Yao (HIT/Macquarie/UNSW/Meituan). Key claims verified against abstract and arXiv HTML: exact match improvements confirmed across datasets; 39–45% retrieval call reduction confirmed; ~1,000 token savings per repair confirmed via w/o Localization ablation. Taxonomy-gated diagnosis confirmed (coverage-gated error attribution). Tool-conditioned repair operators confirmed (prefix reuse). No production deployment reported in the paper — empirical results are on academic benchmarks only. Production applicability is inferential.

## See also

- [S-1894 · The Agentic RAG Evidence Desert](stacks/s1894-the-agentic-rag-evidence-desert-when-your-production-rag-system-fails-where-no-one-has-proven-anything.md) — the diagnosis side of the same problem (what breaks and why)
- [S-1029 · The Agentic RAG Control Stack](stacks/s1029-the-agentic-rag-control-stack-when-your-retrieval-loop-runs-all-night-without-answering.md) — stopping rules for runaway retrieval loops (prevention, not repair)
- [S-1138 · The Failure Taxon Stack](stacks/s1138-the-failure-taxon-stack-when-your-agent-breaks-and-you-dont-know-why.md) — failure classification (Doctor-RAG's taxonomy is a domain-specific subset)
- [S-1951 · The Trace Harness Attribution Stack](stacks/s1951-the-trace-harness-attribution-stack-when-failure-lives-in-the-trace-but-the-fix-lives-in-the-harness.md) — using traces to pinpoint failure location
