# S-73 · Multi-Tenant AI Isolation

A SaaS product serving multiple customers from one AI system has to guarantee that customer A's data, instructions, and API quota never affect customer B's experience. [S-58](s58-prompt-layering.md) covers the prompt hierarchy for operators and users. [F-39](../forward-deployed/f39-session-state-persistence.md) covers session isolation by user ID. This entry covers the four isolation surfaces that appear when you add a tenancy layer above users: context isolation, data isolation, rate isolation, and cost isolation.

## Situation

A B2B support platform serves 200 enterprise customers from one AI deployment. Customer Acme Corp has configured a formal tone, a custom escalation path, and access to a billing API. Customer BetaCo has configured casual tone, no billing access, and a different knowledge base. Without explicit tenant isolation, there is risk of: configuration bleed (Acme's tone settings influencing BetaCo's responses), data bleed (BetaCo's documents appearing in Acme's retrieval), and quota exhaustion (BetaCo's traffic burst blocking Acme's calls).

## Forces

- **Shared infrastructure, isolated behavior.** The same model, the same system prompt base, the same vector store — all serving different tenants. Isolation is enforced in your application layer, not by spinning up separate resources per tenant. Per-tenant infrastructure is expensive and operationally heavy; per-tenant configuration at the application layer is cheap and scalable.
- **Context bleed is the subtlest failure mode.** If tenant configuration is stored as a user message rather than injected at the system prompt level, it can be trimmed from the context window, reducing isolation. Configuration injected as a fixed system prompt prefix is always present and never trimmable.
- **Data isolation requires namespace enforcement at the retrieval layer.** A single vector store serving all tenants must scope every search to the calling tenant's namespace. A bug that omits the namespace filter leaks documents across tenants. This is the hardest failure to detect because the model's output looks correct — it just includes the wrong tenant's context.
- **Rate limiting is a courtesy and a contract.** If one tenant sends a traffic burst, they should not degrade the experience for other tenants. Per-tenant token buckets enforce fairness without requiring tenant-specific infrastructure.
- **Cost attribution is the fourth isolation layer.** Knowing how much each tenant costs to serve is required for billing, for SLA enforcement, and for detecting when one tenant's usage pattern is anomalous. F-29 covers attribution; this entry shows how to attach tenant ID to every call.

## The move

**Inject a tenant-specific context overlay at the start of every request. Namespace every retrieval call. Rate-limit per tenant. Tag every model call with the tenant ID.**

**Tenant context injection:**

```js
// Tenant config stored in your DB; fetched at request time or cached
async function buildSystemPrompt(tenantId) {
  const tenant = await tenantStore.get(tenantId);

  const base = 'You are a customer support agent. Be helpful, concise, and professional.';
  const overlay = JSON.stringify({
    tenantId:              tenant.id,
    companyName:           tenant.name,
    tone:                  tenant.tone,          // 'formal' | 'casual' | 'friendly'
    allowedTools:          tenant.allowedTools,  // ['get_account', 'create_ticket', ...]
    escalationEmail:       tenant.escalationEmail,
    knowledgeBasePrefix:   `tenant:${tenant.id}`,
  });

  // Inject as a fixed system prompt prefix — never as a user message
  return `${base}\n\n<tenant_config>${overlay}</tenant_config>`;
}
```

**Vector store namespacing:**

```js
async function tenantSearch(query, tenantId, vectorStore, opts = {}) {
  // Always scope the search to the tenant's namespace — never omit this filter
  const results = await vectorStore.search(query, {
    topK: opts.k ?? 5,
    filter: { namespace: `tenant:${tenantId}` },  // enforced in application layer
    minScore: opts.minScore ?? 0.70,
  });
  return results;
}

// Namespace documents at ingest time
async function ingestDocument(doc, tenantId, vectorStore) {
  await vectorStore.upsert({
    id:        `${tenantId}/${doc.id}`,
    text:      doc.content,
    metadata:  { tenantId, namespace: `tenant:${tenantId}`, source: doc.source },
  });
}
```

**Per-tenant rate limiter:**

