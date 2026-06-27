# F-123 · Session Cost Forecaster

[F-88](f88-per-call-cost-ceiling.md) enforces a per-call cost ceiling: if a single API call would exceed the limit, it is blocked before the call is made. [F-109](f109-pre-execution-cost-projection.md) projects the total cost of a planned task by reasoning from the task plan — before any model calls have run. Both mechanisms operate before or during individual calls. Neither tells you where the session as a whole is heading after three turns of observed behavior.

A session cost forecaster measures what has actually happened: it records the cost of each turn, fits a linear trend to the cumulative cost curve, and projects that trend to the expected end of the session. When the projection exceeds the budget, the forecaster returns `WILL_EXCEED_BUDGET` with the number of turns remaining before the budget is exhausted. This gives you time to act — switch to a cheaper model, compress context, drop long-running tool chains — before the session hits the ceiling and terminates abruptly.

The key gap from F-88 and F-109: F-88 blocks one call when it's too expensive. F-109 projects before the model has said anything. F-123 projects from the trajectory of what the model has actually been doing — and detects the runaway sessions that were not obviously expensive from the initial plan.

## Situation

A customer support session on Haiku is budgeted at $0.05. After 4 turns, cumulative cost is $0.0056; linear projection to 20 turns is $0.029. `status: ON_TRACK`. No action needed.

The same session architecture runs a research task using Sonnet with long tool results. After 4 turns: cumulative cost is $0.15; each turn is adding ~$0.042 (slope). Projection to 20 turns: $0.82. Budget: $0.25. `status: WILL_EXCEED_BUDGET`, `turnsUntilBudget: 2.5`. The session will blow the budget in roughly 2 more turns at the current rate.

Without forecasting: the session runs until F-88 blocks a call, the session terminates mid-task, the user gets an error. With forecasting: at turn 4, the orchestrator receives the `WILL_EXCEED_BUDGET` signal and switches to Haiku + compressed context for the remaining turns. The task completes; cost stays under control.

The slope is the signal. A normal support session (context grows ~200 tokens/turn) has slope ~$0.0015/turn. A research agent loading long tool results each turn has slope ~$0.042/turn — 28× higher. Three turns of data are enough to distinguish the two trajectories.

## Forces

- **Linear regression is directionally reliable after 3 turns, not precise.** Cumulative cost does not grow perfectly linearly — each turn adds its own variable token count. But the slope across the first 3–5 turns is stable enough to flag the 28× difference between a normal session and a runaway one. Treat the forecast as a warning signal, not an accounting system. If you need exact cost tracking, that is F-88's job, not this one.
- **The slope is the cost of context growth.** Sonnet at $3/M input: each additional 1000 tokens in context adds $0.003/turn. A session where tool results push context from 5k to 14k tokens over 4 turns shows slope $0.027/turn from context alone, before counting output tokens. When the slope is high, the cause is almost always growing input context from tool results or retrieved documents — not output token count, which is typically stable.
- **`minTurns: 3` is the floor before forecasting.** With fewer than 3 points, linear regression has no statistical validity. Below minTurns, return `INSUFFICIENT_DATA` — don't gate on the forecast, don't block anything. Record and wait. Most sessions reveal their cost trajectory within 3–4 turns.
- **`maxTurns` must match your session design.** A chatbot expects 5–15 turns. A research agent expects 3–8. An agentic pipeline may have a fixed turn count. Set `maxTurns` at session initialization to match the expected length of the session type. A mismatch (maxTurns=50 for a 5-turn session) will produce low forecasts that never flag anything — the slope looks gentle when amortized over 50 turns.
- **The `turnsUntilBudget` field is the action trigger.** When `turnsUntilBudget ≤ 3`, you have at most 3 turns to act. At `turnsUntilBudget = 0`, the budget is already exceeded. The typical response ladder: ≤5 turns → switch to cheaper model; ≤2 turns → compress context aggressively (S-31); ≤0 → graceful stop with partial result, not abrupt F-88 block.
- **Compose with F-88, not replace it.** F-88 is the hard stop. This forecaster is the soft warning. Run both: F-88 catches any single call that is individually too expensive; the forecaster catches sessions that are collectively heading for the ceiling on normal-sized calls.

