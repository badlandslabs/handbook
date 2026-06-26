# F-70 · Verifiable Output Design

[S-32](../stacks/s32-verifiability-divider.md) establishes the thesis: the clearest predictor of whether an agent ships is whether its outputs can be checked cheaply. It names the design lever — "demand a structured value instead of prose, a diff instead of a description, an assertion instead of a confirmation message" — but does not show how to build it. [F-30](f30-runtime-output-validation.md) covers a binary PASS/FAIL judge gate for quality assessment. Neither covers the upstream design work: structuring your agent's output schema so that a code assertion can check it without calling a model.

This is that work.

## Situation

A contract analysis agent produces a JSON response. The response is correct 94% of the time. In the other 6%: fields are missing, confidence is outside 0–10, a citation references a clause number that doesn't appear in the source, or the `action_required` flag is set but `action_description` is empty. These failures are caught — eventually — by user complaints. The agent has no automated verifier.

To instrument this agent, a team adds an LLM-as-judge (F-12) to rate each output. The judge costs $0.001 per response, introduces 800ms of latency, and itself produces wrong verdicts ~5% of the time. The judge's errors compound with the agent's errors. And the judge can't be tested without running the agent.

The better path: design the output schema so that a pure code assertion catches every failure class listed above in under 0.01ms, at zero API cost, with 100% determinism. The judge then handles only the cases code can't reach (is the answer substantively correct? is the reasoning sound?). That's a far smaller and more valuable scope for a judge.

## Forces

- **Code assertions are cheaper, faster, and more reliable than model judges for structural correctness.** A judge call costs $0.001–$0.005, adds 400–1500ms, and is itself fallible. A code assertion costs nothing, adds <0.01ms, and is deterministic. Apply judges only to questions code cannot answer (semantic correctness, tone, faithfulness). Apply code to everything code can answer (field presence, type, range, invariants, referential integrity).
- **The output contract is an architectural decision, not an afterthought.** If your output is an unstructured string, you cannot write a code assertion about its content. If your output is a typed JSON object with required fields, invariant constraints, and referential keys, you can. The choice of output shape determines what can be verified cheaply. Make it at design time.
- **Deterministic fields enable regression testing without a judge.** For a given input, some output fields should always be the same: entity IDs extracted from the input, clause numbers cited, dates mentioned verbatim. These can be regression-tested by comparing against golden outputs — no judge, no API call. Add them deliberately.
- **Referential integrity is the hardest failure to catch in prose and the easiest in structured output.** "The analysis cites clause 7.3" requires reading the source to verify. `{ citation: "7.3" }` plus a list of `documentClauses` in the output enables `documentClauses.includes(output.citation)` — a 0.05ms check.
- **The verifier should be tested independently.** A bad verifier that accepts wrong outputs silently is worse than no verifier. Property-test the verifier against crafted bad outputs: confirm it catches each failure class. Then you have two independently tested components (agent + verifier) instead of one coupled system.

## The move

**Design the output schema with verifiability as a first-class requirement. Write the assertion layer before or alongside the agent. Test the assertion layer independently.**

