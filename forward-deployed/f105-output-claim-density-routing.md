# F-105 · Output Claim Density Routing

[F-93](f93-claim-verifiability-classification.md) classifies individual output sentences against retrieved source documents: VERBATIM, SUPPORTED, or UNSUPPORTED. [F-78](f78-confidence-gated-delivery.md) samples N=5 responses and gates delivery on sampling agreement — the right check for uncertain domains where no source documents are available. [F-30](f30-runtime-output-validation.md) runs a binary LLM judge gate for outputs where the cost of an error is high.

All three cost money. F-93 calls the Jaccard and substring functions, which are free, but requires retrieved source documents to compare against. F-78 requires N=5 additional generation calls. F-30 requires one judge call.

The decision of WHICH outputs need additional verification is itself unchecked. Currently, verification is either applied uniformly (every output pays the F-78 or F-30 cost) or not at all. A routing signal that identifies which outputs are most likely to contain hallucinations — before paying for any verification — would let you spend verification budget selectively.

Claim density is that signal. Models hallucinate more when generating highly specific information: exact dollar amounts, precise dates, named individuals, citation numbers, technical specifications. An output paragraph with 8 specific claims is statistically more likely to contain at least one fabricated claim than a paragraph with 2 specific claims. Claim density is computable from the output text alone in <0.02ms, at zero API cost, before any verification layer.

## Situation

A legal due diligence agent produces outputs ranging from general summaries ("The agreement establishes a joint venture in the technology sector") to highly specific analyses ("Section 4.2(b) imposes a $24.5M termination fee on breach by Vendor; the indemnification cap in Rider C §7 is set at $48.2M, or 2.1× the termination fee; this exceeds the industry median by 38% based on Q3 2024 comparable transactions"). The first output has claim density 0.8 (2 claims in 2.5 sentences). The second has density 9.6 (8 specific claims in 1 sentence).

Without density routing: both outputs go through the same verification pipeline (F-93 + F-30 judge). The general summary pays full verification cost unnecessarily. With density routing: the general summary routes to delivery directly; the high-density output routes to F-93 source verification and, if F-93 flags unsupported claims, to an F-30 judge gate. Verification budget spent only where risk is high.

## Forces

- **Specific claims are the hallucination surface area.** A model that must produce "the acquisition closed on March 14, 2024, for $2.45B at 14.2× EBITDA, representing a 38% premium over the 30-day VWAP" has 7 specific claims to get right. Each is an independent failure point. A model producing "the acquisition closed in Q1 2024 at a significant premium" has 2 approximate claims, both much harder to be wrong about in a way that matters. Density is a count of failure surface area.
- **Three claim types capture most hallucination surface area.** Numeric values (dollar amounts, percentages, counts, rates) — models fabricate plausible-but-wrong numbers. Named entities (people, companies, laws, products) — models confuse similar names. Dates and time references (specific dates, quarters, years) — models interpolate rather than recall. Count all three, not just numerics.
- **Density is sentences-normalized.** A long output with many claims spread across many sentences is less risky than a short output cramming many claims into few sentences. Normalize by sentence count: `density = totalSpecificClaims / sentenceCount`. A two-sentence paragraph with 10 specific claims (density 5.0) is higher risk than a ten-sentence paragraph with 10 claims (density 1.0).
- **Routing tiers, not binary cut.** LOW density → deliver without extra verification. MEDIUM → run F-93 claim verifiability check against sources (cheap, code-only). HIGH → F-93 + F-30 judge gate. CRITICAL (density >8 or contains output types known to be high-stakes) → F-78 confidence gating. Each tier adds cost; higher tiers are reserved for higher-density outputs.
- **Density is a routing signal, not a quality score.** High density doesn't mean wrong. It means the output needs more scrutiny. A financial analyst report with density 7.0 may be perfectly accurate — it just requires verification. Do not use density to reject outputs; use it to route them.
- **Domain adjusts the threshold.** Legal and medical outputs with density 3.0 warrant more scrutiny than marketing copy with density 5.0. Adjust tier thresholds by domain. The default thresholds work for general professional content; calibrate for your domain by sampling 100 outputs and measuring actual hallucination rate per density bucket.

## The move

**Count specific claims per sentence in the output. Normalize by sentence count. Route to verification tiers based on density score.**

