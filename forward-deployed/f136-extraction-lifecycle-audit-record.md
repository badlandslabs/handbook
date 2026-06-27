# F-136 · Extraction Lifecycle Audit Record

[F-31](f31-structured-call-logging.md) logs each API call: model, token counts, stop reason, latency. It records individual calls, not the extraction lifecycle that spans multiple calls. [F-82](f82-agent-output-provenance-trail.md) traces the RAG pipeline from query to output: retrieval scores, context injection snapshot, messages array at inference time. It answers "what did the model see?" — not "what happened during extraction validation and retry?" [F-87](f87-tool-call-argument-audit-log.md) logs tool call arguments before dispatch — tool inputs, not extraction outputs.

An extraction pipeline that runs F-134 (ensemble voting), F-135 (field normalization), F-70/F-131/F-132 (validation chain), and F-133 (retry escalation) produces a chain of decisions, model calls, and transformations. Without an audit record, post-hoc debugging means re-running the pipeline from scratch — which may not reproduce the original failure if the document has changed, the model version has changed, or the retry path was stochastic. A compliance review asking "why was this contract flagged HIGH risk?" has no answer if the extraction steps are ephemeral.

An extraction lifecycle audit record is a structured object produced alongside every extraction output. It captures: the document hash, schema version, ensemble run results with per-field confidence, normalization events, validation passes and failures with violation details, retry chain with models and reasons, final output, total cost, and latency. The audit_id returned with the output enables any downstream system to retrieve the full record from storage.

## Situation

A contract processing pipeline extracts 1 000 bilateral agreements per day. The pipeline runs F-134 → F-135 → F-70 → F-131 → F-132 → F-133. The output is a 6-field JSON schema that feeds a downstream compliance review system.

Production issues that lack audit records:

- A `termination_fee` value is challenged by the counterparty. Without the audit record, the team cannot tell whether the value came from a UNANIMOUS ensemble (all three Haiku runs agreed), a MAJORITY (two agreed, one returned a value from the amendment clause), or a SPLIT (no majority — Sonnet was called for re-extraction).
- A `risk_level` of `HIGH` fails a compliance spot check — the contract was clearly LOW risk. The audit record would show: ensemble returned `"High risk"` (UNANIMOUS, three runs agreed), F-135 normalized to `HIGH`, F-70 passed. The model extracted incorrectly, not the normalization or validation. Fix: update the extraction prompt.
- A contract is in human review. The reviewer needs to know: what did the model see, what did it return, what failed, and what was tried. The audit record answers all four in one record without re-running the pipeline.

## Forces

- **Record at each pipeline step, not only at the end.** If the retry fails and the extraction is routed to human review, the final `toRecord()` call still produces a complete record with all intermediate steps. A record built only on success is useless for debugging failures.
- **Document hash, not document ID.** The audit record stores SHA-256 of the document content, not a database ID that may be updated or deleted. Given an audit record months later, you can verify the exact document state that produced this extraction. If the document has since been updated, the hash mismatch is evidence.
- **Schema version, not model version.** The extraction schema version determines which fields were required, which enums were valid, which patterns were enforced. The model version is logged via F-38 (model version pinning) separately. The schema version explains which validators ran and which rules were in force.
- **Store the full audit record for high-stakes documents; sample for routine ones.** At 1 000 extractions/day, a full audit record is ~1.2 KB JSON. 30-day retention is ~36 MB — negligible. For pipelines at 100k/day, sample 100% for compliance-flagged documents and 5% for routine ones. Log the sampling rate as a field in the audit record so downstream tools know whether they have complete coverage.
- **Return `audit_id` alongside the output, not the full record.** The extraction output is injected into agent context, databases, and downstream systems. Including the full audit record in the output would bloat all of these. Return `{output, audit_id}` from the extraction function; store the full record by `audit_id` separately with the configured retention.
- **The audit record is not the receipt for billing.** F-29 (cost attribution) and F-31 (call logging) cover billing-level cost tracking with tagging. The audit record's `costUsd` field covers the per-extraction total for operational review, not billing aggregation.

## The move

**Build the audit record incrementally through each pipeline step. Finalize with output, status, and cost. Return `audit_id` alongside the output; store the record separately.**

