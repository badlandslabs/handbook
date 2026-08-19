# S-2856 · The Tool-Call Failure Layer Stack — When Your Agent Thinks It Worked But the Tool Lied

Your agent completed the task. HTTP 200. No exceptions. Fourteen minutes later a user reports the ticket was never created, the search returned nothing, and the refund went to the wrong person. The tool called correctly, executed correctly, and returned a response that looked right — but the outcome never happened. This is the tool-call failure layer problem: the gap between "the tool fired" and "the tool worked."

Production telemetry across Scalekit (2025–2026, n=2.3M tool calls) shows 1 in 20 AI tool invocations fail in production. Of those failures, the majority are silent — no exception, no error code, no log line that triggers an alert. The agent continues, incorporating a false result into its reasoning. The model compensates confidently. You find out from a user.

## Forces

- **Tool failures live below the error boundary.** Traditional exception handling catches crashes and non-zero exit codes. Most tool failures return HTTP 200 with semantically wrong data. Your try/catch fires for the wrong thing.
- **The same HTTP code means different things at different layers.** HTTP 401 from an expired access token vs. HTTP 401 from a revoked refresh token produce identical responses but require opposite recovery actions. Treating them the same generates retry storms.
- **Partial execution returns HTTP 200.** The tool accepted the request, processed part of it, and either errored mid-way or never committed. The call succeeded; the outcome failed. This is the hardest failure class to detect because nothing in the protocol says "I accepted but didn't finish."
- **Auth failures are the largest single failure category** (29% of all tool-call failures per Scalekit), yet teams rarely treat the auth layer as a monitored, recoverable component of their tool-calling infrastructure.

## The move

Tool-call failures cluster into four independent layers. Each requires different detection logic and recovery strategies.

### Layer 1 — Identity/Auth
The tool credentials are wrong, expired, or revoked. The call never reaches the upstream service.

Detection:
- Categorize HTTP 401 by token type: access token (short-lived, retry with refresh), refresh token (revocation = structural failure, alert human)
- Monitor token age: if the access token is >50% through its TTL, refresh proactively before the next call rather than on 401
- Track revocation events: an auth event pipeline (webhook or polling from your IdP) lets you invalidate sessions before the next tool call fires

Recovery:
- Access token expiry → refresh + retry once
- Refresh token revoked → halt the task, surface to user, do not retry
- Service account key rotation → refresh cached credentials, re-queue

```python
def call_tool_with_auth(tool_fn, *args, **kwargs):
    # Proactive token refresh: if access token is >50% through TTL, refresh first
    if access_token_age() > TOKEN_TTL * 0.5:
        credentials = refresh_credentials()
        tool_fn = partial(tool_fn, credentials=credentials)

    try:
        return tool_fn(*args, **kwargs)
    except AuthError as e:
        if e.token_type == "access" and not e.is_revoked:
            # Short-lived expiry: refresh and retry once
            credentials = refresh_credentials()
            return tool_fn(*args, **kwargs, credentials=credentials)
        else:
            # Refresh token revoked or structural failure: halt
            raise AgentHaltError(f"Auth unrecoverable: {e}") from e
```

### Layer 2 — Connector/Proxy
The path between your agent and the upstream API is broken, rate-limited, or returning unexpected responses. The call reached the proxy but didn't reach the service.

Detection:
- HTTP 429 → back off, track rate limit headers (Retry-After, X-RateLimit-Reset)
- HTTP 5xx from the connector → circuit breaker; after N failures in a window, stop routing to that endpoint
- Response schema mismatch (tool says it returns `{"id": str}` but gets `{"id": int}`) → schema fingerprinting in integration tests

Recovery:
- 429 → exponential backoff with jitter up to the Retry-After value
- Connector 5xx → circuit breaker trips after 3 failures in 30s; fallback to replica endpoint if available
- Schema mismatch → log the drift, surface to ops, do not retry blindly

### Layer 3 — Upstream API
The upstream service itself is down, returning errors, or experiencing degraded performance. Your connector and auth are fine.

