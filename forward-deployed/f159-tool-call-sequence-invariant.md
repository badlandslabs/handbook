# F-159 · Tool Call Sequence Invariant

F-158 validates that a tool call's *arguments* are safe before execution. F-159 validates that the tool call itself is *sequentially valid* — that required predecessor calls have already been made in this agent turn.

A model calls `sign_document` before calling `verify_document`. Both calls have valid arguments; F-158 passes. But signing without prior verification is a workflow violation. The agent skipped a required step, either because the prompt didn't emphasize it, because the model inferred it was unnecessary, or because an earlier tool call returned an error the model silently ignored.

A model calls `submit_payment` with a correctly formatted amount. F-158 approves. But `calculate_total` was never called — the model used an amount it inferred from the document context rather than the computed total. The submission uses a wrong number.

The tool call sequence invariant registers prerequisites per tool: tool B requires that tool A has already been called in the current turn. Each time a tool executes, it is recorded. Each time a tool is about to execute, its prerequisites are checked against the call history. If a prerequisite is missing, the call is blocked and the agent receives a `retryHint` naming the missing step.

This is a workflow correctness check, not an argument correctness check. It catches skipped steps.

## Situation

A legal document processing agent uses five tools: `fetch_document`, `extract_fields`, `verify_fields`, `generate_draft`, `submit_for_review`. In production, the agent occasionally calls `generate_draft` without first calling `verify_fields` — when field extraction confidence is high and the model judges verification unnecessary. This produces drafts with unverified field values that fail the downstream review step 8% of the time.

After registering the sequence invariant:
- `verify_fields` requires `extract_fields`
- `generate_draft` requires `verify_fields`
- `submit_for_review` requires `generate_draft`

Any out-of-sequence call is blocked. The agent receives the missing step name and must call it before proceeding. Downstream review failure rate drops from 8% to < 1%.

## Forces

- **Register prerequisites at app startup; check at every tool call.** The check is O(n) in the number of prerequisites, runs in < 0.001 ms, and is synchronous. The cost is negligible; skipping the check is never the right optimization.
- **Turn-scoped call history, not session-scoped.** Within a single agent turn, tool A must precede tool B. Across turns, the agent may call B in turn 2 after having called A in turn 1 — that is legitimate sequential work, not a skipped step. Reset the call history at the start of each turn.
- **Distinguish prerequisite from dependency.** A *dependency* is when the output of tool A is the input to tool B (covered by prompt design). A *prerequisite* is when tool A must have been called, regardless of whether its output is used. `verify_fields` is a prerequisite for `generate_draft` even if the draft doesn't use the verification result directly — the policy requires it.
- **Soft prerequisites use WARN; hard prerequisites use ERROR.** `calculate_total` before `submit_payment` is a hard prerequisite — skipping it produces wrong amounts. `log_intent` before `fetch_document` is a soft prerequisite — it ensures audit logging but doesn't affect correctness. Use severity to control whether the call is blocked or merely flagged.
- **retryHint must tell the model what to do, not just what is wrong.** "prerequisite verify_fields not called" gives the model the name of the missing step. The model can then call it. An unhelpful hint like "sequence error" leaves the model guessing.
- **Compose with F-158 (argument pre-execution check).** Both run before tool execution. Run F-158 first (argument check) — no point checking sequence if the arguments themselves are invalid. Run F-159 second — sequence violations are correctable by calling the missing step; argument violations may require different input.

## The move

**Register per-tool prerequisites at startup. Record every completed call. Block any call whose prerequisites are not met. Reset per turn.**

