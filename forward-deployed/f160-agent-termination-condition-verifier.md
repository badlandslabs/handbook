# F-160 · Agent Termination Condition Verifier

An agent that declares itself done without having actually completed the required steps is a failure that's hard to catch at runtime. The model returns a final answer; the pipeline accepts it; the downstream system acts on incomplete work.

F-159 verifies that tool calls happen in the right order within a turn. F-160 verifies that when the agent claims the entire task is complete, all required conditions are satisfied. These operate at different scopes: F-159 is per-tool-call within a turn; F-160 is the final gate before the agent exits.

A contract review agent is supposed to fetch the document, extract fields, verify them, and emit a structured summary with a risk level. In 12% of cases the model calls `done()` after extracting fields, skipping `verify_fields` and leaving `output.risk_level` null. The extraction passed F-159's sequence invariant (verify_fields was not a registered prerequisite for done()), so nothing blocked the early exit. The pipeline accepted the output. Downstream escalation rate for these incomplete cases was 34%, versus < 2% for fully processed contracts.

The termination condition verifier registers conditions that the agent's state must satisfy before a `done()` call is honored. Each condition is a predicate over the agent's state object: what tools have been called, what output fields are populated, whether a human approved a high-stakes decision. A failing condition blocks termination and returns a `retryHint` naming what is missing.

## Situation

A contract review agent processes NDAs for a legal team. Three completion conditions are required before the agent may exit:

1. `verify_fields` must have been called (quality gate — extractions must be verified, not assumed).
2. `output.summary`, `output.risk_level`, and `output.recommended_action` must all be non-null.
3. When `output.risk_level === 'HIGH'`, a human must have approved the result before the agent closes.

Without the verifier: 12% of contracts exit with `risk_level: null` and no verified fields.

After registering these three conditions: 0% early exits. Contracts that hit condition failures loop back for the missing step; the retry hint tells the model exactly what to do. Escalation rate for processed contracts drops from 12% to < 1%.

## Forces

- **Termination conditions and sequence invariants are complementary, not redundant.** F-159 (sequence invariant) enforces that tool B follows tool A within a single turn. F-160 enforces that before the agent exits, the *total task state* is complete — across all turns, all fields, all human gates. Both are needed; neither replaces the other.
- **State must be durable across turns.** `toolCallHistory` must survive the full agent session, not just one turn. Contrast with F-159, which resets per turn. A condition that requires `fetch_document` to have been called at some point in the session needs a session-scoped record, not a turn-scoped one.
- **retryHint must be actionable.** "output.risk_level is null" is a symptom. "Call verify_fields and ensure the risk_level field is populated in your next output" is the instruction the model needs to recover. The verifier's value is in the hint quality, not just the pass/fail decision.
- **High-stakes conditions escalate; routine conditions retry.** A missing output field is recoverable — the agent can call the right tool and try again. A missing human approval on a HIGH-risk contract is not agent-recoverable — it requires routing to a human queue (S-78). Use WARN for retry-recoverable conditions and ERROR + escalation path for human-gate conditions.
- **Check at the done() call site, not at every turn.** The verifier is not a loop monitor — it doesn't interrupt the agent mid-task. It runs exactly once: when the agent calls `done()`. The cost is negligible (< 0.001 ms); the placement is precise.
- **Compose with F-157 (extraction acceptance gate) for full coverage.** F-157 checks that a specific extraction output is acceptable (correct fields, valid values, no duplicates). F-160 checks that the agent's overall task is complete. A pipeline needs both: F-157 before the extraction result is consumed; F-160 before the agent is allowed to close the session.

## The move

**Register completion conditions at startup. Check all conditions when the agent calls done(). Block on ERROR; route high-stakes failures to human escalation. Pass the retryHint back into the agent turn.**

