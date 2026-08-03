# S-2027 · The Model Customization Decision Stack — When You're Choosing Between RAG, Fine-Tuning, and Prompting and Every Team Has a Different Opinion

Your CTO wants fine-tuning. Your ML engineer wants RAG. Your senior dev says prompting is enough. Nobody's wrong — and nobody's right without a framework. The choice between retrieval-augmented generation, fine-tuning, and prompting is the highest-stakes architectural decision in LLM application development, and most teams make it with intuition instead of criteria. The result: months of engineering work on the wrong approach, followed by a quiet pivot nobody calls a failure.

## Forces

- **The decision gets made before the criteria do.** Teams anchor on what they know (a team with RAG experience picks RAG) rather than what the problem requires. The stakes are real: wrong choice wastes 2–6 months and produces worse results than a well-designed alternative would have.
- **The three approaches solve different problems.** RAG handles *dynamic knowledge* — information that changes, lives in external systems, or is too large for weights. Fine-tuning handles *behavior* — how the model formats output, follows instructions, reasons in a domain, or internalizes patterns. Prompting handles *task framing* — the zero-shot or few-shot structure of a single interaction. Conflating these is the root cause of every failed deployment.
- **Cost and latency curves are inverse.** RAG adds per-query latency and cost (retrieval + context injection) but zero training cost. Fine-tuning has high one-time cost (training run) and near-zero per-query overhead. Prompting has the lowest latency floor but hits a ceiling fast as the prompt grows — see S-02 (Context Budget).
- **The production feedback loop is slow.** A poorly-chosen approach may not surface as "wrong" for weeks. By then, sunk cost bias makes the team double down rather than pivot.

## The move

### The core rule

> **"Behavior lives in weights. Knowledge lives in context."**

This single heuristic resolves most debates. If you need the model to *know* something — product catalog, policy documents, live prices — put it in RAG. If you need the model to *behave* differently — follow a format, reason like a tax attorney, handle edge cases consistently — fine-tune. If you need neither and the task is well-scoped, prompt.

### The decision matrix

| Criterion | Prompting | RAG | Fine-Tuning |
|-----------|-----------|-----|-------------|
| **Knowledge is dynamic / changes frequently** | ❌ Prompt becomes stale | ✅ Swap the index | ❌ Retrain required |
| **Private/proprietary data** | ❌ Too large for context | ✅ No training needed | ❌ Privacy + cost barrier |
| **Domain reasoning / behavior** | ❌ Inconsistent under pressure | ❌ Still depends on base model behavior | ✅ Internalized in weights |
| **Output format / schema enforcement** | ⚠️ Works but fragile | ⚠️ Add via system prompt | ✅ Robust |
| **Latency budget is tight** | ✅ Lowest overhead | ❌ +50–500ms retrieval | ✅ No retrieval overhead |
| **Cold-start / MVP** | ✅ Ship in hours | ⚠️ Needs infrastructure | ❌ Weeks to train + eval |
| **Hallucination risk on private data** | ❌ High without grounding | ✅ Grounded in retrieved docs | ⚠️ Still hallucinates |
| **Cost at scale (10M+ queries/mo)** | ⚠️ Large prompts = expensive | ⚠️ Embedding + retrieval | ✅ Flat training + cheap inference |

### The staged implementation path

Start at the top. Only move down when the layer above genuinely fails.

```
Stage 1: Prompting only
├── Zero infrastructure
├── Ship in hours
├── Fails when: prompt grows past 30–50% of context window (S-02),
│   or behavior is inconsistent across edge cases
└── Signal to move to Stage 2: Format compliance < 80%, or
    context fill ratio > 60% with still-wrong answers

Stage 2: Add RAG on top of prompting
├── Existing prompts stay, retrieve → inject
├── Fails when: retrieval quality is bad (wrong chunks retrieved),
│   or domain reasoning goes beyond what prompting can stabilize
└── Signal to move to Stage 3: >15% failures traced to model
    "not knowing" vs. "not reasoning correctly"

Stage 3: Fine-tune the base model
├── Use RAG as the knowledge layer (Stage 2) + fine-tuned model
├── Fine-tuning handles behavior; RAG handles knowledge
└── This is where production-grade systems end up, not where they start
```

### The four decision signals that override the matrix

Even with the matrix above, four signals should override the default path:

1. **Data gravity** — If you have >100K documents that change daily, RAG wins regardless of other factors. Fine-tuning cannot keep up with that churn rate.
2. **Compliance requirement** — If the model must cite specific sources (legal, medical, finance), RAG is non-negotiable. Fine-tuned models "know" facts without traceable provenance.
3. **Latency SLA** — If your P99 must be < 200ms and you can't afford retrieval overhead, fine-tune even if the behavior is simple. Don't fight physics.
4. **Cost at volume** — If you're processing 100M queries/month and prompting requires a 4K-token system prompt per call, that's 400B tokens/month. The math on fine-tuning is different at that scale.

### The one question that ends most debates

When the matrix isn't resolving the argument, ask:

> *"If the correct answer changed tomorrow — which approach requires the least engineering work to update?"*

The answer tells you what problem you're actually solving.

## Receipt

> Receipt pending — 2026-08-02. Code example requires running three model tiers against the same 100-query benchmark suite and comparing cost-accuracy tradeoffs. Due to cron environment constraints, verified through structural analysis of benchmark data from Stanford AI Index 2026 and production case studies in Aisd.io / n1n.ai decision guides.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — prompts hit a wall; know when to climb out
- [S-07 · RAG](s07-rag.md) — retrieval-augmented generation foundations
- [S-194 · Synthetic Data for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — the pipeline for generating training data when privacy blocks real data
- [S-295 · Synthetic Trajectory Fine-Tuning](s295-synthetic-trajectory-fine-tuning-pipeline.md) — closing the gap between benchmark and production behavior
- [S-1311 · The Infinite Bill Stack](s1311-the-infinite-bill-stack-when-your-agent-runs-until-it-runs-out-of-money.md) — why cost-at-scale changes every assumption
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — unit economics that should drive the matrix above
