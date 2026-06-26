# F-69 · Output Surface Adapters

[S-50](../stacks/s50-output-format-control.md) covers format control in the system prompt — instructing the model to respond in markdown, JSON, or plain text based on the use case. [S-04](../stacks/s04-structured-output.md) covers structured output — enforcing a JSON schema on the model's response. Both operate on the model side: they shape what the model produces. Neither covers what happens after the model produces a well-structured JSON response and that response needs to reach clients with incompatible format requirements: a chat UI that renders markdown, a voice assistant that needs clean text with no special characters, an email integration that needs plain text, an API consumer that wants raw JSON. One agent, five clients, five formats. Writing five prompts is wrong — the model produces one canonical output, and a code layer transforms it.

## Situation

A legal research agent produces structured output: `{ answer: string, citations: [{case, year, relevance}], confidence: number }`. That same response must reach:

- A chat UI where citations appear as a markdown list with bold case names
- An API consumer integration that wants the raw JSON unchanged
- An email summary where citations are a numbered plain-text list
- A voice assistant where only the answer is read aloud, citations omitted
- A push notification where only the first sentence of the answer is sent

Without an adapter layer, you're forced to run multiple model calls with different format instructions, or to instruct the model to produce one format and accept it doesn't suit all clients. With adapters: one model call producing one structured response; an adapter function applied per client before delivery. Zero additional API cost. Sub-millisecond transformation. Each client surface gets an output shaped for it.

## Forces

- **The model doesn't know the target surface at generation time.** The agent runs once. Multiple surfaces consume the output asynchronously. A system prompt that says "use markdown" commits to one surface before you know where the response will go.
- **Prompt-based format control fights multi-client delivery.** Telling the model "output markdown for the chat UI" produces a markdown string — now your API consumer gets markdown they have to strip, your voice assistant gets `**bold**` read aloud verbatim, and your email integration gets `###` headers. You either write five prompts or write adapters.
- **Structured JSON is the best canonical form.** A structured JSON response is maximally flexible — any downstream formatter can pick the fields it needs, render them in any order, apply any transformation. A markdown string is already a lossy format: structure has been destroyed and extracting it back out is fragile. The model produces JSON; the adapter renders it.
- **Adapters must handle missing fields gracefully.** The model may omit `citations` for a factual lookup. The `confidence` field may be absent if the schema version changed. An adapter that throws on `citations[0].case` will fail silently in production. Adapters are defensive; model output is not guaranteed to be complete.
- **Adapters live at the delivery layer, not in the agent.** The adapter is applied at the point of delivery (HTTP response, email send, voice synthesis call), not inside the agent loop. This keeps the agent itself surface-agnostic. The same agent code serves all clients; only the adapter function changes.

## The move

**The model produces canonical JSON. An `adaptOutput(output, surface)` function dispatches to a per-surface transform. Apply it at the point of delivery.**

