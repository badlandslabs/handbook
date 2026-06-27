# S-177 · Output Length Overrun Gate

[S-47](s47-output-length-control.md) controls output length through prompt instructions: "respond in JSON only," "be concise," structural output contracts. [S-139](s139-max-tokens-by-task-type.md) sets a static `max_tokens` per call type — extraction gets 500, summarization gets 1000, classification gets 50. These mechanisms work on the input side, before the model generates a response.

Neither catches the output that arrives anyway. A model instructed to return compact JSON occasionally returns the same JSON padded with explanatory prose — "governing_law_explanation: 'The governing law clause on page 12 specifies...'"  — because it inferred the caller would find context helpful. A classification model asked to return a single label sometimes returns "NDA — Non-Disclosure Agreement. Contains mutual confidentiality obligations..." because the document felt complex enough to warrant explanation. The static `max_tokens` cap eventually truncates, but at 2000 tokens for a task that should produce 50, the truncation happens far too late.

The output length overrun gate runs after the call returns. It compares actual output tokens to a per-call-type contract. If actual exceeds the contract ceiling, it routes to one of three handlers: TRIM (structured JSON — re-extract required fields, discard the rest, deliver trimmed output immediately with no additional API call), WARN (log the overrun and pass through — for formats where truncation would break semantics), or FAIL (reject and retry with an explicit conciseness instruction added to the prompt). The gate prevents bloated responses from propagating downstream into stored records, subsequent context injections, or UI renders.

## Situation

A contract extraction pipeline serves three call types with known output contracts. `extraction` calls should return compact JSON with five required fields (~200 tokens). `summarization` calls should return a 2–3 paragraph brief (~350 tokens). `classification` calls should return a single label (~25 tokens).

Without the gate, in a sample of 9 calls: two overrun their contract. Call 3 is an `extraction` call returning 355 tokens — the model appended `governing_law_explanation`, `contract_value_breakdown`, and `parties_analysis` to the five required fields. The trimmer extracts only the five required fields and returns 36 tokens. Call 9 is a `classification` call returning 65 tokens — the model appended a reasoning paragraph after the label. That call fails and retries with the explicit instruction: "Return the document type label only. No explanation."

The bloat from call 3 would otherwise flow into subsequent turns as re-injected context: 319 extra tokens × 10 000 calls/day × 10% overrun rate = $1.28/day downstream injection savings at Haiku output pricing. The savings compound across each session that re-injects the stored extraction.

## Forces

- **Output tokens are already billed when the gate fires.** The gate does not reduce the cost of the overrunning call. Its value is preventing downstream injection of bloated content and reducing retry cost when `FAIL` routes to a concise-prompted retry that generates the short output first time. Over many calls, the trim operation (free) and shorter retries (billed at the short output rate) save more than the initial overrun costs.
- **TRIM is only safe for structured outputs with a known required-field schema.** Trimming free-form prose produces incoherent partial text. Only apply TRIM to JSON or structured formats where required fields can be extracted by name. For prose, use WARN or FAIL.
- **The trimmer must rebuild valid JSON, not truncate raw text.** Cutting a JSON string at character position produces broken JSON. Parse the full JSON, extract only required fields, re-serialize with `JSON.stringify`. If the JSON is invalid (the model returned partial JSON already truncated by `max_tokens`), fall back to a prose truncation at the last sentence boundary.
- **Contract ceilings should be set at 1.5× the p95 actual output length.** At p95, 95% of within-contract calls have room. The extra 50% headroom absorbs genuine legitimate variation — a longer contract genuinely requires a longer summary. Set the ceiling from observation, not from intuition. S-143 (output token variance tracking) provides the p95 measurement.
- **FAIL routes to retry, not silence.** A failed call should add an explicit instruction to the retry prompt: "Your previous response was {N} tokens. Return only the required fields. No explanations, no analysis." The first retry typically corrects: the model understands the constraint when stated explicitly rather than inferred from the output format.
- **Different call types warrant different overflow behaviors.** Classifications should never overflow — a classification that runs long has failed structurally, not just verbosely. FAIL and retry. Extractions can be trimmed without losing correctness — the required fields are still present. Summarizations are harder — truncating a summary breaks its flow; WARN and monitor, then adjust the prompt if WARN rate exceeds 5%.

## The move

**Define per-call-type contracts with ceiling and overflow handler. Check after each response. TRIM structured JSON to required fields; FAIL and retry with explicit instruction for classifications; WARN and log for prose.**

