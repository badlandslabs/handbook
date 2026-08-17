# S-2748 · The Cascading Hallucination Stack — When Your Agent Pipeline Produces Confident Nonsense

Your agentic RAG pipeline runs four stages: query rewriting, retrieval, reranking, synthesis. Each stage looks healthy — no errors, valid outputs, HTTP 200. The final answer cites five sources and reads as authoritative. All five sources say something different. The agent synthesized a coherent-sounding answer that none of them actually support. Your validation checks pass because each intermediate step was locally correct. The failure mode is global — and it accumulated silently across four boundaries. This is cascading hallucination: the dominant failure mode in production agentic RAG pipelines, and the one that your unit tests will never catch.

## Forces

- **Local correctness ≠ global correctness.** Each pipeline stage can produce valid, coherent output while introducing a factual micro-error. Downstream stages treat micro-errors as ground truth and build on them confidently. The pipeline is individually rational at every step and collectively wrong at the end.
- **Conditionally coherent errors propagate without friction.** The CHARM framework (arXiv:2606.04435, Mishra 2026) defines the failure precisely: stage $s_i$ produces output $c_i$ containing factual error $\epsilon_i$, which is propagated as valid context to $s_{i+1}$, which generates $c_{i+1}$ that is *conditionally coherent* given $c_i$ but factually incorrect. Coherence with prior context is not the same as factual accuracy — and most validation frameworks measure coherence, not accuracy.
- **Reranking amplifies rather than corrects.** Rerankers optimize for relevance given the retrieval context — not for factual alignment with ground truth. A confidently wrong retrieval result gets reranked higher because it semantically matches the query better than the correct answer.
- **Synthesis inherits all upstream errors.** The LLM that synthesizes the final answer has no signal that the context it received was corrupted at stage one. It generates a fluent, confident response that is a composition of validated-looking falsehoods.

## The move

**1. Instrument the inter-stage boundary, not the outputs.**

Most pipelines validate stage outputs. Cascading hallucination lives in the *passage* between stages. Insert an entailment check at each inter-stage boundary: does $c_{i+1}$ actually require $c_i$ as context, or is it conditionally coherent without being entailed?

```
entailment_score = nli_model(c_i, c_i+1)
if entailment_score < THRESHOLD:
    flag("cascade_suspected", stage=i)
    # do not pass corrupted context downstream
```

The CHARM framework achieves 89.4% cascade detection with a 5.3% false-positive rate using entailment scoring at stage boundaries — specifically checking whether downstream outputs are *entailed by* rather than merely *coherent with* prior context.

**2. Ground-truth anchors at retrieval, not synthesis.**

At the retrieval stage, validate retrieved documents against a small frozen ground-truth set — not to filter results, but to compute per-document reliability scores. Documents that contradict known facts get annotated with $\epsilon$ labels. Downstream stages receive `(document, reliability_score)` and weight accordingly. This prevents Stage 1 micro-errors from being treated as high-confidence context.

**3. The cascade-break checkpoint.**

Insert a mandatory verification step after every two pipeline stages. A lightweight verifier re-asks the original query against accumulated context and checks whether the partial answer trajectory is consistent. If inconsistencies accumulate beyond a threshold, trigger a *rollback-to-source* rather than continuing synthesis. This limits error propagation depth: the maximum cascade length in CHARM's evaluation drops from 4.2 stages to 1.4 when checkpoint verification is active.

**4. Contrastive synthesis.**

Rather than generating one answer from retrieved context, generate two answers — one from the current context and one from a maximally-constrained subset of only the highest-confidence retrieved documents. If the two answers diverge significantly, surface the divergence rather than defaulting to the longer one. This is a practical signal that cascading errors are active.

## When to reach for this

Your pipeline has 3+ sequential RAG stages (query rewriting → retrieval → reranking → synthesis, or equivalent). You observe outputs that are fluent, confident, and wrong — with citations that don't support the claims. Your per-stage evaluation metrics are all green. You have no cascade-level signal in your observability stack.

## See also
- [S-1123 · The Trajectory Evaluation Stack](/stacks/s1123-the-trajectory-evaluation-stack-when-your-benchmark-says-95-percent-but-users-are-furious.md) — eval approaches that catch cross-stage failures
- [S-1136 · The Context Sanitization Gate](/stacks/s1136-the-context-sanitization-gate-stack-when-your-agent-treats-retrieval-noise-as-ground-truth.md) — filtering noise before it enters the pipeline
- [S-1109 · The Eval Quality Gap Stack](/stacks/s1109-the-eval-quality-gap-stack-when-your-agent-improves-and-you-dont-know-if-it-got-better.md) — metrics that measure the wrong axis
