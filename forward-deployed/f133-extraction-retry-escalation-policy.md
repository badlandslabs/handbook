# F-133 · Extraction Retry Escalation Policy

[F-131](f131-output-field-string-pattern-validator.md) validates string field formats and produces a list of violations with ERROR/WARN severity. [F-132](f132-output-array-cardinality-validator.md) validates array field cardinality and produces the same violation structure. [F-70](f70-structured-output-validation.md) validates required fields, types, enums, and invariants. All three tell you what is wrong with an extraction. None of them tell you what to do about it.

The default when validation fails is to retry. But retry without a policy devolves into one of two failure modes: retry the same model with the same prompt (no new information, same failure) or always escalate to the most expensive model (correct but 4–8× the cost for a problem the cheap model would fix with a correction hint). The actual optimal path is: retry the same model with targeted correction hints first, then upgrade the model if that fails, then route to human review if the model itself cannot resolve it.

An extraction retry escalation policy encodes this as a decision function: given the attempt number and the validation result, return the action to take. The policy is stateless per call — the caller tracks the attempt count. The decision is driven by three tiers: first failure gets a same-model retry with hints derived from the violation list; second failure gets a model upgrade with the remaining hints; third failure routes to human review regardless of what the violations say.

## Situation

A contract extraction pipeline runs on Haiku ($0.80/$4.00 per M tokens). Validation catches two failure modes at high frequency: `clause_id` returns the section heading instead of the registry ID (F-131 catches this), and `parties` returns one name instead of two (F-132 catches this). Both are format and completeness failures — not ambiguity failures. They recur because the model stops reading before the counterparty signature block.

Without a policy:
- Option A: always retry on failure. The same model makes the same mistake on the same input — retry loop. Cost per retry: $0.0008. Loops are bounded only by the session budget (S-160). No escalation; errors recur.
- Option B: on any failure, escalate to Sonnet. 40% of contracts fail on the first extraction. All 40% pay the Sonnet rate ($3.00/$15.00 per M). At 1 000 contracts/day: 400 Sonnet calls × ~$0.003 = $1.20/day extra, even when most failures were Haiku-fixable with a hint.

With a 3-tier policy:
- Attempt 1 fails → retry Haiku with hint: "clause_id must be CL-{digits}; ensure both parties are identified." Cost: $0.0008.
- Attempt 2 fails → retry Sonnet (the model may need stronger reasoning to find the counterparty block). Cost: $0.0030.
- Attempt 3 fails → human review queue. No further model cost for this contract.
- 80% of retries succeed at attempt 2. Human review receives only the genuinely hard cases.

## Forces

- **Hints change the outcome; identical retries do not.** A model that returned `clause_id: "Section 4"` on attempt 1 will return the same thing on attempt 2 if the prompt is unchanged. The retry hint must tell it exactly what format is required and what it returned: "clause_id must be in CL-{digits} format (you returned 'Section 4')." Targeted correction yields different behavior; generic retry yields the same failure.
- **Attempt 1 retry is the same model, not an upgrade.** The format hint is cheap information. Most extraction failures are surface-level — the model can correct them when told. Upgrading to Sonnet before confirming the hint doesn't help wastes $0.0022 per contract that would have been fixed by $0.0008 of hint-guided Haiku.
- **Attempt 2 upgrade is for failures that need stronger reasoning.** If attempt 1 with hints still fails, the model may be missing something in the document structure that requires deeper reading — long contract, dense formatting, ambiguous section boundaries. Sonnet has higher reasoning capacity for these cases.
- **Attempt 3 is never another model call.** There is no model tier above Sonnet in this policy. If Sonnet cannot fix it with two attempts, the failure is structural — bad OCR, missing pages, a template the model has not seen. Model escalation cannot fix structural failures. Route to the human queue.
- **Build hints from the violation list, not from the raw validation result.** Each violation from F-131 and F-132 contains the field name, the value that failed, and the expected format. A `buildRetryHints()` function maps these to English instructions targeted at the model. Do not pass the raw violation object to the model — it is for your system, not the model.
- **The policy is a decision function, not a retry loop.** The caller runs the loop; the policy decides each step. This keeps the policy testable in isolation — you can unit-test every decision path without running actual extractions.

