# S-2205 · The Retry Amplification Stack — When Retrying a Corrupted Tool Call Makes Things Worse

Your database lookup tool returns HTTP 200 with valid JSON — truncated at 4KB by an undocumented gateway cap. The model correctly identifies the response as broken and retries. The tool returns the same truncated payload. Twelve retries later, the model stops retrying, infers a plausible partial result, and ships a wrong answer upstream. The logs show twelve consecutive 200 OKs. No error was ever raised.

This is not a retry problem. It is a **retry amplification** problem — when the act of retrying makes things worse, not better.

## Forces

- **Every agent retry re-processes the full conversation context.** A microservice retry costs ~10x its normal payload (kilobytes). An agent retry costs 8,000–50,000 tokens depending on conversation depth. Tian Pan (April 2026) documented retry storms producing **200x token cost** relative to a single successful execution. A single flaky endpoint can turn a $0.01 task into a $2 meltdown in under a minute.

- **Agents retry on corrupted, non-recoverable failures.** Standard retry logic (exponential backoff, jitter, 3 attempts) was designed for transient failures — timeouts, rate limits, network blips. The 80% of agent failures that are *semantic* — malformed output, schema drift, partial responses, authorization failures with error messages in the body — do not improve with repetition. The same corrupted payload arrives on every retry, but the agent's confidence in the tool decreases while the token burn continues.

- **The dual-retry loop compounds everything.** Most agent frameworks implement retry logic at the infrastructure level *and* let the agent decide to retry at the application level. Classic retry-3-with-backoff inside the framework, then retry-3 at the agent loop = 9 attempts with no recovery. BIPI's production deployment (fintech, 18 months) found this the single most common cause of runaway token consumption.

- **Error codes don't distinguish recoverable from permanent.** HTTP 200 on a truncated response, HTTP 200 on an auth-expired session, HTTP 200 on a rate-limit response with error in the body — all look identical to a naive retry circuit. The agent has no signal that retrying is futile, so it keeps trying until the loop terminates by exhaustion, not by recovery.

## The move

### Layer 1 — Semantic error classification before retry

Distinguish transient from permanent at the response level, not the HTTP level.

```python
import json

def classify_tool_response(response: dict) -> str:
    """Classify BEFORE deciding to retry."""
    http_status = response.get("status_code", 200)

    # Permanent failures — never retry
    if http_status in (401, 403, 404, 422):
        return "permanent"

    # Check response body semantics
    body = response.get("body", {})
    if isinstance(body, dict):
        # Auth failures masquerading as 200
        if body.get("error") in ("token_expired", "session_invalid",
                                  "insufficient_permissions"):
            return "permanent"

        # Partial/corrupt responses
        if body.get("_truncated") or body.get("_incomplete"):
            return "permanent"

        # Rate limit with retry-after
        if http_status == 429:
            return "transient"

    # Unknown/unstructured — treat as unknown
    return "unknown"

def should_retry(response: dict, attempt: int, max_attempts: int = 2) -> bool:
    classification = classify_tool_response(response)
    if classification == "permanent":
        return False  # Don't retry. Escalate instead.
    if classification == "unknown" and attempt >= max_attempts:
        return False
    return True
```

The key insight: **a retry budget of 2 on "unknown" errors, with permanent errors rejected immediately**, cuts 80% of the retry amplification damage. You're no longer retrying truncated payloads twelve times.

### Layer 2 — Budget-aware retry that accounts for token cost

Instead of retry count, budget by *incremental* token cost.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class RetryBudget:
    base_token_cost: int          # tokens in one full round-trip
    max_increment_count: int = 3  # allow 3x base cost before hard stop
    attempt: int = 0

    def can_retry(self) -> bool:
        return self.attempt < self.max_increment_count

    def record_attempt(self, tokens_consumed: int):
        self.attempt += 1

    def escalate(self) -> dict:
        """Called when budget is exhausted — escalate to human or fallback."""
        return {
            "action": "escalate",
            "reason": "retry_budget_exhausted",
            "attempts": self.attempt,
            "tokens_burned": self.attempt * self.base_token_cost,
        }

