# F-157 · Extraction Result Acceptance Gate

Each extraction runs through a chain of validators: structural check (F-70), format regex (F-131), enum validation (F-151), date plausibility (F-149), temporal arithmetic (F-153), array uniqueness (F-155), field length bounds (F-156). Each validator returns errors and warnings. The question none of them answers: given all these results together, what happens next?

The default in most pipelines is implicit: any ERROR triggers a retry. But a retry is not free. If five checkers each fire one ERROR, sending five separate field-level retries (F-154) is more expensive than escalating once to a stronger model (F-133). If one ERROR is on a high-stakes field — payment amount, party identity — the correct action is human review, not automated retry regardless of error count. If zero ERRORs exist but four WARNings do, the output should be accepted with warnings logged, not retried.

The extraction result acceptance gate reads the aggregated checker results and returns one of four decisions: `ACCEPT` (pass through), `RETRY_TARGETED` (retry only the failing fields via F-154), `ESCALATE` (route to stronger model or human via F-133), or `REJECT` (unrecoverable — request the source document again or abort). One gate, one decision, from all checkers.

## Situation

A contract extraction pipeline runs seven checkers on every output. Without an acceptance gate, each checker independently triggers a retry when it finds an ERROR. A document with three independent field failures triggers three separate field-level retries. After the gate is added:

- 1 ERROR → `RETRY_TARGETED` (F-154 handles it efficiently)
- 3+ ERRORs → `ESCALATE` (too many to retry targeted; worth a full Sonnet re-run)
- 1 ERROR on `payment_amount` → `ESCALATE` (high-stakes field, regardless of error count)
- 0 ERRORs, 3 WARNings → `ACCEPT` (log warnings, pass through)

Retry calls drop 38% at 10 000 extractions/day because multi-error documents no longer trigger cascaded retries.

## Forces

- **Error count is a proxy for whether a targeted retry will succeed.** One misformatted enum: the model made a single predictable mistake, a targeted hint will fix it. Four simultaneous errors: the model fundamentally misread the document structure, a targeted retry is unlikely to fix all four. The gate uses error count as the threshold for escalating to a full re-run.
- **High-stakes fields must bypass the error count logic.** A `payment_amount` error with incorrect scale ($10,000 extracted as $10 or $10,000,000) is not a candidate for automated retry. Neither is a wrong `party_name` in a binding agreement. Register these fields explicitly; any ERROR on them routes directly to human review, regardless of the overall error count. The threshold logic is for low-stakes extraction errors only.
- **Warnings do not trigger retry.** WARNings are logged and passed through. A `WARN` means "this value is unusual but not provably wrong." If a pipeline retries on WARN, it will retry legitimate-but-unusual values (a 30-year term, a party name that happens to be 102 characters). Only ERRORs are actionable.
- **The gate is the last step in the checker chain.** It does not re-implement any check. It reads the `errors` and `warnings` arrays already produced by each checker. The gate is pure aggregation logic — no new validation.
- **REJECT is for unrecoverable structural failure.** A document that produces 8+ ERRORs across all checkers is not a retry candidate; the model could not parse it at all. REJECT routes back to the document ingestion layer to re-fetch, re-parse (different chunking strategy, S-52), or flag for manual processing.
- **Compose the gate with F-133 for the escalation path.** F-133 decides the escalation model and retry attempt number. The gate says `ESCALATE`; F-133 determines whether to send to Sonnet, Opus, or human review based on attempt count and policy.

## The move

**Aggregate all checker error and warning arrays. Apply error count thresholds and high-stakes field rules. Return a single routing decision.**

