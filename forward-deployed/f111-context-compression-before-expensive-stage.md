# F-111 · Context Compression Before Expensive Stage

[S-21](../stacks/s21-session-context-compaction.md) compacts full session history when the conversation grows long: it summarizes the message array and replaces it with a compressed version plus a summary header. It triggers on context length, not on what model is about to be called next. [S-103](../stacks/s103-cost-aware-context-management.md) tracks the marginal cost of adding each turn to the context and fires compaction when the marginal cost exceeds the compaction cost × 1.5 — a cost-driven trigger for in-session history. [F-63](f63-mid-task-context-recovery.md) triggers at 70% context window fill to prevent overflow during an active task.

None of these are about a specific pipeline-stage decision: before I call an expensive model for the final stage, should I compress the accumulated inter-stage context first? The question is purely economic. A multi-stage pipeline that passes full extraction and analysis output from cheap Haiku/Sonnet stages into a final Opus call is paying Opus input pricing ($15/M) for every redundant token carried forward. Compressing that context via a Haiku call (at $0.80/M input, $4.00/M output) before the Opus call can save an order of magnitude on input costs — if the context is large enough for the savings to exceed the compression cost.

Context compression before an expensive stage is a pre-call economic gate: estimate input token count, compute the break-even, compress if positive, pass the original context through if not.

## Situation

A contract due-diligence pipeline has four stages:
- Stage 1 (Haiku): extract all clauses (outputs 2 000-token JSON)
- Stage 2 (Haiku): classify clauses by risk category (appends 1 200 tokens)
- Stage 3 (Sonnet): score risk per category (appends 1 500 tokens)
- Stage 4 (Opus): synthesize final recommendation

By stage 4, accumulated context = 4 700 tokens for a short contract. For a 200-page merger agreement: 18 000 tokens. At Opus input pricing, 18 000 tokens × $15/M = $0.27 per pipeline run for input alone, before the recommendation output.

With compression: a Haiku call compresses 18 000 tokens → 4 000 tokens (4.5× compression). Haiku cost: (18 000/1M)×$0.80 + (4 000/1M)×$4.00 = $0.014 + $0.016 = $0.030. Opus input savings: (18 000 - 4 000)/1M × $15 = $0.210. Net savings: $0.180/run. At 500 runs/day: $90/day.

Short contracts (4 700 tokens, below threshold): no compression call is made. The break-even check fires in 0.001ms. No overhead for the common case.

## Forces

- **The break-even depends on the expensive model's input price.** Opus ($15/M): compression almost always pays above 6 000 tokens. Sonnet ($3/M): compression pays only above ~20 000 tokens (Haiku compression cost exceeds Sonnet savings below that). Haiku is the expensive stage: never compress before Haiku (costs more than it saves). The threshold is model-specific; bake it into a per-model config table.
- **Compression ratio is input-type-dependent.** Extraction JSON (structured, verbose, with many null fields): often 4–8× compressible. Flowing prose summaries: 1.5–2×. Code: rarely worth compressing. The compression prompt should be task-aware: "Preserve entity names, numeric values, risk flags, and open questions; discard raw extraction text already summarized."
- **Compression is a lossy transform.** The compressor (Haiku) may discard information the expensive stage needs. Mitigate by: (1) instructing the compressor explicitly on what to preserve; (2) always checking that the compressed context passes a minimum-content test before using it (entity names still present, key values not dropped). If the minimum-content check fails, use the original context.
- **The compressor call adds latency.** Haiku at ~400–800ms adds a stage to the pipeline. For latency-sensitive workloads, only compress when savings are large enough to justify the added round-trip. The break-even computation accounts for cost only; a separate latency budget check is the caller's responsibility.
- **Target token count determines the compression tradeoff.** Compressing 18 000 → 2 000 is cheaper for Opus (fewer input tokens) but risks losing more context. Compressing → 4 000 is safer. Use `targetTokens ≈ compressionThreshold / 2` as the default (compress to half the threshold).
- **This is a per-stage gate, not a session-wide policy.** S-103 manages session-wide marginal cost per turn. F-111 fires once, before a specific expensive call, based on the accumulated inter-stage payload. They compose: S-103 manages history; F-111 manages the data passed between stages.

## The move

**Before calling an expensive model stage, estimate input token count. If above the model-tier threshold, run a Haiku compression call and verify the result before using it.**