```js
// --- Output length overrun gate ---
// Runs after each API response. Compares actual output tokens to per-call-type contract.
// TRIM: re-extract required JSON fields (no API call). WARN: pass through + log. FAIL: retry.
// Distinct from S-47 (prompt-side length control) and S-139 (static max_tokens by task type).

function estimateTokens(str) { return Math.ceil(str.length / 4); }

const CONTRACTS = {
  extraction:    { targetTokens: 200, maxTokens: 300, onOverrun: 'TRIM'  },
  summarization: { targetTokens: 350, maxTokens: 550, onOverrun: 'WARN'  },
  classification:{ targetTokens:  25, maxTokens:  50, onOverrun: 'FAIL'  },
};

function detectOverrun(callType, outputText) {
  const contract = CONTRACTS[callType];
  if (!contract) return { status: 'NO_CONTRACT', callType };
  const actualTokens = estimateTokens(outputText);
  const overrunTokens = actualTokens - contract.maxTokens;
  if (overrunTokens <= 0) return { status: 'WITHIN_CONTRACT', callType, actualTokens };
  return {
    status: 'OVERRUN', callType, actualTokens,
    maxTokens: contract.maxTokens,
    overrunTokens, overrunFactor: parseFloat((actualTokens / contract.maxTokens).toFixed(2)),
    action: contract.onOverrun,
  };
}

function trimToRequiredFields(jsonText, requiredFields) {
  try {
    const parsed = JSON.parse(jsonText);
    const trimmed = {};
    for (const f of requiredFields) { if (parsed[f] !== undefined) trimmed[f] = parsed[f]; }
    const text = JSON.stringify(trimmed);
    return {
      success: true, text,
      originalTokens: estimateTokens(jsonText), trimmedTokens: estimateTokens(text),
      fieldsKept: Object.keys(trimmed),
      fieldsDropped: Object.keys(parsed).filter(k => !requiredFields.includes(k)),
    };
  } catch {
    // Invalid JSON (e.g. truncated by max_tokens): trim at last sentence boundary
    const maxChars = CONTRACTS.extraction.maxTokens * 4;
    let cut = jsonText.lastIndexOf(' ', maxChars);
    if (cut < maxChars * 0.7) cut = maxChars;
    return { success: false, text: jsonText.slice(0, cut) + '…', originalTokens: estimateTokens(jsonText), trimmedTokens: CONTRACTS.extraction.maxTokens };
  }
}

const EXTRACTION_REQUIRED = ['contract_id', 'parties', 'effective_date', 'governing_law', 'contract_value'];

// Integration: check after every API response, route by overflow action
async function callWithOverrunGate(callType, callFn, retryFn) {
  const output = await callFn();
  const check  = detectOverrun(callType, output);
  if (check.status !== 'OVERRUN') return { output, overrun: null };

  if (check.action === 'TRIM') {
    const trim = trimToRequiredFields(output, EXTRACTION_REQUIRED);
    return { output: trim.text, overrun: check, trimmed: trim };
  }
  if (check.action === 'FAIL') {
    // Retry once with explicit conciseness instruction injected
    const retryOutput = await retryFn(`Your previous response was ${check.actualTokens} tokens. Return only the required label. No explanation.`);
    return { output: retryOutput, overrun: check, retried: true };
  }
  // WARN: pass through, log
  console.warn(`[overrun-gate] ${callType}: ${check.actualTokens} tok > ${check.maxTokens} max (${check.overrunFactor}×)`);
  return { output, overrun: check, warned: true };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 9 calls across 3 call types, 2 overruns (22%). `detectOverrun()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Output Length Overrun Gate ===

Contracts: extraction max=300 TRIM | summarization max=550 WARN | classification max=50 FAIL

Call 1 [extraction]: WITHIN_CONTRACT    35 tok
Call 2 [extraction]: WITHIN_CONTRACT    32 tok
Call 3 [extraction]: OVERRUN 355 tok > 300 max  (1.18×)  action=TRIM
  TRIM: 355 → 36 tok  (dropped 319)
  kept:    [contract_id, parties, effective_date, governing_law, contract_value]
  dropped: [governing_law_explanation, contract_value_breakdown, parties_analysis]
Call 4 [extraction]: WITHIN_CONTRACT   234 tok
Call 5 [summarization]: WITHIN_CONTRACT    64 tok
Call 6 [summarization]: WITHIN_CONTRACT   359 tok
Call 7 [classification]: WITHIN_CONTRACT    1 tok
Call 8 [classification]: WITHIN_CONTRACT    1 tok
Call 9 [classification]: OVERRUN 65 tok > 50 max  (1.3×)  action=FAIL
  FAIL: reject; retry with explicit output-length instruction

Overruns: 2/9 (22%)   extraction 1/4   summarization 0/2   classification 1/3

TRIM savings: 319 tok removed (avg 319 tok/overrun — bloat not re-injected downstream)
At 10 000 calls/day, 10% extraction overrun rate (Haiku $4.00/M output):
  $1.28/day downstream injection savings  ($466/year)
  (output tokens billed at generation time; gate prevents propagation of bloat)

=== Timing (1 000 000 iterations) ===
detectOverrun():                     0.0006 ms
trimToRequiredFields() JSON rebuild: 0.0095 ms

Zero API calls. Zero tokens. Runs after every response.
```

## See also

[S-47](s47-output-length-control.md) · [S-139](s139-max-tokens-by-task-type.md) · [S-143](s143-output-token-variance-tracking.md) · [F-133](../forward-deployed/f133-extraction-retry-escalation-policy.md) · [S-176](s176-context-section-budget-enforcer.md)

## Go deeper

Keywords: `output length overrun gate` · `LLM response length enforcement` · `output token contract` · `trim JSON response` · `extraction output length check` · `response bloat detection` · `max tokens enforcement post-call` · `output overrun retry` · `response length gate agent` · `LLM output length contract`