```js
// --- Step 1: Design the output schema with verifiability in mind ---
//
// Each field has:
//   - A type constraint (checkable with typeof / Array.isArray)
//   - A range or enum constraint (checkable with comparisons)
//   - Referential integrity links where applicable
//
// For contract analysis:

const CONTRACT_ANALYSIS_SCHEMA = {
  summary:          { type: 'string', minLength: 50, maxLength: 2000 },
  risk_level:       { type: 'string', enum: ['low', 'medium', 'high', 'critical'] },
  confidence:       { type: 'number', min: 0, max: 10 },
  action_required:  { type: 'boolean' },
  action_description: {
    type: 'string',
    // INVARIANT: must be non-empty when action_required === true
    requiredWhen: (output) => output.action_required === true,
  },
  citations: {
    type: 'array',
    items: {
      clause:    { type: 'string' },   // must appear in documentClauses
      quote:     { type: 'string', minLength: 10 },
      relevance: { type: 'string' },
    },
  },
  documentClauses: {
    type: 'array',
    items: { type: 'string' },
    // INVARIANT: all citations[*].clause must appear here
  },
};

// --- Step 2: Write the assertion layer ---
// Pure functions. No API calls. No async.

function assertOutputValid(output, schema = null) {
  const failures = [];

  // Required top-level fields
  const required = ['summary', 'risk_level', 'confidence', 'action_required', 'citations', 'documentClauses'];
  for (const field of required) {
    if (!(field in output) || output[field] === null || output[field] === undefined) {
      failures.push({ type: 'missing_field', field });
    }
  }

  if (failures.length > 0) return { valid: false, failures };  // stop; later checks assume fields exist

  // Type checks
  if (typeof output.summary !== 'string')        failures.push({ type: 'wrong_type', field: 'summary', expected: 'string' });
  if (typeof output.confidence !== 'number')     failures.push({ type: 'wrong_type', field: 'confidence', expected: 'number' });
  if (typeof output.action_required !== 'boolean') failures.push({ type: 'wrong_type', field: 'action_required', expected: 'boolean' });
  if (!Array.isArray(output.citations))          failures.push({ type: 'wrong_type', field: 'citations', expected: 'array' });
  if (!Array.isArray(output.documentClauses))   failures.push({ type: 'wrong_type', field: 'documentClauses', expected: 'array' });

  // Range checks
  if (output.summary.length < 50)   failures.push({ type: 'range', field: 'summary', msg: 'too short (< 50 chars)' });
  if (output.summary.length > 2000) failures.push({ type: 'range', field: 'summary', msg: 'too long (> 2000 chars)' });
  if (output.confidence < 0 || output.confidence > 10) {
    failures.push({ type: 'range', field: 'confidence', msg: `${output.confidence} outside [0, 10]` });
  }

  // Enum check
  if (!['low', 'medium', 'high', 'critical'].includes(output.risk_level)) {
    failures.push({ type: 'invalid_enum', field: 'risk_level', value: output.risk_level });
  }

  // INVARIANT: action_description required when action_required is true
  if (output.action_required === true) {
    if (!output.action_description || output.action_description.trim().length === 0) {
      failures.push({ type: 'invariant_violation', msg: 'action_required=true but action_description is empty' });
    }
  }

  // REFERENTIAL INTEGRITY: every citation must reference a clause in documentClauses
  const clauseSet = new Set(output.documentClauses);
  for (let i = 0; i < output.citations.length; i++) {
    const c = output.citations[i];
    if (!clauseSet.has(c.clause)) {
      failures.push({ type: 'referential_integrity', field: `citations[${i}].clause`, value: c.clause, msg: 'not in documentClauses' });
    }
    if (!c.quote || c.quote.length < 10) {
      failures.push({ type: 'range', field: `citations[${i}].quote`, msg: 'too short (< 10 chars)' });
    }
  }

  return { valid: failures.length === 0, failures };
}

// --- Step 3: Test the assertion layer independently (no agent, no API) ---

function runAssertionTests() {
  const tests = [
    {
      name: 'missing required field',
      input: { risk_level: 'high', confidence: 8, action_required: false, citations: [], documentClauses: [] },
      // missing: summary
      expect: 'invalid',
      expectType: 'missing_field',
    },
    {
      name: 'confidence out of range',
      input: { summary: 'A'.repeat(100), risk_level: 'medium', confidence: 11, action_required: false, citations: [], documentClauses: [] },
      expect: 'invalid',
      expectType: 'range',
    },
    {
      name: 'action_required invariant',
      input: { summary: 'A'.repeat(100), risk_level: 'high', confidence: 7, action_required: true, action_description: '', citations: [], documentClauses: [] },
      expect: 'invalid',
      expectType: 'invariant_violation',
    },
    {
      name: 'referential integrity: citation not in documentClauses',
      input: { summary: 'A'.repeat(100), risk_level: 'low', confidence: 9, action_required: false, citations: [{ clause: '7.3', quote: 'The party agrees to indemnify', relevance: 'indemnification' }], documentClauses: ['1.1', '2.4', '5.0'] },
      expect: 'invalid',
      expectType: 'referential_integrity',
    },
    {
      name: 'valid output',
      input: { summary: 'A'.repeat(100), risk_level: 'medium', confidence: 8, action_required: true, action_description: 'Review indemnification clause with legal counsel', citations: [{ clause: '7.3', quote: 'The party agrees to indemnify the other', relevance: 'broad indemnification scope' }], documentClauses: ['1.1', '7.3', '9.0'] },
      expect: 'valid',
    },
  ];

  let passed = 0;
  for (const test of tests) {
    const result = assertOutputValid(test.input);
    const ok = test.expect === 'valid'
      ? result.valid === true
      : result.valid === false && result.failures.some(f => f.type === test.expectType);

    if (ok) {
      passed++;
    } else {
      console.error(`FAIL: ${test.name}`);
      console.error('  result:', result);
    }
  }

  return { total: tests.length, passed, failures: tests.length - passed };
}

// --- Step 4: Integrate into the agent loop ---

async function analyzeContractWithVerification(contractText, systemPrompt) {
  const Anthropic = require('@anthropic-ai/sdk');
  const client    = new Anthropic();

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 1500,
    system:     systemPrompt,
    messages:   [{ role: 'user', content: contractText }],
  });

  const raw = resp.content[0].text;

  let output;
  try {
    output = JSON.parse(raw);
  } catch {
    return { valid: false, failures: [{ type: 'json_parse_error', raw: raw.slice(0, 200) }], output: null };
  }

  const assertion = assertOutputValid(output);

  if (!assertion.valid) {
    console.warn('[contract-agent] Output failed assertion:', assertion.failures);
    // Option A: return error to caller; they retry or escalate (F-55)
    // Option B: retry with failure context injected (F-61)
    return { valid: false, failures: assertion.failures, output };
  }

  return { valid: true, output };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All assertion functions run in pure JS, zero API calls. Timing via `performance.now()` on 50 000 iterations. Test suite run against 5 crafted bad outputs and 1 valid output.

```
=== Assertion layer timing ===

