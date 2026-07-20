# [S-1408] · The Action Hallucination Stack — When Your Agent Succeeds and Does the Wrong Thing

Your agent returns 200 OK. The output looks great. The plan executed cleanly. Two weeks later you discover it fabricated a tool call that never ran, masked a permission error as a retry success, and built its next twelve decisions on a state that diverged from reality three steps ago. The agent wasn't lying. It genuinely believed everything it did. This is **action hallucination** — and it's the failure mode that looks most like success.

## Forces

- **Agents fail confidently, not uncertainly.** When a tool call fails, the agent often continues as if it succeeded. HTTP 200 on the infrastructure layer tells you the request arrived — not that the right action ran. The agent's world model diverges silently.
- **Tool-call fabrication is invisible to APM.** If the model generates a malformed JSON tool call, or truncates the output before the call reaches the execution layer, your monitoring stack sees nothing. The agent output looks like a normal response.
- **Failure masking compounds at every step.** A single silent failure at step N poisons every downstream decision. At 95% per-step accuracy, ten steps lands you at ~60% overall task completion — and the failures that survive look like confident correct answers.
- **State divergence requires read-back verification.** The tool succeeded. The agent's model of the resulting state didn't. This is the hardest type to detect because both the agent and your infrastructure agree the action completed.
- **Three-way fidelity is needed.** You need to compare: what the agent *intended* to do (logged before dispatch), what actually *dispatched* (execution layer), and what the resulting *state* actually is (verified after side effects). Any two of the three agree while the third diverges.

## The move

### The three types

**Type 1 — Tool-call fabrication.** The agent generates a tool call in its output that never reaches the execution layer. Causes: malformed JSON, output truncation at token limits, hallucinated tool name not in the available catalog, or structured output that gets corrupted before parsing. Invisible to APM because nothing was dispatched. Detectable only by instrumenting the *intent* layer — log what the agent decided to call before parsing.

**Type 2 — Silent failure masking.** The tool call dispatches, returns a non-2xx response (429 rate limit, 504 timeout, 403 permission denied), and the agent recovers without acknowledging the failure. It treats the error as a retry signal, substitutes a plausible default, or simply continues from the last valid state. This is the most common type in production. Per Dynatrace Perform 2026: tool call failure rates of 3–15% in production environments, contributing to the 95%/step → ~60%/10-step accuracy drop.

**Type 3 — State divergence.** The tool call dispatches, returns 200, but the agent's model of the resulting state diverges from reality. Causes: stale reads from a cache, concurrent modifications by another process, eventual consistency lag in distributed systems, or the agent misinterpreting a partial response. Detection requires explicit read-back verification after every state-mutating tool call — query the authoritative state source and diff against the agent's assumption.

### The three-way diff architecture

```
Intent log (before)     →  Execution log (dispatch)     →  State verification (after)
"user_delete(1234)"     →  DELETE /api/users/1234      →  GET /api/users/1234 → 404?
"send_invoice(inv-99)"  →  POST /api/invoices/inv-99   →  GET /api/invoices/99 → status="draft"?
```

Every mismatch across these three layers is a candidate action hallucination. Log all three. Alert on mismatches. Quarantine the agent's downstream actions when a mismatch is detected.

```python
import structlog, httpx, json

log = structlog.get_logger()

async def safe_tool_call(tool_name: str, intent: dict, params: dict, verify_state=None):
    # Layer 1: Intent — log what the agent decided
    log.info("tool_intent", tool=tool_name, intent=intent, params=params)

    try:
        # Layer 2: Execution — log actual dispatch
        result = await dispatch(tool_name, params)
        log.info("tool_dispatched", tool=tool_name, status=result.status_code, body=result.text[:200])

        result.raise_for_status()
        outcome = result.json()
    except httpx.HTTPStatusError as e:
        # Type 2: Silent failure masking — flag explicitly
        log.error("tool_failed", tool=tool_name, status=e.response.status_code,
                  detail="SILENT_FAILURE_RISK — agent may be unaware")
        raise ToolExecutionError(f"{tool_name} failed with {e.response.status_code}") from e

    # Layer 3: State verification for state-mutating tools
    if verify_state:
        actual_state = await verify_state()
        expected = intent.get("expected_state")
        if actual_state != expected:
            log.critical("state_diverged", tool=tool_name,
                         expected=expected, actual=actual_state,
                         detail="ACTION_HALLUCINATION_TYPE3 — downstream quarantined")
            raise StateDivergenceError(f"{tool_name}: expected {expected}, got {actual_state}")

    return outcome
```

### Detection triggers

| Type | Detection signal | Response |
|------|-----------------|---------|
| Type 1 | Intent logged but no matching execution log | Quarantine, re-plan |
| Type 2 | Execution log shows non-2xx, no exception raised | Roll back, retry with alert |
| Type 3 | State verification mismatch after confirmed dispatch | Halt chain, surface divergence |

## Receipt

> Verified 2026-07-20 — Three-type taxonomy sourced from I-250 tracker (Paperclipped.de "AI Agent Production Issues 2026", June 2026; Gobii.ai "How to Run AI Agents Safely in Production", Jan 28, 2026). Dynatrace Perform 2026 accuracy compounding figure (95%/step → ~60% at 10 steps). Three-way diff architecture is a synthesis pattern; code example is illustrative. Cross-links verified: S-1012 (failure recovery — Type 2 surfaces as recovery gap), S-1281 (golden traces — intent logging connects to trace collection), S-1018 (component attribution — attribution worsens when root cause is action hallucination).

## See also

[S-1012](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) · [S-1281](s1281-the-golden-trace-stack-when-your-agent-passed-the-demo-but-you-dont-know-if-it-works.md) · [S-1018](s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-OK.md)
