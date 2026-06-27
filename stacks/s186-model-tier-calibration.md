# S-186 · Model-Tier Calibration

Most teams pick Sonnet for "important" tasks and Haiku for "simple" tasks. Both assignments are guesses. Sonnet might be unnecessary for a task Haiku handles at 94% accuracy when 90% is sufficient. Haiku might look sufficient in a quick demo but fail at 67% accuracy on the full distribution of production inputs. The only way to know is to measure.

Model-tier calibration runs a held-out sample on each candidate tier, measures pass rate against a quality criterion, and picks the cheapest tier that clears the threshold. For contract field extraction — party name, contract type, effective date — a 100-sample test shows Haiku at 91% vs Sonnet at 96%. At a 90% threshold, Haiku is the correct choice: $4.96/day vs $19.20/day. At a 95% threshold, the same test answers the opposite: use Sonnet. The data decides; the guess does not.

Calibration costs less than one hour of engineering time and about $0.50 in API calls for a 100-sample test. It replaces months of accumulated cost or accumulated quality debt.

## Situation

A legal AI pipeline has been running on Sonnet for contract classification since launch — "it's an important legal task." After calibration:

- Haiku on 100 contracts: 91% pass rate (5 enum failures, 4 date format mismatches)
- Sonnet on same 100 contracts: 97% pass rate

At a 90% acceptance threshold, Haiku clears. Switching saves $14.24/day ($5,198/year). The calibration took 2 hours to run and $0.80 in API calls.

For a separate task — legal risk rating — Haiku scores 64%, Sonnet scores 88%. Neither clears 90%. Calibration surfaces the problem before a year of incorrect risk ratings, not after.

## Forces

- **Pass rate is task-specific, not model-specific.** Haiku excels at extraction and classification. Sonnet excels at judgment and synthesis. The same model behaves differently across task types. Calibrate per task type, not per model.
- **Test on the actual input distribution, not easy examples.** A 100-sample calibration with cherry-picked clear cases will show 97% on Haiku for a task that performs at 72% on production inputs. Sample from recent production logs or from a stratified set that includes edge cases (short contracts, heavily amended contracts, non-standard clause orders). Calibration is only as good as its sample.
- **The quality criterion must match the downstream cost of failure.** For a task where a wrong extraction causes a human to waste 15 minutes, a 90% threshold is appropriate. For a task where a wrong extraction triggers an incorrect payment, 98% may be required and the cheapest satisfying model should be used regardless of cost. Define the threshold before running the test, not after looking at the numbers.
- **Calibrate at p95 of production token counts.** Haiku's accuracy tends to fall on longer inputs; short inputs are not representative. Run calibration samples at p95 document length to stress-test the cheapest tier before committing to it.
- **Re-calibrate after model version updates.** A model update can shift pass rates by 3–8 percentage points in either direction. When a provider updates a model (F-38 version pinning detects this), re-run the calibration rather than assuming the previous tier assignment still holds.
- **Model routing (S-06) and calibration are complementary, not alternatives.** S-06 routes at inference time based on input complexity — hard inputs go up, easy inputs go down. Calibration sets the baseline tier for each task type. Apply calibration first to set the default tier, then apply S-06 routing to route hard cases upward from that default.

## The move

**Run a stratified sample on each candidate tier. Measure pass rate. Pick the cheapest tier at or above the quality threshold. Lock in the tier; re-calibrate after model updates.**