## The move

**Decide per attempt: accept, retry same, retry upgrade, or escalate to human. Build targeted hints from the violation list. Three tiers; no fourth model call.**

```js
// --- Extraction retry escalation policy ---
// Stateless per call: caller tracks attempt count.
// Tier 1 (attempt 1 fails): retry same model with correction hints from violations.
// Tier 2 (attempt 2 fails): upgrade to expensive model, same hints.
// Tier 3 (attempt 3 fails): human review — no further model call.
// Integrates with F-70, F-131, F-132 violation output.

// Build targeted correction instructions from F-131/F-132/F-70 violation objects.
function buildRetryHints(violations) {
  return violations
    .filter(function(v) { return v.severity === 'ERROR'; })
    .map(function(v) {
      if (v.issue === 'TOO_FEW')  return v.field + ' requires at least ' + v.min + ' items (found ' + v.count + ')';
      if (v.issue === 'TOO_MANY') return v.field + ' allows at most '    + v.max + ' items (found ' + v.count + ')';
      if (v.expected)             return v.field + ' must be in '        + v.expected + ' format (you returned ' + JSON.stringify(v.value) + ')';
      return v.field + ' failed validation';
    })
    .join('; ');
}

class ExtractionRetryPolicy {
  constructor(opts) {
    opts = opts || {};
    this._maxAttempts = opts.maxAttempts != null ? opts.maxAttempts : 3;
    this._cheapModel  = opts.cheapModel  || 'claude-haiku-4-5-20251001';
    this._expModel    = opts.expModel    || 'claude-sonnet-4-6';
  }

  // Given the attempt number (1-based) and the validation result, decide what to do.
  // validationResult: the output of F-131/F-132/F-70 validate() — { status, violations, errorCount }
  // Returns:
  //   { action: 'ACCEPT' }
  //   { action: 'RETRY',       model, reason, attemptNumber, retryHints }
  //   { action: 'HUMAN_REVIEW', reason, attemptNumber }
  decide(attemptNumber, validationResult) {
    if (!validationResult || validationResult.status === 'PASS') {
      return { action: 'ACCEPT', attemptNumber: attemptNumber };
    }

    if (attemptNumber >= this._maxAttempts) {
      return { action: 'HUMAN_REVIEW', reason: 'MAX_ATTEMPTS_REACHED', attemptNumber: attemptNumber };
    }

    const hints = buildRetryHints(validationResult.violations);

    if (attemptNumber === 1) {
      return {
        action:       'RETRY',
        model:        this._cheapModel,
        reason:       'FIRST_FAILURE_RETRY_SAME',
        attemptNumber: attemptNumber,
        retryHints:   hints,
      };
    }

    // attemptNumber === 2 (and < maxAttempts)
    return {
      action:       'RETRY',
      model:        this._expModel,
      reason:       'SECOND_FAILURE_UPGRADE',
      attemptNumber: attemptNumber,
      retryHints:   hints,
    };
  }
}

// --- Integration: extraction loop with retry policy ---

const POLICY = new ExtractionRetryPolicy({ maxAttempts: 3 });

async function extractWithRetry(document, schema, queryType) {
  let model = 'claude-haiku-4-5-20251001';
  let extraInstructions = '';

  for (let attempt = 1; attempt <= 3; attempt++) {
    const output    = await callModel(model, buildPrompt(schema, extraInstructions), document);
    const validated = validateExtraction(output);  // F-70 → F-131 → F-132 chain

    const decision  = POLICY.decide(attempt, validated);

    if (decision.action === 'ACCEPT') {
      return { output, attempt, model };
    }

    if (decision.action === 'HUMAN_REVIEW') {
      return { output: null, attempt, reason: 'HUMAN_REVIEW', violations: validated.violations };
    }

    // RETRY: update model and extra instructions for next attempt
    model             = decision.model;
    extraInstructions = decision.retryHints;
    log({ event: 'extraction_retry', attempt, reason: decision.reason, retryHints: extraInstructions });
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `decide()` timed over 100 000 iterations. `maxAttempts: 3`. Cheap model: `claude-haiku-4-5-20251001`. Expensive model: `claude-sonnet-4-6`.

```
=== ExtractionRetryPolicy timing (100 000 iterations) ===

