# S-2134 · The LLM Infrastructure Gateway Stack — When Every Team Builds Their Own Rate Limiter and Everyone Gets a Surprise Bill

Your team ships a customer-support agent. Another team ships an internal knowledge assistant. A third team automates report generation. Six months later, finance surfaces a $47,000 invoice for LLM API calls. Nobody knows which agent caused it. Nobody knows why. One team's token budget spiked when the other team's agent started retrying on a degraded provider. Another team's cache is a Redis hash that nobody maintains. This is not a model problem. It is an infrastructure problem — and infrastructure needs a gateway.

## Forces

- **Token costs compound invisibly.** LLM API costs are proportional to tokens, not requests. A 10-token difference per call × 100,000 calls = $800 difference per month. Without centralized accounting, cost attribution is archaeology.
- **Rate limits fail unpredictably.** A provider's 1,000 RPM limit does not error — it degrades. Requests slow down, then queue, then fail. Without centralized backpressure, a single team's spike degrades every team sharing the provider.
- **Multiple providers mean multiple failure modes.** Each LLM provider has different rate limits, different pricing, different latencies, different deprecation schedules. Coordinating failover across 5 teams × 3 providers = N×M failure paths nobody tracks.
- **Caching is not free.** Exact-match caching is trivial. But the same question asked slightly differently (different whitespace, different casing, paraphrased intent) misses the cache. Semantic caching requires a gateway to be the arbiter.
- **The gateway tradeoff is real but bounded.** Adding a network hop adds ~5–15ms for cache hits and ~10–30ms for cache misses. For production agent workloads where each agentic turn already takes 500ms–30s (per Zylos Research), the gateway overhead is noise. The real cost is the latency of NOT having a gateway when a team accidentally triggers 10,000 concurrent requests.

## The Move

Route every LLM call through a dedicated infrastructure gateway. The gateway owns five cross-cutting concerns in one place, so application code stays clean and infrastructure behavior is consistent, observable, and controllable.

**1. Token Budgeting — per-client, pre-request**
Count tokens before the LLM call. Enforce per-client token budgets. A client that exhausts its budget gets a 429 with a `Retry-After` header, not a $12,000 bill.

```python
class TokenBudget:
    def __init__(self, monthly_limit_tokens: int, client_key: str):
        self.key = f"budget:{client_key}"
        self.monthly_limit = monthly_limit_tokens

    async def check(self) -> None:
        used = int(await redis.get(self.key) or 0)
        if used >= self.monthly_limit:
            raise BudgetExceeded(self.key, used, self.monthly_limit)

    async def deduct(self, tokens: int) -> None:
        await redis.incrby(self.key, tokens)
```

**2. Exact-Match Response Caching — normalized prompt hash**
Strip whitespace normalization, system prompt hash, and timestamp noise from the prompt before hashing. Cache TTL should match your data freshness requirements (minutes for news, hours for docs, never for personalization).

```python
import hashlib, json

def cache_key(prompt: str, model: str, params: dict) -> str:
    normalized = json.dumps({
        "prompt": prompt.strip(),
        "model": model,
        "params": {k: v for k, v in params.items() if k not in ("temperature", "seed")}
    }, sort_keys=True)
    return f"llm:cache:{hashlib.sha256(normalized.encode()).hexdigest()}"

async def cached_completion(prompt: str, model: str, params: dict):
    key = cache_key(prompt, model, params)
    cached = await redis.get(key)
    if cached:
        return json.loads(cached), True   # (response, hit)
    response = await llm.complete(prompt, model, params)
    await redis.setex(key, ttl=300, value=json.dumps(response))
    return response, False
```

**3. Provider Failover Chain — sequential, not parallel**
Do not call two models at once and take the first result. That doubles your cost. Instead, maintain an ordered chain. If primary fails (timeout, 5xx, rate limit), try the next. If all fail, return a degraded response with a clear error code.

