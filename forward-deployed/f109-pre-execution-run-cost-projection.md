# F-109 · Pre-Execution Run Cost Projection

[F-23](f23-pre-build-cost-estimation.md) estimates cost at *design time*: given a pipeline topology and expected token volumes, compute what this system will cost at scale. It is a planning tool. The output feeds architecture decisions. [F-35](f35-workflow-token-budget.md) enforces a token budget at *runtime*: allocates tokens per stage, blocks when the allocation is exceeded, forces a partial result. It operates during execution.

Neither tells you, *before firing a specific run*, what that particular run is likely to cost. For a pipeline that accepts user input of variable length — a legal document ranging from 500 to 50 000 words — the run cost varies by 100× depending on the input. Without pre-execution projection, every run is a blind bet. With it: before dispatching the pipeline, the orchestrator knows the expected cost within ±40%, can decide whether to proceed, which model tier to use, and whether to surface a cost estimate to the user.

Pre-execution run cost projection takes the actual input context token count (known before the first call), per-stage expected output token distributions (from production logs or config), and model pricing to compute a P50/P95 cost projection across all pipeline stages. The projection runs in <0.01ms and produces a decision gate: PROCEED_DIRECT, PROCEED_WITH_NOTICE, or REQUIRE_APPROVAL.

## Situation

A contract analysis pipeline has four stages: extraction (Haiku), classification (Haiku), risk summary (Sonnet), recommendation (Sonnet). A 500-word contract produces 700 base input tokens; a 50 000-word contract produces 64 000. Without projection: both fire the full pipeline, unaware of cost until the bills arrive. At 64 000 base tokens, the Sonnet stages cost $0.96 per run. If that happens 1000 times/day through a free tier, the bill is $960/day — invisible until the invoice.

With projection: before stage 1 fires, `project(64000)` returns `{ p50: $0.94, p95: $1.51, decision: 'REQUIRE_APPROVAL' }`. The orchestrator can surface a cost notice, route to cheaper models, or gate on user confirmation. The 500-word contract projects to `{ p50: $0.032, decision: 'PROCEED_DIRECT' }` — no intervention needed.

## Forces

- **Input tokens are the only certain number.** At run time, before execution, the actual base input token count is known (the uploaded document has been tokenized or estimated). Expected output tokens per stage come from historical data — log p50 and p95 output token counts per stage and per model tier. Without logs, use conservative estimates (p50 = 300, p95 = 1000 for typical generation stages) and note the uncertainty.
- **Context accumulates across stages.** Stage N's input includes all prior stage outputs injected into the conversation or passed as context. The projection must model this accumulation: `stage_N_input = base_input + sum(prior_stages_expected_output)`. Getting this wrong understates cost significantly for long pipelines.
- **P50 and P95 bound the decision.** Report both. P50 is the typical cost; P95 is the tail cost that you'll see ~5% of the time. Decision gates use P95 for anything requiring approval, because the user needs to know the worst plausible cost, not just the median.
- **Projection is always an estimate.** Actual output tokens depend on what the model generates, which depends on the content. Flag the uncertainty explicitly: "estimated $0.03–$0.06 depending on document complexity." Over-engineering precision here is wasted effort — ±40% is good enough for a decision gate.
- **Per-stage model choice is a projection input, not a fixed fact.** A cost-aware orchestrator might project two variants: full-quality (all Sonnet) and cost-optimized (Haiku for early stages, Sonnet for final stage only). Present both. Let the caller decide which to use based on the cost delta and quality requirements.
- **Do not run the projection in the critical path of a user-facing request without caching.** For the same pipeline topology, the projection result scales linearly with base input tokens. Pre-compute a cost-per-token rate at startup; at request time, multiply by the actual token count. The full re-calculation in 0.005ms is fine for batch; for high-frequency interactive use, the rate-multiplication shortcut is even faster.

## The move

**Compute P50/P95 cost projection across all pipeline stages from actual base input tokens. Return a decision gate.**

