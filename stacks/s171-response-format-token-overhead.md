# S-171 · Response Format Token Overhead

[S-47](s47-output-length-control.md) establishes the economic case: output tokens cost 4–5× more than input tokens per dollar, and unconstrained generation inflates cost far beyond what the task requires. [S-139](s139-dynamic-max-tokens-by-task-type.md) assigns a `max_tokens` ceiling per task type to cap the worst case. [S-50](s50-prompt-format.md) covers the input prompt format — how to write system prompt instructions (XML tags vs markdown vs prose). None of these address a source of output token waste that is independent of verbosity: the serialization format you ask the model to use for structured output.

For a 6-field extraction (clause ID, effective date, termination date, governing law, risk level, and a two-party list), the same data costs 50 tokens in pretty-printed JSON and 40 tokens in compact JSON — a 20% difference from whitespace alone. Ask for YAML and you get 36 tokens; ask for a markdown code block wrapper around compact JSON and you add 3 tokens back. At 10 000 calls per day on Haiku output pricing, the difference between pretty JSON and compact JSON is $0.40/day. Across a pipeline with four extraction calls per session, that is $1.60/day — $584/year — from one formatting decision made at design time that can be changed with a single word in the prompt.

The format choice also affects parse reliability. Pipe-delimited output is 14 tokens for the same data — 72% fewer — but breaks when values contain the delimiter character, and models occasionally re-introduce column headers or add stray separators. YAML requires a custom parser and fails silently when the model adds unexpected indentation. Compact JSON uses native structured output APIs, parses with `JSON.parse()` in every language, and the model has been trained extensively on it. The format with the lowest net cost is not always the one with the fewest raw tokens.

## Situation

A contract extraction pipeline asks the model to return a 6-field JSON object per document. The prompt instructs "respond with a JSON object." In practice, the model returns pretty-printed JSON with indentation — 50 tokens per response. The pipeline wraps the prompt in a markdown code block instruction ("respond with ```json...```") that adds 3 more tokens. At 10 000 documents per day, the extraction step costs $2.00/day in output tokens for this schema.

Switching to compact JSON with no code block wrapper drops to 40 tokens — $1.60/day, saving $146/year. Shortening field key names (clause_id → cid, effective_date → eff) drops to 29 tokens — $1.16/day, saving $306/year — at the cost of prompt readability and a key mapping layer at parse time.

The decision is: how much readability overhead is the team willing to pay for? Compact JSON with original key names is the default correct answer. Short aliases pay off only in high-volume, long-lived pipelines where the schema is stable.

## Forces

- **"Respond with JSON" instructs the model to return pretty-printed JSON by default.** Models learn from human-written examples that pretty JSON with indentation is the canonical form. "Respond with compact JSON" or injecting a compact JSON example in the few-shot section overrides this. The cost of not specifying is the indentation whitespace on every response.
- **Markdown code block wrappers serve chat UIs, not API pipelines.** `\`\`\`json ... \`\`\`` makes output readable in a conversation interface. In an API pipeline, it adds tokens and requires a stripping step before `JSON.parse()`. Pipeline prompts should not include code block instructions unless the downstream consumer is a chat UI.
- **Pipe-delimited output requires header context in the prompt.** The model needs to know what each column represents. A header row in the prompt adds 15+ input tokens per call to specify column order — and the model still occasionally inserts extra headers or reorders columns. For nested or variable-length data (arrays, optional fields), pipe-delimited is unreliable. Use it only for flat records of simple scalar values where the schema is rigid and the values never contain the delimiter character.
- **YAML looks compact but adds tokens for nested structures.** A top-level scalar field like `risk_level: HIGH` is shorter than `"risk_level":"HIGH"` (15 vs 19 chars). But arrays cost more: YAML uses a dash prefix per item (`- Alpha Corp\n- Beta Ltd`) while JSON uses `["Alpha Corp","Beta Ltd"]`. For real extraction schemas with arrays and nested objects, YAML is rarely cheaper than compact JSON, and it adds parser complexity.
- **Short key aliases break human readability and require a mapping layer.** Mapping `clause_id → cid` saves 6 characters per occurrence, or about 2 tokens. The mapping table must be maintained in sync with the schema and in the prompt. If a key alias changes, the parser breaks silently on old responses in the audit log. Use short aliases only when the schema is frozen and the daily call volume makes the savings material (>100 000 calls/day).
- **Structured output APIs enforce format at the model layer.** Anthropic's structured output and OpenAI's `json_mode` / response format APIs ensure the model returns valid JSON without manual parsing of partial responses. These APIs do not control whitespace — specify compact JSON in the prompt schema description, not just in the `type` constraint.

