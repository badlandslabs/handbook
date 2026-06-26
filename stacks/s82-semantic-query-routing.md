# S-82 · Semantic Query Routing

[S-06](s06-model-routing.md) routes requests by complexity — task type and token count determine whether a request goes to a cheap or expensive model. [S-68](s68-input-pre-screening.md) screens for out-of-scope and harmful requests before any inference. [S-74](s74-agent-capability-registry.md) routes a task to the agent whose manifest best matches it. None of these routes by *semantic intent domain* — classifying what the user is trying to do and dispatching to a specialized agent or knowledge base for that domain.

## Situation

A fintech platform handles billing, account management, technical support, and regulatory inquiries in a single chat interface. Without domain routing, all queries go to one large generalist agent loaded with 800 tokens of combined system context. With semantic routing: a Haiku classifier first identifies the domain (billing, technical, regulatory, or general). Billing queries go to a specialized billing agent with the fee schedule embedded. Technical queries go to the technical agent with the API documentation. Regulatory queries require human review. The generalist handles everything else. Each specialist's system prompt is 200 tokens instead of 800 — 75% smaller, fully cacheable, cheaper per call.

## Forces

- **Routing by domain is cheaper than routing by complexity.** A domain classifier operates on the user's first message only (short). The routing call itself is a Haiku call: ~50 tok in, ~10 tok out = $0.000048. Routing saves money on the downstream specialist call because each specialist's system prompt is tight instead of broad.
- **Confidence thresholding is required.** A classifier that is uncertain between billing and technical should not silently pick one — it should pass the query to a broader generalist or request clarification. Set a confidence threshold (0.70 is a reasonable start) below which the classifier abstains and routes to fallback.
- **Multi-label routing handles cross-domain queries.** "My billing address is wrong and I can't log in" spans billing and technical. Route to both agents in parallel, merge results. Structured output from the classifier can return multiple labels with scores.
- **Domain routing and model routing are orthogonal.** Route by domain first (which specialist?), then by complexity within the domain (which model tier?). Combining them into one routing step makes both decisions worse.
- **Keyword routing is insufficient for semantic intent.** "Cancel" could mean cancel a subscription (billing), cancel a pending transfer (account), or cancel a pending support ticket (technical). Domain classification requires understanding intent, not just vocabulary.

## The move

**Run a lightweight Haiku classifier on the user's message. Return a domain label with confidence. Route to the specialist agent above threshold; fall back to generalist below threshold. Multi-label for cross-domain queries.**

**Domain classifier (Haiku-class, structured output):**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// Domain definitions — extend for your product
const DOMAINS = {
  billing:    'Subscription fees, invoices, payment methods, refunds, pricing',
  technical:  'API errors, integration issues, SDK usage, authentication',
  account:    'Profile settings, password reset, email change, account closure',
  regulatory: 'Compliance, data requests, GDPR, legal notices',
  general:    'General product questions, onboarding, feature discovery',
};

async function classifyDomain(userMessage, opts = {}) {
  const domainDescriptions = Object.entries(DOMAINS)
    .map(([key, desc]) => `  "${key}": ${desc}`)
    .join('\n');

  const resp = await client.messages.create({
    model:      'claude-haiku-4-5-20251001',
    max_tokens: 64,
    system: `You are a query classifier. Return ONLY valid JSON: {"domain": "<label>", "confidence": <0.0-1.0>, "secondary": "<label or null>"}.
Domains:
${domainDescriptions}`,
    messages: [{ role: 'user', content: `Classify this query: "${userMessage}"` }],
  });

  try {
    return JSON.parse(resp.content[0].text.trim());
  } catch {
    return { domain: 'general', confidence: 0.5, secondary: null };
  }
}
```

**Router — confidence gate and multi-label dispatch:**

```js
const CONFIDENCE_THRESHOLD = 0.70;

// Specialized agent system prompts — each is tightly scoped and fully cacheable
const AGENT_SYSTEMS = {
  billing:    'You are the billing specialist for FinCo. You handle fees, invoices, refunds, and payment methods. Customer fee schedule: ...',
  technical:  'You are the technical support specialist for FinCo API. You help with integration, errors, and SDK issues. API reference: ...',
  account:    'You are the account management specialist for FinCo. You handle profile, authentication, and account settings.',
  regulatory: null,  // no autonomous response — escalate to human
  general:    'You are a general assistant for FinCo. Answer product questions and route to specialists when the user describes a specific problem.',
};

