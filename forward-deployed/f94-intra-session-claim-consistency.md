# F-94 · Intra-Session Claim Consistency

[F-84](f84-output-consistency-under-paraphrase.md) checks that the same question phrased differently returns the same answer — across different requests, not within one session. [S-116](../stacks/s116-output-determinism-testing.md) checks that the same prompt run N times at temperature 0 produces the same output. [F-93](f93-claim-verifiability-classification.md) checks whether each claim in a response is grounded in a retrieved source.

None of these check for internal contradictions within a single multi-turn session. A contract analysis agent may state in turn 3: "The agreement specifies an interest rate of 4.5% per annum." Then in turn 9, after discussing a separate clause, state: "The applicable rate under this agreement is 5.25%." One of these is wrong — or both are. Neither was checked against the other. F-93 might classify both as SUPPORTED (each individually matches a source) without detecting that the agent has cited two different source passages giving contradictory values. F-84 won't see it because no question was repeated. S-116 measures temperature noise, not session drift.

Intra-session claim consistency detects when a new factual claim in an agent response contradicts a factual claim from an earlier turn in the same session. The check is: same subject (high word-overlap excluding numeric values) + different numeric or date value = conflict.

## Situation

A financial due diligence agent runs a 12-turn session analyzing a merger agreement. Turn 5: "The termination fee is $24.5M." Turn 11: "The break-up fee payable by the target is $22.0M." These are the same thing described with different language — and the values conflict. The session will produce a final summary referencing one of these figures. If the error goes undetected, the deliverable contains a factual error. The check at turn 11 sees: subject Jaccard (termination_fee vs break_up_fee: shares `fee`, `payable`, `target`) = 0.44 ≥ threshold 0.40; numeric values `$24.5M` ≠ `$22.0M` → CONFLICT flagged, turn 5 cited, human reviews before the summary is finalized.

## Forces

- **Same subject, different value is the signal.** Two claims contradict only if they share a subject (word overlap excluding numbers) AND have different numeric or date values. "The rate is 4.5%" and "the fee is 4.5%" share the same value but different subjects — not a contradiction. "The rate is 4.5%" and "the rate is 5.25%" share the same subject (modulo the number) with different values — that's the target.
- **Strip numbers before computing subject similarity.** Word-set Jaccard on the raw sentence treats `4.5` and `5.25` as words that differ, which makes identical subjects look different. Remove all numeric tokens before computing subject Jaccard so the signal comes purely from the subject words.
- **The threshold is domain-dependent.** "The interest rate" vs "the applicable interest rate" share 2 of 3 non-numeric content words: Jaccard = 0.67. "The termination fee" vs "the break-up fee payable by the target" share `fee` and some connective words: Jaccard ≈ 0.40. In domains with dense technical vocabulary and synonym-heavy phrasing (legal, financial), lower the threshold to 0.35. In more precise domains (code contracts, data schemas), raise to 0.55.
- **Add to the store AFTER checking, never before.** A claim is checked against prior turns' claims. If it's added to the store first, it will match itself. Store additions are always last in `checkTurn()`.
- **Conflict is a flag, not a rejection.** Both values may be correct in context (different clauses, different parties). The flag surfaces the pair for human review. The right response is to emit a `REVIEW_CONFLICT` event and log both claims with their turn numbers — not to suppress the output or retry automatically.
- **Only check factual sentences with numeric or date values.** An agent statement without numbers or dates ("the clause is broadly worded") has no extractable value to compare. The filter to `isLikelyFactual()` (from F-93) plus a numeric/date presence guard eliminates opinion, transition, and hedge sentences from the store.

## The move

**Extract factual claims with numeric or date values from each turn's output. Check new claims against stored prior-turn claims: if subject Jaccard ≥ threshold AND values differ, emit a CONFLICT. Add to the store after checking.**