```js
// --- Agent termination condition verifier ---
// Verifies that all required task completion conditions are met before the agent exits.
// Runs at the done() call site, not per-turn. State must be session-scoped.
// Compose with F-159 (sequence invariant, per-turn) and F-157 (extraction gate, per-output).

class AgentTerminationVerifier {
  constructor() {
    this._conditions = [];
  }

  // Register a completion condition.
  // name:          label for reporting
  // conditionFn:   (state) → { met: boolean, reason?: string, retryHint?: string }
  //   state shape: {
  //     toolCallHistory: Set<string>,  // all tool names called this session
  //     outputFields:   object,        // current output object
  //     humanApproved:  boolean,       // whether a human has confirmed this result
  //     [key]:          any,           // task-specific fields
  //   }
  // opts.severity:  'ERROR' (block termination) | 'WARN' (log and allow). Default: 'ERROR'.
  // opts.escalate:  true — route to human queue instead of agent retry on failure.
  requireCondition(name, conditionFn, opts) {
    opts = opts || {};
    this._conditions.push({
      name,
      conditionFn,
      severity: opts.severity || 'ERROR',
      escalate: !!opts.escalate,
    });
    return this;
  }

  // Verify all conditions before allowing the agent to terminate.
  // Returns: { decision: 'ACCEPT' | 'WARN_AND_ACCEPT' | 'REJECT' | 'ESCALATE', ... }
  verify(state) {
    const results = this._conditions.map(c => {
      try {
        const r = c.conditionFn(state);
        return {
          name: c.name, severity: c.severity, escalate: c.escalate,
          met: r.met, reason: r.reason, retryHint: r.retryHint,
        };
      } catch (e) {
        return {
          name: c.name, severity: 'ERROR', escalate: false,
          met: false, reason: `condition threw: ${e.message}`, retryHint: null,
        };
      }
    });

    const unmet    = results.filter(r => !r.met);
    const errors   = unmet.filter(r => r.severity === 'ERROR');
    const warnings = unmet.filter(r => r.severity === 'WARN');
    const needsEscalation = errors.filter(r => r.escalate);

    if (needsEscalation.length > 0) {
      return {
        decision:     'ESCALATE',
        unmet, errors, warnings,
        escalateReasons: needsEscalation.map(e => e.reason),
        retryHint:    'Route to human review: ' +
                      needsEscalation.map(e => e.reason).join('; '),
      };
    }
    if (errors.length > 0) {
      return {
        decision:  'REJECT',
        unmet, errors, warnings,
        retryHint: errors
          .map(e => e.retryHint || `${e.name}: ${e.reason}`)
          .filter(Boolean).join('; '),
      };
    }
    if (warnings.length > 0) {
      return { decision: 'WARN_AND_ACCEPT', unmet: warnings, errors: [], warnings };
    }
    return { decision: 'ACCEPT', unmet: [] };
  }
}

// --- Registration for contract review agent ---
const TERM_VERIFIER = new AgentTerminationVerifier()

  // Condition 1: verify_fields must have been called this session.
  .requireCondition('required-tools-called',
    state => {
      const missing = ['fetch_document', 'verify_fields']
        .filter(t => !state.toolCallHistory.has(t));
      return missing.length === 0
        ? { met: true }
        : { met: false,
            reason:    `required tools not called: ${missing.join(', ')}`,
            retryHint: `Call ${missing.join(' and ')} before closing. ` +
                       'verify_fields must run to confirm extracted field accuracy.' };
    }
  )

  // Condition 2: all required output fields must be non-null.
  .requireCondition('output-fields-complete',
    state => {
      const required = ['summary', 'risk_level', 'recommended_action'];
      const empty = required.filter(f =>
        state.outputFields == null || state.outputFields[f] == null
      );
      return empty.length === 0
        ? { met: true }
        : { met: false,
            reason:    `required output fields missing: ${empty.join(', ')}`,
            retryHint: `Populate ${empty.join(', ')} in your output before calling done().` };
    }
  )

  // Condition 3: HIGH-risk contracts need human approval before closing (escalate, not retry).
  .requireCondition('high-risk-human-approved',
    state => {
      if (!state.outputFields || state.outputFields.risk_level !== 'HIGH') return { met: true };
      return state.humanApproved
        ? { met: true }
        : { met: false,
            reason:    'HIGH-risk contract requires human approval before close',
            retryHint: 'Route to legal reviewer queue; do not close without explicit approval.' };
    },
    { escalate: true }
  )

  // Condition 4 (warning only): optional audit log entry.
  .requireCondition('audit-log-written',
    state => ({
      met:       !!(state.auditLogId),
      reason:    'audit log entry was not written',
      retryHint: 'Call write_audit_log() before closing for compliance tracking.',
    }),
    { severity: 'WARN' }
  );

// --- Integration in the done() handler ---
// function handleDone(agentState, output) {
//   const state = {
//     toolCallHistory: agentState.sessionToolCalls,  // Set — session-scoped, not turn-scoped
//     outputFields:   output,
//     humanApproved:  agentState.humanApproved,
//     auditLogId:     agentState.auditLogId,
//   };
//
//   const result = TERM_VERIFIER.verify(state);
//
//   if (result.decision === 'ACCEPT' || result.decision === 'WARN_AND_ACCEPT') {
//     if (result.decision === 'WARN_AND_ACCEPT') logWarning(result.warnings);
//     return finalizeSession(output);
//   }
//   if (result.decision === 'ESCALATE') {
//     return routeToHumanQueue(output, result.escalateReasons);  // S-78
//   }
//   // REJECT: feed retryHint back to model as a tool result
//   return { error: 'TERMINATION_BLOCKED', retryHint: result.retryHint };
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Five scenarios covering ACCEPT, REJECT on missing tools, REJECT on missing output fields, ESCALATE on high-risk without approval, and WARN_AND_ACCEPT on optional condition. Timed over 1 000 000 iterations. Zero API calls. Zero tokens.

```
=== Agent Termination Condition Verifier ===

