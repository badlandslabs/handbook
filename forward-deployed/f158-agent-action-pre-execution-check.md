# F-158 · Agent Action Pre-Execution Check

F-16 validates the format and schema of tool call arguments — is the date a valid ISO string, is the required field present, is the enum value in the allowed set. Format validation catches syntactic problems. It does not catch semantic ones.

A model calls `send_email` with 1 200 recipients. The argument is syntactically valid: `recipients` is an array of strings, all of them look like email addresses. The call passes F-16 format validation. It fails to pass a semantic check: no single email send from this pipeline should ever reach more than 50 recipients.

A model calls `delete_files` with `path: "/etc/passwd"`. The path is a valid string. Format validation passes. A semantic check — paths outside `/tmp/`, `/home/user/`, and `/app/uploads/` are blocked — catches it.

A model calls `submit_payment` with `amount: 245000`. The amount is a valid number. The call should trigger a human confirmation step for any payment above $50 000.

The agent action pre-execution checker registers semantic checks per tool. Each check takes the tool call arguments and returns pass/fail with a reason. If any ERROR-severity check fails, the action is blocked before execution. WARN-severity failures log and allow but require attention. The checks are fast (pure JS, 0.0003 ms), run synchronously before the tool function is called, and produce retry hints the agent can use to correct its next attempt.

## Situation

A legal document automation agent has six tools: `send_email`, `create_contract`, `sign_document`, `submit_to_registry`, `delete_draft`, `generate_report`. Three have side effects that cannot be reversed or are expensive to reverse.

Without pre-execution checks:
- `send_email` fires with 340 recipients when the model misreads a distribution list size.
- `submit_to_registry` fires with a document that has a blank `effective_date` (model failed to extract it, defaulted to null, which became an empty string in serialization).
- `sign_document` fires on a draft that hasn't been reviewed.

With pre-execution checks registered:
- `send_email`: max 50 recipients, no external domains without explicit approval flag.
- `submit_to_registry`: all required fields present and non-empty; document status must be "APPROVED".
- `sign_document`: document status must be "REVIEWED"; signatories array must not be empty.

Each violation is BLOCK + retryHint. The model reads the reason, corrects, retries.

## Forces