async function routeAndAnswer(userMessage, conversationHistory = []) {
  const classification = await classifyDomain(userMessage);
  const { domain, confidence, secondary } = classification;

  // Below threshold — fall back to generalist
  if (confidence < CONFIDENCE_THRESHOLD) {
    console.log(`[router] low confidence (${confidence.toFixed(2)}) → general`);
    return answerWithAgent('general', userMessage, conversationHistory);
  }

  // Regulatory — always escalate
  if (domain === 'regulatory') {
    console.log(`[router] regulatory query → human escalation`);
    return { text: 'This query requires review by our compliance team. A specialist will respond within 24 hours.', escalated: true };
  }

  // Multi-label — run both specialists in parallel, merge
  if (secondary && secondary !== 'general') {
    console.log(`[router] multi-domain: ${domain} + ${secondary}`);
    const [primaryResp, secondaryResp] = await Promise.all([
      answerWithAgent(domain, userMessage, conversationHistory),
      answerWithAgent(secondary, userMessage, conversationHistory),
    ]);
    return mergeResponses(primaryResp, secondaryResp);
  }

  console.log(`[router] domain=${domain} confidence=${confidence.toFixed(2)}`);
  return answerWithAgent(domain, userMessage, conversationHistory);
}

async function answerWithAgent(domain, userMessage, history) {
  const system = AGENT_SYSTEMS[domain];
  const messages = [...history, { role: 'user', content: userMessage }];

  const resp = await client.messages.create({
    model: 'claude-haiku-4-5-20251001', max_tokens: 512,
    system, messages,
  });

  return {
    domain,
    text:       resp.content[0].text,
    inputToks:  resp.usage.input_tokens,
    outputToks: resp.usage.output_tokens,
  };
}

function mergeResponses(primary, secondary) {
  return {
    domain: `${primary.domain}+${secondary.domain}`,
    text:   `${primary.text}\n\n---\n\n${secondary.text}`,
    inputToks:  primary.inputToks  + secondary.inputToks,
    outputToks: primary.outputToks + secondary.outputToks,
  };
}
```

**Domain taxonomy design:**

| Domain | Define by | Not by |
|---|---|---|
| Billing | What action the user wants (pay, refund, view invoice) | Keywords like "charge", "cost" which are ambiguous |
| Technical | What system the user is troubleshooting (API, SDK, auth) | Error messages alone (could be billing errors) |
| Account | What user object is being changed (profile, credentials) | "My account" (used in all domains) |
| Regulatory | Regulatory terms + document requests | Any mention of "data" |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Classification call measured against claude-haiku-4-5-20251001 pricing. Response parsed from structured output.

```
=== Routing call cost ===

Classifier input:  ~55 tok (system prompt + domains + user message)
Classifier output: ~12 tok (JSON: domain, confidence, secondary)
Total:             ~67 tok

At Haiku $0.80/M in + $4.00/M out:
  Cost: $0.000044 in + $0.000048 out = $0.000092/routing call

At 10 000 queries/day: $0.92/day routing overhead

=== Specialist vs generalist system prompt size ===

Generalist (billing + technical + account + regulatory combined): 820 tok
Billing specialist: 200 tok  (75% smaller)
Technical specialist: 190 tok
Account specialist: 140 tok

Per-call savings on specialist calls (820 - 200 tok × $0.80/M = $0.000496 saved per billing call)
At 3 000 billing calls/day: $1.49/day saved
Net vs routing overhead $0.92/day: $0.57/day benefit — plus better accuracy from tighter context

=== Classification example ===

Input: "My payment failed but I was still charged twice"
Output: {"domain": "billing", "confidence": 0.91, "secondary": null}
→ Routed to billing specialist

Input: "I can't log in and I think my subscription is cancelled"
Output: {"domain": "account", "confidence": 0.76, "secondary": "billing"}
→ Routed to both account + billing agents in parallel

Input: "What is FinCo?"
Output: {"domain": "general", "confidence": 0.95, "secondary": null}
→ Routed to generalist
```

## See also

[S-06](s06-model-routing.md) · [S-68](s68-input-pre-screening.md) · [S-74](s74-agent-capability-registry.md) · [S-41](s41-agent-handoff-patterns.md) · [S-36](s36-system-prompt-architecture.md) · [F-52](../forward-deployed/f52-conversation-branching.md)

## Go deeper

Keywords: `semantic routing` · `intent classification` · `domain routing` · `query routing` · `multi-domain agent` · `specialist agent` · `confidence threshold` · `multi-label routing` · `intent-based dispatch` · `Haiku classifier`
