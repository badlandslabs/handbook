# S-1594 · The Proposal Gate Stack — When Your Agent Knows What It Wants but Hasn't Asked If It Should

Every layer in your agent stack is designed to help the model *decide*. The planning module narrows options. The tool definitions tell it what's available. The system prompt encodes policies. And then the model emits a tool call — and you execute it. That execution is where agents produce phantom records (S-1092), fabricate API responses, and perform irreversible actions that passed every internal check but violated live business state.

The fix is a conceptual inversion: **the agent is not the decider. The agent is the proposer. The infrastructure is the decider.**

This is the Proposal Gate — a validation architecture that intercepts every agent-proposed action before it executes, running it through a staged pipeline of schema validation, semantic checks, and state verification. The model proposes; the gate approves.

## Forces

- **Agent output looks valid even when wrong.** A 200 from the LLM means nothing. The model can produce a structurally correct tool call that targets a non-existent endpoint, sends wrong types, or acts on stale assumptions. None of these cause errors — they cause phantom outcomes.
- **The compound failure math is brutal.** At 95% per-step accuracy, a 10-step workflow succeeds ~60% of the time. Each step without a gate is another compound failure opportunity. A single pre-flight check per step can break the compounding chain.
- **Execution is irreversible; validation is cheap.** The cost of rejecting a bad proposal is one extra LLM round-trip and a validation check. The cost of a phantom record in your database can be a compliance incident. The math always favors the gate.
- **Context changes between proposal and execution.** The agent reasons at time T, but the world moves. A record it assumes exists may have been deleted. A price it cached may have changed. State verification just before execution catches what planning-time reasoning missed.
- **"Works in demo, fails in production" is a missing gate symptom.** Agents demo perfectly because the environment is controlled. Production has race conditions, stale data, concurrent modifications, and API drift — all of which a proposal gate catches.

## The move

The proposal gate sits between the model and the tool executor. It receives the model's proposed action, validates it in three stages, and either approves or rejects.

### Stage 1: Schema Validation

Validate the proposed call against the tool's JSON schema before execution. This catches type errors, missing required fields, and malformed arguments. Do not rely on the model to produce correct types — even with constrained decoding, edge cases escape.

```python
import json
import jsonschema

def validate_schema(tool_name: str, proposed_args: dict) -> tuple[bool, str]:
    """Stage 1: Structural validation against declared tool schema."""
    schema = TOOL_SCHEMAS[tool_name]  # Loaded from your tool registry
    try:
        jsonschema.validate(instance=proposed_args, schema=schema)
        return True, "schema_ok"
    except jsonschema.ValidationError as e:
        return False, f"schema_failed: {e.message}"
```

### Stage 2: Semantic Validation

Beyond schema correctness, validate whether the call makes business sense. This includes: does the ID format match your conventions? Are numeric values in expected ranges? Does the action type exist in your domain model?

```python
def validate_semantic(tool_name: str, proposed_args: dict, context: dict) -> tuple[bool, str]:
    """Stage 2: Business-rule and semantic validation."""
    errors = []

    if tool_name == "create_order":
        # Must have at least one line item
        if not proposed_args.get("line_items"):
            errors.append("Order must have at least one line item")
        # Total must be non-negative
        if proposed_args.get("total_amount", 0) < 0:
            errors.append("Order total cannot be negative")
        # Customer must be active
        customer = context.get("customer", {})
        if not customer.get("is_active"):
            errors.append("Cannot create order for inactive customer")

    if errors:
        return False, "; ".join(errors)
    return True, "semantic_ok"
```

### Stage 3: State Verification

The most critical and most skipped stage. Before executing any action that assumes a resource exists or is in a particular state, verify that state is still true at execution time.

```python
async def verify_state(tool_name: str, proposed_args: dict) -> tuple[bool, str]:
    """Stage 3: Live state verification before execution."""
    checks = []

    if tool_name == "update_order":
        order_id = proposed_args.get("order_id")
        current = await db.orders.find_one({"id": order_id})
        if not current:
            return False, f"Order {order_id} does not exist"
        if current.get("status") == "cancelled":
            return False, f"Order {order_id} is already cancelled"
        # Verify no concurrent modification
        expected_version = proposed_args.get("_expected_version")
        if expected_version and current.get("version") != expected_version:
            return False, f"Order {order_id} modified since planning (version mismatch)"

    if tool_name == "send_email":
        recipient = proposed_args.get("recipient")
        contact = await crm.contacts.find_one({"email": recipient})
        if not contact:
            return False, f"Recipient {recipient} not found in CRM"
        if contact.get("do_not_contact"):
            return False, f"Recipient {recipient} has do-not-contact flag"

    return True, "state_ok"
```

### The Full Gate

```python
async def proposal_gate(
    tool_name: str,
    proposed_args: dict,
    context: dict,
) -> tuple[bool, str, str]:
    """
    Returns (approved, reason, next_action).
    next_action: 'execute' | 'retry_with_feedback' | 'escalate' | 'block'
    """
    # Stage 1: Schema
    ok, reason = validate_schema(tool_name, proposed_args)
    if not ok:
        return False, reason, "retry_with_feedback"

    # Stage 2: Semantic
    ok, reason = validate_semantic(tool_name, proposed_args, context)
    if not ok:
        return False, reason, "escalate"

    # Stage 3: State
    ok, reason = await verify_state(tool_name, proposed_args)
    if not ok:
        return False, reason, "block"

    return True, "gate_passed", "execute"
```

### Gate Outcomes

| Outcome | Meaning | Agent Response |
|---------|---------|---------------|
| `execute` | All gates passed | Proceed with tool call |
| `retry_with_feedback` | Schema error — model can self-correct | Return error with correction hint |
| `escalate` | Semantic violation — needs human review | Log, alert, pause workflow |
| `block` | State conflict — cannot execute safely | Block, explain, suggest alternative |

The retry-with-feedback path is powerful: instead of silently failing or crashing, the agent gets a structured error back and can self-correct. This converts the gate from a blocker into a reliability multiplier.

## Receipt

> Verified 2026-07-24 — Pattern synthesized from: Elba blog on API hallucination (useelba.com), paperclipped practitioner field report (2026), iamstackwell proposal engine pattern, waxell.ai output validation research. Code examples use standard Python (jsonschema, asyncio) aligned with production patterns described in S-767 (tool-call hallucination plateau), S-1092 (phantom value), and S-1016 (agent failure intervention). Gate outcome table maps directly to escalation tiers from S-1005 (AI SRE) and S-1003 (agent failure recovery). Real-world validation rate data: 3–15% tool-call failure rate in production (paperclipped, 2026); 71% orgs experimenting, only 11% in production (Deloitte 2025) — compound failure math is the primary driver.

## See also

- [S-767 · The Tool-Call Hallucination Plateau](s767-the-tool-call-hallucination-plateau.md) — model-level failure rate; this entry addresses it architecturally
- [S-1092 · The Phantom Value Stack](s1092-the-phantom-value-stack-when-your-agent-produces-a-record-that-doesnt-exist.md) — the consequence this gate prevents
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — post-execution correction; the gate is the pre-execution equivalent
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery after the fact; the gate prevents the need for recovery
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the operational discipline that owns the proposal gate