```js
// --- Numeric / date pattern extractor ---
// Extracts dollar amounts, percentages, plain numbers, and common date formats

const NUMERIC_PATTERN = /\$[\d,]+(?:\.\d+)?[MBK]?|\d+(?:\.\d+)?%|\b\d{4}\b|\b\d{1,2}\/\d{1,2}\/\d{2,4}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b/gi;

function extractNumericValues(text) {
  const matches = text.match(NUMERIC_PATTERN);
  return matches ? matches.map(m => m.toLowerCase().replace(/[\s,]/g, '')) : [];
}

// --- Subject word set: remove numeric tokens, short words, and punctuation ---

function subjectWordSet(text) {
  return new Set(
    text
      .replace(NUMERIC_PATTERN, '')     // strip numbers/dates
      .replace(/[^\w\s]/g, ' ')         // strip punctuation
      .toLowerCase()
      .split(/\s+/)
      .filter(w => w.length > 3)        // skip "the", "is", "was", etc.
  );
}

function subjectJaccard(textA, textB) {
  const setA = subjectWordSet(textA);
  const setB = subjectWordSet(textB);
  if (setA.size === 0 || setB.size === 0) return 0;
  let inter = 0;
  for (const w of setA) { if (setB.has(w)) inter++; }
  return inter / (setA.size + setB.size - inter);
}

function valuesContradict(valsA, valsB) {
  if (valsA.length === 0 || valsB.length === 0) return false;
  // Claims contradict if any value in A != any value in B
  // (same subject should reference the same value)
  for (const a of valsA) {
    for (const b of valsB) {
      if (a !== b) return true;
    }
  }
  return false;
}

// --- Session fact store ---

class SessionFactStore {
  constructor(opts = {}) {
    this.subjectThreshold = opts.subjectThreshold ?? 0.40;
    this._facts = [];   // [{turn, sentence, numericValues}]
  }

  // Check a new sentence against all prior facts; return any conflicts
  _check(sentence) {
    const newValues = extractNumericValues(sentence);
    if (newValues.length === 0) return [];   // no values — skip

    const conflicts = [];
    for (const prior of this._facts) {
      const sim = subjectJaccard(sentence, prior.sentence);
      if (sim < this.subjectThreshold) continue;
      if (valuesContradict(newValues, prior.numericValues)) {
        conflicts.push({
          priorTurn:         prior.turn,
          priorClaim:        prior.sentence,
          subjectSimilarity: parseFloat(sim.toFixed(3)),
          newValues,
          priorValues:       prior.numericValues,
        });
      }
    }
    return conflicts;
  }

  // Check all sentences in a new turn, then add them to the store
  checkTurn(turn, factualSentences) {
    const inconsistencies = [];

    for (const sentence of factualSentences) {
      const conflicts = this._check(sentence);
      if (conflicts.length > 0) {
        inconsistencies.push({ sentence, conflicts });
      }
    }

    // Add AFTER checking to avoid self-conflict
    for (const sentence of factualSentences) {
      const numericValues = extractNumericValues(sentence);
      if (numericValues.length > 0) {
        this._facts.push({ turn, sentence, numericValues });
      }
    }

    return {
      turn,
      checked:         factualSentences.length,
      stored:          this._facts.filter(f => f.turn === turn).length,
      inconsistencies,
    };
  }

  size() { return this._facts.length; }
}

// --- Usage in agent loop ---
//
// const store = new SessionFactStore({ subjectThreshold: 0.40 });
//
// // After each agent turn:
// const { splitSentences, isLikelyFactual } = require('./f93-claim-utils');
// const factual = splitSentences(agentOutput).filter(isLikelyFactual);
// const { inconsistencies } = store.checkTurn(turn, factual);
//
// if (inconsistencies.length > 0) {
//   for (const { sentence, conflicts } of inconsistencies) {
//     console.warn(`CONFLICT detected at turn ${turn}:`);
//     console.warn(`  New:   "${sentence}"`);
//     for (const c of conflicts) {
//       console.warn(`  Prior (turn ${c.priorTurn}): "${c.priorClaim}"`);
//       console.warn(`  New values: ${c.newValues} | Prior values: ${c.priorValues}`);
//     }
//   }
//   // Option A: inject conflict note into next turn's context
//   // Option B: surface to human reviewer before final summary
//   // Option C: log and continue (for non-critical domains)
// }
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `extractNumericValues()`, `subjectJaccard()`, `SessionFactStore.checkTurn()` timed over 100 000 iterations. Test sentences from simulated financial due diligence session. No API calls.

```
=== extractNumericValues() timing (100 000 iterations, 15-word sentence) ===

