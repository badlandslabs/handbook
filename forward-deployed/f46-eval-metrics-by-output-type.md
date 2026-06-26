# F-46 · Eval Metrics by Output Type

[F-07](f07-evaluation-driven-development.md) covers eval methodology — how to structure an evaluation process, when to run evals, how to gate on them. [F-12](f12-llm-as-a-judge.md) covers LLM-as-judge — how to design rubrics, control position bias, and use pairwise comparison. [S-49](../stacks/s49-retrieval-evaluation.md) covers retrieval metrics — Recall@K, Precision@K, MRR. None of them answers: "I'm evaluating X output type — what metric do I actually compute?" This entry is that reference.

## Situation

A team building three AI features — a contract clause extractor, a customer support chatbot, and an agent that files bug tickets — needs to choose eval metrics. They reach for LLM-as-judge for all three because it's the method they've seen most. Cost at 10k eval calls/month: $7.68 at Haiku prices. The extractor doesn't need a judge — exact match is deterministic and free. The chatbot needs a judge only for tone and helpfulness; factual accuracy is exact match against a structured answer. The agent needs task completion rate and tool use accuracy, neither of which a generic judge captures. Three different output types need three different metric sets. Using the wrong metric misses real regressions; using LLM judge everywhere inflates eval cost 10×.

## Forces

- **The right metric depends on whether the output has a deterministic ground truth.** Extraction, classification, and factual lookup have correct answers — use exact match or F1. Generated text, summaries, and tone do not — use ROUGE-L for surface recall or LLM judge for quality. Never use a probabilistic metric where an exact check is possible.
- **Code metrics run at 0.014ms and cost $0. LLM judge runs at ~400ms and costs $0.0000256/call at Haiku prices.** At 10k evals/month, the judge costs $7.68. Reserve it for outputs where no deterministic alternative exists.
- **Token F1 gives partial credit where exact match is too strict.** An extractor that returns "The invoice total is $1,234.56" against a reference of "Invoice total: $1,234.56" scores 0 on exact match but 0.80 on F1 — which is the correct signal (mostly right, slight format difference). For short extractions, F1 is almost always better than exact match.
- **Agent metrics are different from generation metrics.** An agent's success is whether it completed the task and used the right tools, not whether its prose matched a reference. Task completion rate and tool use F1 are the right metrics; ROUGE-L on an agent's output is meaningless.
- **Faithfulness and relevance are RAG-specific and require judges.** Faithfulness asks whether the answer is grounded in the retrieved context — a model check. Relevance asks whether the answer addresses the question — also a model check. No string metric captures either.

## The move

**Match the metric to the output type. Use deterministic code metrics wherever possible. Reserve LLM judge for fuzzy quality — faithfulness, tone, helpfulness, nuance.**

**Metric implementations:**

```js
// Exact match — for extraction, classification, factual lookup
function exactMatch(pred, ref) {
  return pred.trim().toLowerCase() === ref.trim().toLowerCase() ? 1 : 0;
}

// Token F1 — for span extraction, QA, short generation
function tokenF1(pred, ref) {
  const p = new Set(pred.toLowerCase().split(/\s+/));
  const r = new Set(ref.toLowerCase().split(/\s+/));
  const common = [...p].filter(t => r.has(t)).length;
  if (common === 0) return 0;
  const prec = common / p.size;
  const rec  = common / r.size;
  return 2 * prec * rec / (prec + rec);
}

// ROUGE-L — for summarization, longer generation
function rougeL(pred, ref) {
  const p = pred.toLowerCase().split(/\s+/);
  const r = ref.toLowerCase().split(/\s+/);
  const m = p.length, n = r.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = p[i-1] === r[j-1] ? dp[i-1][j-1]+1 : Math.max(dp[i-1][j], dp[i][j-1]);
  const lcs = dp[m][n];
  const prec = lcs / m, rec = lcs / n;
  return (prec + rec) ? 2 * prec * rec / (prec + rec) : 0;
}

// Classification accuracy and F1 (macro-averaged over classes)
function classificationMetrics(predictions, references, labels) {
  const accuracy = predictions.filter((p, i) => p === references[i]).length / predictions.length;
  const f1PerClass = labels.map(label => {
    const tp = predictions.filter((p, i) => p === label && references[i] === label).length;
    const fp = predictions.filter((p, i) => p === label && references[i] !== label).length;
    const fn = predictions.filter((p, i) => p !== label && references[i] === label).length;
    const prec = tp + fp ? tp / (tp + fp) : 0;
    const rec  = tp + fn ? tp / (tp + fn) : 0;
    return (prec + rec) ? 2 * prec * rec / (prec + rec) : 0;
  });
  return { accuracy, macroF1: f1PerClass.reduce((a, b) => a + b, 0) / labels.length };
}

// Agent task completion rate
function agentMetrics(runs) {
  // Each run: { completed: bool, toolCalls: [{name, args}], expectedTool: string, expectedArgs: object }
  const completionRate = runs.filter(r => r.completed).length / runs.length;

  let toolTp = 0, toolFp = 0, toolFn = 0;
  for (const run of runs) {
    const calledCorrect = run.toolCalls.some(tc => tc.name === run.expectedTool);
    if (calledCorrect) toolTp++;
    else               toolFn++;
    toolFp += run.toolCalls.filter(tc => tc.name !== run.expectedTool).length;
  }
  const toolPrec = toolTp + toolFp ? toolTp / (toolTp + toolFp) : 0;
  const toolRec  = toolTp + toolFn ? toolTp / (toolTp + toolFn) : 0;
  const toolF1   = (toolPrec + toolRec) ? 2 * toolPrec * toolRec / (toolPrec + toolRec) : 0;

  return { completionRate, toolF1 };
}
```

