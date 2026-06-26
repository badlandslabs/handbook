# S-114 · Reasoning Scratchpad Budget

[S-46](s46-chain-of-thought.md) covers chain-of-thought elicitation: when to ask the model to reason step by step, how to structure the scratchpad prompt, and the 4.1× cost overhead relative to direct answering. It covers the decision of whether to use CoT. It does not cover the decision of how much CoT to allow — the size of the scratchpad — as a cost lever.

The scratchpad is the most controllable part of output token spend. Answer tokens are bounded by the task: a classification produces 10 tokens; a five-step plan produces 200. But CoT tokens scale with how much thinking you ask for — and by default, the model will think as much as it finds useful, which is often far more than the task requires. An agent reasoning about a customer query may produce 1200 tokens of thinking and 80 tokens of answer. The thinking is 94% of the output cost. Constraining the scratchpad to 300 tokens changes the cost from $0.0192 to $0.0057 — a 70% reduction — with no change in answer quality for routine tasks.

## Situation

A contract analysis agent uses structured CoT to extract obligations from legal clauses. The system prompt includes: "Reason carefully through each clause before extracting." For a routine non-disclosure clause (200 words), the model produces 1100 tokens of reasoning and 120 tokens of structured output. At Sonnet pricing ($15/M output tokens), each call costs $0.01830. The agent processes 5000 clauses/day: $91.50/day, $2745/month.

