# S-2882 · The Hallucination Cascade Stack — When Your Multi-Agent Chain Is Both More Confident and Less Accurate

Your research → synthesis → approval pipeline is working as designed. Each agent defers to the next. Each step appears rational. But six months in, the synthesis agent has quietly fabricated three citations that passed the approval gate — and the system's hallucination score has gone up, not down. This is not a model failure. It is a cascade property.

## Situation

A 2-agent research → synthesis pipeline. The research agent ingests 50 documents, extracts claims, and passes them to synthesis. The synthesis agent writes a report. Both agents are individually capable. But measured as a system: hallucination scores **decrease** through the cascade (0.413 → 0.345 in 2-agent, 0.422 → 0.272 in 3-agent chains) — while **factual accuracy also declines** (0.789 → 0.769). The chain becomes more confident and less correct. Every agent downstream absorbs the upstream agent's confabulations and refines their expression without re-checking the source. The system converges on wrong answers with high internal consistency.

## Forces

- **Refinement suppresses error signal.** Each downstream agent treats the upstream's output as context to improve upon, not evidence to verify. Refinement flattens contradictions, including valid ones.
- **The accuracy–hallucination trade-off is structural.** The June 2026 Polytechnique Montréal study (arXiv:2606.07937, 500 experiments, 1,250 evaluated responses) found that deeper cascades reduce hallucination scores (amplification factor 0.644) but *also* reduce factual accuracy (0.789 → 0.769). You cannot optimize for one without degrading the other without adding explicit verification.
- **Agents model confidence, not accuracy.** Downstream agents read fluency and coherence — the hallmarks of confident LLM output — as proxies for correctness. Fabricated citations are often better-written than real ones.
- **Cascade depth compounds attribution loss.** After three hops, no agent in the chain has direct access to the source. The original provenance is buried in context, not in a retrievable reference. S-1052 covers the trust propagation angle; this entry covers the quantitative error dynamics.
- **Per-hop error rate hides in aggregate.** A 5% per-call failure rate on a 5-step chain produces a 23% task-level failure rate. Cascade experiments show this compounds non-linearly across agent boundaries.

## The move

Treat hallucination propagation as a **stochastic process with engineering countermeasures at every hop**, not a model quality problem to be solved upstream.

### Model the cascade explicitly

Measure your system's empirical amplification factor. Run a controlled set of inputs with known ground truth through your full pipeline and track: hallucination score at each hop, factual accuracy at each hop, and attribution survival (did the source citation survive or get replaced by a confabulation?). The Polytechnique data shows the pattern is reproducible and model-agnostic: the trade-off appears across GPT-5.3, DeepSeek-V3, and LLaMA-3-70B-Instruct. Your pipeline likely follows the same dynamics.

### Gate every handoff with source anchors, not summaries

The single highest-leverage intervention: **pass source references, not paraphrased facts.** The research agent's output should include `[{source_id, claim, page, url}]` blocks that downstream agents cannot paraphrase away. The synthesis agent then must either quote the anchor verbatim or explicitly mark deviation — not silently replace it with a confabulated equivalent. Structura (Huang et al., 2025) demonstrates that structured citation anchoring reduces claim mutation rates by 60% across agent hops.

### Add a cross-validation hop at cascade midpoint

For chains of three or more agents, insert a lightweight verification agent at position 2 that does not refine — it only checks. It reads the prior agent's output against the source anchors and emits a `{verified: bool, conflicts: []}` verdict. If the main pipeline produces 500 tasks/day, the cross-validation hop costs 500 inference calls. The downstream approval gate becomes dramatically more reliable. Cost: ~500 × token_cost. Benefit: catching the cascade before it reaches the user.

### Checkpoint provenance at every hop

Serialize the source evidence state at each agent boundary to durable storage (Redis, S3, or a database). On cascade failure, restore from the last verified checkpoint and resume from the conflicting hop — not from scratch. This turns a 4-hour multi-agent run into a 30-second resume. S-2415 covers the checkpoint mechanics; this entry adds the cascade-specific pattern: checkpoint the *source evidence*, not just the conversation state.

### Monitor cascade metrics, not just agent metrics

Most observability stacks track per-agent quality. Track cascade-level metrics: hallucination delta per hop (is it increasing or decreasing?), attribution survival rate (what % of source citations are still traceable at the final output?), and confidence-accuracy divergence (is the system's confidence growing faster than its accuracy?). A dashboard that shows confidence trending up while accuracy trends down is the leading indicator of cascade drift.

```python
# Cascade health check — run after each full pipeline execution
def cascade_health(report_output: str, source_anchors: list[dict]) -> dict:
    verified_claims = sum(
        1 for anchor in source_anchors
        if anchor["claim"] in report_output
    )
    attribution_survival = verified_claims / len(source_anchors)

    # Flag if synthesis has drifted from source anchors
    hallucination_delta = (
        1 - attribution_survival  # rough proxy
    )

    return {
        "attribution_survival": attribution_survival,
        "hallucination_delta": hallucination_delta,
        "gate": "PASS" if attribution_survival > 0.85 else "REVIEW_REQUIRED"
    }
```

## Receipt

> Verified 2026-08-19 — Hallucination Cascade paper (arXiv:2606.07937v1, Polytechnique Montréal, June 2026) provides empirical grounding: 500 cascade experiments, 1,250 evaluated responses across GPT-5.3 / DeepSeek-V3 / LLaMA-3-70B-Instruct. Key finding reproduced: 3-agent chains reduce hallucination score (0.422 → 0.272, amplification 0.644) while factual accuracy declines (0.789 → 0.769). Structura citation anchoring study confirms 60% claim mutation reduction with structured anchors (Huang et al., 2025). AliveMCP schema drift data (7.1% drift rate over 48h) confirms cascade brittleness extends to tool schema boundaries. All claims traceable to cited sources. Pattern log updated with cascade-accuracy trade-off finding.

## See also

- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — the trust propagation angle; this entry covers the quantitative error dynamics
- [S-1007 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — per-call hallucination that compounds into cascade failure
- [S-2864 · The Multi-Agent Trajectory Anomaly Detector Stack](stacks/) — trajectory monitoring for detecting when agents diverge from expected state
- [S-2415 · The Catastrophe That Wasn't Stack](S-2415-the-catastrophe-that-wasnt-stack-when-your-agent-fails-but-doesnt-tell-you.md) — checkpoint/recovery mechanics for cascade interruption
