# F-24 · Graceful Degradation

When the model is down, over budget, or returning bad quality, the question is not "did it fail" — it is "what does the user see." A system that fails gracefully returns something useful; a system that fails badly returns nothing or lies. The difference is three patterns: circuit breakers, partial results, and cost ceilings.

## Situation

A customer support agent hits a provider outage. Without a circuit breaker, 1,000 queued requests each retry 3 times — 1,600 total API calls, 900 seconds of cumulative retry wait, 300 users waiting or getting errors. With a circuit breaker that opens after 5 failures, the same 1,000 requests make 1,010 API calls, 15 seconds of retry wait, and 300 users get an honest "temporarily unavailable" in under a second instead of waiting through three timeouts.

## Forces

- Retry and circuit breaker are different tools. Retry ([F-20](f20-rate-limits-and-retry.md)) handles transient spikes — a single request bounces off a rate limit and succeeds on attempt 2. Circuit breakers handle sustained failures — the provider has been down for 5 minutes and retrying is just burning money and making users wait.
- The application must decide what to return, not just whether to fail. Infrastructure fallback ([S-11](../stacks/s11-llm-gateway-fallback.md)) can route to a different provider; the application layer must decide: full answer from backup provider, cached stale answer, partial answer with caveat, or explicit error. Each has different user experience and cost implications.
- Cost ceilings prevent runaway sessions. An agent loop without a budget check can accumulate unlimited cost — especially in tool-heavy loops or when given ambiguous tasks ([S-38](../stacks/s38-agent-state-design.md)). A per-session budget limit stops the loop before the invoice arrives.
- Partial answers are often better than full errors for user experience. A user who gets "here is what I know, but I can't access live data right now" has something actionable. A user who gets an error has nothing.
- Stale cache answers need timestamps. A cached answer served during an outage is acceptable only if the user knows it may be stale. "As of 5 minutes ago, your balance is $200" is honest; serving it without the caveat is misinformation.
- Quality degradation is also a failure mode. The model may be available but returning low-quality outputs (hallucinating, going off-topic, breaking format). This is a silent failure — no exception fires. Monitoring output quality ([F-02](f02-evaluation-at-scale.md), F-12) and having a quality threshold to trigger degradation is the only defense.

## The move

**Implement three layers: circuit breaker → partial result selection → explicit cost ceiling.**

**Layer 1 — Circuit breaker.**

Track consecutive failures per provider. After `THRESHOLD` failures, open the circuit (stop trying). After `COOLDOWN`, half-open (try one probe). If it succeeds, close the circuit; if not, restart cooldown.

```js
class CircuitBreaker {
  constructor({ threshold = 5, cooldownMs = 30000 } = {}) {
    this.state = 'closed';   // closed | open | half-open
    this.failures = 0;
    this.threshold = threshold;
    this.cooldownMs = cooldownMs;
    this.openedAt = null;
  }

  async call(fn) {
    if (this.state === 'open') {
      if (Date.now() - this.openedAt > this.cooldownMs) {
        this.state = 'half-open';
      } else {
        throw new Error('circuit open');   // fast fail — no API call
      }
    }
    try {
      const result = await fn();
      if (this.state === 'half-open') this._reset();
      this.failures = 0;
      return result;
    } catch (err) {
      this.failures++;
      if (this.failures >= this.threshold) this._open();
      throw err;
    }
  }

  _open()  { this.state = 'open'; this.openedAt = Date.now(); }
  _reset() { this.state = 'closed'; this.failures = 0; this.openedAt = null; }
}
```

**Layer 2 — Partial result selection.**

When the primary call fails and the fallback chain ([S-11](../stacks/s11-llm-gateway-fallback.md)) is exhausted, pick the best available response:

1. **Cache hit** — return the last successful response for this request type, with a freshness caveat: "As of [time], ..."
2. **Partial answer** — return what the agent completed before failure, with explicit "I could not finish"
3. **Graceful error** — tell the user what happened and what to do next: "Our AI service is temporarily unavailable. Contact [support] for immediate help."

Never return a silent empty response or fabricate content to fill the gap.

**Layer 3 — Cost ceiling.**

Track cumulative token cost per session. Before each model call, check against budget:

```js
async function guardedCall(prompt, budget) {
  const estimatedCost = estimateTokens(prompt) * PRICE_PER_TOKEN;
  if (budget.spent + estimatedCost > budget.limit) {
    return { status: 'budget_exceeded', partial: budget.lastResult };
  }
  const result = await model.call(prompt);
  budget.spent += result.usage.total_tokens * PRICE_PER_TOKEN;
  budget.lastResult = result;
  return result;
}
```

At $0.10/session budget and $0.003/call, the ceiling fires after ~33 calls — enough for any legitimate task, a hard stop for runaway loops.

**Name the degraded state explicitly in the response.** Include a machine-readable status field alongside the user-facing message: `{ "status": "degraded", "reason": "service_unavailable", "message": "..." }`. Downstream systems can route on the status; the user sees the message.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Circuit breaker model is deterministic: 1,000 requests, 30% failure rate (sustained outage), 3 retries with exponential backoff (1s base), circuit opens after 5 failures. Response shape token counts are measured.

```
=== Circuit breaker: 30% sustained outage, 1,000 requests ===

Metric                    Without CB    With CB     Savings
Total API calls              1,600       1,010      −590 calls
Total retry wait              900s          15s     −885s
Avg calls per request          1.60        1.01

=== Cost ceiling (session budget $0.10, $0.003/call) ===
Max calls before ceiling: 33
After ceiling: return { status: "budget_exceeded", partial: lastResult }

=== Graceful response shapes (user-facing) ===
Full answer:           36 tokens   $0.22/k calls
Partial (degraded):    26 tokens   $0.16/k calls  ← what the agent completed
Stale cache:           27 tokens   $0.16/k calls  ← with timestamp caveat
Graceful error:        22 tokens   $0.13/k calls  ← honest, actionable
```

The 885-second retry-wait saving is the sharpest number: without a circuit breaker, a 30% sustained outage causes every request to wait through 3 timeouts before failing. With a circuit breaker open, each of those requests fails in milliseconds. The user experience difference is 900 seconds of waiting vs near-instant "temporarily unavailable."

## See also

[S-11](../stacks/s11-llm-gateway-fallback.md) · [F-20](f20-rate-limits-and-retry.md) · [F-03](f03-failure-modes.md) · [F-08](f08-agent-cost-control.md) · [S-38](../stacks/s38-agent-state-design.md)

## Go deeper

Keywords: `circuit breaker` · `graceful degradation` · `partial results` · `cost ceiling` · `stale cache` · `budget enforcement` · `fallback strategy` · `service unavailability` · `agent budget`
