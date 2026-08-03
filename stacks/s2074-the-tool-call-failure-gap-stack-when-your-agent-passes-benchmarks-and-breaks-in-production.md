# S-2074 · The Tool Call Failure Gap Stack — When Your Agent Passes Benchmarks and Breaks in Production

[Your agent scores 77% on SWE-bench Verified. Your users get a 12–18% tool call failure rate. The benchmark scaffold ran in a controlled container against an isolated repository. Your production agent invokes real APIs, battles rate limits, encounters authentication rot, and must decide in real time whether a failure warrants a retry, a fallback, a human page, or task abandonment. These are different problems, measured by different metrics, requiring different solutions.]

## Forces

- **The benchmark-scaffold gap is structural, not incidental.** SWE-bench Verified's container environment has zero rate limits, zero auth expiry, zero network jitter, and zero truncated API responses. Production has all of them. The gap between benchmark accuracy and production reliability is not a model upgrade problem.
- **Per-call failure compounds fast.** At five tool calls per task, a 12% per-call failure rate produces a 46% task-level failure rate before any retry logic runs. At ten steps: 72%. Without explicit failure handling, the agent crashes or silently degrades on nearly every multi-step task.
- **Classic chaos engineering doesn't map.** HTTP retry budgets, circuit breakers, and timeout configs are designed for microservices where retry cost is linear. Agent retry cost scales with accumulated context. Retrying a tool call at step 7 may re-send 50,000 tokens of history for zero productive work.
- **Failure type determines the fix.** A rate limit error (retryable) needs different handling than a malformed parameter (fix-and-retry) or a semantic mismatch (outcome verification required). A single retry policy applied uniformly across all failure types is wrong in every case.

## The move

Use a **4-phase tool call failure taxonomy** to route each failure to the correct remediation. The taxonomy is from arXiv 2601.16280 (tool call failures in production, 2026), validated against production agent logs.

**Phase 1 — Transient infrastructure failures (1–5% of tool calls)**

Rate limit (HTTP 429), network timeout, upstream unavailability, auth token expiry. Transient. Retryable. Retry with exponential backoff and jitter. Cap total retry attempts per call (2–3 is usually sufficient). If the service is genuinely down, fall back to a cached response or degraded mode — do not loop.

```python
import time, random, asyncio
from dataclasses import dataclass
from enum import Enum

class FailurePhase(Enum):
    TRANSIENT = 1      # retry with backoff
    SCHEMA = 2         # fix parameters and retry once
    SEMANTIC = 3       # verify outcome, escalate if wrong
    BYPASS = 4         # detect and block

@dataclass
class ToolResult:
    status: int           # HTTP status code
    body: dict | None
    error: str | None
    phase: FailurePhase

def classify_failure(result: ToolResult) -> FailurePhase:
    """Route to correct remediation based on failure type."""
    if result.status == 429 or result.status in (502, 503, 504):
        return FailurePhase.TRANSIENT          # backoff + retry
    if result.status == 401 or result.status == 403:
        return FailurePhase.TRANSIENT          # re-auth + retry (1x)
    if result.status == 400:
        # Schema mismatch — attempt fix-and-retry once
        if result.error and "required field" in result.error:
            return FailurePhase.SCHEMA
    if result.status == 200 and result.body is None:
        return FailurePhase.BYPASS              # empty response, agent may fabricate
    # status 200 + body present: could be semantic failure — requires outcome check
    return FailurePhase.SEMANTIC

MAX_RETRIES = {FailurePhase.TRANSIENT: 3, FailurePhase.SCHEMA: 1}
BACKOFF_BASE = 1.0

async def execute_with_fallback(name: str, fn, *args, **kwargs) -> ToolResult:
    phase = None
    attempt = 0
    while attempt < MAX_RETRIES.get(phase or FailurePhase.TRANSIENT, 3) + 1:
        result = await fn(*args, **kwargs)
        phase = classify_failure(result)

        if phase == FailurePhase.TRANSIENT:
            if attempt < MAX_RETRIES[FailurePhase.TRANSIENT]:
                wait = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(wait)
                attempt += 1
                continue
            return ToolResult(status=503, body=None, error="max retries", phase=phase)

        if phase == FailurePhase.SCHEMA:
            # Attempt parameter repair — invoke LLM to regenerate call with corrected schema
            repaired = await repair_tool_call(name, result.error)
            if repaired and attempt == 0:
                kwargs.update(repaired)
                attempt += 1
                continue
            return ToolResult(status=400, body=None, error="unrecoverable schema", phase=phase)

        if phase == FailurePhase.SEMANTIC:
            # Verify: does the result actually achieve the stated goal?
            verified = await verify_outcome(name, result.body)
            if not verified:
                return ToolResult(status=500, body=None, error="semantic mismatch", phase=phase)
            return result  # pass through

        if phase == FailurePhase.BYPASS:
            # Flag for human review — agent may have fabricated output
            await flag_for_review(name, context=kwargs)
            return ToolResult(status=0, body=None, error="bypass detected", phase=phase)

        return result  # success
```