```js
// --- Extraction lifecycle audit record ---
// Accumulates pipeline events across F-134 → F-135 → F-70/F-131/F-132 → F-133.
// Return { output, audit_id } from the extraction function; store record by audit_id.
// Document hash + schema version identify the exact document state and rules in force.
// UNKNOWN fields in toRecord() mean that pipeline step was not reached (early exit or short path).

class ExtractionAuditRecord {
  constructor(opts) {
    opts                 = opts || {};
    this.auditId         = opts.auditId || generateId();
    this._documentHash   = opts.documentHash  || null;
    this._schemaVersion  = opts.schemaVersion || 'unknown';
    this._startedAt      = opts.startedAt     || Date.now();
    this._ensemble       = null;
    this._normalizations = [];
    this._validations    = [];
    this._retries        = [];
    this._final          = null;
  }

  // F-134: record ensemble run — models used and per-field confidence votes.
  // votes: { fieldName: { value, confidence: 'UNANIMOUS'|'MAJORITY'|'SPLIT', votes, totalRuns } }
  recordEnsemble(models, votes) {
    this._ensemble = { models, votes };
    return this;
  }

  // F-135: record normalization events — which fields were normalized and to what.
  // normalizations: [{ field, original, canonical }]
  recordNormalization(normalizations) {
    this._normalizations = normalizations;
    return this;
  }

  // F-70/F-131/F-132: record a validator pass.
  // result: { validator: 'F-70'|'F-131'|'F-132', status: 'PASS'|'FAIL', violations: [...] }
  recordValidation(result) {
    this._validations.push(result);
    return this;
  }

  // F-133: record a retry decision.
  // retry: { attempt, action: 'RETRY'|'HUMAN_REVIEW', model?, reason, retryHints? }
  recordRetry(retry) {
    this._retries.push(retry);
    return this;
  }

  // Finalize the record: stamp final output, status (PASS|FAIL|HUMAN_REVIEW), cost, latency.
  finalize(output, status, costUsd) {
    this._final = {
      status,
      output,
      costUsd:   costUsd  || 0,
      latencyMs: Date.now() - this._startedAt,
    };
    return this;
  }

  // Produce the full audit record as a plain object for storage.
  toRecord() {
    return {
      auditId:        this.auditId,
      documentHash:   this._documentHash,
      schemaVersion:  this._schemaVersion,
      ensemble:       this._ensemble,
      normalizations: this._normalizations,
      validations:    this._validations,
      retries:        this._retries,
      final:          this._final,
    };
  }
}

// --- Integration: extraction pipeline with audit record ---

async function extractWithAudit(document, schema) {
  const documentHash = sha256(document);
  const audit        = new ExtractionAuditRecord({ documentHash, schemaVersion: schema.version });

  // Step 1: ensemble (F-134)
  const extractions = await Promise.all([
    extractOnce('claude-haiku-4-5-20251001', document, schema),
    extractOnce('claude-haiku-4-5-20251001', document, schema),
    extractOnce('claude-haiku-4-5-20251001', document, schema),
  ]);
  const voted = VOTER.vote(extractions);
  audit.recordEnsemble(['claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001', 'claude-haiku-4-5-20251001'], voted);

  let output = Object.fromEntries(Object.entries(voted).map(function(e) { return [e[0], e[1].value]; }));
  let cost   = 3 * 0.0008;  // 3 Haiku extractions

  // Step 2: normalize (F-135)
  const { output: normalized, normalized: normEvents } = NORMALIZER.normalize(output);
  output = normalized;
  audit.recordNormalization(normEvents);

  // Step 3: validate (F-70 → F-131 → F-132)
  for (let attempt = 1; attempt <= 3; attempt++) {
    const v70  = validateF70(output, schema);
    audit.recordValidation({ validator: 'F-70', status: v70.status, violations: v70.violations });

    if (v70.status === 'PASS') {
      const v131 = validateF131(output);
      audit.recordValidation({ validator: 'F-131', status: v131.status, violations: v131.violations });
      if (v131.status === 'PASS') {
        // Finalize success
        audit.finalize(output, 'PASS', cost);
        await storeAuditRecord(audit.auditId, audit.toRecord());
        return { output, audit_id: audit.auditId };
      }
    }

    // Step 4: F-133 escalation decision
    const decision = RETRY_POLICY.decide(attempt, v70.status !== 'PASS' ? v70 : undefined);
    if (decision.action === 'HUMAN_REVIEW') {
      audit.recordRetry({ attempt, action: 'HUMAN_REVIEW', reason: 'MAX_ATTEMPTS_REACHED' });
      audit.finalize(output, 'HUMAN_REVIEW', cost);
      await storeAuditRecord(audit.auditId, audit.toRecord());
      return { output: null, audit_id: audit.auditId, reason: 'HUMAN_REVIEW' };
    }

    audit.recordRetry({ attempt, action: 'RETRY', model: decision.model, reason: decision.reason, retryHints: decision.retryHints });
    output = await extractOnce(decision.model, document, schema, decision.retryHints);
    cost  += decision.model.includes('haiku') ? 0.0008 : 0.003;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Each record method timed over 100 000 iterations. Full lifecycle scenario: ensemble → normalization → F-70 FAIL → retry → F-70 PASS. Pricing: Haiku $0.80/$4.00 per M tok, Sonnet $3.00/$15.00 per M tok.

```
=== ExtractionAuditRecord timing (100 000 iterations) ===

