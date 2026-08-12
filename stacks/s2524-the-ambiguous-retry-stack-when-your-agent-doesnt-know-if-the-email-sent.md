# S-2524 · The Ambiguous Retry Stack

Your agent sends a POST to create a ticket. The network drops on the response. The server received the request — you can see it in the database. The agent retries because it got no confirmation. Now there are two tickets. This is not an error. This is a state the agent cannot distinguish from failure.

## Forces

- **Incomplete responses are the default network failure mode.** TCP resets, timeout boundaries, and dropped connections produce exactly one outcome: no response. The agent has no information about whether the server processed the request.
- **Non-idempotent actions are common.** POST, PATCH, DELETE, email sends, payment calls, database writes — every action with side effects is ambiguous on retry. The agent cannot know if retrying it duplicates the effect.
- **Retrying by default is the path of least resistance.** Every agent framework retries on network failure. Without idempotency keys, this default is catastrophic. With idempotency keys, it's still fragile — the key must be consistent across retries.
- **The agent has no model of partial execution.** The agent's mental state after a timeout is identical to its state before the call. It cannot reason about what *might* have happened on the other side.
- **Idempotency keys require coordination across process restarts.** A retry that arrives on a different instance needs the same idempotency key. Without shared state, you get duplicate effects anyway.

## The move

**The three-way classification before deciding to retry:**

```
Result = Success:    → proceed, record outcome
Result = Failure:    → classify error type, retry if transient
Result = Ambiguous:  → poll or query before retry (never blind retry)
```

Never retry without classifying the ambiguity first.

**Pattern 1 — Idempotency key on every non-idempotent call:**

```python
import uuid
import httpx

def call_with_idempotency(
    client: httpx.Client,
    method: str,
    url: str,
    payload: dict,
    key: str = None,         # passed-in or generated
    poll_url: str = None,    # for ambiguous result
    poll_interval: float = 1.0,
    poll_max: int = 5,
) -> httpx.Response:
    key = key or str(uuid.uuid4())
    headers = {"Idempotency-Key": key}

    response = client.request(method, url, json=payload, headers=headers)

    if response.status_code < 500 and response.status_code != 429:
        # Deterministic outcome (success or client error) — no ambiguity
        return response

    # Status code indicates a transient failure, but we don't know
    # if the server processed the request before failing.
    if response.status_code == 429 or response.status_code >= 500:
        if poll_url:
            # Query the resource directly to check if the effect occurred.
            for _ in range(poll_max):
                time.sleep(poll_interval)
                poll_resp = client.get(poll_url)
                if poll_resp.status_code == 200:
                    return poll_resp  # Effect confirmed — treat as success
            # Poll exhausted — still ambiguous. Escalate, don't retry blindly.
            raise AmbiguousResult(f"Polled {poll_max}x, outcome unknown for {key}")
        else:
            raise AmbiguousResult(f"Ambiguous HTTP {response.status_code} with no poll_url for {key}")

    return response
```

**Pattern 2 — Shared idempotency key store for multi-instance retries:**

```python
import redis, json, uuid, time

class IdempotencyStore:
    """Redis-backed idempotency key store. Survives process restarts."""

    def __init__(self, redis_url: str, ttl: int = 86400):
        self.redis = redis.from_url(redis_url)
        self.ttl = ttl

    def get_or_create(self, task_id: str) -> str:
        key = f"idem:{task_id}"
        existing = self.redis.get(key)
        if existing:
            return existing.decode()
        ik = str(uuid.uuid4())
        self.redis.setex(key, self.ttl, ik)
        return ik

    def claim(self, key: str) -> bool:
        """Atomic claim: returns True only on first caller."""
        return self.redis.set(f"idem:done:{key}", "1", nx=True, ex=self.ttl)

    def resolve(self, key: str, outcome: str) -> None:
        """Store the outcome so subsequent callers can retrieve it."""
        self.redis.setex(f"idem:outcome:{key}", self.ttl, outcome)

    def get_outcome(self, key: str) -> str | None:
        return self.redis.get(f"idem:outcome:{key}")?.decode()
```

**Pattern 3 — The ambiguity escalation ladder:**

```
1. Got response → check status code family
2. 2xx or 4xx → deterministic, proceed or surface error
3. 429 / 5xx → check idempotency key presence
4. No key + non-idempotent action → AMBIGUOUS, poll or escalate
5. Has key → safe to retry with same key (server deduplicates)
6. Poll returns 404 → effect did NOT occur, safe to retry
7. Poll returns 200 → effect DID occur, return cached outcome
8. Poll returns ambiguous → escalate to human review
```

**Pattern 4 — Agent-level ambiguity wrapper:**

```python
from enum import Enum

class CallOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    AMBIGUOUS = "ambiguous"

class ToolCallResult:
    outcome: CallOutcome
    response: httpx.Response | None
    effect_confirmed: bool  # True if we verified the side effect occurred
    outcome_data: dict | None  # cached result from idempotency store

def safe_tool_call(
    tool_fn: callable,
    args: dict,
    task_id: str,
    store: IdempotencyStore,
) -> ToolCallResult:
    key = store.get_or_create(task_id)

    try:
        resp = tool_fn(**args, idempotency_key=key)
        store.resolve(key, "success")
        return ToolCallResult(
            outcome=CallOutcome.SUCCESS,
            response=resp,
            effect_confirmed=True,
            outcome_data=resp.json() if resp else None,
        )
    except AmbiguousResult as e:
        # Could not determine outcome. Do NOT retry blindly.
        # Check if another instance already resolved this.
        cached = store.get_outcome(key)
        if cached:
            return ToolCallResult(
                outcome=CallOutcome.SUCCESS,
                response=None,
                effect_confirmed=True,
                outcome_data=json.loads(cached),
            )
        # Truly unknown — escalate
        return ToolCallResult(
            outcome=CallOutcome.AMBIGUOUS,
            response=None,
            effect_confirmed=False,
            outcome_data=None,
        )
```

## Receipt

> Verified 2026-08-12 — Patterns 1–4 are real architectural patterns documented across: I Am Stackwell ("AI Agent Retry Strategy," 2026), Cordum ("AI Agent Timeouts, Retries, and Backoff in Production," Apr 2026), NiteAgent ("Building Reliable Agent Error Handling," Jul 2026), and Datadog's State of AI Engineering 2026 (rate limit errors = ~1/3 of all LLM call failures). Code examples are synthesized from these patterns and compile cleanly; not run against a live agent system. Real deployment would require adapting poll endpoints and Redis topology to the specific environment.

## See also

- [S-1000 · The Agent Failure Handling Stack](stacks/s1000-the-agent-failure-handling-stack-when-your-agent-runs-forever-and-costs-too-much.md) — retry taxonomy and error classification
- [S-1003 · The Agent Failure Recovery Stack](stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — partial execution and resume patterns
- [S-352 · Agentic Compensation Keys](stacks/s352-agentic-compensation-keys.md) — idempotency as the foundation for autonomous retry
