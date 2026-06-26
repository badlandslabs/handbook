# S-68 · Input Pre-Screening

The cheapest inference call is the one you never make. A fast pre-call filter — keyword rules, a tiny classifier, or a short allow-list check — can block out-of-scope and clearly harmful requests before they reach the frontier model. At 15% out-of-scope rate and 10k calls/day, this saves ~$69/month and makes blocked requests respond in under 1ms instead of 1–3 seconds.

## Situation

A customer support agent for Acme Corp receives 10 000 queries/day. Analysis shows 1 500 (~15%) are off-topic: "What's the weather in Chicago?", "What is Bitcoin?", "Who won the game last night?" These queries all go through the full pipeline — system prompt injection, frontier model call, output validation — and return a politely scoped refusal. The refusal costs the same as a useful answer: $0.00154/call. Pre-screening routes them to a static "I help with Acme products and billing — I can't answer that" response at <1ms and zero inference cost.

## Forces

- **Out-of-scope refusals are expensive no-ops.** The model has to read the full system prompt, process the user query, decide it's out of scope, and generate a refusal. Every step of that pipeline runs at full cost. A keyword rule produces the same refusal in microseconds.
- **Pre-screening is not guardrails.** [F-04](../forward-deployed/f04-guardrails.md) runs after the model call to check whether the output is safe. Pre-screening runs before the model call to check whether the input warrants calling the model at all. Both are needed; neither replaces the other.
- **The screening layer has three gates.** Security: block prompt injection, jailbreak, and harmful request patterns. Scope: block clearly out-of-scope topics. Routing: for queries that fall into a known-answer bucket (e.g. "what are your hours?"), answer with a static response without calling the model at all.
- **False positives cost trust, not just money.** A keyword rule that blocks a legitimate query ("I'm having a problem with the weather widget in your dashboard") is a support failure. Calibrate conservatively; route ambiguous cases to the model rather than blocking them.
- **Screening is a front door, not a wall.** The goal is to catch the clearly-wrong cases fast. The model's judgment handles everything else. Don't build a screening layer so aggressive that it requires constant maintenance.

## The move

**Run a keyword + pattern check before every model call. Block security violations immediately. Redirect out-of-scope requests with a static response. Pass everything else to the model.**

```js
const INJECTION_PATTERNS = [
  'ignore your instructions', 'ignore previous instructions',
  'act as ', 'pretend you are', 'you are now', 'jailbreak',
  'ignore all rules', 'disregard your',
];

const OUT_OF_SCOPE_KEYWORDS = [
  'weather', 'bitcoin', 'cryptocurrency', 'stock price', 'sports score',
  'news headline', 'recipe', 'politics', 'election',
];

const STATIC_ANSWERS = [
  { pattern: 'business hours', response: 'Acme support is available 9am–6pm PT, Mon–Fri. Chat is available 24/7.' },
  { pattern: 'phone number',   response: 'Our support number is 1-800-ACME-HELP. Press 2 for billing.' },
];

function preScreen(userInput) {
  const lower = userInput.toLowerCase();

  // Gate 1: security — block immediately, log for security review
  if (INJECTION_PATTERNS.some(p => lower.includes(p))) {
    return { action: 'block', reason: 'security', response: 'I can\'t help with that request.' };
  }

  // Gate 2: static answer — no model call needed
  const staticMatch = STATIC_ANSWERS.find(s => lower.includes(s.pattern));
  if (staticMatch) {
    return { action: 'static', reason: 'known-answer', response: staticMatch.response };
  }

  // Gate 3: out-of-scope — polite redirect, no model call
  if (OUT_OF_SCOPE_KEYWORDS.some(k => lower.includes(k))) {
    return { action: 'redirect', reason: 'out-of-scope',
      response: 'I specialize in Acme products and billing. For that question, try a general search engine.' };
  }

  return { action: 'pass' };
}

async function handleQuery(client, systemPrompt, userInput) {
  const screen = preScreen(userInput);

  if (screen.action !== 'pass') {
    // Log for calibration — not for blocking decisions
    console.log({ type: 'pre-screen', reason: screen.reason, query: userInput.slice(0, 80) });
    return screen.response;
  }

  // Only here do we call the model
  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 512,
    system: systemPrompt,
    messages: [{ role: 'user', content: userInput }],
  });
  return response.content[0].text;
}
```

**Calibration loop:**

```
1. Log every pre-screen action with the blocked query (truncated for privacy)
2. Weekly: review a sample of blocked queries — are any legitimate?
3. If false-positive rate > 1%: narrow the keyword list or add exclusion patterns
4. Monthly: review out-of-scope block reasons vs model refusals — 
   if the model would have refused it anyway, you're saving money; 
   if the model would have answered it, widen scope or remove the keyword
```

**Upgrade path:** keyword rules handle the clear-cut cases. If you need finer-grained intent detection (distinguish "how do I cancel" from "I want to complain about my cancellation"), replace Gate 3 with a small classifier (Haiku-class model or on-device classifier). The pattern is the same: pre-call decision → pass or handle without frontier model.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Inference price: $3.00/M input, $15.00/M output (claude-sonnet-4-6). Pre-screen keyword list is illustrative; actual lists are product-specific.

```
=== Pre-screen speed ===
$ node -e "
const kw = ['weather', 'bitcoin', 'stock price', 'politics', 'sports'];
const N = 100000;
const t0 = performance.now();
for (let i = 0; i < N; i++) kw.some(k => 'What is the weather?'.toLowerCase().includes(k));
console.log('Per check:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Per check: 0.0007 ms

=== Action latency comparison ===
Pre-screen block (keyword):    < 1 ms
Frontier model call:        1 000–3 000 ms (p50–p99)

Blocked queries respond 1000–3000× faster than model calls.

=== Cost savings (10k queries/day, 15% out-of-scope) ===

Frontier call cost:
  65 tok system + 28 tok input = 93 tok input  × $3.00/M  = $0.000279
  84 tok output                                 × $15.00/M = $0.001260
  Total per call: $0.001539

Daily blocked calls:      10 000 × 15% = 1 500
Daily savings:            1 500 × $0.001539 = $2.31
Monthly savings:          $69/month

=== Scale ===
Volume         15% OOS block    Monthly savings
 10k/day       1 500 blocked    $69/month
100k/day      15 000 blocked    $693/month
500k/day      75 000 blocked    $3 465/month
```

The savings compound with static-answer routing: queries with known answers (hours, contact info, return policy) can be answered directly at 0 token cost, adding to the blocked fraction without any keyword-list maintenance cost.

## See also

[F-04](../forward-deployed/f04-guardrails.md) · [F-13](../forward-deployed/f13-prompt-injection.md) · [S-06](s06-model-routing.md) · [S-36](s36-system-prompt-architecture.md) · [S-65](s65-multi-model-pipelines.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `input pre-screening` · `intent classification` · `pre-call filter` · `keyword gate` · `out-of-scope routing` · `static answer` · `injection detection` · `front door pattern` · `scope enforcement` · `query triage`
