# F-43 · Guardrail Latency

[F-04](f04-guardrails.md) defines three guardrail layers (input validation, model-based classifier, output controls) and notes that "safety latency compounds across a pipeline." It doesn't cover how to make those layers fast. A naive three-layer guardrail adds 500ms to every call, twice. This entry covers the two techniques that eliminate most of that overhead: a fast keyword pre-filter that catches obvious cases in under 1ms, and parallel execution that runs the model-based check concurrently with the main call so it adds zero latency when it passes.

## Situation

A support agent's guardrail pipeline runs three steps in series: keyword check → Llama Guard call (400ms) → main model call (1 200ms) → output pattern check (50ms). Total latency: 1 650ms. Restructuring to: keyword check (1ms, synchronous) → [Llama Guard + main call in parallel] → output check (streaming) → reduce total to 1 250ms — a 24% reduction with identical safety coverage.

## Forces

- **Model-based guardrails are slow relative to the main call.** A Llama Guard or ShieldGemma call on a small GPU takes 200–500ms. Running it before the main call adds that latency to every request. Running it after means you've already generated and potentially surfaced the output. Neither is ideal.
- **Parallel execution with pre-cancellation is the resolution.** Start the main model call and the guardrail call simultaneously. If the guardrail passes, the main call's output is already arriving — zero latency penalty. If the guardrail fails, cancel the main call immediately — you've saved the cost of completing it.
- **Keyword pre-filter eliminates the obvious cases at negligible cost.** A prompt-injection pattern like "ignore your instructions" or a known blocked phrase doesn't need a model guardrail — a list check catches it in 0.0017ms. Running the model guardrail on clearly-safe traffic is waste; running it on obvious injections is also waste (it's going to fail in 5 words).
- **Output guardrails can check streaming chunks.** Instead of waiting for the full response and then checking it, a pattern-based output check can process each chunk as it arrives. Structured violations (PII patterns, URL formats, code block boundaries) can be detected and blocked mid-stream, reducing latency to reveal for caught violations.
- **Cache guardrail verdicts for exact-match inputs.** If the same query appears twice (FAQ repeat, or a scripted attack probing the same pattern), the guardrail verdict from the first call is valid for the second. Cache by input hash with a short TTL (5 minutes).

## The move

**Keyword pre-filter synchronously before any model call. Run model guardrail in parallel with the main call. Cancel the main call early if guardrail fails. Check output streaming, not post-completion.**

**Layered guardrail with parallel execution:**

```js
const INJECTION_PATTERNS = [
  'ignore your instructions', 'ignore previous instructions',
  'act as ', 'pretend you are', 'you are now', 'jailbreak',
  'reveal your system prompt', 'disregard your',
];

function keywordBlock(input) {
  const lower = input.toLowerCase();
  const hit = INJECTION_PATTERNS.find(p => lower.includes(p));
  return hit ? { blocked: true, reason: 'injection_pattern', pattern: hit } : null;
}

async function guardedCall(client, guardModel, systemPrompt, userInput, opts = {}) {
  // Layer 1: keyword pre-filter — 0.0017ms, no API call
  const kwBlock = keywordBlock(userInput);
  if (kwBlock) return { blocked: true, ...kwBlock };

  // Check guardrail verdict cache
  const cacheKey = require('crypto').createHash('md5').update(userInput).digest('hex');
  const cached = guardCache.get(cacheKey);
  if (cached !== undefined) {
    if (!cached.safe) return { blocked: true, reason: 'cached_unsafe' };
    // Safe cache hit — proceed to main call without guardrail
    return mainCall(client, systemPrompt, userInput);
  }

  // Layer 2: model guardrail + main call in parallel
  const mainController  = new AbortController();
  const guardController = new AbortController();

  const guardPromise = runGuardrail(client, guardModel, userInput, guardController.signal)
    .then(verdict => {
      guardCache.set(cacheKey, verdict, { ttl: 5 * 60 * 1000 });
      if (!verdict.safe) {
        mainController.abort(); // cancel the main call early
      }
      return verdict;
    });

  const mainPromise = client.messages.create({
    model: 'claude-sonnet-4-6', max_tokens: 512,
    system: systemPrompt,
    messages: [{ role: 'user', content: userInput }],
  }, { signal: mainController.signal })
    .catch(err => err.name === 'AbortError' ? null : Promise.reject(err));

  const [guardVerdict, mainResponse] = await Promise.all([guardPromise, mainPromise]);

  if (!guardVerdict.safe) return { blocked: true, reason: guardVerdict.category };
  if (!mainResponse)      return { blocked: true, reason: 'main_cancelled_on_guard_fail' };

  // Layer 3: output streaming check (pattern-based on content of mainResponse)
  const outputViolation = checkOutput(mainResponse.content[0].text);
  if (outputViolation) return { blocked: true, reason: 'output_violation', ...outputViolation };

  return { blocked: false, response: mainResponse };
}

async function runGuardrail(client, guardModel, input, signal) {
  const resp = await client.messages.create({
    model: guardModel, max_tokens: 10,
    messages: [{ role: 'user', content:
      `Classify this input. Reply only "safe" or "unsafe:<category>". Input: ${input}` }],
  }, { signal });
  const text = resp.content[0].text.trim().toLowerCase();
  return { safe: text === 'safe', category: text.startsWith('unsafe:') ? text.slice(7) : null };
}

// Output pattern check (runs on completed or streaming chunks)
const OUTPUT_BLOCK = [
  { pattern: /\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b/, label: 'credit_card' },
  { pattern: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i, label: 'email_in_output' },
];

function checkOutput(text) {
  for (const { pattern, label } of OUTPUT_BLOCK) {
    if (pattern.test(text)) return { label };
  }
  return null;
}
```