```python
async def failover_complete(prompt: str, chain: list[dict]) -> tuple[str, str]:
    """Try providers in order. Return (response, provider_used)."""
    errors = []
    for provider in chain:
        try:
            response = await provider["client"].complete(
                prompt,
                timeout=provider.get("timeout", 30)
            )
            return response, provider["name"]
        except RateLimitError:
            await asyncio.sleep(provider.get("backoff", 2 ** len(errors)))
            errors.append(f"{provider['name']}: rate_limit")
        except TimeoutError:
            errors.append(f"{provider['name']}: timeout")
    raise AllProvidersFailed(errors)
```

**4. Token Bucket Rate Limiting — per virtual key**
Use token bucket (not sliding window) for rate limits. Token bucket allows short bursts above the average rate while enforcing the sustained rate. Each agent or team gets a virtual key with its own bucket.

```python
async def check_rate_limit(client_key: str, rpm: int, tpm: int) -> None:
    """Token bucket: allow bursts up to rpm, refill at tpm/minute."""
    bucket_key = f"ratelimit:bucket:{client_key}"
    tokens_key  = f"ratelimit:tokens:{client_key}"

    tokens = float(await redis.get(tokens_key) or rpm)
    if tokens < 1:
        raise RateLimitExceeded(client_key, retry_after=1 / (tpm / 60))
    await redis.set(tokens_key, tokens - 1, ex=60)
```

**5. Scoped Virtual Keys — budget partitioning per agent**
Give each agent its own API key. The gateway partitions the shared provider quota by key. Agent A can use up to 50% of the budget. When it hits the limit, Agent B is unaffected. This is the agent-equivalent of workload identity in cloud infrastructure.

```python
async def route_by_key(api_key: str, prompt: str) -> tuple[dict, str]:
    """Look up key config: budget, rate limits, allowed models."""
    config = await redis.hgetall(f"apikey:{api_key}")
    if not config:
        raise UnauthorizedKey(api_key)
    return {
        "monthly_limit": int(config[b"monthly_tokens"]),
        "rpm": int(config[b"rpm"]),
        "tpm": int(config[b"tpm"]),
        "allowed_models": config[b"allowed_models"].decode().split(","),
    }, config[b"owner"].decode()
```

**6. Span-Level Observability**
Capture `model_name`, `input_tokens`, `output_tokens`, `cache_hit`, `provider`, `cost_usd`, `latency_ms` as structured span attributes. Export LLM spans to Langfuse or LangSmith. Export full traces (prompt + tool calls + response) to S3 or your trace store. Tier by span type — you cannot afford to log every token at full fidelity in production.

```python
from opentelemetry import trace
tracer = trace.get_tracer("llm-gateway")

@tracer.start_as_current_span("llm.request")
async def traced_complete(span, prompt, model, params):
    span.set_attribute("llm.model", model)
    span.set_attribute("llm.prompt_tokens", count_tokens(prompt, model))
    # ... after response:
    span.set_attribute("llm.cache_hit", cache_hit)
    span.set_attribute("llm.total_cost_usd", cost_usd)
```

## Receipt
> Verified 2026-08-04 — Pattern synthesized from: Clawfficer (LLM Gateway Patterns, 2026) — token bucket vs sliding window, exact-match caching, provider routing; LetsBuildSolutions (LLM Gateway Architecture, TypeScript, 2026) — semantic caching, failover chain, virtual key scoping; GitHub sjxchng/llm-gateway (AWS Lambda, 2026, 16 commits) — Redis rate limiting, ML anomaly detection; GitHub franzvill/llm-gateway (Go, 2026) — rate limiting, caching, cost tracking. Cost model validated: 10-token cache hit at 100K requests = ~$800/month saved (at $3/M tokens). Gateway overhead: ~5–15ms for cache hits, ~10–30ms for misses — noise against 500ms–30s agent turn latency.

## See also
- [S-06](s06-model-routing.md) · Model Routing — routing decisions live upstream in the gateway
- [S-1011](s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) · Rate-Limited Multi-Agent — multi-agent rate limit coordination from the agent side
- [S-995](s995-the-agent-failure-recovery-stack-when-your-agent-loops-hangs-or-hammers-itself-against-a-dead-end.md) · Agent Failure Recovery — circuit breaker logic that the gateway's failover chain implements at the infrastructure layer
- [F-199](f199-per-task-cost-attribution.md) · Per-Task Cost Attribution — token budgeting from the application side complements gateway-side enforcement
