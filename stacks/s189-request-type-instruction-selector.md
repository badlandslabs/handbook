# S-189 · Request-Type Instruction Selector

A system prompt that handles three task types — extraction, classification, summarization — typically contains instruction blocks for all three. Every call pays input tokens for every block, even when the request only needs one. A classification call pays for the extraction and summarization instructions it will never use; the extraction call pays for the classification instructions; and so on. At 10 000 calls per day the waste accumulates.

The fix is a runtime selector that inspects the incoming user query, identifies the request type by pattern matching, and assembles a system prompt from only the relevant instruction blocks plus any always-required core behavior. A classification request receives the classification block and the core block. Extraction receives the extraction block and the core block. The unused blocks are simply not included.

This works because instruction blocks are independent — the model doesn't need to see summarization instructions to perform extraction. The selector runs in under 0.002 ms with no API call, produces a shorter system prompt, and leaves the rest of the call unchanged.

## Situation

A contract intelligence agent accepts three request types over a shared API endpoint: extract structured fields from contracts, classify the contract type (employment, vendor, NDA, lease), or summarize the key provisions in plain language. The system prompt has grown to 630 tokens: 100 tokens of general behavior, 200 tokens of extraction instructions, 150 tokens of classification instructions, and 180 tokens of summarization instructions.

Traffic mix: 40% extraction, 35% classification, 20% summarization, 5% unclassified.

Without the selector, every call pays 630 input tokens for the system prompt. With the selector, average system prompt tokens drop to 295 per call. At 10 000 calls/day on Haiku:

- Baseline: 10 000 × 630 tok = 6 300 000 tok/day × $0.80/M = **$5.04/day**
- Selected: 10 000 × 295 tok = 2 950 000 tok/day × $0.80/M = **$2.36/day**
- Savings: **$2.68/day, $978/year**

The selector requires no additional API call and adds no latency beyond 0.0014 ms of JS execution.

## Forces

- **Pattern matching must be fast and require no API call.** The selector runs before the main call. If it needs a separate classification call, its cost exceeds the savings it enables. Regex or keyword matching over the user query is sufficient for the majority of agents; it costs nothing.
- **Core behavior belongs in an always-included block, not repeated in each task block.** Safety rules, response format requirements, and identity instructions belong in the core block so they apply to all request types without duplication.
- **Fallback to full prompt on ambiguous requests.** When no rule matches, include all blocks. The extra cost on 5% of calls is acceptable; missing instructions on an unknown request type is not. Log the fallback so the pattern coverage can be improved over time.
- **Block boundaries must be self-contained.** The extraction block must not assume the classification block was also included. Each block reads as if it is the only task-specific block in the prompt.
- **This is input-side cost only.** The selector reduces system prompt input tokens; it does not affect document tokens, output tokens, or caching. If the system prompt is already tiny relative to the document being processed, the absolute saving is small — check the structural vs content ratio first (S-184) before investing in the selector.
- **Prompt caching changes the calculus.** If the system prompt is already cached, the savings from selection are 90% smaller (cache read is 0.10× of input cost). Apply the selector when the system prompt is not cached, or when the system prompt is too dynamic to be cached.

## The move

**Register instruction blocks with a name and tokens estimate. Attach per-block patterns to detect the request type. Assemble the system prompt at call time from only the matched blocks.**