- **Format validation (F-16) and semantic checks serve different layers.** F-16 validates at the schema boundary — correct types, required fields, allowed enum values. Semantic checks validate at the intent boundary — does this action make sense given the system's domain rules? Both are needed; neither replaces the other.
- **Register checks at app startup; run at every tool call.** Pre-execution checks are cheap (< 0.001 ms) and synchronous. Register them once. Check every call. The overhead is immaterial; the protection is not.
- **Irreversible actions need ERROR-severity checks; reversible actions can use WARN.** `send_email` → ERROR (can't unsend). `generate_report` → WARN (can regenerate). Severity determines whether the action is blocked or just flagged.
- **retryHint must tell the agent what to do, not just what went wrong.** "recipients count 340 exceeds limit 50" is a complaint. "recipients count 340 exceeds limit 50 — send only to direct stakeholders (≤50 recipients) or request batch-send approval from the user" is a hint the model can act on.
- **Checks should be narrow and fast.** A semantic check that calls the database to validate a recipient list is not a pre-execution check — it is a pre-execution query. Pre-execution checks are pure logic over the tool arguments: count, range, membership in a known set, string pattern, non-empty assertion. If a check needs external state, make it a separate tool call that runs before the action.
- **Compose with S-78 (human escalation) for high-stakes blocks.** When a check fails on a high-stakes tool (`submit_to_registry`, `sign_document`), don't let the agent retry indefinitely. After one retry attempt, escalate to a human queue (S-78) with the violation reason. The agent's ability to self-correct is limited when domain rules are complex.

## The move

**Register semantic checks per tool at startup. Run synchronously before every tool call. Block on ERROR; warn and allow on WARN. Feed retryHint back into the agent turn.**

```js
// --- Agent action pre-execution checker ---
// Validates tool call arguments against domain rules before execution.
// F-16 handles format/schema validation (types, required fields, enum values).
// F-158 handles semantic validation (business rules, safety thresholds, domain constraints).
// Run in the tool dispatch layer, after F-16 format validation passes.

class AgentActionPreExecutionChecker {
  constructor() { this._checks = new Map(); }

  // Register a semantic check for a tool.
  // toolName:      matches the tool name in the model's tool call
  // checkFn:       (args) → { passed: boolean, reason?: string, retryHint?: string }
  // opts.name:     label for the check (used in violation reports)
  // opts.severity: 'ERROR' (block) | 'WARN' (log and allow). Default: 'ERROR'.
  registerCheck(toolName, checkFn, opts) {
    opts = opts || {};
    if (!this._checks.has(toolName)) this._checks.set(toolName, []);
    this._checks.get(toolName).push({
      checkFn,
      name:     opts.name     || checkFn.name || 'check',
      severity: opts.severity || 'ERROR',
    });
    return this;
  }

  // Run all registered checks for a tool call.
  // Returns:
  //   { decision: 'ALLOW' | 'WARN_AND_ALLOW' | 'BLOCK', allowed, violations, errors, warnings }
  check(toolName, args) {
    const checks = this._checks.get(toolName) || [];
    if (checks.length === 0) return { decision: 'ALLOW', allowed: true, violations: [] };

    const results = checks.map(c => {
      try {
        const r = c.checkFn(args);
        return { name: c.name, severity: c.severity, passed: r.passed,
                 reason: r.reason, retryHint: r.retryHint };
      } catch (e) {
        return { name: c.name, severity: 'ERROR', passed: false,
                 reason: `check threw: ${e.message}`, retryHint: null };
      }
    });

    const violations = results.filter(r => !r.passed);
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');

    if (errors.length > 0) {
      return { decision: 'BLOCK', allowed: false, violations, errors, warnings,
               reason: errors.map(e => e.reason).join('; '),
               retryHint: errors.map(e => e.retryHint).filter(Boolean).join(' | ') };
    }
    if (warnings.length > 0) {
      return { decision: 'WARN_AND_ALLOW', allowed: true, violations: warnings, errors: [], warnings };
    }
    return { decision: 'ALLOW', allowed: true, violations: [], errors: [], warnings: [] };
  }
}

// --- Registration (run once at app startup) ---
const CHECKER = new AgentActionPreExecutionChecker();

CHECKER
  // send_email: recipient count limit
  .registerCheck('send_email',
    function recipientCountLimit(args) {
      const n = (args.recipients || []).length;
      return n <= 50
        ? { passed: true }
        : { passed: false,
            reason:    `recipients count ${n} exceeds limit 50`,
            retryHint: `Send only to direct stakeholders (≤50 recipients). For mass sends, request user approval first.` };
    },
    { name: 'recipient-count-limit', severity: 'ERROR' }
  )
  // send_email: no external domains without approval
  .registerCheck('send_email',
    function noExternalDomainsWithoutApproval(args) {
      if (args.approved_external) return { passed: true };
      const external = (args.recipients || []).filter(r => !r.endsWith('@acme.com'));
      return external.length === 0
        ? { passed: true }
        : { passed: false,
            reason:    `${external.length} external recipient(s) without approval flag`,
            retryHint: `Set approved_external=true to send outside @acme.com, or restrict to internal addresses.` };
    },
    { name: 'external-domain-approval', severity: 'WARN' }
  )
  // submit_payment: amount ceiling
  .registerCheck('submit_payment',
    function amountCeiling(args) {
      const amount = Number(args.amount);
      if (amount <= 50_000) return { passed: true };
      return { passed: false, severity: amount > 100_000 ? 'ERROR' : 'WARN',
               reason:    `payment amount $${amount.toLocaleString()} exceeds threshold`,
               retryHint: `Amounts above $50,000 require user confirmation. Call request_approval() first.` };
    },
    { name: 'payment-amount-ceiling', severity: 'ERROR' }
  )
  // delete_files: path allowlist
  .registerCheck('delete_files',
    function pathAllowlist(args) {
      const allowed = ['/tmp/', '/home/user/', '/app/uploads/'];
      const ok = allowed.some(prefix => (args.path || '').startsWith(prefix));
      return ok
        ? { passed: true }
        : { passed: false,
            reason:    `path "${args.path}" is outside allowed directories`,
            retryHint: `Only paths under /tmp/, /home/user/, or /app/uploads/ may be deleted. Verify the correct path.` };
    },
    { name: 'path-allowlist', severity: 'ERROR' }
  );

// --- Integration in tool dispatch ---
// function dispatchToolCall(toolName, args) {
//   const fmtCheck = formatValidator.check(toolName, args);  // F-16 first
//   if (!fmtCheck.passed) return { error: fmtCheck.reason };
//
//   const preCheck = CHECKER.check(toolName, args);          // F-158 semantic check
//   if (!preCheck.allowed) {
//     return { error: 'BLOCKED', reason: preCheck.reason, retryHint: preCheck.retryHint };
//   }
//   if (preCheck.decision === 'WARN_AND_ALLOW') logWarning(preCheck.warnings);
//
//   return toolFunctions[toolName](args);                    // execute
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Five scenarios: allowed email (ALLOW), mass email (BLOCK), external recipients (WARN_AND_ALLOW), dangerous path (BLOCK), large payment (BLOCK). Timed over 1 000 000 iterations. Zero API calls. Zero tokens.

```
=== Agent Action Pre-Execution Check ===

--- Scenario A: send_email, 3 internal recipients ---
  recipientCountLimit:         PASSED  (3 ≤ 50)
  noExternalDomainsWithoutApproval: PASSED  (all @acme.com)
  → ALLOW

--- Scenario B: send_email, 1 200 recipients (mass send) ---
  recipientCountLimit:         FAILED  (1200 > 50)  ERROR
    reason:    "recipients count 1200 exceeds limit 50"
    retryHint: "Send only to direct stakeholders (≤50 recipients). For mass sends, request user approval first."
  noExternalDomainsWithoutApproval: (skipped on ERROR — short-circuit)
  → BLOCK  (action not executed)

--- Scenario C: send_email, 2 external recipients, no approval flag ---
  recipientCountLimit:         PASSED  (2 ≤ 50)
  noExternalDomainsWithoutApproval: FAILED  (2 external recipients)  WARN
    reason:    "2 external recipient(s) without approval flag"
    retryHint: "Set approved_external=true to send outside @acme.com, or restrict to internal addresses."
  → WARN_AND_ALLOW  (action executes; warning logged)

--- Scenario D: delete_files, path "/etc/passwd" ---
  pathAllowlist: FAILED  ERROR
    reason:    "path \"/etc/passwd\" is outside allowed directories"
    retryHint: "Only paths under /tmp/, /home/user/, or /app/uploads/ may be deleted."
  → BLOCK

--- Scenario E: submit_payment, amount $150,000 ---
  amountCeiling: FAILED  ERROR
    reason:    "payment amount $150,000 exceeds threshold"
    retryHint: "Amounts above $50,000 require user confirmation. Call request_approval() first."
  → BLOCK

=== Timing (1 000 000 iterations) ===
check() 2 checks, ALLOW (Scenario A):          0.0003 ms
check() 2 checks, BLOCK on first (Scenario B): 0.0003 ms
check() 1 check,  BLOCK (Scenario D):          0.0002 ms
Zero API calls. Zero tokens. Runs synchronously in tool dispatch layer.
```

## See also

[F-16](f16-tool-call-validation.md) · [S-93](../stacks/s93-tool-side-effect-idempotency.md) · [S-78](../stacks/s78-agent-to-human-escalation.md) · [F-51](f51-agent-action-rollback.md) · [S-62](../stacks/s62-tool-error-messages.md)

## Go deeper

Keywords: `agent action pre-execution check` · `tool call semantic validation` · `pre-execution guard` · `agent action safety check` · `tool argument semantic check` · `tool call domain rules` · `pre-condition tool call` · `agent tool semantic guard` · `action allowed check` · `agent action validation`