Detection:
- HTTP 503 / 504 → upstream timeout or overload
- Upstream SLA monitoring via synthetic probes or health endpoints
- Response latency spikes: if p99 latency exceeds 3x your baseline, flag the tool as degraded

Recovery:
- 503/504 → retry with backoff; if still failing after 3 attempts, surface to agent with degraded status
- Tell the agent explicitly: `tool_result = {"status": "degraded", "tool": "search_api", "message": "upstream timeout after 3 retries"}`
- Let the agent decide whether to use a degraded tool or wait

### Layer 4 — Execution Semantics
The tool fired, returned HTTP 200, but the action didn't happen the way the agent expected. The tool's description didn't match its behavior.

Detection:
- **Outcome verification**: for write operations, query the affected resource after the tool returns to confirm the change occurred
- **Empty/null responses with no error**: if a tool returns `[]` or `null` where it previously returned results, surface this as a potential failure even on HTTP 200
- **Idempotency key tracking**: if the tool supports idempotency keys, store the returned key and verify the operation completed under that key

Recovery:
- Outcome not confirmed → retry the specific operation with the same idempotency key
- Empty response on write tool → query the resource; if the write didn't land, retry
- Semantic mismatch (tool said it would return `data[]` but returned `{"status": "queued"}`) → parse the actual response schema, surface a structured error to the agent

```python
def verify_tool_outcome(tool_result, tool_name, verification_fn):
    """For write tools: verify the outcome actually occurred."""
    if not verification_fn(tool_result):
        # Outcome didn't confirm — retry once with same idempotency key
        tool_result = retry_with_idempotency(tool_result.idempotency_key)
        if not verification_fn(tool_result):
            raise ToolSemanticFailure(
                f"Tool '{tool_name}' returned success but outcome "
                f"could not be verified after retry. "
                f"Last response: {tool_result}"
            )
    return tool_result
```

### The unified pattern

Layer 1 (auth) and Layer 2 (connector) failures are **infrastructure failures** — detect and recover programmatically. Layer 3 (upstream) failures are **external failures** — detect, back off, and degrade gracefully. Layer 4 (execution semantics) failures are **semantic failures** — detect by verifying outcomes, not HTTP codes.

The mistake most teams make: treating all four layers as if they were Layer 3 (retry on error). This works for Layer 3 but burns tokens and may cause duplicate side effects at Layer 4.

```python
# Unified tool call with all four layers handled
def robust_tool_call(tool_fn, verification_fn=None, max_retries=2):
    outcome = call_tool_with_auth(tool_fn)
    outcome = handle_connector_layer(outcome)
    outcome = handle_upstream_layer(outcome)

    if verification_fn:
        outcome = verify_tool_outcome(outcome, tool_fn.__name__, verification_fn)

    return outcome
```

## Cross-links

- S-1023 (Recovery Ladder) — builds on the insight that HTTP 200 ≠ success; this entry adds the taxonomy for *why* HTTP 200 ≠ success
- S-1032 (Dead Letter Stack) — the retry strategy here maps to the step-level vs. agent-level retry distinction in S-1032
- S-1057 (Tool-Call Hallucination Plateau) — Layer 4 overlaps with tool-call hallucinations but from a different angle: S-1057 covers the agent choosing the wrong tool; this entry covers the chosen tool lying about its result
- S-1056 (MCP Tool Contract Gate) — MCP schema drift is a Layer 2/4 failure; the contract gate prevents it upstream
- S-1018 (Component-Level Attribution) — the 4-layer taxonomy provides the diagnostic map that S-1018's attribution framework needs

## Sources

- Scalekit: "Tool Call Failures in Production" (2025–2026, n=2.3M calls) — 1-in-20 failure rate, 29% auth failures, partial execution returning HTTP 200
- Harness Engineering Academy: "Implementing Reliable Tool Calling in Production AI Agents" (Apr 2026) — retry storm pattern, latency-triggered loops
- Hacker News / colinfly: "What broke when I tried to evaluate an AI agent in production" — broken URLs, localhost in cloud, missing API keys, Reddit blocking; most failures were system-level, not model-level