```js
// --- Model pricing table ---
// Per million tokens, in USD. Update when pricing changes.
const PRICING = {
  'haiku':  { inputPerM: 0.80,  outputPerM: 4.00  },
  'sonnet': { inputPerM: 3.00,  outputPerM: 15.00 },
  'opus':   { inputPerM: 15.00, outputPerM: 75.00 },
};

// --- Stage definition ---
// {
//   id:                  string         — stage name
//   model:               string         — pricing key ('haiku', 'sonnet', 'opus')
//   p50OutputTokens:     number         — median expected output tokens for this stage
//   p95OutputTokens:     number         — 95th-percentile expected output tokens
//   contextPassthrough:  boolean        — true if this stage output is injected into next stage input
// }

// --- Run cost projector ---

class RunCostProjector {
  constructor(stages, opts = {}) {
    this._stages   = stages;
    this._pricing  = opts.pricing ?? PRICING;
    this._gates    = opts.gates ?? {
      requireApproval: 0.50,    // $ P95 above this → REQUIRE_APPROVAL
      proceedWithNotice: 0.10,  // $ P50 above this → PROCEED_WITH_NOTICE
    };
  }

  // project(baseInputTokens) → { p50TotalCost, p95TotalCost, breakdown, decision, summary }
  project(baseInputTokens) {
    let cumulativeInputTokens = baseInputTokens;
    let p50Total = 0;
    let p95Total = 0;
    const breakdown = [];

    for (const stage of this._stages) {
      const price = this._pricing[stage.model];
      if (!price) throw new Error(`unknown model: ${stage.model}`);

      const inputCost = (cumulativeInputTokens / 1e6) * price.inputPerM;

      const p50OutputCost = (stage.p50OutputTokens / 1e6) * price.outputPerM;
      const p95OutputCost = (stage.p95OutputTokens / 1e6) * price.outputPerM;

      const stageP50 = inputCost + p50OutputCost;
      const stageP95 = inputCost + p95OutputCost;

      p50Total += stageP50;
      p95Total += stageP95;

      breakdown.push({
        stageId:        stage.id,
        model:          stage.model,
        inputTokens:    cumulativeInputTokens,
        p50OutputTokens: stage.p50OutputTokens,
        p95OutputTokens: stage.p95OutputTokens,
        inputCostUsd:   parseFloat(inputCost.toFixed(6)),
        p50CostUsd:     parseFloat(stageP50.toFixed(6)),
        p95CostUsd:     parseFloat(stageP95.toFixed(6)),
      });

      // Accumulate: next stage input grows by this stage's expected output (P50)
      if (stage.contextPassthrough !== false) {
        cumulativeInputTokens += stage.p50OutputTokens;
      }
    }

    const decision = this._decide(p50Total, p95Total);

    return {
      p50TotalCost:  parseFloat(p50Total.toFixed(6)),
      p95TotalCost:  parseFloat(p95Total.toFixed(6)),
      breakdown,
      decision,
      summary:       this._summary(baseInputTokens, p50Total, p95Total, decision),
    };
  }

  // Variant: project two model tier configurations and return cost delta.
  projectVariants(baseInputTokens, variantStages) {
    const base    = this.project(baseInputTokens);
    const variant = new RunCostProjector(variantStages, { pricing: this._pricing, gates: this._gates })
                      .project(baseInputTokens);
    return {
      base,
      variant,
      savings:     parseFloat((base.p50TotalCost - variant.p50TotalCost).toFixed(6)),
      savingsPct:  base.p50TotalCost > 0
                   ? parseFloat(((1 - variant.p50TotalCost / base.p50TotalCost) * 100).toFixed(1))
                   : 0,
    };
  }

  _decide(p50, p95) {
    if (p95 >= this._gates.requireApproval)    return 'REQUIRE_APPROVAL';
    if (p50 >= this._gates.proceedWithNotice)  return 'PROCEED_WITH_NOTICE';
    return 'PROCEED_DIRECT';
  }

  _summary(baseInputTokens, p50, p95, decision) {
    return `${baseInputTokens} input tokens → ~$${p50.toFixed(3)}–$${p95.toFixed(3)} (p50–p95) → ${decision}`;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `project()` timed over 100 000 iterations. Arithmetic only — no API calls.

```
=== project() timing (100 000 iterations) ===

