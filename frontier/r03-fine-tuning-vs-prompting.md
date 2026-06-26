# R-03 · Fine-tuning vs Prompting vs RAG

Three ways to make a model behave the way you want. Most people reach for fine-tuning too early.

## Forces
- Fine-tuning takes time, money, and expertise to do right; prompting takes an afternoon
- Prompting has a quality ceiling — some behaviors can't be prompted into a model
- RAG and prompting both depend on what fits in the context window
- Fine-tuning bakes knowledge into weights — it can't be updated without retraining

## The move

**Decision tree:**

```
Start here: Can you solve it with a good prompt?
    ├─ YES → use prompting. Done.
    └─ NO: Is the problem that the model lacks recent or private knowledge?
        ├─ YES → use RAG (cheaper, updatable, citable). Done.
        └─ NO: Is the problem that the model generates the wrong style, format, or behavior?
            ├─ YES → consider fine-tuning.
            └─ Are you sure prompting can't fix it? Try 20 more examples first.
```

**Prompting** — use when:
- The task is new or exploratory
- You need to iterate quickly
- The model's base knowledge is sufficient
- Budget is limited

**RAG** — use when:
- The model needs access to specific, current, or private knowledge
- You need citations/sources in the output
- Knowledge changes frequently
- You want to update the knowledge without retraining

**Fine-tuning** — use when:
- You need a consistent style, tone, or format the model won't hold via prompting
- You have >1000 high-quality labeled examples
- Inference latency matters and a smaller fine-tuned model outperforms a larger prompted one
- You're running at enough scale to justify the one-time training cost

**What fine-tuning does NOT fix:**
- Hallucination (fine-tuning on wrong data makes it worse)
- Knowledge gaps (use RAG for facts)
- Fundamental capability limits (a small model fine-tuned on hard reasoning tasks won't beat a frontier model)

## Receipt
> Receipt pending — 2026-06-25. Decision tree based on widely-agreed field practice. Fine-tuning costs depend on provider, dataset size, and model — get current quotes from Anthropic/OpenAI fine-tuning pages before budgeting.

## See also
[S-07](../stacks/s07-rag.md) · [R-07](r07-post-training-rlvr.md) · [R-01](r01-model-landscape.md) · [S-06](../stacks/s06-model-routing.md)

## Go deeper
Keywords: `fine-tuning` · `LoRA` · `QLoRA` · `RLHF` · `DPO` · `RAG vs fine-tuning` · `instruction tuning` · `few-shot prompting`