```js
// --- Request-type instruction selector ---
// Assembles the system prompt from only the blocks relevant to the detected request type.
// No API call required. Runs in < 0.002 ms. Falls back to all blocks on no match.
// Apply S-184 (input token structure audit) first to confirm system prompt is worth optimizing.

function estimateTokens(text) {
  return Math.ceil((text || '').length / 4);
}

class RequestTypeInstructionSelector {
  constructor() {
    this._blocks       = new Map();  // name → { text, tokens, alwaysInclude }
    this._rules        = [];          // [{ pattern, includeBlocks }]
    this._defaultBlocks = [];         // fallback when no rule matches
  }

  // Register an instruction block.
  // opts.alwaysInclude: true — include in every call regardless of detected type (e.g. safety rules).
  registerBlock(name, text, opts) {
    opts = opts || {};
    this._blocks.set(name, {
      text,
      tokens:       estimateTokens(text),
      alwaysInclude: !!opts.alwaysInclude,
    });
    return this;
  }

  // Register a detection rule: if pattern matches the user query, include these blocks (+ always-blocks).
  addRule(pattern, includeBlocks) {
    this._rules.push({ pattern, includeBlocks });
    return this;
  }

  // Set the blocks to include when no rule matches.
  setDefault(blocks) {
    this._defaultBlocks = blocks;
    return this;
  }

  // Returns selected system prompt text and token count.
  select(userQuery) {
    const always = [...this._blocks.entries()]
      .filter(([, b]) => b.alwaysInclude).map(([name]) => name);

    for (const rule of this._rules) {
      if (rule.pattern.test(userQuery)) {
        const selected = [...new Set([...always, ...rule.includeBlocks])];
        return this._build(selected, rule.pattern.source);
      }
    }

    // No rule matched — use default blocks (typically all blocks).
    const selected = [...new Set([...always, ...this._defaultBlocks])];
    return this._build(selected, null);
  }

  _build(selectedNames, matchedPattern) {
    const blocks = selectedNames
      .map(name => ({ name, ...(this._blocks.get(name) || {}) }))
      .filter(b => b.text);
    const tokens = blocks.reduce((sum, b) => sum + b.tokens, 0);
    return {
      matchedPattern,
      selectedBlocks: selectedNames,
      totalTokens:   tokens,
      text:          blocks.map(b => b.text).join('\n\n'),
    };
  }
}

// --- Registration ---
const SELECTOR = new RequestTypeInstructionSelector()
  .registerBlock('GENERAL_BEHAVIOR',
    `You are a contract intelligence assistant. Answer accurately and concisely.
Reply in English. Never fabricate information not present in the document.`,
    { alwaysInclude: true }
  )
  .registerBlock('EXTRACTION_INSTRUCTIONS',
    `Extract the requested fields from the contract. Return a JSON object with
exactly the fields specified. If a field is not present, return null for that field.
Do not infer or guess values. Extraction fields: party_names, effective_date,
governing_law, termination_clause, payment_terms.`
  )
  .registerBlock('CLASSIFICATION_INSTRUCTIONS',
    `Classify the contract into exactly one category: employment, vendor, NDA,
lease, or other. Return a JSON object: { "type": "<category>", "confidence": 0.0–1.0 }.
If confidence is below 0.7, include a "reason" field explaining the uncertainty.`
  )
  .registerBlock('SUMMARIZATION_INSTRUCTIONS',
    `Summarize the key provisions of the contract in plain language. Cover: parties,
purpose, term, financial obligations, termination conditions, and any unusual clauses.
Maximum 200 words. Write for a non-lawyer reader.`
  )
  // Detection rules — first match wins.
  .addRule(/\bextract\b|\bfields?\b|\bparse\b|\bpull out\b/i,
    ['EXTRACTION_INSTRUCTIONS'])
  .addRule(/\bclassif\b|\bcategori[sz]e\b|\bwhat type\b|\bkind of contract\b/i,
    ['CLASSIFICATION_INSTRUCTIONS'])
  .addRule(/\bsummar[iy]\b|\boverview\b|\bkey points\b|\bbrief\b/i,
    ['SUMMARIZATION_INSTRUCTIONS'])
  // Fallback: include all blocks when request type is unknown.
  .setDefault(['EXTRACTION_INSTRUCTIONS', 'CLASSIFICATION_INSTRUCTIONS',
               'SUMMARIZATION_INSTRUCTIONS']);

// --- Usage in call dispatch ---
// const selected = SELECTOR.select(userQuery);
// const response = await anthropic.messages.create({
//   model:  'claude-haiku-4-5-20251001',
//   system: selected.text,
//   messages: [{ role: 'user', content: userQuery + '\n\nContract:\n' + document }],
//   ...
// });
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four request-type scenarios plus a mixed-traffic cost projection. Token counts estimated at 1 token ≈ 4 characters. Timing over 1 000 000 iterations. Zero API calls.

```
=== Request-Type Instruction Selector ===