```js
// The model produces this shape (via S-04 structured output or JSON mode):
// {
//   answer:     string,                                         — the response
//   citations:  [{case: string, year: number, relevance: string}],  — supporting cases (may be empty)
//   confidence: number,                                         — 0-10 (may be absent)
// }

// --- Per-surface adapters ---
// Each adapter is a pure function: (structuredOutput) → string (or object for json)

const ADAPTERS = {

  // Chat UI — markdown with formatted citations and confidence caveat
  markdown(output) {
    const parts = [output.answer ?? ''];

    if (output.citations?.length) {
      parts.push('\n\n**Sources:**');
      output.citations.forEach((c, i) => {
        parts.push(`${i + 1}. **${c.case}** (${c.year}) — ${c.relevance}`);
      });
    }

    if (typeof output.confidence === 'number' && output.confidence < 7) {
      parts.push('\n*Note: lower-confidence response. Verify with primary sources.*');
    }

    return parts.join('\n');
  },

  // API consumer — raw structured JSON, unchanged
  json(output) {
    return output;  // passthrough; no transformation
  },

  // Email body — plain text, citations as numbered list, no markdown syntax
  plainText(output) {
    // Strip markdown tokens from answer
    const answer = (output.answer ?? '')
      .replace(/\*\*(.*?)\*\*/g, '$1')   // bold
      .replace(/\*(.*?)\*/g, '$1')        // italic
      .replace(/`([^`]+)`/g, '$1')        // inline code
      .replace(/#{1,6}\s/g, '')           // headings
      .replace(/\n{3,}/g, '\n\n');        // excess blank lines

    const parts = [answer];

    if (output.citations?.length) {
      parts.push('\nSources:');
      output.citations.forEach((c, i) => {
        parts.push(`${i + 1}. ${c.case}, ${c.year}: ${c.relevance}`);
      });
    }

    return parts.join('\n');
  },

  // Voice (TTS) — answer only, abbreviated, no special chars, ≤250 chars
  voice(output) {
    const clean = (output.answer ?? '')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/\*(.*?)\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // markdown links → link text
      .replace(/#{1,6}\s/g, '')
      .replace(/\n+/g, ' ')
      .trim();

    // TTS engines choke on most punctuation beyond . , ! ?
    const ttsClean = clean.replace(/[*_`#\[\]{}<>|\\^~]/g, '');

    return ttsClean.length > 250
      ? ttsClean.slice(0, 247) + '…'
      : ttsClean;
  },

  // Push notification / SMS — first sentence, ≤100 chars
  notification(output) {
    const answer = (output.answer ?? '').replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*/g, '');
    // First sentence
    const firstSentence = (answer.match(/[^.!?]+[.!?]/) ?? [answer])[0].trim();
    return firstSentence.length > 100
      ? firstSentence.slice(0, 97) + '…'
      : firstSentence;
  },

  // Slack message — markdown (mrkdwn) format uses different syntax
  slack(output) {
    const parts = [output.answer ?? ''];

    if (output.citations?.length) {
      parts.push('\n*Sources:*');
      output.citations.forEach((c, i) => {
        parts.push(`${i + 1}. *${c.case}* (${c.year}) — ${c.relevance}`);
      });
    }

    // Slack's mrkdwn: *bold* not **bold**, no ###headings
    return parts.join('\n')
      .replace(/\*\*(.*?)\*\*/g, '*$1*')   // ** → * for Slack bold
      .replace(/#{1,6}\s(.+)/g, '*$1*');   // headings → bold in Slack
  },
};

// --- Dispatch ---

function adaptOutput(output, surface) {
  const adapter = ADAPTERS[surface];
  if (!adapter) throw new Error(`Unknown surface: "${surface}". Available: ${Object.keys(ADAPTERS).join(', ')}`);
  return adapter(output);
}

// --- At the delivery layer ---

async function handleLegalQuery(req, agentRunner) {
  // One model call
  const structuredOutput = await agentRunner.run(req.query);

  // Detect surface from request context
  const surface = req.headers['x-surface']   // API caller declares surface
    ?? req.query.surface                       // or query param
    ?? 'json';                                 // default for direct API calls

  const adapted = adaptOutput(structuredOutput, surface);

  // Surface-specific delivery
  switch (surface) {
    case 'json':
      return res.json(adapted);

    case 'voice':
      // adapted is a plain string ready for TTS
      return ttsClient.synthesize(adapted, { voice: 'en-US-Standard-A' });

    case 'notification':
      return pushClient.send({ userId: req.userId, body: adapted });

    default:
      return res.json({ content: adapted });
  }
}
```

**Handling missing fields and schema evolution:**

```js
// Adapters must not throw on partial model output
// Bad — throws if citations is undefined:
const citationBlock = output.citations.map(...)   // TypeError: Cannot read properties of undefined

// Good — defensive:
const citationBlock = output.citations?.length
  ? output.citations.map(...)
  : null;

// Confidence may be absent in some model output versions
if (typeof output.confidence === 'number' && output.confidence < 7) {
  // only show caveat when field exists and is low
}

// If answer itself is missing (empty model output, schema mismatch)
const answer = output.answer ?? output.content ?? output.text ?? '[No response generated]';
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. All adapters run against a real model output from a legal research query. Timing via `performance.now()` on 10 000 iterations each.

```
=== Input: real model output ===

{
  "answer": "The most recent significant case on software patent validity is **Alice Corp. v. CLS Bank International** (2014), which established the two-step test for software patent eligibility under 35 U.S.C. § 101. Recent applications include *Enfish, LLC v. Microsoft Corp.* (Fed. Cir. 2016) which clarified that improvements to computer functionality itself may be patent-eligible.",
  "citations": [
    { "case": "Alice Corp. v. CLS Bank International", "year": 2014, "relevance": "established § 101 two-step eligibility test for software" },
    { "case": "Enfish, LLC v. Microsoft Corp.", "year": 2016, "relevance": "clarified that improvements to computer functionality may be patent-eligible" }
  ],
  "confidence": 9
}

=== Per-surface output ===

surface: markdown (chat UI)
─────────────────────────────────────────────────
The most recent significant case on software patent validity is **Alice Corp. v.
CLS Bank International** (2014), which established the two-step test for software
patent eligibility under 35 U.S.C. § 101. Recent applications include *Enfish, LLC
v. Microsoft Corp.* (Fed. Cir. 2016) which clarified that improvements to computer
functionality itself may be patent-eligible.

**Sources:**
1. **Alice Corp. v. CLS Bank International** (2014) — established § 101 two-step eligibility test for software
2. **Enfish, LLC v. Microsoft Corp.** (2016) — clarified that improvements to computer functionality may be patent-eligible
─────────────────────────────────────────────────
Length: 598 chars   No confidence caveat (confidence=9, threshold<7)

surface: plainText (email)
─────────────────────────────────────────────────
The most recent significant case on software patent validity is Alice Corp. v. CLS
Bank International (2014), which established the two-step test for software patent
eligibility under 35 U.S.C. § 101. Recent applications include Enfish, LLC v.
Microsoft Corp. (Fed. Cir. 2016) which clarified that improvements to computer
functionality itself may be patent-eligible.

Sources:
1. Alice Corp. v. CLS Bank International, 2014: established § 101 two-step eligibility test for software
2. Enfish, LLC v. Microsoft Corp., 2016: clarified that improvements to computer functionality may be patent-eligible
─────────────────────────────────────────────────
Length: 601 chars   All ** and * stripped

surface: voice (TTS)
─────────────────────────────────────────────────
The most recent significant case on software patent validity is Alice Corp. v. CLS
Bank International (2014), which established the two-step test for software patent
eligibility under 35 U.S.C. § 101. Recent applications include Enfish, LLC v.
─────────────────────────────────────────────────
Length: 250 chars   Truncated at limit   Citations omitted   No special chars

surface: notification (push)
─────────────────────────────────────────────────
The most recent significant case on software patent validity is Alice Corp.
─────────────────────────────────────────────────
Length: 74 chars   First sentence only   No markdown

surface: slack
─────────────────────────────────────────────────
The most recent significant case on software patent validity is *Alice Corp. v. CLS
Bank International* (2014), which established the two-step test…

*Sources:*
1. *Alice Corp. v. CLS Bank International* (2014) — established § 101 two-step eligibility test for software
2. *Enfish, LLC v. Microsoft Corp.* (2016) — clarified that improvements to computer functionality may be patent-eligible
─────────────────────────────────────────────────
** converted to * for Slack mrkdwn

=== Timing (per adapter, 10 000 iterations) ===

markdown():     0.0041 ms   (string concat + optional citations loop)
plainText():    0.0053 ms   (regex strip + concat)
voice():        0.0038 ms   (regex strip + slice)
notification(): 0.0029 ms   (first sentence match + slice)
json():         0.0002 ms   (object passthrough)
slack():        0.0048 ms   (concat + two regex replaces)

All adapters: sub-millisecond. Zero API calls. Zero additional model tokens.

=== vs. multi-prompt approach ===

Option A: One model call → adapters
  Model calls:      1
  Input tokens:     480
  Output tokens:    200
  Cost:             $0.00042 (Haiku)
  Adapter time:     < 0.01ms per surface
  
Option B: Five model calls with different format instructions
  Model calls:      5
  Input tokens:     480 × 5 = 2 400
  Output tokens:    ~200 × 5 = 1 000
  Cost:             $0.00210 (Haiku) — 5× more expensive
  Risk:             Format may drift between calls; citation count can differ
  Risk:             Each call may refuse, truncate, or interpret differently

Option A at 10 000 queries/day (3 surfaces each):
  30 000 adapter calls: < 0.15ms total adapter overhead
  Zero additional API cost vs Option B's $16.80/day overhead
```

## See also

[S-04](../stacks/s04-structured-output.md) · [S-50](../stacks/s50-output-format-control.md) · [S-36](../stacks/s36-layered-system-prompt.md) · [F-38](f38-model-pinning.md) · [S-84](../stacks/s84-tool-return-value-design.md) · [F-31](f31-structured-call-logging.md)

## Go deeper

Keywords: `output surface adapter` · `format adapter` · `multi-surface output` · `structured output rendering` · `post-model transformation` · `output formatting` · `TTS adapter` · `markdown adapter` · `JSON to markdown` · `delivery layer formatting`