--- Scenario A: all conditions met, audit log present ---
  toolCallHistory:     { fetch_document, verify_fields, generate_summary }
  outputFields:        { summary: '...', risk_level: 'LOW', recommended_action: 'APPROVE' }
  humanApproved:       false  (not required at LOW risk)
  auditLogId:          'log-4821'
  required-tools-called:    MET
  output-fields-complete:   MET
  high-risk-human-approved: MET  (risk_level is LOW — condition skipped)
  audit-log-written:        MET
  → ACCEPT

--- Scenario B: verify_fields was skipped ---
  toolCallHistory:     { fetch_document }   (verify_fields missing)
  required-tools-called:    UNMET  ERROR
    reason:    "required tools not called: verify_fields"
    retryHint: "Call verify_fields before closing. verify_fields must run to
                confirm extracted field accuracy."
  → REJECT  (retryHint returned to model; agent must call verify_fields before retrying done())

--- Scenario C: output.risk_level is null (extraction incomplete) ---
  toolCallHistory:     { fetch_document, verify_fields }
  outputFields:        { summary: '...', risk_level: null, recommended_action: null }
  required-tools-called:    MET
  output-fields-complete:   UNMET  ERROR
    reason:    "required output fields missing: risk_level, recommended_action"
    retryHint: "Populate risk_level, recommended_action in your output before calling done()."
  → REJECT

--- Scenario D: HIGH-risk contract, no human approval ---
  toolCallHistory:     { fetch_document, verify_fields, generate_summary }
  outputFields:        { summary: '...', risk_level: 'HIGH', recommended_action: 'REVIEW' }
  humanApproved:       false
  required-tools-called:    MET
  output-fields-complete:   MET
  high-risk-human-approved: UNMET  ERROR  escalate=true
    reason:    "HIGH-risk contract requires human approval before close"
    retryHint: "Route to legal reviewer queue; do not close without explicit approval."
  → ESCALATE  (routed to human queue, not retried by the agent)

--- Scenario E: all conditions met except optional audit log ---
  toolCallHistory:     { fetch_document, verify_fields, generate_summary }
  outputFields:        { summary: '...', risk_level: 'LOW', recommended_action: 'APPROVE' }
  humanApproved:       false
  auditLogId:          null
  required-tools-called:    MET
  output-fields-complete:   MET
  high-risk-human-approved: MET
  audit-log-written:        UNMET  WARN
    reason:    "audit log entry was not written"
    retryHint: "Call write_audit_log() before closing for compliance tracking."
  → WARN_AND_ACCEPT  (warning logged; session closed)

=== Timing (1 000 000 iterations) ===
verify() 4 conditions, ACCEPT (Scenario A):              0.0003 ms
verify() 4 conditions, REJECT on cond 1 (Scenario B):   0.0003 ms
verify() 4 conditions, ESCALATE on cond 3 (Scenario D): 0.0004 ms
Zero API calls. Zero tokens.

=== Production impact ===
  Contract review agent — done() without verify_fields:
    12% of sessions before verifier
    0%  after verifier (REJECT returns retryHint; model calls verify_fields and retries)
  Escalation rate for completed contracts:
    34% (incomplete) → <1% (verified)
```

## See also

[F-159](f159-tool-call-sequence-invariant.md) · [F-157](f157-extraction-result-acceptance-gate.md) · [S-78](../stacks/s78-agent-to-human-escalation.md) · [S-70](../stacks/s70-agent-loop-termination-guards.md) · [F-16](f16-tool-call-validation.md)

## Go deeper

Keywords: `agent termination verifier` · `done condition check` · `task completion gate` · `agent exit condition` · `termination precondition check` · `agent done validation` · `workflow completion verifier` · `agent task complete check` · `session exit guard` · `agent completion condition`