decide() ACCEPT       (attempt 1, PASS):         0.0001 ms
decide() RETRY_SAME   (attempt 1, FAIL):         0.0012 ms
decide() RETRY_UPGRADE(attempt 2, FAIL):         0.0005 ms
decide() HUMAN_REVIEW (attempt 3, FAIL):         0.0001 ms

=== Scenario: 3-attempt extraction lifecycle ===

--- Attempt 1 → validation PASS ---
decide(1, { status: 'PASS', violations: [] }):
{ action: 'ACCEPT', attemptNumber: 1 }

--- Attempt 1 → 2 ERRORs ---
violations: [
  { field: 'clause_id', value: 'Section 4', expected: 'CL-{digits}', severity: 'ERROR' },
  { field: 'parties',   issue: 'TOO_FEW',   count: 1, min: 2,        severity: 'ERROR' }
]
decide(1, failResult):
{
  action:       'RETRY',
  model:        'claude-haiku-4-5-20251001',
  reason:       'FIRST_FAILURE_RETRY_SAME',
  attemptNumber: 1,
  retryHints:   'clause_id must be in CL-{digits} format (you returned "Section 4"); parties requires at least 2 items (found 1)'
}

--- Attempt 2 → 1 ERROR persists ---
violations: [
  { field: 'clause_id', value: 'Section 4', expected: 'CL-{digits}', severity: 'ERROR' }
]
decide(2, failResult):
{
  action:       'RETRY',
  model:        'claude-sonnet-4-6',
  reason:       'SECOND_FAILURE_UPGRADE',
  attemptNumber: 2,
  retryHints:   'clause_id must be in CL-{digits} format (you returned "Section 4")'
}

--- Attempt 3 → still failing ---
decide(3, failResult):
{ action: 'HUMAN_REVIEW', reason: 'MAX_ATTEMPTS_REACHED', attemptNumber: 3 }
→ Route to human review queue.

=== Cost per attempt (500-tok input + 100-tok output) ===

Attempt 1 (Haiku):  $0.000800
Attempt 2 (Sonnet): $0.003000
Savings vs always Sonnet for both retries: $0.002200 per contract fixed at attempt 2

At 1 000 contracts/day, 40% fail attempt 1, 80% of those fixed at attempt 2:
  With policy:    400 Haiku retries × $0.0008 + 80 Sonnet retries × $0.0030 = $0.56/day
  Always Sonnet:  400 Sonnet retries × $0.0030                               = $1.20/day
  Savings: $0.64/day from deferring model upgrade to second failure

=== Decision matrix ===

Attempt │ Validation  │ Action       │ Model   │ Change from prior call
────────┼─────────────┼──────────────┼─────────┼────────────────────────
1       │ PASS        │ ACCEPT       │ —       │ Done
1       │ FAIL        │ RETRY_SAME   │ Haiku   │ Add retryHints to prompt
2       │ PASS        │ ACCEPT       │ —       │ Done
2       │ FAIL        │ RETRY_UPGRADE│ Sonnet  │ Upgrade model + retryHints
3       │ PASS        │ ACCEPT       │ —       │ Done
3       │ FAIL        │ HUMAN_REVIEW │ —       │ Queue for human review
```

## See also

[F-131](f131-output-field-string-pattern-validator.md) · [F-132](f132-output-array-cardinality-validator.md) · [F-70](f70-structured-output-validation.md) · [F-130](f130-per-turn-model-router.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-20](f20-rate-limits-and-retry.md)

## Go deeper

Keywords: `extraction retry policy` · `escalation on validation failure` · `retry with model upgrade` · `extraction retry hints` · `validation-driven retry` · `human review escalation` · `retry tier policy` · `extraction model upgrade strategy` · `targeted retry instruction` · `correction-guided extraction retry`