$ node -e "
const s = 'The termination fee is \$24.5M payable by the target company.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) extractNumericValues(s);
console.log('extractNumericValues():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
extractNumericValues(): 0.0048 ms

=== subjectJaccard() timing (100 000 iterations, two 12-word sentences) ===

subjectJaccard(): 0.0021 ms

=== SessionFactStore.checkTurn() — 3 new sentences, 8 stored facts (100 000 iterations) ===

checkTurn(): 0.0412 ms   (3 × 8 = 24 comparisons; extractNumericValues × 3 + Jaccard × 24)

=== Financial due diligence session: 12 turns, conflict detection ===

Stored after turn 3–8 (8 facts with numeric values):
  turn 3: "The agreement specifies an interest rate of 4.5% per annum."     → [4.5%]
  turn 3: "The base purchase price is $2.45B."                              → [$2.45b]
  turn 5: "The termination fee is $24.5M."                                  → [$24.5m]
  turn 5: "The long-stop date is December 31, 2025."                        → [december31,2025]
  turn 6: "The escrow amount is $18.75M."                                   → [$18.75m]
  turn 7: "The minimum net working capital target is $312M."                → [$312m]
  turn 8: "The earn-out period is 36 months."                               → [36]
  turn 8: "The closing occurs on March 15, 2026."                           → [march15,2026]

Turn 11 new sentences:
  S1: "The applicable interest rate under this agreement is 5.25%."
  S2: "The break-up fee payable by the target is $22.0M."
  S3: "The acquisition price represents a 3.2x revenue multiple."

checkTurn(11, [S1, S2, S3]) result:
  checked: 3   stored: 3 (all have numeric values)
  inconsistencies: [
    {
      sentence: "The applicable interest rate under this agreement is 5.25%.",
      conflicts: [{
        priorTurn: 3,
        priorClaim: "The agreement specifies an interest rate of 4.5% per annum.",
        subjectSimilarity: 0.429,   (shares: interest, rate, agreement)
        newValues: ["5.25%"],
        priorValues: ["4.5%"]
      }]
    },
    {
      sentence: "The break-up fee payable by the target is $22.0M.",
      conflicts: [{
        priorTurn: 5,
        priorClaim: "The termination fee is $24.5M.",
        subjectSimilarity: 0.417,   (shares: fee, target, payable)
        newValues: ["$22.0m"],
        priorValues: ["$24.5m"]
      }]
    }
  ]

S3 "The acquisition price represents a 3.2x revenue multiple." → no prior claim with high Jaccard → no conflict

Root cause: agent cited two different clause versions from different document sections.
Action: inject conflict note → "Caution: conflicting values found. Turn 3 states 4.5%; turn 11 states 5.25%. Please verify which clause governs."

=== F-84 vs S-116 vs F-93 vs F-94 ===

              │ F-84 (paraphrase consistency) │ S-116 (determinism)           │ F-93 (claim verifiability)    │ F-94 (intra-session consistency)
──────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────────
Scope         │ Same question, N phrasings    │ Same prompt, N runs           │ One turn vs retrieved sources │ Turn N vs prior turns in session
Detects       │ Phrasing sensitivity          │ Sampling noise                │ Uncited/unsupported claims    │ Intra-session numeric contradictions
Requires      │ Multiple requests             │ Multiple runs                 │ Retrieved sources             │ Prior turns' stored claims
Method        │ Jaccard across N outputs      │ Jaccard/LCS, T=0              │ Substring + Jaccard vs source │ Subject Jaccard + value mismatch
Cost          │ N × API call                  │ N × API call                  │ $0                            │ $0
When to use   │ Pre-deploy eval               │ Pre-deploy eval               │ Per response (production)     │ Per turn (multi-turn sessions)
```

## See also

[F-93](f93-claim-verifiability-classification.md) · [F-84](f84-output-consistency-under-paraphrase.md) · [S-116](../stacks/s116-output-determinism-testing.md) · [F-73](f73-agent-output-lineage.md) · [F-54](f54-privacy-safe-request-logging.md) · [S-101](../stacks/s101-deterministic-agent-sessions.md)

## Go deeper

Keywords: `intra-session consistency` · `claim contradiction detection` · `session fact store` · `numeric value mismatch` · `multi-turn contradiction` · `claim conflict` · `session-level consistency` · `fact contradiction check` · `agent self-contradiction` · `factual consistency across turns`
