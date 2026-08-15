# [S-2682] · The LLM Gateway Failure Atlas

When your LLM proxy returns HTTP 200, passes every health check, and your dashboards look green — but downstream application state is silently corrupted and you won't find out until users complain.

## Situation

You're running LiteLLM, Portkey, or a custom gateway to route across Claude, GPT-5, Gemini, DeepSeek, and Kimi. You have latency dashboards, error rate alerts, and provider health checks. Everything looks fine. Then you notice: some users got duplicate responses, others got truncated completions that your app treated as valid, and your cost dashboard is 40% over budget because retries and token limits are being hit silently. The proxy is healthy. The providers are up. The failure is in the layer between them, and none of your standard monitors caught it.

## Forces

- Multi-provider LLM gateways are now critical production infrastructure — 100+ providers routed through a single proxy — yet their failure modes remain undocumented and independently rediscovered per team
- Standard monitoring (latency percentiles, error rates, uptime SLAs) is structurally blind to the most operationally severe failures: silent corruptions that return HTTP 200
- The gap between a healthy-looking gateway and a silently failing one can persist for hours or days before application-level symptoms surface
- Multi-provider routing introduces cross-layer failures no single-provider SDK ever had to handle
- LiteLLM alone has 97M monthly PyPI downloads and stores all provider credentials in one PostgreSQL database — a single SQL injection in the API key verification path gives an attacker all of them

## The move

**Use FailureAtlas: a two-axis taxonomy (5 layers × detectability) for LLM gateway failures.**

### Axis 1 — Failure Origin Layer

| Layer | What fails | Silent? | Loud? |
|-------|-----------|---------|-------|
| **L1: Network/Transport** | TCP timeouts, TLS handshake stalls, DNS resolution, async-Python event-loop blocking | Partial disconnects, provider-request-replication causing duplicate submissions | Connection refused, TLS cert errors |
| **L2: Streaming/Protocol** | SSE chunk transport, inter-chunk state tracking, `finish_reason` timing | Truncated tokens dropped mid-stream with no error; `finish_reason=length` vs. actual truncation indistinguishable at transport layer | Chunk checksum failures, SSE parse errors |
| **L3: State/Session** | In-flight request state, conversation context continuity, session affinity | Provider switches mid-conversation — same session routed to different provider loses context; agentic loops re-trigger because state was silently reset | Session store connection errors, context overflow errors |
| **L4: Model Behavior** | Provider-specific output format, `finish_reason` semantics, token counting | Silent response format drift: Kimi K2.6 double-wraps JSON in `json` fences; Gemini 3.1 Pro appends trailing commas `,}`; DeepSeek omits keys that Claude includes. Application parses succeed but data is malformed | Provider rate limits, content policy violations |
| **L5: Governance/Cost** | Token budgets, spend limits, rate limit enforcement, context window overflows | Context window silently truncated at LLM level (not HTTP level) — request returns 200 with partial completion, app treats as complete | Quota exceeded errors, rate limit 429s |

### Axis 2 — Detectability

**Loud failures** → surface immediately via HTTP errors, exceptions, or non-200 status codes. Standard monitoring catches these.

**Silent failures** → return HTTP 200, pass every health check, and corrupt application state semantically. These are the danger.

Five verified silent catalog entries from FailureAtlas (arXiv:2607.17525v1):

1. **Asyncio Event Loop Block** (L1, Silent) — I/O-bound proxy in async Python blocks the event loop; requests queue silently, latency grows from 50ms to 50s without any error
2. **Truncated Completion Accepted as Valid** (L2, Silent) — Provider hits `finish_reason=length` or silently drops stream; application receives partial response and treats it as complete
3. **Provider Switch Breaks Session Continuity** (L3, Silent) — Load balancer routes session to a different provider mid-conversation; context is lost, agent re-triggers loops, no error surfaced
4. **Format Drift Across Providers** (L4, Silent) — Kimi's double-fence JSON, Gemini's trailing commas, and DeepSeek's missing optional keys all parse as valid JSON but break application logic downstream
5. **Context Window Overflow Handled at LLM Layer** (L5, Silent) — Context truncated inside the provider's inference engine; proxy sees HTTP 200, application sees a complete response that is actually truncated

### Detection strategy

```python
# Semantic-level observability — not just latency/error rate
from opentelemetry import trace

tracer = trace.get_tracer("llm-gateway")

@tracer.start_as_current_span("llm.call")
def call_llm(provider, model, messages):
    span = trace.get_current_span()
    span.set_attribute("provider", provider)
    span.set_attribute("model", model)
    span.set_attribute("msg_count", len(messages))

    response = proxy.chat.completions.create(
        model=f"{provider}/{model}",
        messages=messages,
        stream=True
    )

    full_content = ""
    finish_reason = None
    for chunk in response:
        full_content += chunk.choices[0].delta.content or ""
        if chunk.choices[0].finish_reason:
            finish_reason = chunk.choices[0].finish_reason

    # L2/L4/L5 Silent failure detection
    span.set_attribute("finish_reason", str(finish_reason))
    span.set_attribute("content_length", len(full_content))
    span.set_attribute("content_length_tokens", estimate_tokens(full_content))

    # Flag silent failures
    if finish_reason == "length":
        span.set_attribute("silent_failure", True)
        span.add_event("context_truncated_at_provider_layer")
    if is_incomplete_json(full_content):
        span.set_attribute("silent_failure", True)
        span.add_event("malformed_response_format_detected")

    return full_content
```

### CVE overlay: LiteLLM SQL Injection

CVE-2026-42208 (CVSS 9.3, LiteLLM v1.81.16–v1.83.6) — pre-auth SQL injection in the API key verification path. Exploited within 36 hours of disclosure. LiteLLM stores all provider credentials in a single PostgreSQL database; the injection lets an attacker:
- Enumerate production schema objects
- Exfiltrate virtual API keys and stored provider credentials
- Mint new keys via `/key/generate`

**Fix:** Upgrade to `v1.83.10-stable`. If upgrade is not immediately possible, restrict network access to the LiteLLM proxy management port and audit `/key/*` endpoint access logs for anomalies.

## Receipt

> Verified 2026-08-15 — Source: arXiv:2607.17525v1 (Pandey & Singh, Metriqual, July 2026) + CSA research note on CVE-2026-42208 (April 2026) + FailureAtlas GitHub (metriqual/failure-atlas) + Dev.to xidao multi-provider routing analysis (May 2026). The 5-layer taxonomy and loud/silent detectability axis were extracted verbatim from FailureAtlas abstract and confirmed against Q2BSTUDIO.com summary. LiteLLM CVE details confirmed against OpenCVE, NVD, CSA, and LiteLLM official advisory. Provider format drift (Kimi, Gemini, DeepSeek) confirmed from xidao analysis.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — dispatch logic before the failure surface
- [S-2681 · Agent Orchestration Stack](s2681-the-agent-orchestration-stack-when-one-agent-is-not-enough-and-ten-are-too-many.md) — cross-agent state failures build on L3 State/Session layer
- [S-1062 · MCP Supply Chain Integrity](s1062-the-mcp-supply-chain-integrity-stack-when-your-model-context-protocol-becomes-your-attack-surface.md) — CVE/security overlay for agent infrastructure