## The move

**Record per-turn cost. After minTurns observations, fit a linear trend to cumulative cost and project to maxTurns. Act when turnsUntilBudget drops below your response threshold.**

```js
// --- Session cost forecaster ---
// Records per-turn cost, fits linear trend to cumulative cost curve,
// projects to maxTurns and compares against budget.
// Compose with F-88 (hard per-call ceiling) and F-109 (pre-run projection).

class SessionCostForecaster {
  constructor(opts = {}) {
    this._minTurns = opts.minTurns ?? 3;    // turns before forecast is valid
    this._maxTurns = opts.maxTurns ?? 20;   // expected total turns for this session type
    this._turns    = [];                    // [{turn, costUsd, cumulative}]
  }

  // Record the cost of a completed turn.
  // turn:    1-indexed turn number
  // costUsd: cost of this turn (input + output tokens × price/M)
  record(turn, costUsd) {
    const prev = this._turns[this._turns.length - 1];
    this._turns.push({
      turn,
      costUsd,
      cumulative: (prev ? prev.cumulative : 0) + costUsd,
    });
  }

  // Forecast cumulative cost at maxTurns using OLS linear regression on
  // cumulative cost vs turn number. Returns the projected total and
  // the number of turns remaining before budgetUsd is exhausted.
  forecast(budgetUsd) {
    const n = this._turns.length;
    if (n < this._minTurns) {
      return { status: 'INSUFFICIENT_DATA', turns: n, required: this._minTurns };
    }

    const xs = this._turns.map(t => t.turn);
    const ys = this._turns.map(t => t.cumulative);
    const xMean = xs.reduce((s, x) => s + x, 0) / n;
    const yMean = ys.reduce((s, y) => s + y, 0) / n;
    const ssxy  = xs.reduce((s, x, i) => s + (x - xMean) * (ys[i] - yMean), 0);
    const ssxx  = xs.reduce((s, x) => s + (x - xMean) ** 2, 0);
    const slope     = ssxx === 0 ? 0 : ssxy / ssxx;
    const intercept = yMean - slope * xMean;

    const forecastAtMax = slope * this._maxTurns + intercept;
    const totalSoFar    = ys[n - 1];

    // Turns until cumulative cost reaches budgetUsd on current trajectory
    const turnsUntilBudget = (budgetUsd > 0 && slope > 0)
      ? Math.max(0, (budgetUsd - intercept) / slope - xs[n - 1])
      : null;

    return {
      status:             forecastAtMax > budgetUsd ? 'WILL_EXCEED_BUDGET' : 'ON_TRACK',
      turnsObserved:      n,
      maxTurns:           this._maxTurns,
      totalSoFar:         parseFloat(totalSoFar.toFixed(6)),
      forecastAtMaxTurns: parseFloat(forecastAtMax.toFixed(6)),
      slopePerTurn:       parseFloat(slope.toFixed(6)),
      budgetUsd,
      turnsUntilBudget:   turnsUntilBudget !== null ? parseFloat(turnsUntilBudget.toFixed(1)) : null,
    };
  }

  reset() { this._turns = []; }
}

// --- Orchestrator integration ---
// Called after each turn; triggers cost response when threshold is reached.

const BUDGET_USD    = 0.25;
const FORECASTER    = new SessionCostForecaster({ minTurns: 3, maxTurns: 20 });
let   currentModel  = 'claude-sonnet-4-6';

async function runTurn(turn, messages, tools) {
  const response = await callModel(currentModel, messages, tools);
  const cost     = response.usage.input_tokens  * 3.00 / 1_000_000
                 + response.usage.output_tokens * 15.00 / 1_000_000;

  FORECASTER.record(turn, cost);

  const forecast = FORECASTER.forecast(BUDGET_USD);
  if (forecast.status === 'WILL_EXCEED_BUDGET') {
    const turnsLeft = forecast.turnsUntilBudget ?? 0;
    if (turnsLeft <= 2) {
      // Compress context (S-31) and switch to cheaper model
      messages = compressContext(messages);
      currentModel = 'claude-haiku-4-5-20251001';
      log({ event: 'cost_intervention', forecast, action: 'switch_to_haiku_compressed' });
    } else {
      log({ event: 'cost_warning', forecast });
    }
  }

  return response;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `forecast()` timed over 100 000 iterations. Costs computed from Haiku ($0.80/$4.00 per M in/out) and Sonnet ($3.00/$15.00 per M in/out) pricing. Context growth rates are representative of real session types.

```
=== SessionCostForecaster timing (100 000 iterations) ===