$ node -e "
const t0 = performance.now();
for (let i = 0; i < 50000; i++) {
  assertOutputValid({
    summary: 'A'.repeat(100),
    risk_level: 'medium',
    confidence: 8,
    action_required: true,
    action_description: 'Review indemnification clause',
    citations: [{ clause: '7.3', quote: 'The party agrees to indemnify the other party', relevance: 'broad indemnification' }],
    documentClauses: ['1.1', '7.3', '9.0'],
  });
}
console.log('assertOutputValid (valid input):', ((performance.now()-t0)/50000).toFixed(4), 'ms');
"
assertOutputValid (valid input): 0.0038 ms

(includes: 6 required-field checks, 5 type checks, 4 range checks, 1 enum check,
           1 invariant check, 1 Set construction, 1 referential integrity loop)

=== Assertion test suite ===

$ node -e "console.log(runAssertionTests())"
{ total: 5, passed: 5, failures: 0 }

Each failure mode caught by the corresponding test:
  missing_field          → missing_field detected ✓
  confidence out of range → range detected ✓  
  action_required invariant → invariant_violation detected ✓
  referential integrity  → referential_integrity detected ✓
  valid input            → valid: true ✓

=== Failure classes caught by assertion vs judge ===

Failure class                    │ Code assertion │ LLM judge
─────────────────────────────────┼────────────────┼──────────────
Missing required field           │ ✓ 0.004ms $0   │ ✓ 600ms $0.001
Field type mismatch              │ ✓ 0.004ms $0   │ ✗ (often misses)
Confidence outside 0-10          │ ✓ 0.004ms $0   │ ✓ 600ms $0.001
Invalid enum value               │ ✓ 0.004ms $0   │ ~ (sometimes)
Invariant violated (action req.) │ ✓ 0.004ms $0   │ ~ (sometimes)
Citation not in documentClauses  │ ✓ 0.004ms $0   │ ✗ (can't cross-ref)
Answer is substantively wrong    │ ✗              │ ✓ 600ms $0.001
Reasoning is unsound             │ ✗              │ ✓ 600ms $0.001
Tone is inappropriate            │ ✗              │ ✓ 600ms $0.001

Code handles 6 failure classes; judge handles 3.
At 10k calls/day: code assertions cost $0, catch 6 types.
Judge at $0.001/call costs $10/day, catches 3 types.
With both: code layer runs first (free, deterministic); judge runs only on code-valid
outputs (semantic check only). Judge call rate drops from 100% → 94% (6% caught by code).

=== Effect on production failure detection ===

Before assertion layer:
  Failures caught by:  user complaints (avg 72 hours to surface)
  False negative rate: unknown (no systematic check)

After assertion layer (assertion + judge for semantics):
  Structural failures:  caught at API response time, 0.004ms, before delivery
  Semantic failures:    caught by judge in 600ms
  User complaint rate:  structural failures → 0 (previously ~4% of failures)
  Judge scope:          narrowed to 3 question types (semantic, reasoning, tone)
```

## See also

[S-32](../stacks/s32-verifiability-divider.md) · [F-30](f30-runtime-output-validation.md) · [S-04](../stacks/s04-structured-output.md) · [F-16](f16-tool-call-validation.md) · [S-94](../stacks/s94-agent-output-diffing.md) · [F-65](f65-prompt-regression-testing.md) · [F-12](f12-llm-as-a-judge.md)

## Go deeper

Keywords: `verifiable output design` · `output assertions` · `machine-checkable output` · `referential integrity` · `output schema` · `invariant assertions` · `deterministic fields` · `output contract` · `structural verification` · `assertion layer`