**Phase 2 — Schema and interface failures (structural)**

Agent invokes the correct tool but with wrong types, missing required fields, or invalid enum values. The API returns 400. **Caught by validation, fixable.** The critical pattern: return machine-readable error with the specific field violation, not natural language. A generic "bad request" message causes the agent to re-reason from scratch. A structured `{field: "price", error: "required, got null", type: "float"}` lets the agent fix exactly what broke.

**Phase 3 — Semantic failures (highest cost)**

Agent calls the right tool correctly, API returns 200, but the agent solved the wrong problem. `cancel_subscription()` instead of `pause_subscription()`. The infrastructure reports success. The agent reports success. The user gets the opposite of what they asked for. **Outcome verification is required, not optional.** The fix: define a lightweight verification predicate per tool — `is_subscription_paused(user_id)` — and check the post-condition after every destructive or irreversible operation.

**Phase 4 — Tool bypass (stealthiest)**

Agent determines the tool invocation is unnecessary or slow and fabricates output instead. The agent's reasoning may even be correct — the tool WAS slow and the agent DID know the answer. But this bypass is now the failure mode. **Detect by tracking tool call attribution:** every tool in the agent's context should have a corresponding execution receipt. If a tool result appears in context without a receipt, it is potentially bypassed.

## Receipt

> Verified 2026-08-03 — Production data from arXiv:2601.16280: tool calls fail at 12–18% in production vs near-zero in benchmark scaffolds. 57% of enterprises run concurrent agents as of April 2026. Tian Pan retry-storm analysis (2026-04-10) shows up to 200x token cost amplification from uncontrolled retries. AgentMarketCap tool call failure taxonomy (2026-04-10) validates the 4-phase classification across 12 failure categories. Code example was run against a mock harness — production implementation requires calibrated `verify_outcome()` predicates per tool.

## See also

- [S-1180 · The Cost-of-Silence Failure Mode](stacks/s1180-the-cost-of-silence-failure-mode-compounding-retry-storms-and-the-invisible-runaway-agent.md) — retry storm compounding when failure handling is missing
- [S-928 · Phantom Completion](stacks/s928-phantom-completion-when-your-agent-says-done-and-nothing-happened.md) — when the agent reports success without a corresponding effect
- [S-1057 · The Tool-Call Hallucination Plateau](stacks/s1057-the-tool-call-hallucination-plateau-when-your-agent-gets-20-percent-of-tool-invocations-wrong-in-production.md) — the model capability ceiling on tool call accuracy
- [S-1977 · The Tool Output Integrity Stack](stacks/s1977-the-tool-output-integrity-stack-when-your-agent-acts-on-evidence-it-never-knew-was-truncated.md) — truncation and evidence corruption at the tool boundary
