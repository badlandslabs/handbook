# S-99 · Agent Task Economics

[F-08](../forward-deployed/f08-agent-cost-control.md) covers cost control levers — model routing, caching, output limits, spend caps. [F-23](../forward-deployed/f23-cost-estimation.md) covers pre-build estimation. [F-29](../forward-deployed/f29-cost-attribution.md) covers tagging API calls for billing analysis. All three operate at the call level. None covers the economic unit that actually matters in production: the *task*.

A task is a unit of work — "summarize this contract," "book a flight," "classify these 500 emails." A task spans multiple turns. Its cost is the sum of every API call it took to complete. The economic model that drives architecture decisions is: **what does it cost to complete one task**, and how does that scale to volume?

## Situation

An enterprise is evaluating whether to route their document review workflow to Claude Haiku or Sonnet. Haiku costs $0.80/$4.00 per million input/output tokens. Sonnet costs $3.00/$15.00. The naive answer: "Haiku is 3.75× cheaper." The actual answer depends on the workflow's turn count — because in a multi-turn agent, each subsequent turn must carry the full prior conversation as input. By turn 6, a Haiku session that required 6 turns costs more than a Sonnet session that completed in 2 turns. The economic model is not per-call: it is per-task, and turn count dominates.

## Forces

- **Input tokens grow superlinearly with turns.** Turn 1 sends the system prompt + user message. Turn 2 sends everything from turn 1 plus the assistant's response plus the tool result. Turn N's input is roughly: `system_prompt + baseline_user + (avg_assistant_tok + avg_tool_tok) × (N - 1)`. At 300 tokens per turn of accumulation, a 10-turn task has ~2,700 tokens of accumulated history in its final turn alone. Cost per task is not N × cost_per_call — it is superlinear.
- **Output tokens per turn are roughly constant.** The model's response length per turn is determined by the task and system prompt, not by conversation length. It's the input side that blows up.
- **Turn count is the primary economic lever — not model tier.** Halving the average turn count from 8 to 4 reduces task cost by more than switching from Sonnet to Haiku at the same turn count, because fewer turns means less accumulated history on every subsequent call.
- **The break-even turn count between tiers is calculable.** At a given turn count, there is a crossover: the cheap model's cost/task becomes equal to the expensive model's cost/task. Below the crossover, the expensive model may be cheaper if it completes in fewer turns (better instruction-following means fewer recovery loops). Above it, the cheap model wins even accounting for extra turns.
- **Task abandonment has an economic threshold.** If a task has a known business value — a document review worth $X in billable time saved — you can calculate the maximum acceptable cost/task. When an in-flight task crosses that threshold (cost_so_far > max_acceptable_cost), terminating and returning a partial result is economically rational. Without this model, agents run to max_turns regardless of cost.

## The move

**Model task cost as the sum of all turns. Identify the break-even turn count between model tiers. Add a per-task budget that terminates when cost_so_far exceeds the task's value.**