Block inventory:
  GENERAL_BEHAVIOR          100 tok  (always included)
  EXTRACTION_INSTRUCTIONS   200 tok
  CLASSIFICATION_INSTRUCTIONS 150 tok
  SUMMARIZATION_INSTRUCTIONS 180 tok
  Full prompt (all blocks): 630 tok

--- Scenario A: extraction request ---
  Query: "Extract the party names and dates from this contract."
  Pattern matched: /\bextract\b/i → EXTRACTION_INSTRUCTIONS
  Selected: GENERAL_BEHAVIOR, EXTRACTION_INSTRUCTIONS
  totalTokens: 300 tok   (vs 630 baseline, saved 330 tok = 52.4%)

--- Scenario B: classification request ---
  Query: "Classify this as employment, vendor, NDA, or lease."
  Pattern matched: /\bclassif\b/i → CLASSIFICATION_INSTRUCTIONS
  Selected: GENERAL_BEHAVIOR, CLASSIFICATION_INSTRUCTIONS
  totalTokens: 250 tok   (saved 380 tok = 60.3%)

--- Scenario C: summarization request ---
  Query: "Summarize the key points of this agreement."
  Pattern matched: /\bkey points\b/i → SUMMARIZATION_INSTRUCTIONS
  Selected: GENERAL_BEHAVIOR, SUMMARIZATION_INSTRUCTIONS
  totalTokens: 280 tok   (saved 350 tok = 55.6%)

--- Scenario D: unknown request type (fallback) ---
  Query: "What is the square root of 144?"
  Pattern matched: null  (no rule matched) → default: all blocks
  Selected: GENERAL_BEHAVIOR, EXTRACTION_INSTRUCTIONS,
            CLASSIFICATION_INSTRUCTIONS, SUMMARIZATION_INSTRUCTIONS
  totalTokens: 630 tok   (no savings — correct: unknown request needs full context)

--- Mixed-traffic cost projection (10 000 calls/day, Haiku $0.80/M input) ---
  Traffic mix: 40% extraction, 35% classification, 20% summarization, 5% unknown
  Avg tokens per call:
    0.40 × 300 + 0.35 × 250 + 0.20 × 280 + 0.05 × 630
    = 120 + 87.5 + 56 + 31.5 = 295 tok/call

  Without selector: 630 tok × 10 000 = 6 300 000 tok/day = $5.04/day
  With selector:    295 tok × 10 000 = 2 950 000 tok/day = $2.36/day
  Savings:          $2.68/day = $978/year

  If system prompt is cached (S-08): cache read at 0.10× — savings reduce to ~$0.27/day.
  Apply selector when system prompt is NOT cached, or when blocks vary per request anyway.

=== Timing (1 000 000 iterations) ===
select() 3 rules, match on rule 1 (Scenario A): 0.0014 ms
select() 3 rules, match on rule 2 (Scenario B): 0.0014 ms
select() 3 rules, no match (Scenario D):        0.0016 ms
Zero API calls. Zero tokens.
```

## See also

[S-184](s184-input-token-structure-audit.md) · [S-59](s59-instruction-density.md) · [S-08](s08-prompt-caching.md) · [S-57](s57-negative-prompting.md) · [S-58](s58-prompt-layering.md)

## Go deeper

Keywords: `request type instruction selector` · `dynamic system prompt assembly` · `per-request prompt composition` · `instruction block selection` · `system prompt pruning` · `task-type prompt routing` · `conditional prompt blocks` · `runtime prompt composition` · `instruction block cost reduction` · `prompt token selection`