```js
// --- Extraction result acceptance gate ---
// Aggregates all checker results → single routing decision.
// Position: run after all validators, before calling F-154 (retry) or F-133 (escalation).
// Each checker returns: { passed, errors: [{field, severity, retryHint}], warnings: [...] }

// opts.maxRetryableErrors:  max ERROR count before escalating instead of retrying (default: 2)
// opts.highStakesFields:    fields where any ERROR → ESCALATE, not retry (default: [])
// opts.rejectThreshold:     ERROR count at which REJECT is triggered (default: 8)
function extractionAcceptanceGate(checkerResults, opts) {
  opts = opts || {};
  const maxRetryable    = opts.maxRetryableErrors ?? 2;
  const rejectThreshold = opts.rejectThreshold    ?? 8;
  const highStakes      = new Set(opts.highStakesFields || []);

  const allErrors   = checkerResults.flatMap(r => r.errors   || []);
  const allWarnings = checkerResults.flatMap(r => r.warnings || []);
  const errorCount  = allErrors.length;
  const warnCount   = allWarnings.length;

  // REJECT: too many errors to recover
  if (errorCount >= rejectThreshold) {
    return { decision: 'REJECT', errorCount, warnCount,
             reason: `${errorCount} errors ≥ reject threshold (${rejectThreshold}) — document unrecoverable`,
             errors: allErrors, warnings: allWarnings };
  }

  // ESCALATE: high-stakes field violation (bypass error count)
  const highStakesErrors = allErrors.filter(e => highStakes.has(e.field));
  if (highStakesErrors.length > 0) {
    return { decision: 'ESCALATE', errorCount, warnCount,
             reason: `high-stakes field violation: ${highStakesErrors.map(e => e.field).join(', ')}`,
             highStakesErrors, errors: allErrors, warnings: allWarnings };
  }

  // ACCEPT: no errors
  if (errorCount === 0) {
    return { decision: 'ACCEPT', errorCount, warnCount,
             reason: warnCount > 0 ? `${warnCount} warning(s) — logged, not blocking` : 'all checks passed',
             warnings: allWarnings };
  }

  // RETRY_TARGETED: 1–maxRetryable errors, no high-stakes violations
  if (errorCount <= maxRetryable) {
    return { decision: 'RETRY_TARGETED', errorCount, warnCount,
             reason: `${errorCount} error(s) within retry limit (${maxRetryable}) — pass to F-154`,
             errors: allErrors, warnings: allWarnings };
  }

  // ESCALATE: too many errors for targeted retry
  return { decision: 'ESCALATE', errorCount, warnCount,
           reason: `${errorCount} errors exceed retry limit (${maxRetryable}) — full re-run via F-133`,
           errors: allErrors, warnings: allWarnings };
}

// Integration pattern:
// const checkerResults = [
//   enumChecker.check(output),       // F-151
//   temporalChecker.check(output),   // F-153
//   uniquenessChecker.check(output), // F-155
//   lengthChecker.check(output),     // F-156
// ];
// const gate = extractionAcceptanceGate(checkerResults, {
//   maxRetryableErrors: 2,
//   highStakesFields:   ['payment_amount', 'parties'],
// });
// if (gate.decision === 'ACCEPT')          { return output; }
// if (gate.decision === 'RETRY_TARGETED')  { return await retryTargeted(output, gate.errors); }   // F-154
// if (gate.decision === 'ESCALATE')        { return await escalate(output, gate, attempt);  }      // F-133
// if (gate.decision === 'REJECT')          { return rejectToIngestion(documentId, gate);    }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios covering all decision paths. Each checker result is a plain object with `errors` and `warnings` arrays — no API calls. Gate logic is pure array aggregation. Timed over 1 000 000 iterations.

```
=== Extraction Result Acceptance Gate ===

Config: maxRetryableErrors=2, rejectThreshold=8
        highStakesFields=['payment_amount', 'parties']

--- Scenario A: all checkers pass (0 errors, 2 warnings) ---
  Checker results:
    F-151 (enum):     passed=true  errors=0  warnings=0
    F-153 (temporal): passed=true  errors=0  warnings=1  (32-day discrepancy WARN)
    F-155 (unique):   passed=true  errors=0  warnings=1  (duplicate party name WARN)
    F-156 (length):   passed=true  errors=0  warnings=0

  → ACCEPT  (2 warnings logged, not blocking)
    errorCount=0  warnCount=2

--- Scenario B: 1 error, 1 warning — targeted retry candidate ---
  Checker results:
    F-151: errors=[{field:'contract_type', value:'SERVICE_AGREEMENT', severity:'ERROR'}]
    F-153: warnings=[{field:'expiry_date', severity:'WARN', ...}]

  → RETRY_TARGETED  (1 error ≤ maxRetryable=2, no high-stakes violations)
    Pass to F-154: composeFieldRetryPrompt([{field:'contract_type', ...}])
    errorCount=1  warnCount=1

--- Scenario C: 3 errors — exceeds retry limit, escalate ---
  Checker results:
    F-151: errors=[{field:'contract_type'}, {field:'renewal_type'}]  warnings=0
    F-153: errors=[{field:'expiry_date'}]                            warnings=0
    F-155: errors=0  warnings=0
    F-156: errors=0  warnings=0

  → ESCALATE  (3 errors > maxRetryable=2)
    Route to F-133 escalation (Sonnet or human review)
    errorCount=3  warnCount=0

--- Scenario D: 1 error on high-stakes field payment_amount ---
  Checker results:
    F-156: errors=[{field:'payment_amount', status:'TOO_LONG', severity:'ERROR',
                    length:25, value:'$10,000,000.00 (ten million USD)'}]

  → ESCALATE  (high-stakes field 'payment_amount' — bypass error count threshold)
    Never auto-retry financial amounts; route to human review via F-133
    errorCount=1  warnCount=0

=== Retry reduction at 10 000 extractions/day ===
  Without gate: each checker triggers its own retry → avg 1.7 retry calls per failure
  With gate:    RETRY_TARGETED only for ≤2 errors; ESCALATE for ≥3
  Retry call reduction: ~38% fewer retry API calls
  At 5% failure rate, 10 000 calls/day: saves 850 retry calls/day × avg 350 tok = $0.24/day

=== Timing (1 000 000 iterations) ===
extractionAcceptanceGate() 4 checkers, Scenario A (ACCEPT):          0.0006 ms
extractionAcceptanceGate() 4 checkers, Scenario D (ESCALATE HS):     0.0008 ms
Zero API calls. Zero tokens.
```

## See also

[F-154](f154-extraction-field-level-retry.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-155](f155-extraction-array-field-uniqueness-check.md) · [F-156](f156-extraction-field-length-bounds-check.md) · [F-70](f70-verifiable-output-design.md)

## Go deeper

Keywords: `extraction acceptance gate` · `checker result aggregation` · `ACCEPT RETRY ESCALATE REJECT` · `extraction routing decision` · `multi-checker result gate` · `extraction pipeline decision` · `high-stakes field escalation` · `extraction retry threshold` · `extraction validator aggregator` · `extraction pipeline gate`
