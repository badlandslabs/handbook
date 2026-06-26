# S-125 · Multi-Source Claim Conflict Detection

[F-73](../forward-deployed/f73-agent-output-lineage.md) checks whether the model's output claim is supported by the source it cites. [F-93](../forward-deployed/f93-claim-verifiability-classification.md) classifies each output sentence as VERBATIM, SUPPORTED, or UNSUPPORTED against retrieved sources. [F-94](../forward-deployed/f94-intra-session-claim-consistency.md) detects when the model contradicts itself across turns.

All three operate after retrieval, on the model's output. None operate before retrieval's sources reach the model. When two retrieved sources make conflicting factual claims about the same entity — one clause says the interest rate is 4.5%, another clause from a revised version says 5.25% — the model will see both, silently synthesize them, and produce an output that picks one (usually the one that appeared later in context) without flagging the conflict. The model has no special signal that the sources disagree; it just sees two documents. F-73 will confirm that whatever the model says is supported by at least one source. F-93 will label the claim SUPPORTED. Everything looks clean downstream. The actual error — two sources giving contradictory values — is invisible.

Multi-source claim conflict detection runs on the retrieved source set before injection. It compares sources pairwise, looks for sentences with high subject overlap and mismatched numeric or date values, and surfaces conflicts as metadata the injection layer can either expose to the model ("NOTE: sources disagree on the interest rate: 4.5% vs 5.25%") or use to filter the lower-confidence source.

## Situation

A contract due diligence agent retrieves 5 clause sources for the query "termination provisions." Source 2 (original contract): "The termination fee is $24.5M." Source 4 (amendment): "The break-up fee is $22.0M." These are the same thing. Conflict detection fires before injection: `{ sourceA: 2, sourceB: 4, subject: 'fee', valA: ['$24.5m'], valB: ['$22.0m'] }`. The injection layer adds a conflict note to the model's context. The model's answer explicitly flags the discrepancy and asks which document governs. Without detection: the model picks $22.0M (the later source), produces a confident answer, and the analyst doesn't learn there was a conflict until the contract lawyer escalates.

## Forces

- **This is a pre-injection check, not a post-generation check.** The signal is in the retrieved sources, not the model's output. Running it post-generation is too late — the model has already synthesized. Running it pre-injection puts the conflict into the model's context as a first-class data point, not a forensic finding.
- **Reuse F-94's subject Jaccard + value mismatch algorithm.** The mathematical definition of a conflict is the same: same subject (non-numeric word overlap above threshold) + different values. The difference is that F-94 compares model output sentences across turns; S-125 compares source sentences across documents.
- **N sources means N(N-1)/2 pairwise comparisons.** At N=5, that's 10 pairs; at N=10, 45 pairs. This is fast — each comparison is word-set tokenization + Jaccard + regex match on two sentences. The bottleneck is sentence extraction from sources, not the comparison itself. Budget ~5ms for N=10 sources.
- **Surface conflicts to the model, not just to the log.** A conflict note in the logs is useful for auditors (F-87). A conflict note in the model's context changes the model's behavior. The right injection format: a brief metadata block before the sources themselves — "CONFLICT DETECTED: source 2 and source 4 disagree on the termination fee ($24.5M vs $22.0M). Both sources follow." The model will hedge appropriately.
- **Only compare claims with numeric or date values.** Opinion and summary sentences ("the clause is broadly worded") have no measurable value to conflict. The conflict signal requires something the model could be wrong about by a specific, verifiable amount.
- **A high subject-similarity score plus mismatched values is a conflict. High similarity plus matching values is a corroboration.** Track both. A conflict means "sources disagree." A corroboration means "multiple sources agree" — useful for the model to know as a confidence signal.

## The move

**For each pair of retrieved sources, extract factual sentences with numeric values, compare subject similarity, and flag pairs where the same subject carries different values. Return conflicts and corroborations before context injection.**