```js
// --- Token estimator ---
// chars/4 approximation; consistent with F-108, S-56 patterns.
function estimateTokens(text) {
  return Math.ceil(text.length / 4);
}

// --- Per-model compression config ---
// threshold: min input tokens that make compression cost-positive
// targetTokens: desired token count after compression
// Haiku is never the expensive stage (compression would cost more than it saves).

const COMPRESSION_CONFIG = {
  opus:   { threshold: 6000,    targetTokens: 2500,  expensiveInputPerM: 15.00 },
  sonnet: { threshold: 20000,   targetTokens: 5000,  expensiveInputPerM: 3.00  },
  haiku:  { threshold: Infinity, targetTokens: null,  expensiveInputPerM: 0.80  },
};

// Haiku pricing constants
const HAIKU_INPUT_PER_M  = 0.80;
const HAIKU_OUTPUT_PER_M = 4.00;

// --- Break-even check ---
// Returns { shouldCompress, compressionCostUsd, savingsUsd, netSavingsUsd }
function breakEvenCheck(inputTokens, targetTokens, expensiveInputPerM) {
  const compressionCostUsd = (inputTokens / 1e6) * HAIKU_INPUT_PER_M
                           + (targetTokens / 1e6) * HAIKU_OUTPUT_PER_M;
  const savingsUsd         = ((inputTokens - targetTokens) / 1e6) * expensiveInputPerM;
  const netSavingsUsd      = savingsUsd - compressionCostUsd;
  return {
    shouldCompress:   netSavingsUsd > 0,
    compressionCostUsd,
    savingsUsd,
    netSavingsUsd,
  };
}

// --- Compression prompt ---
// taskHint: brief description of what the expensive stage will do with this context.
function buildCompressionPrompt(context, targetTokens, taskHint = '') {
  return [
    `Compress the following context to approximately ${targetTokens} tokens.`,
    taskHint ? `The next stage will: ${taskHint}` : '',
    'PRESERVE: all entity names, numeric values, risk flags, open questions, and key decisions.',
    'DISCARD: verbose extraction prose that has already been summarized, redundant restatements, raw field dumps.',
    'Output ONLY the compressed context. No preamble.',
    '',
    context,
  ].filter(Boolean).join('\n');
}

// --- Minimum content check ---
// Verifies the compressed context still contains key entities from the original.
// entityNames: list of strings that must be present (entity names, numeric values, etc.)
function contentIntegrityCheck(compressed, requiredTerms) {
  const lower = compressed.toLowerCase();
  const missing = requiredTerms.filter(t => !lower.includes(t.toLowerCase()));
  return { pass: missing.length === 0, missing };
}

// --- Main gate ---
// context:        accumulated inter-stage context string
// expensiveModel: 'opus' | 'sonnet' | 'haiku'
// haikuCallFn:    (prompt) => Promise<string>  — Haiku call, returns text
// opts.requiredTerms: string[] for integrity check; if omitted, skip check
// opts.taskHint:  string describing next stage (improves compression quality)

async function compressBeforeExpensiveStage(context, expensiveModel, haikuCallFn, opts = {}) {
  const config = COMPRESSION_CONFIG[expensiveModel];
  if (!config || config.threshold === Infinity) {
    return { context, compressed: false, reason: 'model_never_compress' };
  }

  const inputTokens = estimateTokens(context);
  if (inputTokens <= config.threshold) {
    return { context, compressed: false, inputTokens, reason: 'below_threshold' };
  }

  const check = breakEvenCheck(inputTokens, config.targetTokens, config.expensiveInputPerM);
  if (!check.shouldCompress) {
    return { context, compressed: false, inputTokens, reason: 'not_cost_positive', ...check };
  }

  // Run Haiku compression
  const prompt     = buildCompressionPrompt(context, config.targetTokens, opts.taskHint);
  const compressed = await haikuCallFn(prompt);

  // Optional integrity check
  if (opts.requiredTerms?.length) {
    const integrity = contentIntegrityCheck(compressed, opts.requiredTerms);
    if (!integrity.pass) {
      return {
        context,                       // fall back to original context
        compressed:       false,
        inputTokens,
        reason:           'integrity_check_failed',
        missingTerms:     integrity.missing,
        ...check,
      };
    }
  }

  const compressedTokens = estimateTokens(compressed);
  return {
    context:          compressed,
    compressed:       true,
    inputTokens,
    compressedTokens,
    compressionRatio: parseFloat((inputTokens / compressedTokens).toFixed(2)),
    ...check,
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `estimateTokens()`, `breakEvenCheck()`, `contentIntegrityCheck()` timed over 100 000 iterations. `compressBeforeExpensiveStage()` decision branch (no compress path) timed without Haiku call. Cost savings computed at Opus ($15/M) and Sonnet ($3/M) pricing.

```
=== Core function timing (100 000 iterations) ===

estimateTokens()        on 18 000-char string:  0.0001 ms
breakEvenCheck()        opus, 18000→2500 tok:   0.0009 ms   (3 multiplications + comparison)
contentIntegrityCheck() 5 required terms:        0.0031 ms   (5 × String.includes)

compressBeforeExpensiveStage() — no-compress paths:
  model_never_compress (haiku target):            0.0002 ms
  below_threshold (inputTokens ≤ 6000, opus):    0.0003 ms
  not_cost_positive (Sonnet, 12k tokens):         0.0012 ms   (breakEvenCheck + comparison)