## The move

**Ask for compact JSON. Drop the markdown code block wrapper. Audit your prompt for format instructions that default to pretty-printed output or add unnecessary wrappers. Reserve format changes for schemas above 100 000 calls/day.**

```js
// --- Response format token overhead analysis ---
// Run at schema design time to pick the cheapest reliable format.

function estimateTokens(str) {
  return Math.ceil(str.length / 4);  // chars/4 approximation for English/JSON
}

// Measure format cost for a given extraction schema's sample output.
function analyzeFormatOverhead(sampleOutput) {
  const compact   = JSON.stringify(sampleOutput);
  const pretty    = JSON.stringify(sampleOutput, null, 2);
  const codeBlock = '```json\n' + compact + '\n```';

  const results = [
    { name: 'pretty JSON',          tokens: estimateTokens(pretty),    note: 'model default when asked for "json"' },
    { name: 'compact JSON',         tokens: estimateTokens(compact),   note: 'no whitespace; use this' },
    { name: 'compact + code block', tokens: estimateTokens(codeBlock), note: 'adds 4-6 tok; drop in API pipelines' },
  ];

  const baseline = results[0].tokens;
  for (const r of results) {
    r.savingVsPretty = Math.round((r.tokens - baseline) / baseline * 100);
  }
  return results;
}

// --- Prompt instruction comparison ---

// WRONG: instructs model to use pretty JSON + code block wrapper
const wrongInstruction = 'Respond with the extracted fields as a JSON object in a code block.';

// RIGHT: instructs model to use compact JSON, no wrapper
const rightInstruction = 'Respond with a compact JSON object. No indentation. No code block. Example: {"clause_id":"CL-42","risk_level":"HIGH"}';

// The example in the instruction itself demonstrates compact format.
// One real compact example in the prompt is more reliable than ten words of instruction.

// --- Cost projection ---

function dailyCost(tokensPerCall, callsPerDay, outputPricePerMillionUsd) {
  return tokensPerCall * callsPerDay / 1e6 * outputPricePerMillionUsd;
}

// At 10k calls/day, Haiku output pricing ($4.00/M):
// pretty JSON (50 tok):         $2.00/day
// compact JSON (40 tok):        $1.60/day  → $0.40/day saved
// compact JSON aliases (29 tok): $1.16/day  → $0.84/day saved
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Same 6-field extraction output serialized in five formats. Token counts via `Math.ceil(str.length / 4)`. Haiku output pricing $4.00/M. `JSON.stringify()` timed over 1 000 000 iterations.

```
=== Response Format Token Overhead Analyzer ===

Input: 6-field contract extraction
       (clause_id, effective_date, termination_date,
        governing_law, risk_level, parties[2])

Format                                  Tokens  vs Pretty
────────────────────────────────────────────────────────────
Pretty JSON (indented)                      50       0%   ← model default for "respond with json"
Compact JSON                                40     -20%   ← use this
Compact JSON + code block wrapper           43     -14%   ← worse than compact; drop the wrapper
Compact JSON with short aliases             29     -42%   ← use only for frozen, high-volume schemas
YAML-style                                  36     -28%   ← avoid; parser complexity, brittle indentation
Pipe-delimited                              14     -72%   ← cheapest but unreliable for nested data

=== Batch cost impact (Haiku output $4.00/M, 10 000 calls/day) ===

Pretty JSON     (50 tok): $2.00/day
Compact JSON    (40 tok): $1.60/day   ← 20% savings; $146/year
Compact aliases (29 tok): $1.16/day   ← 42% savings; $306/year

=== Parse reliability ===

compact JSON:     native API support; JSON.parse() universal; model well-trained
YAML:             requires yaml.parse(); indentation errors on extra whitespace → parse fail
pipe-delimited:   breaks on "|" in values; model adds spurious headers
code block:       strips wrapper required before JSON.parse(); no reliability gain

=== Timing (1 000 000 iterations) ===

JSON.stringify() 6 fields: 0.0019 ms
estimateTokens() (chars/4): 0.0000 ms
```

## See also

[S-47](s47-output-length-control.md) · [S-139](s139-dynamic-max-tokens-by-task-type.md) · [S-50](s50-prompt-format.md) · [S-84](s84-tool-return-value-design.md) · [F-142](../forward-deployed/f142-cross-extraction-field-consistency-check.md)

## Go deeper

Keywords: `response format token cost` · `JSON output token overhead` · `compact JSON vs pretty JSON` · `output serialization format` · `extraction output format` · `markdown code block token waste` · `YAML vs JSON tokens` · `pipe delimited output tokens` · `LLM output format selection` · `structured output token efficiency`