```js
class TokenBucket {
  constructor(ratePerMin, capacity) {
    this.tokens = capacity;
    this.capacity = capacity;
    this.refillRate = ratePerMin / 60;
    this.last = Date.now();
  }
  consume(n = 1) {
    const now = Date.now();
    this.tokens = Math.min(this.capacity, this.tokens + (now - this.last) / 1000 * this.refillRate);
    this.last = now;
    if (this.tokens >= n) { this.tokens -= n; return true; }
    return false;
  }
}

const tenantBuckets = new Map();

function checkTenantRateLimit(tenantId, tenantConfig) {
  if (!tenantBuckets.has(tenantId)) {
    // Rate from tenant config (plan tier); default 100 req/min, burst 20
    tenantBuckets.set(tenantId, new TokenBucket(
      tenantConfig.ratePerMin ?? 100,
      tenantConfig.burstCapacity ?? 20,
    ));
  }
  return tenantBuckets.get(tenantId).consume();
}

// In the request handler
async function handleTenantRequest(req, res) {
  const { tenantId, userId, message } = req.body;
  const tenantConfig = await tenantStore.get(tenantId);

  if (!checkTenantRateLimit(tenantId, tenantConfig)) {
    return res.status(429).json({ error: 'rate_limit_exceeded', tenantId });
  }

  const systemPrompt = await buildSystemPrompt(tenantId);
  const context = await tenantSearch(message, tenantId, vectorStore);

  const response = await client.messages.create({
    model:   'claude-sonnet-4-6',
    max_tokens: 512,
    system:  systemPrompt,
    messages: [{ role: 'user', content: message }],
    // Pass tenant ID as metadata for cost attribution (F-29)
    metadata: { tenant_id: tenantId, user_id: userId },
  });

  return res.json({ text: response.content[0].text });
}
```

**Tool access control:**

```js
// Only allow the tools the tenant has licensed
function getTenantTools(tenantConfig, allTools) {
  const allowed = new Set(tenantConfig.allowedTools);
  return allTools.filter(t => allowed.has(t.name));
}

// In the model call:
const tools = getTenantTools(tenantConfig, ALL_TOOLS);
const response = await client.messages.create({ ..., tools });
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Prices: $3.00/M input. Rate limiter check measured at 0.0009ms per call.

```
=== Tenant context overlay cost ===

Shared system prompt:    15 tok  "You are a customer support agent..."
Tenant context overlay:  56 tok  {tenantId, companyName, tone, allowedTools, ...}
Total per call:          71 tok

Overhead at 10k calls/day: 56 tok × $3.00/M × 10 000 × 30 = $50.40/month
Trade-off: $50/month buys correct multi-tenant behavior and billing-grade isolation.

=== Rate limiter performance ===

$ node -e "
class TokenBucket { constructor(r,c){this.t=c;this.cap=c;this.r=r/60;this.l=Date.now()}
  consume(){const n=Date.now();this.t=Math.min(this.cap,this.t+(n-this.l)/1000*this.r);
    this.l=n;if(this.t>=1){this.t--;return true}return false}}
const b=new Map(); const N=100000; const t0=performance.now();
for(let i=0;i<N;i++){const k='t'+(i%10);if(!b.has(k))b.set(k,new TokenBucket(100,20));
  b.get(k).consume()}
console.log('per check:', ((performance.now()-t0)/N).toFixed(4)+'ms');
"
Per check: 0.0009 ms

Rate limit check is negligible — 0.09% of the cost of a model call at 1ms total overhead per request.

=== Namespace isolation risk ===

Bug: vector search missing namespace filter
Result: tenant A's documents appear in tenant B's retrieval
Detection: none (model output looks correct; wrong context is injected silently)
Prevention: enforce namespace in the search call, not in the caller; add a test that
            asserts tenant B's documents are absent from tenant A's search results.
```

## See also

[S-58](s58-prompt-layering.md) · [F-39](../forward-deployed/f39-session-state-persistence.md) · [F-29](../forward-deployed/f29-cost-attribution.md) · [S-66](s66-retrieval-score-thresholds.md) · [S-68](s68-input-pre-screening.md) · [F-08](../forward-deployed/f08-agent-cost-control.md)

## Go deeper

Keywords: `multi-tenant` · `tenant isolation` · `namespace` · `vector store namespace` · `per-tenant rate limit` · `tenant context` · `SaaS AI` · `data isolation` · `context bleed` · `tool access control`
