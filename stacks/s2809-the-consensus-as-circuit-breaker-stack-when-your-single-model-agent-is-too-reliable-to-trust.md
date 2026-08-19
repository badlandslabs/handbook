# S-2809 · The Consensus-as-Circuit-Breaker Stack — When Your Single-Model Agent Is Too Reliable to Trust

A single expensive model gives you the illusion of reliability. Run the same task across three diverse model families and watch one of them catch a critical hallucination the others missed. This is not a research curiosity — it is a production pattern: consensus voting across model families achieves better reliability than any single model at lower total cost.

## Forces

- A single model's confidence is not a reliability signal. Models hallucinate with high confidence, and self-consistency (same-model N-shot) misses correlated blind spots
- Same-model panels share training data, alignment patterns, and failure modes — agreement within a family proves nothing
- Running a frontier model on every sub-task is expensive. Running a cheap model alone is unreliable. Neither alone is sufficient
- The "compound failure" math (S-200): a 12-step workflow at 95% per-step accuracy yields ~54% end-to-end reliability. Consensus voting breaks this by making each step's output verifiable across independent validators
- Cross-model agreement is a calibrated confidence signal that neither model alone can produce about itself

## The move

**Decompose, sample, vote, and scale dynamically.** This is the consensus-as-circuit-breaker pattern:

**Step 1 — Task decomposition into atomic units.** Break the workflow into sub-tasks small enough that each is independently verifiable. Each atomic unit becomes a consensus round, not the entire workflow. This is the same insight as S-200's step-level reliability — but instead of measuring per-step accuracy, you *enforce* it.

**Step 2 — Parallel micro-agent sampling.** Execute each atomic sub-task simultaneously on N diverse model families. "Diverse" is the operative word: pick models with different training data, alignment techniques, and architectures (e.g., Claude + Gemini + Llama). Running three Haiku-class models in parallel gives you diversity at 3× cheap cost — not 3× expensive cost.

**Step 3 — Semantic consensus voting.** Cluster outputs by semantic similarity (not string match — token drift and paraphrasing produce different surface forms for the same answer). Select the majority-cluster answer. Reject clusters below a threshold (e.g., 2-of-3, 3-of-5) as "no consensus" and escalate.

**Step 4 — Dynamic consensus scaling.** Not every sub-task needs the same vote size. Scale consensus intensity by risk:

```python
def consensus_round(prompt: str, sub_task_risk: str) -> str:
    risk_to_n = {"low": 3, "medium": 5, "high": 7}
    n = risk_to_n.get(sub_task_risk, 3)

    # Parallel execution across diverse model families
    responses = await asyncio.gather(*[
        call_model("claude-haiku", prompt),
        call_model("gemini-flash", prompt),
        call_model("llama-3.3-70b", prompt),
        *[call_model("mixtral", prompt) for _ in range(n - 3)]
    ])

    # Semantic clustering — not exact match
    clusters = cluster_by_embedding_similarity(responses)
    winning_cluster = max(clusters, key=len)

    if len(winning_cluster) >= (n // 2 + 1):
        return winning_cluster[0]  # majority answer
    else:
        raise ConsensusUnreachable(
            f"No majority for sub-task. Max cluster: {len(winning_cluster)}/{n}"
        )
```

**Step 5 — Budget governance.** Set a per-task consensus budget. If the cumulative cost of the consensus round exceeds a single frontier model call, fall back to the frontier model for that sub-task. This prevents consensus from becoming more expensive than the thing it replaces.

## The math

The Six Sigma Agent (arxiv 2601.22290) reports: running atomic tasks across 3 diverse micro-agents with majority voting achieved **50,000 DPMO → 3.4 DPMO** (14,700× reliability improvement) while using **80% fewer tokens** vs. single-frontier-model execution. The mechanism: each dissenting vote is a circuit breaker that prevents a wrong answer from propagating into the next stage of the workflow.

Cross-model consensus catches failures that self-consistency misses. Self-consistency (S-24) reduces variance within one model's outputs — but if that model shares a blind spot with its N samples, all votes agree on the wrong answer. Cross-family consensus breaks this by introducing genuinely independent error sources.

## When to invoke consensus

Do not run consensus on every call. The overhead is 3–7× token cost per sub-task. Use it as a circuit breaker:

| Trigger | Consensus depth |
|---------|---------------|
| Tool call with side effects (write, delete, send) | High (5–7 models) |
| Decision point that gates downstream workflow | Medium (3–5 models) |
| Simple retrieval or formatting | None (single model) |
| High-stakes domain (medical, legal, financial) | High, always |
| User-facing output | Medium (3 models, mandatory) |

## The failure mode nobody talks about

Consensus voting can fail in a subtle way: when all models are wrong but agree. This happens in knowledge-boundary tasks where training data is sparse or poisoned. The circuit breaker for this is a **groundedness probe** — after consensus, run the winning answer against a retrieval source. If the retrieval contradicts the consensus answer, revert to human review regardless of vote margin.

## Receipt

> Verified 2026-08-18 — arxiv 2601.22290 (Six Sigma Agent, Lyzr Research) demonstrates 14,700× reliability improvement via consensus-driven micro-agent execution on 50,000 tasks. The consensus-as-circuit-breaker pattern is operationalized in llm-council (GitHub, multi-model dashboard), PromptQuorum's AI consensus scoring (production use in research validation, medical, and legal domains), and RouteLLM's semantic similarity routing (GHeN 2025). William Zujkowski's field report on multi-model consensus voting (Jan 2026) confirms ~78% task satisfaction on 200 production tasks, with the 22% failure rate concentrated in high-stakes decisions where consensus was skipped for speed.

## See also

- [S-200 · Agent Reliability Compounding](s200-agent-reliability-compounding.md) — the math this pattern defeats
- [S-29 · False Consensus](s29-false-consensus.md) — why same-model panels share blind spots
- [F-77 · Cross-Model Divergence Detection](f77-cross-model-divergence.md) — cheap-vs-expensive agreement as a confidence signal
- [S-24 · Self-Consistency](s24-self-consistency.md) — within-model majority voting (the weaker sibling)