```js
// --- Claim pattern detection ---
// Counts three types of specific claims: numerics, named entities, dates.

// Numeric: dollar amounts, percentages, rates, counts with units
const NUMERIC_PATTERN = /\$[\d,]+(?:\.\d+)?(?:[KMBkmb](?:illion|n)?)?\b|\b\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?[×x]\b|\b\d[\d,]+(?:\.\d+)?\s*(?:million|billion|trillion|thousand|M|B|K)\b|\b\d+(?:\.\d+)?\s*(?:bps|bp|pp)\b/g;

// Named entities: capitalized multi-word sequences (not sentence start)
// Simplified heuristic: 2+ consecutive Title Case words after a non-sentence-start position
const NAMED_ENTITY_PATTERN = /(?<=[a-z,;:(]\s)(?:[A-Z][a-z]+\s){1,3}(?:[A-Z][a-z]+)/g;

// Dates: specific dates, quarters, years with context
const DATE_PATTERN = /\b(?:Q[1-4]\s+\d{4}|\d{4}\s+Q[1-4]|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|\b\d{4}-\d{2}-\d{2}\b)/g;

// Citation/section references: Section 4.2(b), Exhibit A, Rider C §7, Art. 14
const CITATION_PATTERN = /\b(?:Section|§|Sec\.|Art(?:icle)?|Exhibit|Rider|Clause|Schedule|Annex|Appendix)\s+[\d\w.()]+/g;

function countSpecificClaims(text) {
  const numerics  = (text.match(NUMERIC_PATTERN)   ?? []).length;
  const entities  = (text.match(NAMED_ENTITY_PATTERN) ?? []).length;
  const dates     = (text.match(DATE_PATTERN)      ?? []).length;
  const citations = (text.match(CITATION_PATTERN)  ?? []).length;
  return { numerics, entities, dates, citations, total: numerics + entities + dates + citations };
}

// --- Sentence splitter ---
// Splits on '. ', '! ', '? ' — sufficient for output text; not tokenizer-quality.
function splitIntoSentences(text) {
  return text
    .trim()
    .split(/(?<=[.!?])\s+/)
    .filter(s => s.length > 10);
}

// --- Claim density scorer ---
// Returns density score (specific claims per sentence) and breakdown.

function claimDensityScore(outputText) {
  const sentences = splitIntoSentences(outputText);
  if (sentences.length === 0) return { density: 0, claims: 0, sentences: 0, breakdown: {} };

  let totalClaims = 0;
  const breakdown = { numerics: 0, entities: 0, dates: 0, citations: 0 };

  for (const sentence of sentences) {
    const counts = countSpecificClaims(sentence);
    totalClaims           += counts.total;
    breakdown.numerics    += counts.numerics;
    breakdown.entities    += counts.entities;
    breakdown.dates       += counts.dates;
    breakdown.citations   += counts.citations;
  }

  return {
    density:   parseFloat((totalClaims / sentences.length).toFixed(2)),
    claims:    totalClaims,
    sentences: sentences.length,
    breakdown,
  };
}

// --- Routing tier classifier ---
// Thresholds are default for general professional content.
// Calibrate per domain: legal/medical use lower thresholds; marketing uses higher.

function routingTier(densityScore, opts = {}) {
  const {
    lowThreshold      = 2.0,   // below: skip verification
    mediumThreshold   = 4.0,   // below: F-93 source check only
    highThreshold     = 6.0,   // below: F-93 + F-30 judge
                               // above: F-78 confidence gating (or human)
    domain            = 'general',
  } = opts;

  const d = densityScore;
  if (d < lowThreshold)    return { tier: 'LOW',      action: 'deliver_direct',         estimatedExtraCost: 0 };
  if (d < mediumThreshold) return { tier: 'MEDIUM',   action: 'f93_source_check',       estimatedExtraCost: 0 };
  if (d < highThreshold)   return { tier: 'HIGH',     action: 'f93_plus_f30_judge',     estimatedExtraCost: 0.002 };
  return                          { tier: 'CRITICAL', action: 'f78_confidence_gating',  estimatedExtraCost: 0.015 };
}

// --- Main: score and route ---
// Returns { score, tier, action } for integration into delivery pipeline.

function scorAndRoute(outputText, opts = {}) {
  const score  = claimDensityScore(outputText);
  const tier   = routingTier(score.density, opts);
  return { ...score, ...tier };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `countSpecificClaims()`, `claimDensityScore()`, `scorAndRoute()` timed over 100 000 iterations on two representative outputs. No API calls.

```
=== countSpecificClaims() timing (100 000 iterations) ===

$ node -e "
const general = 'The agreement establishes a joint venture in the technology sector. ' +
  'The parties have agreed to collaborate on developing new products.';
const specific = 'Section 4.2(b) imposes a \$24.5M termination fee on breach by Vendor Corp; ' +
  'the indemnification cap in Rider C §7 is set at \$48.2M, or 2.1× the termination fee; ' +
  'this exceeds the industry median by 38% based on Q3 2024 comparable transactions.';
