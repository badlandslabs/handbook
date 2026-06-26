# S-63 · Output Text Cleaning

[S-39](s39-output-parsing-robustness.md) covers recovering malformed structured output — JSON in markdown fences, prose preamble before a JSON block. This entry covers the adjacent problem: the model returns text, not JSON, and the text has noise that shouldn't reach the user or the downstream system. Preambles, filler trailers, unwanted markdown, and AI disclaimers are the four common patterns. The fix is almost always in the prompt, not the post-processor.

## Situation

A support agent returns responses for display in a mobile app. The API call works. The responses are accurate. But they start with "Sure! I'd be happy to help with that." and end with "I hope this helps! Let me know if you need anything else." The product manager files a ticket: the copy sounds robotic and wastes space on a small screen. The options are: fix the prompt (30 minutes), or build a post-processor (3 days). Both work. The prompt fix is cheaper to build and cheaper to run.

## Forces

- **Contamination costs output tokens.** Every preamble character the model generates is billed. A 15-token "Sure! I'd be happy to help!" on 10 000 calls/day wastes $67/month at $15/M output. The preamble adds no value and is removed before display — it is pure waste.
- **The prompt fix is cheaper than the post-processor.** Adding "Respond directly. No preamble. No closing remarks." to the system prompt is ~10 tokens (input price: $3/M). It eliminates all four contamination types. Building and maintaining regex-based cleaning for edge cases costs engineering time and is never complete.
- **Post-processors have failure modes the prompt doesn't.** Regex preamble stripping fails on preambles that don't match the pattern. It works until the model changes its phrasing; then it silently stops working. The output contract in the prompt is a specification — the model tries to follow it at every call.
- **AI disclaimers are the hardest to strip.** Preambles and trailers are at the edges of the string; they're easy to detect by position. Disclaimers are embedded mid-sentence: "As an AI, I don't have access to real-time data, but the recommendation is..." After stripping "As an AI, I don't have access to real-time data, but", what remains is the actual content. Regex surgery on this is fragile. The prompt fix is: "Do not include disclaimers about being an AI."
- **The post-processor is still worth building for defense-in-depth.** Customer-facing product text that goes through a model should have a cleaning pass even if the prompt is well-crafted. Models update, prompts drift, edge cases appear. The post-processor is the last line.

## The move

**Add an output contract to the system prompt. Build a cleaning pipeline for legacy systems or defense-in-depth. Log which cleaner fires so you know when the prompt is drifting.**

**Output contract (prompt-first fix):**

```xml
<output>
Respond directly. Do not start with "Sure", "Of course", "I'd be happy to", or any acknowledgment.
Do not end with "I hope this helps", "Let me know if", or any closing remark.
Plain text only — no Markdown formatting (no bold, headers, code spans) unless the caller explicitly requests it.
Do not include disclaimers about being an AI or about knowledge cutoff dates.
</output>
```

This 49-token addition eliminates all four contamination types at input price (~$0.15/day at 10k calls). The same 15 wasted output tokens cost $0.23/day — the contract pays back on day one.

**Post-processing pipeline:**

```js
const PREAMBLE_STARTERS = ['sure', 'of course', "i'd be happy", 'certainly', 'happy to help',
                            "here's what", "here's the", "great question", 'absolutely'];

function stripPreamble(text) {
  const lower = text.toLowerCase();
  const startsWithPreamble = PREAMBLE_STARTERS.some(p => lower.startsWith(p));
  if (!startsWithPreamble) return text;
  // Preambles end at the first blank line or paragraph break
  const breakIdx = text.search(/\n\n|\n(?=[A-Z])/);
  return breakIdx > 0 ? text.slice(breakIdx).trim() : text;
}

const TRAILER_ENDINGS = ['i hope this helps', 'let me know if', "feel free to", "don't hesitate", 'please let me know'];

function stripTrailer(text) {
  const sentences = text.split(/(?<=[.!?])\s+/);
  while (sentences.length > 1) {
    const last = sentences[sentences.length - 1].toLowerCase();
    if (TRAILER_ENDINGS.some(t => last.includes(t))) sentences.pop();
    else break;
  }
  return sentences.join(' ').trim();
}

function stripMarkdown(text) {
  return text
    .replace(/\*\*([^*\n]+)\*\*/g, '$1')   // **bold**
    .replace(/\*([^*\n]+)\*/g, '$1')        // *italic*
    .replace(/`([^`\n]+)`/g, '$1')          // `code span`
    .replace(/^#{1,6}\s+/gm, '');           // ## headers
}

function cleanTextOutput(text, { markdown = false, preamble = true, trailer = true } = {}) {
  let s = text.trim();
  if (preamble) s = stripPreamble(s);
  if (trailer)  s = stripTrailer(s);
  if (markdown) s = stripMarkdown(s);
  return s;
}

// Log which cleaner fired — tells you when prompt is drifting
function cleanWithMetrics(text, opts, metrics) {
  const after = {
    preamble: stripPreamble(text),
    trailer:  stripTrailer(text),
  };
  if (after.preamble !== text) metrics.increment('output.preamble_stripped');
  if (after.trailer  !== text) metrics.increment('output.trailer_stripped');
  return cleanTextOutput(text, opts);
}
```

**Disclaimer handling:**

AI disclaimers are position-ambiguous — they don't always start or end the response. The regex approach is unreliable. Use two alternatives:

1. **Prompt contract** (preferred): "Do not include disclaimers about being an AI or knowledge limitations. If you don't know something, say 'I don't have information on that' and stop."
2. **Filter-and-flag** (fallback): detect `as an ai` or `as a language model` in the response; flag for human review rather than attempting regex surgery.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Prices: $3.00/M input, $15.00/M output.

```
=== Contamination token overhead per type ===

Type         Dirty    Clean    Overhead
preamble     33 tok → 18 tok   +15 tok
trailer      30 tok → 15 tok   +15 tok
markdown     35 tok → 28 tok   +7 tok
disclaimer   23 tok → 11 tok   +12 tok

=== Output contract fix ===

Output contract: 49 input tokens (system prompt addition)
Avg contamination: ~12 output tokens/call

At 10k calls/day:
  Contamination cost (no contract):  ~$55/month wasted output tokens
  Output contract input cost:        ~$44/month
  Net saving with prompt fix:        ~$11/month + engineering time saved

=== Post-processing pipeline test (3/4 types handled by position-based cleaners) ===

preamble    PASS  (paragraph break detection)
trailer     PASS  (sentence boundary scan from end)
markdown    PASS  (targeted regex per syntax)
disclaimer  PARTIAL — position-ambiguous; use prompt contract + flag, not regex
```

## See also

[S-39](s39-output-parsing-robustness.md) · [S-04](s04-structured-output.md) · [S-47](s47-output-length-control.md) · [S-57](s57-negative-prompting.md) · [S-59](s59-instruction-density.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `output cleaning` · `preamble stripping` · `filler removal` · `markdown stripping` · `AI disclaimer` · `output post-processing` · `output contract` · `text normalization` · `response hygiene`