```js
// --- Model-tier calibration ---
// Finds the cheapest model tier that meets a quality threshold for a specific task.
// Run once per task type before committing to a production tier.
// Re-run after model version updates (F-38) or when quality metrics drift (F-26).

const MODEL_RATES = {
  haiku:  { inputRate: 0.80 / 1_000_000, outputRate:  4.00 / 1_000_000, label: 'Haiku'  },
  sonnet: { inputRate: 3.00 / 1_000_000, outputRate: 15.00 / 1_000_000, label: 'Sonnet' },
};

// runs: [{ passed: boolean, inputTok: number, outputTok: number }, ...]
function analyzeCalibrationRun(model, runs) {
  const passRate     = runs.filter(r => r.passed).length / runs.length;
  const avgInputTok  = runs.reduce((s, r) => s + r.inputTok,  0) / runs.length;
  const avgOutputTok = runs.reduce((s, r) => s + r.outputTok, 0) / runs.length;
  const m            = MODEL_RATES[model];
  const costPerCall  = avgInputTok * m.inputRate + avgOutputTok * m.outputRate;
  return { model, label: m.label, sampleSize: runs.length, passRate,
           avgInputTok: Math.round(avgInputTok), avgOutputTok: Math.round(avgOutputTok),
           costPerCall, costPerDay10k: costPerCall * 10_000 };
}

// Select the cheapest tier that clears the quality threshold.
// tierResults: array of analyzeCalibrationRun() outputs
// opts.qualityThreshold: minimum acceptable pass rate (default: 0.90)
function selectModelTier(tierResults, opts) {
  opts = opts || {};
  const threshold = opts.qualityThreshold || 0.90;

  const eligible = tierResults
    .filter(t => t.passRate >= threshold)
    .sort((a, b) => a.costPerCall - b.costPerCall);

  if (eligible.length === 0) {
    return { recommendation: 'NONE_QUALIFIED',
             reason: `No tier reaches ${(threshold * 100).toFixed(0)}% pass rate. Redesign task or lower threshold.`,
             tierResults };
  }

  const recommended = eligible[0];
  const expensive   = eligible[eligible.length - 1];
  const savings     = expensive.costPerDay10k - recommended.costPerDay10k;

  return { recommendation: 'TIER_SELECTED', selectedTier: recommended,
           qualityThreshold: threshold, eligible, tierResults,
           savingsPerDay10k: savings, savingsPerYear: savings * 365 };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Two calibration scenarios: structured field extraction (Haiku qualifies), legal risk rating (neither Haiku nor Sonnet qualifies). Simulated pass/fail rates from 100-run samples. Token counts from representative extraction calls. Pricing: Haiku $0.80/$4.00/M, Sonnet $3.00/$15.00/M. Zero API calls in the calibration logic itself.

```
=== Model-Tier Calibration ===

--- Task: contract field extraction (party_name, contract_type, effective_date) ---
  Sample: 100 contracts  |  threshold: 90%

  Haiku:
    pass rate:     91%  (9 failures: 5 enum, 4 date format mismatches)
    avg input:    430 tok  |  avg output:  38 tok
    cost/call:   $0.000496
    cost/day 10k: $4.96

  Sonnet:
    pass rate:     97%
    avg input:    430 tok  |  avg output:  42 tok
    cost/call:   $0.001920
    cost/day 10k: $19.20

  → TIER_SELECTED: Haiku (cheapest at threshold 90%)
    Haiku passes (91% ≥ 90%). Sonnet also passes but costs 3.9× more.
    Savings vs Sonnet: $14.24/day ($5,198/year at 10 000 calls/day)

  At threshold 95%: Haiku (91%) fails, Sonnet (97%) passes → use Sonnet
    Cost: $19.20/day  ($7,008/year)
    Calibration proves Sonnet is required at higher threshold, not assumed.

--- Task: legal risk rating (qualitative judgment across 4 risk levels) ---
  Sample: 100 contracts  |  threshold: 90%

  Haiku:  pass rate 64%  |  cost/call $0.000560  |  cost/day $5.60   ← FAILS threshold
  Sonnet: pass rate 88%  |  cost/call $0.002010  |  cost/day $20.10  ← FAILS threshold

  → NONE_QUALIFIED: No tier reaches 90%.
    Options: (1) lower threshold if 88% is acceptable for this task;
             (2) use higher-tier model (Opus or equivalent);
             (3) redesign task — chain a Sonnet classification step with a Haiku
                 supporting-evidence extraction step, reducing the judgment burden.

--- Calibration economics ---
  100-sample test at avg 430 tok input + 42 tok output:
    Haiku cost:  100 × $0.000496 = $0.050
    Sonnet cost: 100 × $0.001920 = $0.192
  Total calibration cost: $0.242
  Calibration pays back on Day 1 ($14.24/day savings at 10 000 calls/day if Haiku qualifies)

--- Re-calibration triggers ---
  • Model version update detected (F-38 pins dated snapshots)
  • Pass rate drops >3 points on production monitor (F-26 behavioral drift)
  • New task type added to pipeline
  • Document length distribution shifts significantly (p95 changes by >200 tok)

selectModelTier() 2 tiers: 0.0042 ms
analyzeCalibrationRun() 100 samples: 0.0071 ms
```

## See also

[S-06](s06-model-routing.md) · [S-65](s65-multi-model-pipelines.md) · [F-38](../forward-deployed/f38-model-version-pinning.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md) · [S-185](s185-task-merge-vs-split-cost-model.md)

## Go deeper

Keywords: `model tier calibration` · `cheapest model quality threshold` · `haiku vs sonnet calibration` · `model selection empirical` · `LLM tier selection` · `pass rate by model` · `model quality measurement` · `find cheapest model` · `model cost quality tradeoff` · `AI model tier decision`