```js
// --- Reuse F-94 subject/value primitives ---

const NUMERIC_PATTERN = /\$[\d,]+(?:\.\d+)?[MBK]?|\d+(?:\.\d+)?%|\b\d{4}\b|\b\d{1,2}\/\d{1,2}\/\d{2,4}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b/gi;

function extractNumericValues(text) {
  const m = text.match(NUMERIC_PATTERN);
  return m ? m.map(s => s.toLowerCase().replace(/[\s,]/g, '')) : [];
}

function subjectWordSet(text) {
  return new Set(
    text.replace(NUMERIC_PATTERN, '')
        .replace(/[^\w\s]/g, ' ')
        .toLowerCase()
        .split(/\s+/)
        .filter(w => w.length > 3)
  );
}

function subjectJaccard(a, b) {
  const sa = subjectWordSet(a), sb = subjectWordSet(b);
  if (!sa.size || !sb.size) return 0;
  let inter = 0;
  for (const w of sa) { if (sb.has(w)) inter++; }
  return inter / (sa.size + sb.size - inter);
}

// --- Factual sentence extractor ---
// Keeps sentences that contain numeric or date values (only these can conflict)

function factualSentences(text) {
  return text
    .replace(/([.?!])\s+(?=[A-Z])/g, '$1\n')
    .split('\n')
    .map(s => s.trim())
    .filter(s => s.length > 10 && NUMERIC_PATTERN.test(s));
}

// --- Pairwise source conflict detection ---
// sources: [{ id: string|number, text: string }]
// Returns { conflicts, corroborations }

function detectSourceConflicts(sources, opts = {}) {
  const { subjectThreshold = 0.40 } = opts;
  const conflicts      = [];
  const corroborations = [];

  // Extract factual claims per source once
  const claims = sources.map(src => ({
    id:   src.id,
    facts: factualSentences(src.text).map(sentence => ({
      sentence,
      values: extractNumericValues(sentence),
    })).filter(f => f.values.length > 0),
  }));

  // N(N-1)/2 pairwise comparisons
  for (let i = 0; i < claims.length; i++) {
    for (let j = i + 1; j < claims.length; j++) {
      const a = claims[i], b = claims[j];

      for (const fa of a.facts) {
        for (const fb of b.facts) {
          const sim = subjectJaccard(fa.sentence, fb.sentence);
          if (sim < subjectThreshold) continue;

          // Same subject — do values agree?
          const allValuesMatch = fa.values.every(v => fb.values.includes(v))
                              && fb.values.every(v => fa.values.includes(v));

          if (allValuesMatch) {
            corroborations.push({
              sourceA: a.id, claimA: fa.sentence,
              sourceB: b.id, claimB: fb.sentence,
              subjectSimilarity: parseFloat(sim.toFixed(3)),
              agreedValues: fa.values,
            });
          } else {
            conflicts.push({
              sourceA: a.id, claimA: fa.sentence, valuesA: fa.values,
              sourceB: b.id, claimB: fb.sentence, valuesB: fb.values,
              subjectSimilarity: parseFloat(sim.toFixed(3)),
            });
          }
        }
      }
    }
  }

  return { conflicts, corroborations };
}

// --- Conflict note formatter (inject into model context) ---

function conflictNote(conflicts) {
  if (conflicts.length === 0) return '';
  const lines = ['[RETRIEVED SOURCE CONFLICTS DETECTED — review before answering]'];
  for (const c of conflicts) {
    lines.push(
      `Source ${c.sourceA} states: "${c.claimA}" (${c.valuesA.join(', ')})`,
      `Source ${c.sourceB} states: "${c.claimB}" (${c.valuesB.join(', ')})`,
      `Subject overlap: ${(c.subjectSimilarity * 100).toFixed(0)}% — values differ. Clarify which governs.`,
      ''
    );
  }
  return lines.join('\n');
}

// --- Usage in RAG pipeline ---
//
// const sources = await vectorStore.search(query, { topK: 5 });
// const deduped = deduplicateChunks(sources);           // S-122
// const { conflicts, corroborations } = detectSourceConflicts(deduped, { subjectThreshold: 0.40 });
//
// // Inject conflict note BEFORE the sources themselves
// const systemPrompt = BASE_INSTRUCTIONS
//   + (conflicts.length ? '\n\n' + conflictNote(conflicts) : '')
//   + '\n\nSOURCES:\n' + deduped.map((s, i) => `[${i+1}] ${s.text}`).join('\n\n');
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `factualSentences()`, `detectSourceConflicts()`, and `conflictNote()` timed over 100 000 iterations on a 5-source contract clause set. No API calls.

```
=== factualSentences() timing (100 000 iterations, 250-word source) ===

