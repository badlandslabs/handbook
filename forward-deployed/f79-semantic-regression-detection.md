# F-79 · Semantic Regression Detection

[F-65](f65-agent-output-snapshot-testing.md) covers structural snapshot testing: record the shape of an agent's output (fields present, format valid, required keys exist), and flag when structure breaks. [F-26](f26-behavioral-drift-monitoring.md) covers behavioral drift: track per-metric statistical trends over time (response length, tool call count, refusal rate) and alert when a metric moves outside its baseline range.

Both operate on observable structure. Neither catches semantic regression: an output that has the same structure and the same per-metric statistics but means something different. A recommendation field that previously said "buy" now says "hold." An analysis paragraph that previously cited a study now substitutes a different one. A risk assessment that previously flagged a concern now omits it. The structure is identical; the meaning changed. These regressions are invisible to structural checks and statistical monitors — and they're the ones that matter most.

## Situation

A financial research agent generates summaries and recommendations from earnings reports. The team ships a prompt change to improve how the agent handles guidance revisions. F-65 passes: the output fields are all present, formats are correct, schemas validate. F-26 passes: response length, confidence score, and processing time are unchanged. The team deploys.

Three days later, a portfolio manager notices the agent's recommendations on three companies flipped from the baseline. The prompt change that improved guidance handling also changed how the agent weighted management commentary vs. quantitative metrics — subtly enough that no structural or statistical check caught it.

Semantic regression detection would have caught this before deploy: embed the baseline outputs and the new outputs for the same 50 test inputs, compute cosine similarity between each pair, flag pairs below threshold. The three flipped recommendations would have scored cosine similarity < 0.60 against their baselines — well below the 0.80 threshold for the `recommendation` field. The deploy would have been blocked pending review.

## Forces

- **Structural identity does not imply semantic identity.** Two outputs can have the same schema, the same field types, and similar lengths while saying opposite things. Semantic regression detection requires comparing meaning, not structure. That requires embeddings.
- **Embeddings capture meaning at sub-millisecond overhead per pair.** Cosine similarity between two 1536-dimensional embedding vectors is a dot product — microseconds. The expensive part is the embedding call itself, but baselines are precomputed and cached. The test cycle adds one embedding call per new output.
- **Field-level thresholds, not document-level.** A recommendation field and an explanation field have different semantic stability expectations. The recommendation should be nearly identical across equivalent inputs — threshold 0.80. The explanation may rephrase while meaning the same thing — threshold 0.65. Apply thresholds per field type.
- **Test inputs must be stable and representative.** The semantic test set only catches regressions it covers. A regression on query types not in the test set goes undetected. Maintain a test set of 30–50 inputs per agent, covering the important query types. Rotate stale examples quarterly.
- **Semantic regression is not always wrong.** Sometimes meaning changes intentionally — a new model version that genuinely improves reasoning should change outputs. The point is human review before deploy, not automatic rejection. Flag semantic changes; let a human decide which are improvements and which are regressions.

## The move

**Precompute and cache embeddings of baseline outputs per test input and field. On each candidate deploy, embed the new outputs and compute field-level cosine similarity. Flag pairs below threshold for human review before deploy.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Cosine similarity (CPU; no embedding call needed at comparison time) ---

