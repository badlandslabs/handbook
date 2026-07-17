# S-1248 · The Token Drift Stack: When Your Long-Running Agent Holds Keys That Expire and Nobody Knows

Your agent runs for 8 hours across HubSpot, Salesforce, and Google Workspace simultaneously. At hour 3, the HubSpot token expires. The agent doesn't crash. It gets an empty response, interprets it as "no leads today," writes a partial artifact, and marks the task complete. The run shows green. The customer sees silence. Nobody knows until the daily sync report surfaces a 0-contact day.

## Forces

- **OAuth TTLs are short; agent runs are long.** HubSpot tokens last 30 minutes. Google tokens last 1 hour. Salesforce tokens last 15 minutes to 2 hours depending on org config. An agent that runs for 6–24 hours will face multiple token expirations per integration — by design.
- **Token expiry doesn't always throw.** The most common failure mode is silent: empty tool results the LLM interprets as "no data found," partial writes that corrupt downstream state, or hallucinated recovery paths that look like progress. Agents don't crash — they drift.
- **Multiple independent TTL clocks compound the problem.** Managing one token's refresh is a solved auth problem. Managing three or more independent TTL clocks inside a single stateful agent run — with no shared refresh schedule and concurrent async tool calls — is an orchestration problem, not an auth configuration problem.
- **Refresh tokens have their own end-of-life clock on a different axis.** A refresh token that itself expires (Google: 7 days; others vary) requires a full re-authorization flow that blocks the run and may need a human to re-approve.

## The Move

### 1. Treat token state as a first-class agent resource

Model every token as a resource object with an explicit `expires_at` timestamp, not just a boolean `is_valid`. Track `issued_at`, `TTL_seconds`, `refresh_token_expires_at`, and `provider`. Before any tool call, check the token's remaining lifetime and refresh proactively — don't wait for a 401.

```python
class TokenState:
    provider: str
    access_token: str
    expires_at: datetime       # UTC
    refresh_token: str | None
    refresh_expires_at: datetime | None  # None = non-expiring
    buffer_seconds: int = 120  # refresh this many seconds early

    def needs_refresh(self) -> bool:
        return datetime.utcnow() + timedelta(seconds=self.buffer_seconds) >= self.expires_at
```

### 2. Run a background token refresh loop

Before the main agent loop starts, spawn a background coroutine that continuously monitors all token states and refreshes proactively. This runs independently of the agent's tool execution, so refresh latency doesn't block task progress.

```python
async def token_refresh_loop(tokens: dict[str, TokenState], refresh_fn: dict[str, callable]):
    while True:
        for name, state in tokens.items():
            if state.needs_refresh():
                new_state = await refresh_fn[name](state.refresh_token)
                tokens[name] = new_state
        await asyncio.sleep(30)  # check every 30s
```

### 3. Validate tool results against token health, not just response content

A 200 OK with empty data can mean either "no results" or "token expired silently." Add an explicit token-health signal to every tool result envelope:

```python
@dataclass
class ToolResult:
    data: Any
    token_healthy: bool  # True = fresh token used, False = token was near/expiry
    warning: str | None  # "used token 89% through its lifetime"
```

If `token_healthy == False`, the LLM can treat the result differently: flag uncertainty, retry with a freshly-refreshed token, or escalate.

### 4. Gate long-running tasks on a token health checkpoint

Before entering a multi-hour agent run, validate that all required tokens will survive the estimated run duration. Factor in the minimum TTL:

```python
def can_start_run(tokens: dict[str, TokenState], estimated_duration: timedelta) -> bool:
    for name, state in tokens.items():
        remaining = state.expires_at - datetime.utcnow()
        if remaining < estimated_duration:
            return False  # or trigger pre-run refresh
    return True
```

If a token's refresh token is expired (not just the access token), halt the run with an escalation — this requires re-authorization and a human-in-the-loop.

### 5. Instrument token lifecycle as observability events

Emit structured events for every refresh lifecycle transition:

```json
{"event": "token_refresh", "provider": "hubspot", "outcome": "success", "latency_ms": 210}
{"event": "token_refresh", "provider": "salesforce", "outcome": "failed", "reason": "invalid_grant", "action": "escalate"}
{"event": "tool_call_on_expiring_token", "provider": "google", "token_age_pct": 87, "remaining_seconds": 458}
```

Alert on `token_refresh.failure` events and on runs that used tokens above 80% TTL without a refresh.

## Tradeoffs

- **Refresh buffer too aggressive** → unnecessary API calls to the OAuth provider; may hit rate limits.
- **Refresh buffer too conservative** → occasional silent failures slip through before refresh fires.
- **Per-token polling** → scales O(n) with integrations. For large agent fleets, push via webhook from the OAuth provider instead of polling.
- **Refresh token expiry is not recoverable automatically.** Design for it: store the authorization grant and prompt for re-auth well before the refresh token expires.

## Sources

- [Scalekit: OAuth Token Refresh for Long-Running Agents](https://www.scalekit.com/blog/oauth-token-refresh-long-running-agents) (May 2026)
- [Scalekit: How to Handle Token Refresh for AI Agents in Production](https://www.scalekit.com/blog/how-handle-token-refresh-ai-agents) (May 2026)
- [Descope: AI Agent Credential Management Best Practices](https://www.descope.com/blog/post/ai-agent-credential-management) (May 2026)
