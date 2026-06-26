# S-11 · LLM Gateway and Fallback Architecture

Your LLM call will fail. The question is whether your system fails with it.

## Forces
- Provider outages are routine: gateway telemetry (Portkey) observed 114 Anthropic incidents in 90 days in early 2026, 30 of them major
- HTTP errors are only one failure mode — 200 OK with truncated JSON, empty content, or off-topic output is also failure
- Naive fallback (Sonnet → GPT-4o) can cost *more* during outages than normal operation if the fallback is a pricier model
- Three failure types need different chains: network/5xx errors, content-policy rejections (Claude HTTP 529 "Overloaded"), and context-window overflows

## The move

**Three distinct fallback chains — not one:**

| Failure type | Signal | Chain |
|---|---|---|
| Network / 5xx | Timeout, 500, 502, 503 | Primary → cheaper same-provider → different provider → local |
| Overloaded | Claude 529, 11.7% rate in Sep 2025 | Retry with backoff → Haiku → local |
| Context overflow | `context_window_exceeded` error | Summarize → re-send, or route to larger-window model |

Correct cascade order: expensive primary → cheaper same-provider → different provider → local model. Jumping straight to a different provider skips the cheap same-provider tier and erases your cost savings.

**Quality circuit breaker — trip on semantics, not just HTTP status:**
```python
# Illustrative — not run
def is_degraded(response) -> bool:
    if not response.content:
        return True
    text = response.content[0].text
    if len(text) < 10:                     # empty or near-empty
        return True
    if text.strip().endswith(("{", "[")):  # truncated JSON
        return True
    return False
```
Wire this check after every call. If `is_degraded` fires, treat it as a failure and step down the fallback chain.

**LiteLLM Router config (self-hosted YAML, illustrative):**
```yaml
# Illustrative — not run
model_list:
  - model_name: primary
    litellm_params:
      model: anthropic/claude-sonnet-4-6
  - model_name: fallback-cheap
    litellm_params:
      model: anthropic/claude-haiku-4-5

router_settings:
  fallbacks: [{"primary": ["fallback-cheap"]}]
  context_window_fallbacks: [{"primary": ["fallback-cheap"]}]
  num_retries: 2
  retry_after: 5
```
`context_window_fallbacks` is a distinct key — it routes overflow errors separately from general failures.

**Managed gateway alternative — Portkey:**
- Handles 10B+ requests/month; per-request observability baked in
- Proactive degradation detection (catches silent 200 OK failures)
- Drop-in: change `base_url`, add `x-portkey-api-key` header

## Receipt
> Verified 2026-06-25. Incident count (114 in 90 days, 30 major) and Claude 529 error rate (11.7%, Sep 2025) from Portkey blog, sourced from their gateway telemetry. LiteLLM `context_window_fallbacks` key verified against LiteLLM Router docs. Portkey request volume from portkey.ai. Code blocks above are illustrative and have not been run.

## See also
[S-06](s06-model-routing.md) · [F-24](../forward-deployed/f24-graceful-degradation.md) · [F-03](../forward-deployed/f03-failure-modes.md) · [W-04](../workspace/w04-observability.md)

## Go deeper
Keywords: `LiteLLM Router` · `Portkey` · `circuit breaker` · `LLM fallback` · `Claude 529` · `context window fallback`