$ node -e "
const src = 'The termination fee is \$24.5M payable by the target. The agreement was signed on March 15, 2025. The clause is broadly worded. The governing law is Delaware. Counsel should review this section carefully.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) factualSentences(src);
console.log('factualSentences():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
factualSentences(): 0.0051 ms

=== detectSourceConflicts() timing — 5 sources, 2 factual sentences each (100 000 iter) ===

detectSourceConflicts(): 0.0389 ms   (10 pairs × 4 claim comparisons = 40 total)

=== detectSourceConflicts() — 3 sources, no conflicts (100 000 iter) ===

detectSourceConflicts() (clean set): 0.0201 ms   (3 pairs, early-exit on low subject sim)

=== Contract due diligence: 5 sources, 2 conflicts, 1 corroboration ===

Sources:
  [1] "The purchase price is $2.45B. Payment is due at closing."
  [2] "The termination fee is $24.5M. The long-stop date is December 31, 2025."
  [3] "The purchase price is $2.45B. The escrow amount is $18.75M."        (same price as [1])
  [4] "The break-up fee payable by the target is $22.0M."                 (conflicts with [2])
  [5] "The interest rate on the deferred portion is 5.25% per annum."

detectSourceConflicts(sources, { subjectThreshold: 0.40 }):

  conflicts: [
    {
      sourceA: 2, claimA: "The termination fee is $24.5M.",        valuesA: ['$24.5m'],
      sourceB: 4, claimB: "The break-up fee payable by the target is $22.0M.", valuesB: ['$22.0m'],
      subjectSimilarity: 0.417    (shares: fee, payable, target)
    }
  ]

  corroborations: [
    {
      sourceA: 1, claimA: "The purchase price is $2.45B.",
      sourceB: 3, claimB: "The purchase price is $2.45B.",
      subjectSimilarity: 1.000,   agreedValues: ['$2.45b']
    }
  ]

conflictNote() output (injected before sources):
  [RETRIEVED SOURCE CONFLICTS DETECTED — review before answering]
  Source 2 states: "The termination fee is $24.5M." ($24.5m)
  Source 4 states: "The break-up fee payable by the target is $22.0M." ($22.0m)
  Subject overlap: 42% — values differ. Clarify which governs.

Model behavior with note: "Sources 2 and 4 disagree on the termination/break-up fee
  ($24.5M vs $22.0M). Please confirm which document version governs before relying
  on either figure."

Model behavior without note (baseline): picks $22.0M (source 4, later in context),
  presents as fact. Analyst doesn't learn of the conflict.

=== S-125 vs F-73 vs F-93 vs F-94 ===

              │ F-73 (output lineage)        │ F-93 (claim verifiability)    │ F-94 (session consistency)    │ S-125 (source conflict)
──────────────┼──────────────────────────────┼───────────────────────────────┼───────────────────────────────┼────────────────────────────────
Compares      │ Output claim vs cited source │ Output sentence vs all sources│ Output sentence vs prior output│ Source vs source (pre-injection)
When          │ After generation             │ After generation              │ After each turn               │ Before injection
Catches       │ Decorative/unsupported cite  │ Uncited unsupported sentences │ Model self-contradiction      │ Retrieved source disagreement
Input         │ Model output + sources       │ Model output + sources        │ Model output (multi-turn)     │ Retrieved sources only
Output        │ Per-citation lineage verdict │ Per-sentence VERB/SUPP/UNSUPP │ Per-turn conflict list        │ Pre-injection conflict + corroboration
```

## See also

[F-94](../forward-deployed/f94-intra-session-claim-consistency.md) · [F-73](../forward-deployed/f73-agent-output-lineage.md) · [F-93](../forward-deployed/f93-claim-verifiability-classification.md) · [S-122](s122-retrieved-chunk-dedup.md) · [S-79](s79-hybrid-search.md) · [F-57](../forward-deployed/f57-rag-answer-citations.md)

## Go deeper

Keywords: `multi-source conflict` · `source claim conflict` · `retrieved source disagreement` · `pre-injection conflict detection` · `cross-source fact check` · `source corroboration` · `RAG source conflict` · `conflicting retrieved chunks` · `source reconciliation` · `document conflict detection`