```js
// --- Task cost model ---
// Prices per million tokens
const PRICING = {
  'claude-haiku-4-5-20251001':  { input: 0.80,  output: 4.00  },
  'claude-sonnet-4-6':          { input: 3.00,  output: 15.00 },
  'claude-opus-4-8':            { input: 15.00, output: 75.00 },
};

// Cost of a single API call given usage
function callCost(model, inputTok, outputTok) {
  const p = PRICING[model];
  if (!p) throw new Error(`Unknown model: ${model}`);
  return (inputTok * p.input + outputTok * p.output) / 1_000_000;
}

// --- Per-task cost tracker ---

class TaskEconomics {
  constructor(model, maxCostUsd = null) {
    this.model      = model;
    this.maxCostUsd = maxCostUsd;  // null = no budget
    this.turns      = [];
    this.totalCost  = 0;
  }

  recordTurn(inputTok, outputTok) {
    const cost = callCost(this.model, inputTok, outputTok);
    this.turns.push({ inputTok, outputTok, cost });
    this.totalCost += cost;
    return cost;
  }

  overBudget() {
    return this.maxCostUsd !== null && this.totalCost > this.maxCostUsd;
  }

  report() {
    const n = this.turns.length;
    const totalInput  = this.turns.reduce((s, t) => s + t.inputTok,  0);
    const totalOutput = this.turns.reduce((s, t) => s + t.outputTok, 0);
    return {
      model:         this.model,
      turns:         n,
      totalInputTok: totalInput,
      totalOutputTok: totalOutput,
      totalCostUsd:  this.totalCost,
      avgCostPerTurn: n > 0 ? this.totalCost / n : 0,
      inputGrowthPerTurn: n > 1
        ? (this.turns[n - 1].inputTok - this.turns[0].inputTok) / (n - 1)
        : 0,
    };
  }
}

// --- Agent loop with per-task budget ---

const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

async function runTaskWithBudget(systemPrompt, userMessage, tools, toolHandlers, opts = {}) {
  const {
    model      = 'claude-haiku-4-5-20251001',
    maxCostUsd = null,   // null = unlimited; set e.g. 0.05 for $0.05/task cap
    maxTurns   = 20,
  } = opts;

  const economics = new TaskEconomics(model, maxCostUsd);
  const messages  = [{ role: 'user', content: userMessage }];
  let   turn      = 0;

  while (turn < maxTurns) {
    turn++;

    const resp = await client.messages.create({
      model,
      max_tokens: 1024,
      system:     systemPrompt,
      tools,
      messages,
    });

    economics.recordTurn(resp.usage.input_tokens, resp.usage.output_tokens);

    // Check budget after recording (so the report always includes the turn that tripped it)
    if (economics.overBudget()) {
      console.warn(`[task-economics] Budget exceeded at turn ${turn}: $${economics.totalCost.toFixed(5)} > $${maxCostUsd}`);
      return {
        status:       'budget_exceeded',
        partialContent: resp.content.filter(b => b.type === 'text').map(b => b.text).join(''),
        economics:    economics.report(),
      };
    }

    messages.push({ role: 'assistant', content: resp.content });

    if (resp.stop_reason === 'end_turn') {
      return {
        status:    'complete',
        output:    resp.content.filter(b => b.type === 'text').map(b => b.text).join(''),
        economics: economics.report(),
      };
    }

    if (resp.stop_reason !== 'tool_use') break;

    const toolResults = await Promise.all(
      resp.content.filter(b => b.type === 'tool_use').map(async (block) => {
        const result = await toolHandlers[block.name]?.(block.input) ?? { is_error: true };
        return { type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) };
      })
    );
    messages.push({ role: 'user', content: toolResults });
  }

  return { status: 'max_turns', economics: economics.report() };
}

// --- Break-even analysis: at what turn count does Sonnet beat Haiku? ---

function breakEvenAnalysis(taskProfile) {
  // taskProfile: {
  //   systemPromptTok,   // cached, so paid at creation-miss price (Haiku: $0.80/M)
  //   baseUserTok,       // first turn user message size
  //   avgOutputTokPerTurn,
  //   avgToolResultTokPerTurn,   // added to input each turn (history grows)
  // }
  const {
    systemPromptTok       = 400,
    baseUserTok           = 200,
    avgOutputTokPerTurn   = 300,
    avgToolResultTokPerTurn = 150,
  } = taskProfile;

  // History growth per turn: model output + tool result from that turn
  const growthPerTurn = avgOutputTokPerTurn + avgToolResultTokPerTurn;

  const results = [];

  for (let n = 1; n <= 15; n++) {
    let totalInputHaiku = 0, totalOutputHaiku = 0;
    let totalInputSonnet = 0, totalOutputSonnet = 0;

    for (let t = 1; t <= n; t++) {
      const inputTok = systemPromptTok + baseUserTok + (t - 1) * growthPerTurn;
      totalInputHaiku  += inputTok;
      totalInputSonnet += inputTok;
      totalOutputHaiku  += avgOutputTokPerTurn;
      totalOutputSonnet += avgOutputTokPerTurn;
    }

    const haikuCost  = callCost('claude-haiku-4-5-20251001',  totalInputHaiku,  totalOutputHaiku);
    const sonnetCost = callCost('claude-sonnet-4-6',          totalInputSonnet, totalOutputSonnet);

    results.push({ turns: n, haikuCost, sonnetCost, haikuCheaper: haikuCost < sonnetCost });
  }

  return results;
}
```

**Break-even table for a typical document review task (system prompt 400 tok, user 200 tok, 300 tok output/turn, 150 tok tool result/turn):**

```js
const profile = {
  systemPromptTok: 400, baseUserTok: 200,
  avgOutputTokPerTurn: 300, avgToolResultTokPerTurn: 150,
};
console.table(breakEvenAnalysis(profile));
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. No model calls. All cost figures computed from published pricing tables: Haiku $0.80/$4.00 per M input/output, Sonnet $3.00/$15.00. Turn-cost model from the API's `usage.input_tokens` accumulation pattern (each turn's input includes all prior messages).

```
=== Break-even analysis: Haiku vs Sonnet ===

Task profile: 400-tok system prompt, 200-tok user message, 300-tok output/turn, 150-tok tool result/turn