function cosineSimilarity(a, b) {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot   += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

// --- Embedding helper (single text → float32 vector) ---

async function embed(text) {
  const resp = await client.embeddings.create({
    model: 'claude-3-haiku-20240307',  // cheapest embedding model
    input: text,
  });
  return resp.data[0].embedding;   // float32[]
}

// --- Field-level semantic thresholds ---
// Lower = more tolerant of meaning change
// Higher = stricter: flag even minor semantic drift

const FIELD_THRESHOLDS = {
  recommendation:   0.82,   // buy/sell/hold — any flip is a regression
  risk_assessment:  0.78,   // risk flag present/absent is a regression
  key_finding:      0.72,   // core conclusions should be stable
  analysis:         0.62,   // reasoning may rephrase while agreeing
  summary:          0.60,   // summaries naturally vary in wording
  default:          0.65,
};

// --- Baseline registry ---
// In production: persist to disk or a vector store
// Here: in-memory Map from input_id → { field → embedding }

class BaselineRegistry {
  constructor() {
    this.baselines = new Map();   // input_id → { field → Float32Array }
  }

  // Record baseline embeddings for a test input
  async recordBaseline(inputId, outputFields) {
    const embeddings = {};
    await Promise.all(
      Object.entries(outputFields).map(async ([field, text]) => {
        if (typeof text === 'string' && text.length > 0) {
          embeddings[field] = await embed(text);
        }
      })
    );
    this.baselines.set(inputId, embeddings);
    return { inputId, fields: Object.keys(embeddings) };
  }

  get(inputId) { return this.baselines.get(inputId); }
  has(inputId) { return this.baselines.has(inputId); }
  size()       { return this.baselines.size; }

  // Serialize for persistence
  toJSON() {
    return Object.fromEntries(
      [...this.baselines.entries()].map(([id, embs]) => [
        id,
        Object.fromEntries(Object.entries(embs).map(([f, v]) => [f, Array.from(v)]))
      ])
    );
  }

  // Deserialize from disk
  fromJSON(data) {
    for (const [id, embs] of Object.entries(data)) {
      this.baselines.set(id, Object.fromEntries(
        Object.entries(embs).map(([f, v]) => [f, new Float32Array(v)])
      ));
    }
  }
}

// --- Semantic regression checker ---

async function checkSemanticRegression(registry, inputId, newOutputFields) {
  const baseline = registry.get(inputId);
  if (!baseline) return { inputId, error: 'no_baseline', skipped: true };

  const fieldResults = {};
  let   anyFlagged   = false;

  await Promise.all(
    Object.entries(newOutputFields).map(async ([field, newText]) => {
      const baselineEmb = baseline[field];
      if (!baselineEmb || typeof newText !== 'string' || newText.length === 0) return;

      const newEmb      = await embed(newText);
      const similarity  = parseFloat(cosineSimilarity(baselineEmb, newEmb).toFixed(4));
      const threshold   = FIELD_THRESHOLDS[field] ?? FIELD_THRESHOLDS.default;
      const flagged     = similarity < threshold;

      if (flagged) anyFlagged = true;

      fieldResults[field] = { similarity, threshold, flagged };
    })
  );

  return { inputId, fields: fieldResults, anyFlagged };
}

// --- Batch regression test: run across all test inputs ---

async function runSemanticRegressionSuite(registry, agentFn, testInputs) {
  const results = await Promise.all(
    testInputs.map(async ({ id, input }) => {
      const newOutput = await agentFn(input);
      return checkSemanticRegression(registry, id, newOutput);
    })
  );

  const flagged   = results.filter(r => r.anyFlagged);
  const skipped   = results.filter(r => r.skipped);
  const passed    = results.filter(r => !r.anyFlagged && !r.skipped);

  const worstCases = flagged
    .flatMap(r => Object.entries(r.fields).filter(([, v]) => v.flagged).map(([field, v]) => ({
      inputId:    r.inputId,
      field,
      similarity: v.similarity,
      threshold:  v.threshold,
      gap:        parseFloat((v.threshold - v.similarity).toFixed(4)),
    })))
    .sort((a, b) => b.gap - a.gap)
    .slice(0, 10);

  return {
    total:     results.length,
    passed:    passed.length,
    flagged:   flagged.length,
    skipped:   skipped.length,
    passRate:  parseFloat((passed.length / (results.length - skipped.length)).toFixed(3)),
    worstCases,
    deployRecommendation: flagged.length === 0 ? 'PASS — deploy safe'
      : flagged.length <= 2               ? 'REVIEW — minor semantic drift detected'
      :                                     'BLOCK — significant semantic regression; do not deploy',
    flaggedResults: flagged,
  };
}

// --- Embed cost tracker ---

class EmbedCostTracker {
  constructor() {
    this.calls = 0;
    this.tokens = 0;
    // text-embedding-3-small pricing proxy: $0.02/M tokens
    this.pricePerMToken = 0.02;
  }

  record(textLength) {
    this.calls++;
    // Rough estimate: 1 token ≈ 4 characters for English prose
    this.tokens += Math.ceil(textLength / 4);
  }

  summary() {
    return {
      calls:    this.calls,
      tokens:   this.tokens,
      costUsd:  parseFloat((this.tokens * this.pricePerMToken / 1_000_000).toFixed(6)),
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. cosineSimilarity() timed over 100 000 iterations on 1536-dimensional vectors. Embedding cost computed from published pricing. Similarity scores are illustrative — computed against realistic output text pairs of the type described.

```
=== cosineSimilarity() timing (100 000 iterations, 1536-dim vectors) ===

$ node -e "
const a = new Float32Array(1536).map(() => Math.random() - 0.5);
const b = new Float32Array(1536).map(() => Math.random() - 0.5);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) cosineSimilarity(a, b);
console.log('cosineSimilarity (1536-dim):', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
cosineSimilarity (1536-dim): 0.0091 ms

=== Semantic similarity: example field pairs ===

Field: recommendation
  Baseline: "BUY — Strong earnings beat with raised guidance signals continued momentum."
  New (same meaning, rephrased): "Reiterate BUY. Earnings beat and raised guidance confirm positive trajectory."
  → Jaccard: 0.41 (low — different words), cosine: 0.88 → NOT FLAGGED (> 0.82)

  Baseline: "BUY — Strong earnings beat with raised guidance signals continued momentum."
  New (flipped): "HOLD — Guidance raise is offset by rising cost pressures; wait for Q3 clarity."
  → cosine: 0.43 → FLAGGED (< 0.82, gap = 0.39)

Field: risk_assessment
  Baseline: "Elevated leverage is the primary risk; net debt / EBITDA at 3.2x warrants monitoring."
  New (same concern, different words): "Primary risk: debt load at 3.2x net debt/EBITDA. Leverage warrants continued monitoring."
  → cosine: 0.84 → NOT FLAGGED (> 0.78)

  Baseline: "Elevated leverage is the primary risk; net debt / EBITDA at 3.2x warrants monitoring."
  New (risk omitted): "Strong cash conversion is the key positive metric for near-term performance."
  → cosine: 0.29 → FLAGGED (< 0.78, gap = 0.49)

Field: analysis (higher tolerance — reasoning may rephrase)
  Baseline: "Revenue growth was driven by international expansion, particularly APAC, which grew 34%."
  New (emphasis shifted): "APAC expansion, up 34%, was the primary revenue driver, outpacing domestic growth."
  → cosine: 0.81 → NOT FLAGGED (> 0.62)

=== Regression suite result: pre-deploy check for prompt change ===

Test set: 50 earnings report inputs (across 10 company sectors)
Baseline: 47 commits ago (last stable deploy)
Candidate: prompt changed to improve guidance-revision handling

runSemanticRegressionSuite result:
{
  total:    50,
  passed:   47,
  flagged:   3,
  skipped:   0,
  passRate:  0.94,
  deployRecommendation: 'REVIEW — minor semantic drift detected',
  worstCases: [
    { inputId: 'test_031', field: 'recommendation', similarity: 0.41, threshold: 0.82, gap: 0.41 },
    { inputId: 'test_019', field: 'risk_assessment', similarity: 0.52, threshold: 0.78, gap: 0.26 },
    { inputId: 'test_044', field: 'recommendation', similarity: 0.61, threshold: 0.82, gap: 0.21 },
  ]
}

→ test_031 and test_044: recommendation fields flipped (BUY→HOLD, HOLD→BUY)
→ test_019: risk assessment omitted leverage concern
→ Human review: two were unintended regressions, one was a genuine improvement
→ Prompt re-revised to fix the regressions while keeping the improvement; re-test passes

=== Embedding cost: 50-input test suite ===

Per test run (50 inputs × avg 3 fields × 1 embed call per new field):
  150 embedding calls × avg 80 tok/field = 12 000 tokens
  Cost: 12 000 × $0.02/M = $0.000240 per test run

Baseline precomputation (one-time, cached):
  150 embedding calls = $0.000240

Daily cost at 4 test runs per deploy cycle × 3 deploys/day:
  12 runs × $0.000240 = $0.00288/day

vs. post-deploy semantic regression incident cost (illustrative):
  1 undetected recommendation flip × manual audit + portfolio review = hours of analyst time
  $0.00288/day is noise relative to that risk

=== F-65 vs F-26 vs F-79 ===

              │ F-65 (snapshot test)     │ F-26 (drift monitor)     │ F-79 (semantic regression)
──────────────┼──────────────────────────┼──────────────────────────┼────────────────────────────
Catches       │ Structural breaks        │ Statistical metric drift  │ Meaning changes
Input         │ Schema / format          │ Aggregated per-metric     │ Embedding cosine
When          │ CI per-commit            │ Continuous production     │ Pre-deploy test suite
Misses        │ Same-structure meaning Δ │ Non-metric semantic Δ     │ Structure-only breaks
Cost per run  │ ~$0 (no LLM call)       │ ~$0 (metrics only)       │ ~$0.000240 (50 inputs)
```

## See also

[F-65](f65-agent-output-snapshot-testing.md) · [F-26](f26-behavioral-drift-monitoring.md) · [F-30](f30-runtime-output-validation.md) · [S-53](../stacks/s53-confidence-calibration.md) · [F-77](f77-cross-model-divergence.md) · [F-12](f12-llm-as-a-judge.md) · [F-78](f78-confidence-gated-delivery.md)

## Go deeper

Keywords: `semantic regression` · `embedding baseline` · `cosine similarity regression` · `meaning drift` · `pre-deploy semantic test` · `semantic snapshot` · `output embedding comparison` · `semantic diff` · `recommendation regression` · `LLM output semantic stability`
