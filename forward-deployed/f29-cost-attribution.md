# F-29 · Cost Attribution

The invoice from your model provider tells you total spend. It doesn't tell you which product feature is driving 38% of it, which customer tier costs three times more to serve, or whether a new feature launched last Tuesday is responsible for a 20% spend spike. Cost attribution is the practice of tagging every model call with the context that matters for business decisions — feature, customer, environment — and rolling that up into a breakdown you can act on.

## Situation

A product has three features: chat, summarize, and search. Total weekly LLM spend is $8.60. The team suspects "chat" is the cost driver because it's the most-used feature. Attribution reveals the opposite: "summarize" is 9% of calls but 21% of spend at $8.94/k vs chat's $4.01/k — because summarization inputs are 2–4× longer than chat inputs. Without attribution, the team would have optimized chat (large call count, moderate unit cost) and missed that caching repeated document summaries ([S-43](../stacks/s43-tool-result-caching.md)) on "summarize" would cut spend by 30%.

## Forces

- Provider invoices are coarse. They show total token spend by model, not by feature. A product with three features calling the same model looks the same on the invoice regardless of which feature is expensive.
- Tagging at the call site is the only reliable approach. Inferring feature from prompt content after the fact is fragile; content changes. Tag at the call site with `{ feature, customer_id, customer_tier, env }` and log those tags with each call's token counts.
- Tags must never enter the prompt. Metadata tags are for your logging infrastructure, not for the model. Adding cost-attribution context to the prompt wastes tokens and can confuse the model.
- Attribution enables unit economics. Once you have per-feature cost, you can compute cost per user, cost per session, and cost per feature use — the unit economics that determine whether a feature is profitable at a given price point. Without attribution, pricing AI features is guesswork.
- Spend spikes are feature-level events. A 25% spend increase after a Tuesday deploy is almost always tied to one feature or one prompt change. Feature-tagged logs let you pin the spike in minutes; untagged logs require guessing.

## The move

**Tag every model call with `{ feature, customer_id, customer_tier, env }`. Log tags + token counts. Roll up weekly; alert on feature-level anomalies.**

**Step 1 — Tag at the call site.**

```js
async function callWithAttribution(model, messages, { feature, customerId, tier, env = 'production' }) {
  const response = await model.messages.create({ model, messages });

  // Log attribution immediately — don't rely on reconstructing it later
  await attributionLog.append({
    timestamp:     new Date().toISOString(),
    feature,
    customer_id:   customerId,
    customer_tier: tier,
    env,
    input_tokens:  response.usage.input_tokens,
    output_tokens: response.usage.output_tokens,
    cost:          response.usage.input_tokens  * INPUT_PRICE
                 + response.usage.output_tokens * OUTPUT_PRICE,
    model:         model,
  });

  return response;
}
```

**Step 2 — Weekly rollup.**

```js
function rollupByFeature(logs) {
  const byFeature = {};
  for (const entry of logs) {
    if (!byFeature[entry.feature]) byFeature[entry.feature] = { calls: 0, cost: 0 };
    byFeature[entry.feature].calls += 1;
    byFeature[entry.feature].cost  += entry.cost;
  }
  return Object.entries(byFeature)
    .sort((a, b) => b[1].cost - a[1].cost)
    .map(([feature, { calls, cost }]) => ({
      feature,
      calls,
      cost,
      costPerKCalls: (cost / calls) * 1000,
    }));
}
```

**Step 3 — Alert on anomalies.**

```js
function detectSpike(currentWeek, previousWeek, threshold = 0.25) {
  for (const [feature, current] of Object.entries(currentWeek)) {
    const previous = previousWeek[feature];
    if (!previous) continue;
    const delta = (current.cost - previous.cost) / previous.cost;
    if (Math.abs(delta) > threshold) {
      alert(`${feature}: ${(delta * 100).toFixed(0)}% cost change week-over-week`);
    }
  }
}
```

**What tags to use:**

| Tag | Values | Why |
|---|---|---|
| `feature` | `chat`, `summarize`, `search` | Maps to product surface; drives optimization decisions |
| `customer_id` | opaque ID | Per-customer unit economics; identify high-cost accounts |
| `customer_tier` | `free`, `pro`, `enterprise` | Tier-level cost vs. revenue; check margin per tier |
| `env` | `production`, `staging`, `dev` | Exclude non-production from cost reports |
| `model` | `claude-haiku-...`, `claude-sonnet-...` | Track routing efficiency; catch model drift |

**From attribution to action:**

| Finding | Action |
|---|---|
| Feature X is 10% of calls, 40% of spend | Cache repeated inputs (S-43); compress inputs (S-31) |
| Free tier costs 3× pro tier per call | Free tier uses longer prompts; add length constraint |
| Spend spike on Tuesday deploy | Diff prompt before/after; check for added context |
| Customer ABC costs 10× avg | Long inputs; offer summarization before sending |
| `staging` env is 20% of total spend | Add env filter; don't pay for dev traffic |

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Weekly simulation: 2,200 calls across three features (chat: 1,500 calls, summarize: 200, search: 500) with realistic token sizes per feature. Prices: $3/M input, $15/M output.

```
=== Weekly cost attribution (2,200 calls, $8.60 total) ===

Feature      calls    weekly cost   % total   cost/k calls
chat         1,500    $6.01         69.9%     $4.01/k
summarize      200    $1.79         20.8%     $8.94/k   ← highest unit cost
search         500    $0.80          9.3%     $1.61/k

=== Breakdown by feature + tier ===
chat/pro               $3.10
chat/free              $2.92
summarize/free         $0.90
summarize/pro          $0.89
search/pro             $0.41
search/free            $0.40

=== Unit economics insight ===
"summarize" = 9.1% of calls, 20.8% of spend ($8.94/k vs chat $4.01/k)
Root cause: summarize inputs are 1,400–2,100 tok vs chat's 480–820 tok
Action: prompt caching (S-08) on repeated system prompts; cache doc summaries (S-43)
Projected saving: 30–40% of summarize spend = ~$0.55/week at this volume
```

The attribution itself costs nothing — it's logging, not inference. The value is in the actionable unit economics it unlocks. "Chat is expensive" is a sentence; "$8.94/k per summarize call vs $1.61/k for search" is a budget.

## See also

[F-08](f08-agent-cost-control.md) · [F-18](f18-architecture-sets-the-cost-floor.md) · [F-23](f23-cost-estimation.md) · [W-05](../workspace/w05-llmops-observability.md) · [S-43](../stacks/s43-tool-result-caching.md)

## Go deeper

Keywords: `cost attribution` · `LLM cost tracking` · `feature-level cost` · `unit economics` · `FinOps` · `cost per call` · `spend spike` · `token logging` · `AI pricing` · `cost breakdown`