# Usage in tool call loop
budget = RetryBudget(base_token_cost=12000)
for attempt in range(10):  # agent loop might try 10 times
    if not budget.can_retry():
        escalate_action = budget.escalate()
        return escalate_action  # stop, don't retry again

    response = call_tool(tool_name, args)
    if should_retry(response, attempt):
        budget.record_attempt(estimate_tokens(response))
        continue  # retry
    else:
        return handle_permanent_failure(response)  # classify and fail fast
```

The key insight: `max_increment_count = 3` means you allow 3x base token cost. After that, you stop regardless of error type and escalate. This is the **retry budget pattern** — budget by cost, not by count.

### Layer 3 — Context-pruned retry

If you must retry, don't replay the full context.

```python
async def retry_with_pruned_context(
    original_messages: list[dict],
    tool_call_id: str,
    error_context: str,
) -> list[dict]:
    """
    Retry a failed tool call with minimal context:
    - System prompt (cached, cheap)
    - Tool schema only
    - The failed tool call + error
    - Brief error context
    """
    system_prompt = original_messages[0]["content"]

    # Find the failed tool call
    failed_call = next(
        m for m in original_messages
        if m.get("tool_call_id") == tool_call_id
    )

    pruned = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Tool call failed: {error_context}"},
        failed_call,
    ]

    return pruned  # ~500 tokens instead of 8,000+
```

Tian Pan's production measurement: context-pruned retry reduces each attempt from 8,000–50,000 tokens to 300–800 tokens — a **10–60x reduction** per retry cycle.

### Layer 4 — Circuit breaker with error fingerprinting

Track error patterns, not just counts.

```python
from collections import defaultdict
from dataclasses import dataclass, field

@dataclass
class ErrorFingerprint:
    tool_name: str
    error_signature: str  # hash of (tool, error_type, error_message_pattern)
    count: int = 0
    last_seen: float = 0

class AgentCircuitBreaker:
    def __init__(self, threshold: int = 3, window_seconds: float = 60.0):
        self.threshold = threshold
        self.window = window_seconds
        self.fingerprints: dict[str, ErrorFingerprint] = field(
            default_factory=lambda: defaultdict(lambda: ErrorFingerprint("", ""))
        )
        self._open_circuits: set[str] = set()

    def _fingerprint(self, tool_name: str, error: dict) -> str:
        # Normalize error for fingerprinting
        error_type = error.get("type", "unknown")
        msg_pattern = error.get("message", "")[:50]  # first 50 chars
        return f"{tool_name}:{error_type}:{msg_pattern}"

    def record_failure(self, tool_name: str, error: dict):
        fp = self._fingerprint(tool_name, error)
        entry = self.fingerprints[fp]
        entry.tool_name = tool_name
        entry.error_signature = fp
        entry.count += 1

        if entry.count >= self.threshold:
            self._open_circuits.add(tool_name)

    def is_circuit_open(self, tool_name: str) -> bool:
        return tool_name in self._open_circuits

    def half_open_attempt(self, tool_name: str) -> bool:
        """Allow one probe attempt to test recovery."""
        self._open_circuits.discard(tool_name)
        return True
```

The key insight: circuit breaker tracks *why* the tool failed, not just *that* it failed. A truncated payload from a database tool triggers the same fingerprint on every retry — after 3 attempts, the circuit opens and routes to a fallback or escalates. This is the **error fingerprint circuit breaker** — it catches the "same broken thing" pattern and stops retrying it.

## Receipt

> Verified 2026-08-05 — Tian Pan (April 10, 2026) documented 200x token cost amplification in retry storms. BIPI (April 2026) documented the dual-retry loop problem and validated retry budgets over retry counts. Waxell 2026 dashboard confirmed retry amplification as top-3 production cost driver. The semantic error classification pattern (permanent vs. transient at response-body level) is documented across BIPI, Preporato, and agent-tool-resilience GitHub library.

## See also

- [S-2204 · The Failure Blind Spot Stack](/stacks/s2204-the-failure-blind-spot-stack-when-your-agent-keeps-retrying-and-nobody-knows-why.md) — when your agent keeps retrying and nobody knows why
- [S-2199 · The Tool Response Gate Stack](/stacks/s2199-the-tool-response-gate-stack-when-your-agent-reasons-over-corrupted-output-and-nobody-checks.md) — when your agent reasons over corrupted output
- [S-1000 · The Agent Recovery Stack](/stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails.md) — general recovery patterns including circuit breakers and dead letter queues
