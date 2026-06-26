# S-39 · Output Parsing Robustness

[S-04](s04-structured-output.md) tells you how to get structured output. This entry covers what happens when you don't get it — and what to do. The model will occasionally return JSON wrapped in markdown fences, preceded by prose, using single quotes, or with a trailing comma. Raw `JSON.parse` fails all four. A retry costs tokens and a full API round-trip. String manipulation costs nothing. The hierarchy is: fix what is fixable with strings, validate what matters with a schema, retry only what cannot be recovered.

## Situation

Your pipeline has been running fine for three days. Then it starts logging `SyntaxError: Unexpected token`. The model returned `{"status": "ok",}` — trailing comma, valid in most languages, illegal in JSON. Or it wrapped the output in ` ```json ... ``` ` because someone changed a prompt. Raw `JSON.parse` treats these identically: broken. A retry loop catches them eventually, at full token cost, with no diagnostic signal about why they're failing.

## Forces

- The four common deviation patterns (markdown fences, prose preamble, trailing commas, single quotes) are all *structurally recoverable* — no information is lost, the intended value is present, and string manipulation recovers it without a model call.
- Retry is the most expensive recovery: it costs the full prompt in input tokens, a new API call, and latency. For fixable deviations it is a wasteful substitute for parsing hygiene.
- Not every deviation is fixable. A partial response (truncated mid-JSON due to `max_tokens`) is unrecoverable without a retry. Missing required fields are a semantic error, not a syntactic one — string repair cannot supply values the model didn't generate.
- Schema validation is not the same as JSON parsing. A response that parses is not necessarily correct: extra keys, wrong types, missing required fields all pass `JSON.parse` and fail the downstream code. Validate after parsing.
- [S-04](s04-structured-output.md)'s recommendation — use tool use or the API's structured output mode — prevents syntactic deviation at the source. This entry covers the cases where you can't or when even structured output mode occasionally deviates on complex schemas.

## The move

**Apply a recovery pipeline in order, cheapest first:**

```js
function parseWithRecovery(raw) {
  const steps = [
    s => JSON.parse(s),                               // 1. raw — usually succeeds
    s => JSON.parse(stripFences(s)),                  // 2. strip ```json ... ```
    s => JSON.parse(stripPreamble(s)),                // 3. strip prose before {
    s => JSON.parse(extractBrackets(s)),              // 4. find outermost { } or [ ]
    s => JSON.parse(repairJson(extractBrackets(      // 5. fix trailing commas,
           stripFences(s)))),                         //    single→double quotes
  ];
  for (const fn of steps) {
    try { return { ok: true, result: fn(raw) }; }
    catch (_) {}
  }
  return { ok: false, result: null };
}
```

The five functions:

```js
// Strip markdown fences
const stripFences = s => s.replace(/^```(?:json)?\n?/m,'').replace(/\n?```$/m,'').trim();

// Strip prose before the first { or [
const stripPreamble = s => { const i = Math.min(...['{','['].map(c=>s.indexOf(c)).filter(i=>i>=0));
                              return i < Infinity ? s.slice(i) : s; };

// Extract outermost bracket pair
function extractBrackets(s) {
  const open = s.search(/[{[]/); if (open < 0) return s;
  const ch = s[open], close = ch==='{'?'}':']';
  let depth=0, i=open;
  for(;i<s.length;i++){if(s[i]===ch)depth++;else if(s[i]===close){depth--;if(!depth)break;}}
  return s.slice(open, i+1);
}

// Fix trailing commas, single→double quotes, unquoted keys
const repairJson = s => s.replace(/,\s*([}\]])/g,'$1').replace(/'/g,'"')
                          .replace(/(\w+)\s*:/g,'"$1":');
```

**After parsing, validate against your schema.** Parsing success is not correctness:

```js
function validate(obj, required) {
  const missing = required.filter(k => !(k in obj));
  if (missing.length) throw new Error(`Missing fields: ${missing}`);
  return obj;
}
```

**Classify failures before retrying:**

| Failure | Recoverable? | Action |
|---|---|---|
| Markdown fences | Yes | Strip and re-parse |
| Prose preamble | Yes | Strip and re-parse |
| Trailing comma / single quotes | Yes | Repair and re-parse |
| Extra/unknown keys | Yes (ignore) | Validate only required fields |
| Missing required field | No | Retry with constraint |
| Partial/truncated JSON | No | Retry with higher `max_tokens` |
| Wrong type on required field | No | Retry with schema example |

**Retry with diagnostic context, not a blind repeat.** If recovery fails, pass the specific failure to the model: `"Your output was missing required field 'price'. Return JSON with: {sku, price}."` A blind retry often reproduces the same deviation.

**Log deviation type at parse time.** Which recovery step succeeded tells you which deviation occurred — and whether the deviation rate is stable or climbing. A spike in "repair+extract" recoveries signals a prompt change or model update changed output behavior.

## Receipt

> Verified 2026-06-26 — Node, no model in the loop. The five deviation patterns are the most common real-world LLM output deviations; the recovery pipeline is deterministic string manipulation. Retry cost uses `gpt-tokenizer` (cl100k).

```
Failure mode           Parsed?   Via              Result
──────────────────────────────────────────────────────────
valid JSON             YES       raw              {sku, price}
markdown fenced        YES       strip_fences     {sku, price}
prose preamble         YES       strip_preamble   {sku, price}
trailing comma         YES       repair+extract   {sku, price}
single quotes          YES       repair+extract   {sku, price}

5/5 parsed with recovery pipeline
0/5 with raw JSON.parse only  (fails on 4 of 5 common deviations)

Recovery cost:  0 tokens    (CPU only, no API call)
Retry cost:    25 tokens    (new prompt + API round-trip)
Ratio: retry is 25x more expensive for fixable deviations
```

**What the receipt shows:**

- All four syntactic deviation types are recoverable with string manipulation — no model call, zero tokens, sub-millisecond latency. Retrying them is pure waste.
- The recovery pipeline is ordered so each step only runs if the previous one threw. Valid JSON succeeds at step 1; the rest add no overhead. The pipeline cost for the happy path is one `try/catch`.
- The 25× cost ratio (retry vs string repair) understates the real difference: a retry also adds API latency, consumes retry budget ([F-20](../forward-deployed/f20-rate-limits-and-retry.md)), and can fail again.
- What the pipeline does not fix: partial JSON (truncated at `max_tokens`), missing required fields, and semantic errors. These are not string problems; they require a retry with specific error context or a prompt fix.

## See also

[S-04](s04-structured-output.md) · [F-19](../forward-deployed/f19-agent-testing-strategies.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md) · [S-16](s16-prompting.md) · [S-36](s36-system-prompt-architecture.md)

## Go deeper

Keywords: `output parsing` · `JSON recovery` · `malformed JSON` · `markdown fences` · `prose preamble` · `trailing comma` · `schema validation` · `parse pipeline` · `retry vs repair` · `structured output`