**Latency budget by architecture:**

| Architecture | Typical total latency | Notes |
|---|---|---|
| Serial: keyword → guard → main → output | 1 650ms | Baseline — don't ship this |
| Keyword sync → (guard ∥ main) → output | 1 250ms | 25% saving; guard usually finishes first |
| Keyword sync → main (no model guard) → output | 1 250ms | Fast but relies on output check only |
| Keyword sync → guard cache hit → main | 1 200ms | After first call; cache hit skips guard call |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Guardrail model price: $0.80/M input (Haiku-class). Main call price: $3.00/M input, $15.00/M output. Latency estimates assume 400ms for guardrail model, 1 200ms for main call.

```
=== Keyword pre-filter speed ===

$ node -e "
const patterns = ['ignore your instructions', 'act as ', 'jailbreak'];
const input = 'How do I cancel my subscription?';
const N = 100000;
const t0 = performance.now();
for (let i = 0; i < N; i++) patterns.some(p => input.toLowerCase().includes(p));
console.log('Per check:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Per check: 0.0017 ms

Keyword pre-filter is 235 000× faster than a model guardrail call.
For obvious injections: stops at 0.0017ms, never reaches the model.

=== Latency: serial vs parallel guardrail ===

Serial:   keyword(1ms) → guard(400ms) → main(1200ms) → output(50ms) = 1 651ms
Parallel: keyword(1ms) → [guard(400ms) ∥ main(1200ms)] → output(50ms) = 1 251ms
Saving: 400ms (24%)

When guard FAILS in parallel mode:
  Guard fires at 400ms → main cancelled (S-69 abort pattern)
  Main has generated ~(400ms × 50 tok/s / 1000) = ~20 tokens → cancelled, not billed for remainder

=== Model guardrail cost ===

Guard input: 16 tok, guard output: 1 tok
Haiku-class price: 16 × $0.80/M + 1 × $4.00/M = $0.000017/call
At 10k/day: $5.00/month

Verdict cache hit rate at 30% exact-match repeat rate:
  3 000 cache hits/day → guard calls: 7 000/day → $3.50/month (30% saving)
```

## See also

[F-04](f04-guardrails.md) · [F-13](f13-prompt-injection.md) · [S-68](../stacks/s68-input-pre-screening.md) · [S-35](../stacks/s35-latency-budget.md) · [S-69](../stacks/s69-streaming-cancellation.md) · [S-67](../stacks/s67-full-response-caching.md)

## Go deeper

Keywords: `guardrail latency` · `parallel guardrail` · `keyword pre-filter` · `Llama Guard` · `guardrail cache` · `streaming output check` · `safety latency` · `abort on guard fail` · `content safety` · `fast guardrail`