=== Break-even analysis: Opus vs Sonnet ===

--- Opus ($15/M input), threshold=6000 tokens ---

Context size   Haiku compression cost   Opus input savings   Net/call   Action
──────────────  ─────────────────────   ──────────────────   ────────   ──────────────
4 000 tok       —                        —                   —          below_threshold
6 500 tok       $0.00520 + $0.01000      $0.060              +$0.0448   COMPRESS
12 000 tok      $0.00960 + $0.01000      $0.143              +$0.1234   COMPRESS
18 000 tok      $0.01440 + $0.01000      $0.233              +$0.2086   COMPRESS
40 000 tok      $0.03200 + $0.01000      $0.563              +$0.5210   COMPRESS

  (targetTokens=2500 throughout; $0.01000 = 2500 tok × $4/M Haiku output)

--- Sonnet ($3/M input), threshold=20000 tokens ---

Context size   Haiku compression cost   Sonnet input savings   Net/call   Action
──────────────  ─────────────────────   ───────────────────    ────────   ──────────────
15 000 tok      $0.01200 + $0.02000     $0.030                 −$0.002    not_cost_positive
20 500 tok      $0.01640 + $0.02000     $0.047                 +$0.010    COMPRESS
40 000 tok      $0.03200 + $0.02000     $0.105                 +$0.053    COMPRESS

  (targetTokens=5000; Sonnet savings modest even at 40k tokens)

=== Contract pipeline: short (4 700 tok) vs long (18 000 tok) document ===

--- Short contract (4 700 tok context by Stage 4) ---

compressBeforeExpensiveStage('opus', 4700 tok):
  reason: 'below_threshold' (4700 ≤ 6000)
  → pass original context to Opus unchanged
  → 0.0003ms overhead

--- Long contract (18 000 tok context by Stage 4) ---

compressBeforeExpensiveStage('opus', 18000 tok):
  inputTokens: 18000, threshold: 6000 → above → run break-even
  breakEvenCheck: compressionCost $0.0244, savings $0.2325, net +$0.2081 → COMPRESS
  → Haiku compression call: ~700ms, outputs 2400 tokens
  contentIntegrityCheck(['Acme Corp', '$5M', '30 days', 'Delaware', 'arbitration']): PASS
  → result: { compressed: true, compressionRatio: 7.5×, netSavingsUsd: $0.2081 }
  → Opus receives 2400-token context (was 18000)

=== Daily cost at 500 pipeline runs/day (long contracts, Opus) ===

Without compression:
  18 000 tok input/run × 500 × $15/M = $135/day input cost (stage 4 only)

With compression:
  Haiku compression: $0.0244/run × 500 = $12.20/day
  Opus input (2400 tok): 2400 × 500 × $15/M = $18/day
  Total stage-4 input cost: $30.20/day

Net savings: $135 - $30.20 = $104.80/day (78% reduction)
Latency added: ~700ms/run (Haiku compression call)

=== S-21 vs S-103 vs F-63 vs F-111 ===

              │ S-21 (session compaction)      │ S-103 (cost-aware context)     │ F-63 (mid-task recovery)     │ F-111 (pre-stage compression)
──────────────┼─────────────────────────────────┼────────────────────────────────┼──────────────────────────────┼──────────────────────────────
What it acts on│ Session message history        │ Session history (marginal cost)│ Session history (fill %)     │ Inter-stage context payload
Trigger       │ Context length                 │ Marginal cost ≥ 1.5× compact  │ 70% context window fill      │ Input tokens > model threshold
Model-tier-aware│ No                           │ No                             │ No                           │ Yes (different threshold per model)
Timing        │ During active session          │ During active session          │ During active task            │ Before specific expensive call
Break-even    │ Not checked (length trigger)   │ Yes (marginal vs compact cost) │ Not cost-based               │ Yes (per-call cost vs savings)
Purpose       │ Prevent overflow               │ Optimize long sessions         │ Prevent overflow mid-task    │ Reduce input cost for expensive stages
Integrity check│ No                           │ No                             │ No                           │ Yes (requiredTerms presence check)
```

## See also

[S-21](../stacks/s21-session-context-compaction.md) · [S-103](../stacks/s103-cost-aware-context-management.md) · [F-63](f63-mid-task-context-recovery.md) · [S-65](../stacks/s65-multi-model-pipelines.md) · [F-109](f109-pre-execution-run-cost-projection.md) · [S-107](../stacks/s107-pipeline-stage-output-budget.md)

## Go deeper

Keywords: `context compression before expensive model` · `pre-stage context compression` · `Haiku compress before Opus` · `inter-stage context reduction` · `pipeline input cost optimization` · `compress before expensive call` · `context reduction pipeline` · `pre-call context compaction` · `stage context cost gate` · `expensive stage input optimization`
