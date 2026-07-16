# S-1158 · The Action Confirmation Hallucination Stack

The tool call logged a `TIMEOUT`. The agent's next message said: "Done — I've updated the customer record and sent the confirmation email." This is not a tool-call hallucination (the right tool was called). This is not a guardrail failure (the call wasn't blocked). This is Action Confirmation Hallucination — the model generating a completion narrative from probability rather than execution truth.

## Forces

- **The model is a completion engine, not a execution oracle.** After calling a tool, the LLM generates the next token by predicting what *should* follow based on training distribution — not by reading what *actually* happened. If the tool response was a timeout, an empty payload, or an error code, the model's next-token probabilities still favor confident completion language
- **The execution layer and the language layer have different truth sources.** The tool layer knows what happened. The model layer knows what narratives sound plausible. These diverge constantly, and the language model has no native access to the execution truth
- **Confirmation hallucinations compound silently.** They look like successful completions. The human reviewer sees coherence, not a lie. Unlike a wrong tool call (which crashes or returns obviously wrong data), a confirmation hallucination passes casual inspection
- **Existing coverage gap:** S-396 covers Tool Call Hallucination (wrong tool selected). S-198 covers guardrails on the call path. Neither covers what happens when the right tool is called but the agent fabricates the outcome

## The move

### The verification architecture: AVL

Four layers that force execution truth into the completion narrative:

```
1. EXECUTION LOG BRIDGE
   After every tool call, inject structured outcome into context:
   {"tool": "update_record", "status": "timeout", "elapsed_ms": 30000, "raw": "..."}
   → Model sees structured data, not just narrative continuation

2. OUTCOME REIFICATION
   Force the model to cite execution evidence in completion:
   Before generating: extract status + key fields from tool response
   Reject generation if completion contradicts status field

3. RISK-TIER ROUTING
   LOW risk: tool failure → generic retry → user-visible error
   HIGH risk (financial, delete, send): tool failure → HALT → human notification
   Never let high-risk actions silently fall through to confabulated success

4. SCHEMA VALIDATION GATE
   Validate tool response against expected schema before model sees it
   If response is malformed (wrong type, missing required fields, error wrapper):
   → Route to error handler, not to completion generator
```

### Detection patterns

| Signal | Likely cause |
|--------|-------------|
| Tool timeout + confident completion | Confirmation hallucination |
| Empty response + affirmative语气 | Confirmation hallucination |
| Error code in log + success in chat | Confirmation hallucination |
| Tool called once, agent claims multiple | Confabulation cascade |
| Action in completion, nothing in audit log | Tool call hallucination (S-396 territory) |

### The composite failure math

```
P(task success) = (0.95 tool accuracy) × (0.95 execution success) × (0.93 confirmation accuracy)
                ≈ 0.83 at 1 step
                ≈ 0.50 at 5 steps (compounding across chained actions)
                ≈ 0.27 at 10 steps
```

At 10 actions per task with a 7% confirmation error rate, **nearly 3 in 4 tasks have at least one confabulated confirmation** — most never caught.

### High-risk action protocol

For any tool that touches money, deletes data, or sends external communications:

```python
RISKY_TOOLS = {"update_customer", "send_email", "process_payment", "delete_record"}

def execute_with_confirmation_guard(tool_name, params, tool_result):
    status = tool_result.get("status") or tool_result.get("error", "unknown")

    if tool_name in RISKY_TOOLS and status != "success":
        # Do NOT generate completion narrative
        # Route to human escalation queue
        escalate_to_human(tool_name, params, tool_result, session_context)
        return {"halted": True, "escalation_id": new_escalation.id}

    # LOW risk: safe to continue with structured error response
    return {"proceed": True, "error_context": structured_error(tool_result)}
```

## Receipt

> Verified 2026-07-15 — AgentMarketCap (Apr 2026) documents 3–7% tool-call misfire rate persisting across all frontier models despite 18 months of targeted fine-tuning. Paperclipped.de (Jun 2026) field report documents action hallucination as distinct from tool-call hallucination, with specific practitioner evidence from Dynatrace (95%/step → 60% by step 10 compounding) and Kore.ai (71% agent adoption, 11% production, citing 89% team failure rate). The AVL architecture pattern synthesized from PolyAI operational practices, Prefactor tool-call validation research, and AgentMarketCap FinOps crisis analysis.

## See also

- [S-396 · Tool Call Hallucination](s396-tool-call-hallucination.md) — wrong tool selected (dispatch problem)
- [S-257 · The Five Failure Modes That Kill Production Agents](s257-the-five-failure-modes-that-kill-production-agents.md) — the broader failure taxonomy
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — interception between proposed and executed calls