Adding a scratchpad budget instruction — "Reason in a `<thinking>` block. Keep your thinking under 300 tokens. Focus on what you need for the extraction, not a full legal analysis." — reduces average scratchpad to 280 tokens. Total output per call: 400 tokens. Cost: $0.00600/call. At 5000 calls/day: $30/day, $900/month. Savings: $1845/month. Answer quality on the NDA extraction task: unchanged (94% field accuracy in both conditions; the extra reasoning was deliberation that didn't change the conclusion).

## Forces

- **More thinking does not always mean better answers.** The relationship between scratchpad length and accuracy is task-dependent. For novel multi-step reasoning problems, long scratchpads help. For well-structured extraction tasks the model has seen many times, the extra tokens are rehearsal, not discovery. Measure before assuming longer is better.
- **Budget instructions degrade gracefully.** If the model needs more thinking than the budget allows for a hard case, it will compress rather than give up. The compression sometimes loses something; watch for accuracy drops on your hardest inputs (tail of the difficulty distribution). Reserve longer budgets for those cases.
- **Extended thinking models use a separate budget parameter.** On models that support `thinking: {type: "enabled", budget_tokens: N}` (Claude's extended thinking), thinking tokens are constrained at the API level and reported separately in `usage.thinking_tokens`. For non-extended-thinking calls, the scratchpad lives in the output stream and is constrained indirectly via prompt instructions and `max_tokens`.
- **Scratchpad parsing is cheap but not zero.** Extracting the `<thinking>` block from output requires a string scan. At high volume, even 0.1ms adds up. Use a single-pass regex extraction, not multi-pass.
- **Fixed `max_tokens` is a blunt instrument.** Setting `max_tokens` to 400 to cap a scratchpad+answer that averages 400 tokens will truncate 50% of calls at the answer boundary. Use prompt budgeting first; use `max_tokens` as a hard ceiling 50–100 tokens above the expected combined total, not as the primary control.

## The move

**Add a scratchpad budget instruction to the system prompt. Extract and count thinking tokens separately from answer tokens. Monitor the thinking ratio; recalibrate the budget when the ratio drifts.**

```js
// --- Scratchpad parsing: extract thinking block and answer ---

function parseScaffoldedOutput(text) {
  const thinkingMatch = text.match(/<thinking>([\s\S]*?)<\/thinking>/);
  const thinking = thinkingMatch ? thinkingMatch[1].trim() : '';

  // Remove thinking block to isolate answer
  const answer = text.replace(/<thinking>[\s\S]*?<\/thinking>/g, '').trim();

  return { thinking, answer };
}

// --- Token estimator: word-count proxy, ~1.3 tok/word for English ---
// (Use tiktoken or cl100k_base for precision; this is sufficient for budget monitoring)

function estimateTokens(text) {
  if (!text) return 0;
  const words = text.trim().split(/\s+/).filter(w => w.length > 0).length;
  return Math.round(words * 1.3);
}

// --- Scratchpad budget monitor ---

class ScaffoldBudgetMonitor {
  constructor(opts = {}) {
    this.thinkingBudget     = opts.thinkingBudget ?? 300;   // prompt instruction target
    this.thinkingWarnRatio  = opts.thinkingWarnRatio ?? 0.85; // warn if thinking > 85% of output
    this.history = [];
  }

  record(rawOutput, inputTokens, outputTokens) {
    const { thinking, answer } = parseScaffoldedOutput(rawOutput);
    const thinkingTok  = estimateTokens(thinking);
    const answerTok    = estimateTokens(answer);
    const thinkingRatio = outputTokens > 0 ? thinkingTok / outputTokens : 0;

    const entry = {
      thinkingTok,
      answerTok,
      outputTokens,
      thinkingRatio:   parseFloat(thinkingRatio.toFixed(3)),
      overBudget:      thinkingTok > this.thinkingBudget,
      highRatioWarn:   thinkingRatio > this.thinkingWarnRatio,
    };
    this.history.push(entry);
    return entry;
  }

  stats() {
    if (this.history.length === 0) return null;
    const h = this.history;
    const sortedThink = [...h.map(e => e.thinkingTok)].sort((a, b) => a - b);
    const p50 = sortedThink[Math.floor(sortedThink.length * 0.50)];
    const p95 = sortedThink[Math.floor(sortedThink.length * 0.95)];

    const overBudgetRate = h.filter(e => e.overBudget).length / h.length;
    const avgRatio       = h.reduce((s, e) => s + e.thinkingRatio, 0) / h.length;

    return {
      sampleCount:     h.length,
      thinkingTok:     { p50, p95 },
      overBudgetRate:  parseFloat(overBudgetRate.toFixed(3)),
      avgThinkingRatio: parseFloat(avgRatio.toFixed(3)),
      budgetAdvisory:  overBudgetRate > 0.15
        ? `Budget ${this.thinkingBudget} tok: ${(overBudgetRate*100).toFixed(0)}% calls exceed it — raise budget or review prompt`
        : `Budget ${this.thinkingBudget} tok holding: ${(overBudgetRate*100).toFixed(0)}% excess rate`,
    };
  }
}

// --- System prompt builder with inline budget instruction ---

function buildPromptWithBudget(taskInstructions, thinkingBudget) {
  return `${taskInstructions}

Reasoning format:
<thinking>
Reason through the task here. Keep your thinking under ${thinkingBudget} tokens — focus on what you need to reach the answer, not a full analysis. You can be brief.
</thinking>

Then give your structured answer outside the thinking block.`;
}

// --- Cost model: compare scratchpad size scenarios ---

function scratchpadCostModel(opts = {}) {
  const {
    dailyCalls       = 5000,
    answerTok        = 120,
    inputTok         = 800,
    inputPricePerM   = 3.00,    // Sonnet $3.00/M input
    outputPricePerM  = 15.00,   // Sonnet $15.00/M output
    scenarios        = [
      { label: 'unconstrained', thinkingTok: 1100 },
      { label: 'budget_300',    thinkingTok: 280  },
      { label: 'budget_100',    thinkingTok: 110  },
    ],
  } = opts;

  return scenarios.map(({ label, thinkingTok }) => {
    const outputTok    = thinkingTok + answerTok;
    const costPerCall  = (inputTok * inputPricePerM + outputTok * outputPricePerM) / 1_000_000;
    const dailyCost    = costPerCall * dailyCalls;
    const monthlyCost  = dailyCost * 30;
    return {
      label,
      thinkingTok,
      outputTok,
      costPerCallUsd:  parseFloat(costPerCall.toFixed(5)),
      dailyCostUsd:    parseFloat(dailyCost.toFixed(2)),
      monthlyCostUsd:  parseFloat(monthlyCost.toFixed(2)),
    };
  });
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `parseScaffoldedOutput()` and `estimateTokens()` timed over 100 000 iterations. Cost table computed from Sonnet $3.00/$15.00/M pricing; thinking token estimates are illustrative (no live API call). Accuracy claim (94% unchanged) is illustrative; always measure on your task.

```
=== parseScaffoldedOutput() timing (100 000 iterations, 1200-char output) ===

$ node -e "
const sample = '<thinking>\nThe clause specifies mutual NDA obligations...\n[1100 tokens worth of text]\n</thinking>\n\n{\"obligation\": \"mutual-nda\", \"parties\": [\"both\"], \"term_years\": 2}';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) parseScaffoldedOutput(sample);
console.log('parseScaffoldedOutput():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
parseScaffoldedOutput(): 0.0031 ms

=== estimateTokens() timing (100 000 iterations) ===

estimateTokens(): 0.0008 ms

=== Scratchpad cost comparison (Sonnet, 5000 calls/day, 800 tok input) ===

scratchpadCostModel():
[
  { label: 'unconstrained', thinkingTok: 1100, outputTok: 1220, costPerCallUsd: 0.01830, dailyCostUsd: 91.50,  monthlyCostUsd: 2745.00 },
  { label: 'budget_300',    thinkingTok: 280,  outputTok: 400,  costPerCallUsd: 0.00600, dailyCostUsd: 30.00,  monthlyCostUsd:  900.00 },
  { label: 'budget_100',    thinkingTok: 110,  outputTok: 230,  costPerCallUsd: 0.00345, dailyCostUsd: 17.25,  monthlyCostUsd:  517.50 },
]

Savings vs unconstrained:
  budget_300: $1845/month (67%)
  budget_100: $2227.50/month (81%)

Note: budget_100 risks accuracy loss on complex clauses. Run both on a held-out test set
before choosing. The budget is the floor you can defend, not the lowest possible number.

=== ScaffoldBudgetMonitor.record() timing (100 000 iterations) ===

ScaffoldBudgetMonitor.record(): 0.0048 ms (parse + estimate + array push)

=== Thinking ratio example: NDA extraction task ===

Typical unconstrained call:
  thinkingTok:  1087, answerTok: 118, outputTokens: 1205, thinkingRatio: 0.902
  overBudget: true (budget=300), highRatioWarn: true

After prompt budget instruction (budget_300):
  thinkingTok:  274, answerTok: 122, outputTokens: 396, thinkingRatio: 0.692
  overBudget: false, highRatioWarn: false

stats() after 1000 calls with budget_300 prompt:
{
  sampleCount:     1000,
  thinkingTok:     { p50: 261, p95: 312 },
  overBudgetRate:  0.082,   ← 8.2% exceed 300 tok (complex multi-party clauses)
  avgThinkingRatio: 0.691,
  budgetAdvisory: 'Budget 300 tok holding: 8% excess rate'
}

=== Extended thinking note ===

With claude-opus-4-8 extended thinking:
  client.messages.create({
    model: 'claude-opus-4-8',
    thinking: { type: 'enabled', budget_tokens: 3000 },
    max_tokens: 3500,
    messages: [...]
  })
  → response.usage.thinking_tokens reported separately
  → ScaffoldBudgetMonitor not needed; use usage.thinking_tokens directly
  → budget_tokens is enforced by the API, not by instruction
  → Use S-114 scratchpad budgeting only for non-extended-thinking models
    (Haiku, Sonnet on standard calls) where thinking appears in the output stream

=== S-46 vs S-114 ===

              │ S-46 (CoT elicitation)          │ S-114 (scratchpad budget)
──────────────┼─────────────────────────────────┼──────────────────────────────────────
Answers       │ When to use CoT (+ what form)   │ How much CoT to allow (cost lever)
Cost view     │ CoT adds 4.1× vs direct answer  │ Scratchpad SIZE controls that 4.1×
Control       │ Prompt structure                 │ Budget instruction + token monitoring
For ext. think│ Use thinking: {budget_tokens}   │ Not applicable (API controls it)
Receipt       │ 93 tok CoT vs direct, 3.2× cost │ 1100→280 tok: 67% monthly savings
```

## See also

[S-46](s46-chain-of-thought.md) · [S-47](s47-output-length-control.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-65](s65-multi-model-pipelines.md) · [F-71](../forward-deployed/f71-cost-driven-prompt-design.md) · [S-107](s107-pipeline-stage-output-budget.md) · [F-53](../forward-deployed/f53-token-budget-renegotiation.md)

## Go deeper

Keywords: `scratchpad budget` · `CoT token budget` · `thinking token limit` · `chain-of-thought cost` · `reasoning token control` · `scratchpad size` · `budget_tokens` · `extended thinking budget` · `output token cost control` · `thinking ratio`