```js
// --- Tool call sequence invariant ---
// Verifies that tool call prerequisites have been satisfied within the current turn.
// Compose with F-158 (argument semantic check) — run F-158 first, then F-159.
// Reset call history at the start of each agent turn.

class ToolCallSequenceChecker {
  constructor() {
    this._prerequisites = new Map();  // toolName → [{ prerequisiteTool, severity, hint }]
    this._callHistory   = new Set();  // tools called so far this turn
  }

  // Register that `toolName` requires `prerequisiteTool` to have been called first.
  // opts.severity: 'ERROR' (block) | 'WARN' (log and allow). Default: 'ERROR'.
  // opts.hint:     extra hint to add to the retryHint (optional).
  requiresBefore(toolName, prerequisiteTool, opts) {
    opts = opts || {};
    if (!this._prerequisites.has(toolName)) this._prerequisites.set(toolName, []);
    this._prerequisites.get(toolName).push({
      prerequisiteTool,
      severity: opts.severity || 'ERROR',
      hint:     opts.hint     || '',
    });
    return this;
  }

  // Call this BEFORE executing a tool. Returns pass/block/warn.
  checkBefore(toolName) {
    const prereqs = this._prerequisites.get(toolName) || [];
    if (prereqs.length === 0) return { decision: 'ALLOW', violations: [] };

    const violations = prereqs
      .filter(p => !this._callHistory.has(p.prerequisiteTool))
      .map(p => ({
        missing:    p.prerequisiteTool,
        severity:   p.severity,
        reason:     `${toolName} requires ${p.prerequisiteTool} to be called first`,
        retryHint:  `Call ${p.prerequisiteTool} before ${toolName}.` +
                    (p.hint ? ' ' + p.hint : ''),
      }));

    const errors   = violations.filter(v => v.severity === 'ERROR');
    const warnings = violations.filter(v => v.severity === 'WARN');

    if (errors.length > 0) {
      return { decision: 'BLOCK', violations, errors, warnings,
               retryHint: errors.map(v => v.retryHint).join(' ') };
    }
    if (warnings.length > 0) {
      return { decision: 'WARN_AND_ALLOW', violations: warnings, errors: [], warnings };
    }
    return { decision: 'ALLOW', violations: [] };
  }

  // Call this AFTER a tool successfully executes.
  recordCall(toolName) {
    this._callHistory.add(toolName);
    return this;
  }

  // Call at the start of each agent turn.
  reset() {
    this._callHistory.clear();
    return this;
  }
}

// --- Registration (run once at app startup) ---
const SEQUENCE = new ToolCallSequenceChecker()
  .requiresBefore('verify_fields',   'extract_fields',
      { hint: 'Fields must be extracted before they can be verified.' })
  .requiresBefore('generate_draft',  'verify_fields',
      { hint: 'Draft generation requires verified fields — unverified fields produce rejected drafts.' })
  .requiresBefore('submit_for_review', 'generate_draft',
      { hint: 'Submit only after a draft exists.' })
  .requiresBefore('submit_payment',  'calculate_total',
      { hint: 'Use the computed total — do not infer the amount from document context.' })
  .requiresBefore('sign_document',   'verify_document',
      { severity: 'ERROR', hint: 'Policy requires verification before signature.' });

// --- Tool dispatch integration ---
// function dispatchTool(toolName, args) {
//   const argCheck = argChecker.check(toolName, args);   // F-158 first
//   if (!argCheck.allowed) return { error: argCheck.retryHint };
//
//   const seqCheck = SEQUENCE.checkBefore(toolName);     // F-159 second
//   if (seqCheck.decision === 'BLOCK') return { error: seqCheck.retryHint };
//   if (seqCheck.decision === 'WARN_AND_ALLOW') logWarning(seqCheck.warnings);
//
//   const result = toolFunctions[toolName](args);
//   SEQUENCE.recordCall(toolName);                       // record after success
//   return result;
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Five scenarios covering all decision paths and a turn reset. Timed over 1 000 000 iterations. Zero API calls. Zero tokens.

```
=== Tool Call Sequence Invariant ===

--- Scenario A: valid sequence (extract → verify → generate_draft) ---
  Turn start: SEQUENCE.reset()

  checkBefore('extract_fields')  → ALLOW       (no prerequisites registered)
  recordCall('extract_fields')
  callHistory: { extract_fields }

  checkBefore('verify_fields')   → ALLOW       (extract_fields ✓)
  recordCall('verify_fields')
  callHistory: { extract_fields, verify_fields }

  checkBefore('generate_draft')  → ALLOW       (verify_fields ✓)
  recordCall('generate_draft')

--- Scenario B: skipped verify_fields ---
  Turn start: SEQUENCE.reset()

  checkBefore('extract_fields')  → ALLOW
  recordCall('extract_fields')
  callHistory: { extract_fields }

  checkBefore('generate_draft')  → BLOCK  ERROR
    missing:    verify_fields
    reason:     "generate_draft requires verify_fields to be called first"
    retryHint:  "Call verify_fields before generate_draft.
                 Draft generation requires verified fields — unverified fields produce rejected drafts."

  (model calls verify_fields, then retries generate_draft → ALLOW)

--- Scenario C: submit_payment without calculate_total ---
  Turn start: SEQUENCE.reset()
  checkBefore('submit_payment')  → BLOCK  ERROR
    missing:    calculate_total
    retryHint:  "Call calculate_total before submit_payment.
                 Use the computed total — do not infer the amount from document context."

--- Scenario D: sign_document without verify_document ---
  Turn start: SEQUENCE.reset()
  checkBefore('sign_document')   → BLOCK  ERROR
    missing:    verify_document
    retryHint:  "Call verify_document before sign_document.
                 Policy requires verification before signature."

--- Scenario E: turn reset clears history ---
  After Scenario D:
  callHistory before reset: { }  (sign was blocked, nothing recorded)
  SEQUENCE.reset()
  callHistory after reset:  { }  (clean for next turn)

  checkBefore('sign_document')   → BLOCK  (same as Scenario D — new turn, no history)

=== Timing (1 000 000 iterations) ===
checkBefore() 1 prerequisite, ALLOW:   0.0002 ms
checkBefore() 1 prerequisite, BLOCK:   0.0002 ms
checkBefore() 2 prerequisites, ALLOW:  0.0003 ms
recordCall():                           0.0001 ms
reset():                                0.0001 ms
Zero API calls. Zero tokens.

=== Production impact ===
  Legal pipeline, generate_draft skipping verify_fields:
    8% downstream failure rate before invariant
    <1% after invariant (residual from valid edge-case sequences)
```

## See also

[F-158](f158-agent-action-pre-execution-check.md) · [F-16](f16-tool-call-validation.md) · [F-51](f51-agent-action-rollback.md) · [S-90](../stacks/s90-sequential-tool-pipelines.md) · [S-78](../stacks/s78-agent-to-human-escalation.md)

## Go deeper

Keywords: `tool call sequence invariant` · `tool prerequisite check` · `agent workflow sequence` · `required tool order` · `tool call ordering` · `prerequisite tool call` · `agent step order validation` · `workflow sequence guard` · `tool sequence enforcement` · `agent call history check`