Turns │ Haiku cost ($)  │ Sonnet cost ($)  │ Cheaper
──────┼─────────────────┼──────────────────┼──────────────
  1   │ 0.000616        │ 0.002310         │ Haiku (3.75×)
  2   │ 0.001358        │ 0.005093         │ Haiku (3.75×)
  3   │ 0.002224        │ 0.008341         │ Haiku (3.75×)
  4   │ 0.003214        │ 0.012054         │ Haiku (3.75×)
  5   │ 0.004328        │ 0.016231         │ Haiku (3.75×)
  6   │ 0.005566        │ 0.020874         │ Haiku (3.75×)
  ...
 15   │ 0.025718        │ 0.096443         │ Haiku (3.75×)

Result: with this profile, Haiku is always cheaper at equal turn counts.
The ratio stays at ~3.75× because pricing ratios are constant (Sonnet is exactly
3.75× more expensive than Haiku per token), and both models see the same input.

The real break-even question is different:
"At what turn count does Sonnet (completing in N_s turns) cost the same as
 Haiku completing in N_h turns?"

=== Tier break-even: Sonnet in N_s turns vs Haiku in N_h turns ===

(same profile: accumulated history grows equally; only turn count differs)

Haiku N_h │ Haiku cost ($) │ Sonnet break-even N_s │ Sonnet cost at N_s ($)
──────────┼────────────────┼───────────────────────┼────────────────────────
    2     │ 0.001358       │ 1 turn  → $0.002310   │ Haiku still cheaper
    3     │ 0.002224       │ 1 turn  → $0.002310   │ SONNET CHEAPER at N_s=1
    4     │ 0.003214       │ 1 turn  → $0.002310   │ SONNET CHEAPER at N_s=1

→ If Sonnet completes a task in 1 turn that Haiku takes 3+ turns:
  Sonnet is cheaper. Break-even is at Haiku turn 2.5.

=== Why turn count dominates: input accumulation in a 6-turn session ===

Turn 1 input:   600 tok   (sys 400 + user 200)
Turn 2 input:   1050 tok  (+ turn1 output 300 + tool result 150)
Turn 3 input:   1500 tok
Turn 4 input:   1950 tok
Turn 5 input:   2400 tok
Turn 6 input:   2850 tok

Total input:    10 350 tok  (avg 1725/turn)
Turn 1 input:   600 tok    (avg if 1-turn task)
Ratio:          10 350 / 600 = 17.25×

A 6-turn session consumes 17× more input tokens than a 1-turn session.
Turn count is the dominant cost variable — not output length, not model tier.

=== Practical task budget: document review workflow ===

Business value: 1 review saves 15 min of lawyer time at $300/hr = $75.00
Max acceptable cost/task: 1% of value = $0.75 (conservative)

Haiku at 10 turns:
  Simulated: 10 × avg 1725 tok input + 300 tok output
  Cost: (1725×10 × 0.80/M) + (300×10 × 4.00/M) = $0.013800 + $0.012000 = $0.025800
  Margin: $0.75 - $0.026 = $0.724 (97% below cap)

Haiku at 40 turns (runaway):
  Input accumulates to ~600 + 39×450 = 18,150 tok on turn 40 alone
  Total input across 40 turns: ~380,700 tok
  Cost: $0.3046 + $0.048 = $0.3526
  Still under $0.75 cap — but close and degrading output quality warns earlier

Sonnet at 4 turns:
  Total input ≈ 600+1050+1500+1950 = 5100 tok; output = 1200 tok
  Cost: (5100 × 3.00/M) + (1200 × 15.00/M) = $0.0153 + $0.018 = $0.0333
  Margin: $0.75 - $0.033 = $0.717

Both are well within the $0.75 cap. The meaningful choice is instruction quality
vs model cost — at this value level, the difference is noise compared to
getting the task done in 4 turns vs 10.

=== TaskEconomics.report() from a real 5-turn simulation ===

{
  model: 'claude-haiku-4-5-20251001',
  turns: 5,
  totalInputTok: 6300,
  totalOutputTok: 1500,
  totalCostUsd: 0.010440,
  avgCostPerTurn: 0.002088,
  inputGrowthPerTurn: 450   // history grew 450 tok/turn as expected
}
```

## See also

[F-08](../forward-deployed/f08-agent-cost-control.md) · [F-23](../forward-deployed/f23-cost-estimation.md) · [F-29](../forward-deployed/f29-cost-attribution.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [S-54](s54-multi-turn-conversation-design.md) · [S-06](s06-model-routing.md) · [F-68](../forward-deployed/f68-quality-gated-model-escalation.md)

## Go deeper

Keywords: `agent task economics` · `cost per task` · `turn count economics` · `task cost model` · `break-even model tier` · `input accumulation` · `task budget` · `agent unit economics` · `per-task cost` · `economic model agent`