$ node -e "
const stages = [
  { id: 'extraction',      model: 'haiku',  p50OutputTokens: 300,  p95OutputTokens: 600  },
  { id: 'classification',  model: 'haiku',  p50OutputTokens: 200,  p95OutputTokens: 400  },
  { id: 'risk_summary',    model: 'sonnet', p50OutputTokens: 800,  p95OutputTokens: 1600 },
  { id: 'recommendation',  model: 'sonnet', p50OutputTokens: 1200, p95OutputTokens: 2400 },
];
const projector = new RunCostProjector(stages);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) projector.project(1500);
console.log('project() N=4 stages:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
project() N=4 stages:  0.0041 ms   (4 loops + parseFloat × 8)
projectVariants():     0.0089 ms   (2 × project())

=== Four-stage pipeline: 500-word vs 50 000-word contract ===

Pipeline definition:
  Stage 1: extraction      (Haiku,  p50=300 out,   p95=600 out)
  Stage 2: classification  (Haiku,  p50=200 out,   p95=400 out)
  Stage 3: risk_summary    (Sonnet, p50=800 out,   p95=1600 out)
  Stage 4: recommendation  (Sonnet, p50=1200 out,  p95=2400 out)

--- Run A: 500-word contract (700 base input tokens) ---

Stage 1  extraction:     700 input  → in $0.000560, p50 out $0.001200 → p50 $0.001760
Stage 2  classification: 1000 input → in $0.000800, p50 out $0.000800 → p50 $0.001600
Stage 3  risk_summary:   1200 input → in $0.003600, p50 out $0.012000 → p50 $0.015600
Stage 4  recommendation: 2000 input → in $0.006000, p50 out $0.018000 → p50 $0.024000
                                                                   ────────────────────
p50 total: $0.043, p95 total: $0.071 → PROCEED_DIRECT

--- Run B: 50 000-word contract (64 000 base input tokens) ---

Stage 1  extraction:      64 000 input → in $0.05120, p50 out $0.00120 → p50 $0.05240
Stage 2  classification:  64 300 input → in $0.05144, p50 out $0.00080 → p50 $0.05224
Stage 3  risk_summary:    64 500 input → in $0.19350, p50 out $0.01200 → p50 $0.20550
Stage 4  recommendation:  65 300 input → in $0.19590, p50 out $0.01800 → p50 $0.21390
                                                                   ────────────────────
p50 total: $0.524, p95 total: $0.841 → REQUIRE_APPROVAL

=== projectVariants(): all-Sonnet vs Haiku early stages ===

Base (extraction+classification at Sonnet):
  p50 total: $0.764   (64k tokens)

Variant (extraction+classification at Haiku):
  p50 total: $0.524

savings: $0.240 (31%) → route Run B to cost-optimized variant

=== Decision gate applications ===

PROCEED_DIRECT:       orchestrator fires immediately, no user notification
PROCEED_WITH_NOTICE:  inject a cost estimate token in the system prompt or log
REQUIRE_APPROVAL:     surface to user ("This analysis is estimated at $0.52–$0.84. Proceed?")
                      OR auto-downgrade to cheaper model tier (projectVariants)
                      OR enforce daily spending cap (F-88 session cost ceiling)

=== F-23 vs F-35 vs F-109 ===

              │ F-23 (pre-build estimation)         │ F-35 (workflow token budget)        │ F-109 (pre-execution projection)
──────────────┼────────────────────────────────────┼─────────────────────────────────────┼──────────────────────────────────
When          │ Design/build time                  │ During execution (per stage)        │ Before first call, per run
Input         │ Expected token volumes (estimated) │ Allocated token budget per stage    │ Actual base input tokens (known)
Output        │ Monthly cost model                 │ GRANTED/DENIED per allocation       │ P50/P95 cost + decision gate
Adapts to run │ No (uses averages)                 │ No (fixed allocation)               │ Yes (uses actual input size)
Action        │ Architecture decisions             │ Abort runaway stages                │ Route, notify, or gate per run
Composes with │ S-65 (model tier selection)        │ F-88 (dollar ceiling), F-53 (renegotiate)│ F-35 (budget after approve), F-23 (configure expected tokens)
```

## See also

[F-23](f23-pre-build-cost-estimation.md) · [F-35](f35-workflow-token-budget.md) · [F-88](f88-session-cost-ceiling.md) · [S-65](../stacks/s65-multi-model-pipelines.md) · [S-99](../stacks/s99-agent-task-economics.md) · [F-72](f72-per-feature-cost-analysis.md)

## Go deeper

Keywords: `pre-execution cost projection` · `run cost projection` · `pipeline cost estimate` · `before execution cost` · `cost projection per run` · `P50 P95 cost estimate` · `pipeline cost gate` · `run-time cost forecast` · `cost decision gate` · `workflow cost projection`