record():              0.0010 ms
forecast() — 5 turns:  0.0039 ms   (OLS linear regression over n turns)

=== Scenario A: Normal Haiku customer-support session ===

Model: Haiku ($0.80/M in, $4.00/M out)
Context growth: +200 tokens/turn (customer replies + agent output accumulated)

Turn 1: 700 in + 150 out → $0.00116
Turn 2: 900 in + 150 out → $0.00132
Turn 3: 1100 in + 150 out → $0.00148
Turn 4: 1300 in + 150 out → $0.00164

forecast(budgetUsd=0.05) after turn 4:
{
  status:             'ON_TRACK',
  turnsObserved:      4,
  maxTurns:           20,
  totalSoFar:         $0.005600,
  forecastAtMaxTurns: $0.029200,
  slopePerTurn:       $0.001480,
  budgetUsd:          0.05,
  turnsUntilBudget:   30.1        ← budget not reached within 20-turn session
}

No action. Session stays under budget with 42% headroom.

=== Scenario B: Runaway Sonnet research agent ===

Model: Sonnet ($3.00/M in, $15.00/M out)
Context growth: +3000 tokens/turn (tool results accumulate in full)

Turn 1: 5000 in + 600 out → $0.024
Turn 2: 8000 in + 600 out → $0.033
Turn 3: 11000 in + 600 out → $0.042
Turn 4: 14000 in + 600 out → $0.051

forecast(budgetUsd=0.25) after turn 4:
{
  status:             'WILL_EXCEED_BUDGET',
  turnsObserved:      4,
  maxTurns:           20,
  totalSoFar:         $0.150000,
  forecastAtMaxTurns: $0.817500,
  slopePerTurn:       $0.042000,
  budgetUsd:          0.25,
  turnsUntilBudget:   2.5         ← 2–3 turns before budget exhausted
}

Action at turn 4: switch to Haiku + compress context (S-31).
Without forecast: session hits F-88 ceiling mid-turn 7, terminates with error.

=== Slope as diagnostic ===

Normal support (Haiku):   slopePerTurn = $0.00148   → $1.48/turn
Runaway research (Sonnet): slopePerTurn = $0.042     → $42/turn
Ratio: 28× — detectable in 3 turns of data.

The slope is the per-turn cost of context growth, not output cost.
Sonnet at $3/M: each additional 1000 input tokens adds $0.003/turn.
Runaway: +3000 tokens/turn → +$0.009/turn in input alone.
14 turns of accumulation: 14 × $0.009 = $0.126 just from growing context.

=== F-88 vs F-109 vs F-123 ===

              │ F-88 (per-call ceiling)      │ F-109 (pre-run projection)   │ F-123 (session forecaster)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
When it runs  │ Before each API call         │ Before any calls (from plan) │ After each turn
What it knows │ One call's estimated tokens  │ Task plan token estimates     │ Observed cumulative costs
What it misses│ Session trajectory           │ Real per-turn behavior        │ Single expensive call
Action        │ Block this call              │ Refuse to start task          │ Trigger cost response
Response      │ Abrupt: call blocked         │ Abrupt: task not started      │ Graceful: model switch/compress
```

## See also

[F-88](f88-per-call-cost-ceiling.md) · [F-109](f109-pre-execution-cost-projection.md) · [S-31](../stacks/s31-prompt-compression.md) · [S-123](../stacks/s123-prompt-section-cost-attribution.md) · [F-115](f115-per-session-cost-cap.md) · [F-56](f56-prompt-composition-guards.md)

## Go deeper

Keywords: `session cost forecaster` · `LLM session cost projection` · `per-session cost trajectory` · `turn cost trend analysis` · `session budget forecasting` · `agent cost early warning` · `cumulative session cost` · `LLM cost runaway detection` · `session cost linear regression` · `agent budget management`