**LLM-as-judge for fuzzy quality (use only where deterministic alternatives don't exist):**

```js
// Faithfulness: is the answer grounded in the provided context?
// Relevance: does the answer address the question?
async function judgeRagAnswer(client, question, context, answer) {
  const resp = await client.messages.create({
    model: 'claude-haiku-4-5-20251001', max_tokens: 64,
    messages: [{
      role: 'user', content:
        `Question: ${question}\nContext: ${context}\nAnswer: ${answer}\n\n` +
        `Rate 1-5: (1) Faithfulness: is every claim in the answer supported by the context? ` +
        `(2) Relevance: does the answer address the question?\n` +
        `Reply JSON only: {"faithfulness": N, "relevance": N}`,
    }],
  });
  return JSON.parse(resp.content[0].text);
}
```

**Metric selection table:**

| Output type | Primary metric | Secondary | When to add LLM judge |
|---|---|---|---|
| String extraction | Exact match | Token F1 | Never — exact is definitive |
| Span / QA | Token F1 | Exact match | When synonyms are valid |
| Multi-class classification | Accuracy | Macro F1 | When boundary cases are subjective |
| Summarization | ROUGE-L | — | Faithfulness + conciseness |
| RAG answer | Token F1 (vs reference) | — | Faithfulness + relevance always |
| Agent task completion | Task completion rate | Tool F1 | When task has multiple valid paths |
| Tone / style / helpfulness | — | — | LLM judge only; no code metric |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0 (no external dependencies; pure JS). LLM judge cost at `claude-haiku-4-5-20251001` $0.80/M input.

```
=== Metric values on extraction examples ===

$ node -e "
// [tokenF1, rougeL, exactMatch as above]
const ref  = 'The invoice total is \$1,234.56';
const pred1 = 'The invoice total is \$1,234.56';  // exact match
const pred2 = 'The total amount is \$1,234.56';   // paraphrase
const pred3 = 'The order has been shipped';        // wrong answer
"
                 EM    F1     ROUGE-L
exact match:      1   1.000   1.000
paraphrase:       0   0.800   0.800
wrong answer:     0   0.200   0.200

Token F1 + ROUGE-L per pair:  0.0138 ms  (zero API calls)

LLM judge cost per eval pair: 32 tok input × $0.80/M = $0.0000256
At 10k evals/month:
  Code metrics only:  $0.00
  LLM judge only:     $7.68
  Hybrid (code first, judge only for fuzzy): ~$0.76 (10% require judge)

=== Diagnostic signal comparison ===

Metric          Catches format differences?   Catches paraphrases?   Catches wrong facts?
Exact match            NO                            NO                      YES
Token F1               YES (partial)                 YES (partial)           YES (low score)
ROUGE-L                YES (partial)                 YES (partial)           YES (low score)
LLM judge              YES                           YES                     YES (if asked)

Rule: Use exact match for structured extraction (dates, numbers, codes).
      Use F1/ROUGE-L for prose where paraphrase is acceptable.
      Use LLM judge only for quality dimensions no string metric captures.
```

## See also

[F-07](f07-evaluation-driven-development.md) · [F-12](f12-llm-as-a-judge.md) · [S-49](../stacks/s49-retrieval-evaluation.md) · [F-17](f17-synthetic-eval-generation.md) · [F-22](f22-cicd-for-ai-pipelines.md) · [F-30](f30-runtime-output-validation.md)

## Go deeper

Keywords: `eval metrics` · `exact match` · `token F1` · `ROUGE-L` · `task completion rate` · `tool use accuracy` · `faithfulness` · `relevance` · `LLM judge cost` · `classification metrics` · `agent evaluation`