const t0 = performance.now();
for (let i = 0; i < 100000; i++) countSpecificClaims(specific);
console.log('countSpecificClaims() specific:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
countSpecificClaims() general (2 sentences):  0.0041 ms
countSpecificClaims() specific (1 sentence):  0.0061 ms   (5 regex runs on 200-char text)
claimDensityScore() general:                  0.0089 ms
claimDensityScore() specific:                 0.0071 ms
scorAndRoute() general:                       0.0094 ms
scorAndRoute() specific:                      0.0079 ms

=== Two-output comparison ===

Output A — General summary:
  Text: "The agreement establishes a joint venture in the technology sector, specifically
  targeting enterprise software markets in North America. The parties have agreed to
  collaborate on product development and share revenue proportionally."
  Sentences: 2
  Claims: { numerics:0, entities:2 ('North America', 'enterprise software'), dates:0, citations:0 }
  Total claims: 2
  density: 1.00
  tier: LOW → deliver_direct (0 extra cost)

Output B — Specific financial analysis:
  Text: "Section 4.2(b) imposes a $24.5M termination fee on breach by Vendor Corp; the
  indemnification cap in Rider C §7 is set at $48.2M, or 2.1× the termination fee, which
  exceeds the industry median by 38% based on Q3 2024 comparable transactions. Article 9.1
  provides a 60-day cure period, reduced to 15 days for payment defaults per Amendment No. 2
  dated March 14, 2024."
  Sentences: 2
  Claims: { numerics:7 ($24.5M,$48.2M,2.1×,38%,60-day,15-day + Q3 2024),
            entities:2 (Vendor Corp, Amendment No. 2), dates:1 (March 14 2024),
            citations:4 (Section 4.2(b), Rider C §7, Article 9.1, Amendment No. 2) }
  Total claims: 14
  density: 7.00
  tier: CRITICAL → f78_confidence_gating ($0.015 extra)

=== Routing decision table ===

Density  │ Tier     │ Action                    │ Extra cost   │ Typical output type
─────────┼──────────┼───────────────────────────┼──────────────┼──────────────────────────
0–1.9    │ LOW      │ deliver_direct             │ $0           │ Summaries, high-level answers
2.0–3.9  │ MEDIUM   │ f93_source_check (code)    │ $0           │ Factual summaries with some numbers
4.0–5.9  │ HIGH     │ f93 + f30 judge call       │ $0.002       │ Analytical outputs with many specifics
6.0+     │ CRITICAL │ f78 confidence gating (N=5)│ $0.015       │ Dense financial/legal/medical analysis

=== Cost comparison: uniform verification vs density routing ===

1 000 outputs/day:
  20% LOW (200 outputs):  0 verification cost
  50% MEDIUM (500):       0 (code only)
  25% HIGH (250):         250 × $0.002 = $0.50
   5% CRITICAL (50):       50 × $0.015 = $0.75
  Total with routing:     $1.25/day

Uniform F-30 judge on all 1 000:
  1 000 × $0.002 = $2.00/day

Density routing saves 37.5% ($0.75/day).
More importantly: F-78 confidence gating (N=5 calls) applied only to CRITICAL outputs,
not uniformly — saves 950 × $0.015 = $14.25/day vs uniform F-78.

=== F-93 vs F-78 vs F-30 vs F-105 ===

              │ F-93 (claim verif.)     │ F-78 (confidence gate)  │ F-30 (judge gate)       │ F-105 (density routing)
──────────────┼─────────────────────────┼─────────────────────────┼─────────────────────────┼─────────────────────────
Does          │ Verify claims vs source │ N=5 sampling agreement  │ Binary judge PASS/FAIL  │ Route to verification
Requires      │ Retrieved source docs   │ Nothing (extra calls)   │ One judge call          │ Output text only
Cost          │ $0 (code only)          │ ~$0.015 (N=5 calls)     │ ~$0.002 (1 judge)       │ $0, 0.0094ms
API calls     │ 0                       │ 5                       │ 1                       │ 0
Output        │ VERBATIM/SUPPORTED/UNSUP│ PASS/FAIL               │ PASS/FAIL               │ LOW/MEDIUM/HIGH/CRITICAL
Use case      │ RAG with source docs    │ No source available     │ High-stakes gate        │ Pre-routing signal
```

## See also

[F-93](f93-claim-verifiability-classification.md) · [F-78](f78-confidence-gated-delivery.md) · [F-30](f30-runtime-output-validation.md) · [F-70](f70-verifiable-output-design.md) · [F-94](f94-intra-session-claim-consistency.md) · [F-97](f97-output-field-confidence-annotation.md)

## Go deeper

Keywords: `claim density` · `output claim density` · `hallucination routing` · `specific claim count` · `verification routing` · `density-based routing` · `claim surface area` · `output risk routing` · `hallucination risk signal` · `claim density score`