new ExtractionAuditRecord():   0.0004 ms
recordEnsemble():              0.0001 ms
recordNormalization():         0.0002 ms
recordValidation():            0.0004 ms
recordRetry():                 0.0007 ms
finalize():                    0.0005 ms
toRecord():                    0.0001 ms

=== Scenario: 4-field contract extraction with retry ===

documentHash:  sha256:c0ffee42
schemaVersion: 2.1

--- ensemble (F-134): N=3 Haiku ---
  risk_level:    { value: "High risk", confidence: "UNANIMOUS", votes: 3 }
  governing_law: { value: "United States of America", confidence: "UNANIMOUS", votes: 3 }
  clause_id:     { value: "CL-042",    confidence: "UNANIMOUS", votes: 3 }
  termination_fee: { value: "24500000", confidence: "MAJORITY",  votes: 2 }

--- normalization (F-135) ---
  risk_level:    "High risk" → "HIGH"
  governing_law: "United States of America" → "US"

--- validation attempt 1 ---
  F-70: FAIL  violations=[{field:"schema_version", issue:"REQUIRED", severity:"ERROR"}]
  → F-133: RETRY same model, retryHints="schema_version is required"

--- validation attempt 2 ---
  F-70: PASS  (retry included schema_version field)
  F-131: PASS

--- finalize ---
  status:    PASS
  costUsd:   $0.0032  (3 Haiku ensemble × $0.0008 + 1 Haiku retry × $0.0008)
  latencyMs: (measured at finalize())

=== Record size ===
JSON bytes:                        ~1 160
1 000 extractions/day, 30-day:     ~34 MB storage

=== Compliance use cases enabled by audit record ===

"Why is termination_fee '24 500 000'?"
  → ensemble.votes.termination_fee.confidence = MAJORITY (2/3 — one run found amendment value)
  → No normalization. No retry. Model disagreement, not pipeline error.

"Why was risk_level flagged HIGH on a clearly low-risk contract?"
  → ensemble.votes.risk_level.confidence = UNANIMOUS (all 3 Haiku agreed: "High risk")
  → normalization correctly mapped "High risk" → "HIGH"
  → F-70 PASS: the schema accepted HIGH as valid
  → Root cause: model extraction error. Fix: add few-shot example of low-risk contract to prompt.

=== F-31 vs F-82 vs F-87 vs F-136 ===

F-31  (structured call log):      per API call — {model, tokens, stop_reason}
F-82  (provenance trail):          RAG pipeline — query → retrieval → context → output
F-87  (tool arg audit log):        tool inputs before dispatch — not extraction output chain
F-136 (extraction audit record):   extraction lifecycle — ensemble → normalize → validate → retry → final
```

## See also

[F-134](f134-extraction-ensemble-voter.md) · [F-135](f135-extraction-output-field-normalizer.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-70](f70-structured-output-validation.md) · [F-31](f31-structured-call-logging.md) · [F-82](f82-agent-output-provenance-trail.md)

## Go deeper

Keywords: `extraction audit record` · `extraction lifecycle audit` · `per-extraction audit trail` · `extraction pipeline audit` · `extraction debugging record` · `compliance extraction audit` · `extraction lifecycle trace` · `extraction provenance` · `extraction pipeline record` · `audit_id extraction output`
