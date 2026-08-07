# S-2276 · The Tool Parameter Gate Stack — When Your Agent Calls the Right Tool with the Wrong Arguments

Your customer service agent has the right tool (`lookup_order`), the right logic, and a perfectly reasoned plan. It calls `lookup_order(order_id="ORD-2026-")` — missing the last 6 digits. The tool returns a 404. The agent doesn't know why. It retries. The same 404. It invents an order status. The customer accepts it. Nobody caught it. The tool worked perfectly. The parameter didn't.

This is the tool parameter gate: the validation boundary between what the model decided to call and what the tool actually received. It's not a model failure. It's not a tool failure. It's a translation failure at the most critical interface in your agent.

## Forces

- **The completion bias turns wrong parameters into confident hallucinations.** When the model passes `status="paid"` to a tool expecting `payment_status="paid"`, the tool returns a schema validation error. The model sees the error and, instead of correcting the parameter name, often infers a plausible answer from context and proceeds — completing the task "successfully" without ever calling the tool correctly.
- **The parameter gap is invisible to every monitoring layer above it.** Traces show the tool was called. Logs show HTTP 200. APM shows no error. Nobody captures that the arguments were semantically wrong — the tool executed, it just executed on the wrong thing.
- **Schema validation catches syntax, not semantics.** A tool that accepts `{"amount": "forty-seven dollars"}` will pass JSON Schema validation. A tool that receives `{"user_id": null}` from a model that hallucinated the user's ID will execute without error. The gap between "valid JSON" and "correct parameter" is where agents silently misbehave.
- **Parameter errors compound exponentially in multi-agent systems.** When Agent A passes a result to Agent B as a tool parameter, any entity-extraction error in A's output becomes a malformed parameter in B's tool call. One hallucinated customer ID in a synthesis step propagates into five failed downstream tool calls.

## The move

### 1. Instrument at the parameter boundary — not inside the tool

Wrap every tool at the call site, not inside it. The wrapper intercepts arguments before they reach the tool and validates them against a **semantic contract** — not just the JSON Schema, but the meaning of the values.

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

class LookupOrderParams(BaseModel):
    order_id: str

    @field_validator("order_id")
    @classmethod
    def order_id_format(cls, v: str) -> str:
        # Enforce format: ORD-YYYY-NNNNNN
        import re
        if not re.match(r"^ORD-\d{4}-\d{6}$", v):
            raise ValueError(
                f"order_id '{v}' does not match required format ORD-YYYY-NNNNNN"
            )
        return v

def wrap_tool(tool_fn, param_model):
    def wrapper(params: dict, session_id: str):
        try:
            validated = param_model.model_validate(params)
        except ValidationError as e:
            # Structured error → model can correct, not guess
            return {
                "error": "parameter_validation_failed",
                "detail": e.errors(),
                "hint": "Fix these fields and retry: "
                        + ", ".join(e.errors()[0]["loc"])
            }
        return tool_fn(validated.model_dump(), session_id)
    return wrapper
```

The key is the `hint` field. A bare validation error tells the model "something is wrong." A structured error with a hint tells the model "specifically this field, fix it like this." Without the hint, the model defaults to completing from context — the completion bias wins.

### 2. Cross-reference parameters against live state before calling

For high-stakes parameters — entity IDs, monetary amounts, user identifiers — verify the parameter value against the live system before executing the tool. This catches hallucinated IDs that pass format validation but reference nothing.

```python
async def validate_params_live(params: dict, tool_name: str) -> dict:
    """Pre-flight validation: check parameter references exist in live state."""
    if tool_name == "lookup_order":
        order = await db.orders.find_one({"order_id": params["order_id"]})
        if not order:
            return {
                "status": "reject",
                "reason": "order_not_found",
                # Don't tell the model the order doesn't exist if it hallucinated
                # the ID — return a safe hint instead
                "hint": "order_id format appears valid but no order matches. "
                        "Verify the order ID from the source document."
            }
    if tool_name == "charge_customer":
        customer = await db.customers.find_one({"customer_id": params["customer_id"]})
        if not customer:
            return {"status": "reject", "reason": "customer_not_found"}
    return {"status": "ok"}
```

The principle: **reject with hints, never infer with silence.** A rejected call with a traceable reason is recoverable. A silently wrong call with a plausible answer is not.

### 3. Enforce semantic type safety, not just JSON Schema

JSON Schema `type: string` is insufficient. Define semantic types that carry meaning:

```python
class EmailAddress(str):
    @classmethod
    def __validate__(cls, v):
        if not re.match(r"^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$", v):
            raise TypeError(f"'{v}' is not a valid email address")
        return v

class CurrencyAmount(float):
    def __new__(cls, value, currency: str = "USD"):
        # Reject string amounts that could be misinterpreted
        if isinstance(value, str):
            try:
                value = float(value.replace("$", "").replace(",", ""))
            except ValueError:
                raise TypeError(f"Cannot parse '{value}' as a currency amount")
        if currency == "USD" and value > 1_000_000:
            raise TypeError(f"Amount ${value:,.2f} exceeds single-transaction limit")
        return super().__new__(cls, value)
```

### 4. Capture the parameter→outcome lineage in traces

Add structured metadata to every tool call span that captures what the model thought it was doing:

```python
span.set_attributes({
    "tool.param.user_id": params["user_id"],
    "tool.param.order_id": params["order_id"],
    "tool.validation.status": validation_result["status"],
    "tool.validation.errors": validation_result.get("errors", []),
    "tool.hint_provided": bool(validation_result.get("hint")),
    "genai.tool_call.reasoning": model_reasoning_snapshot,
})
```

This makes it possible to answer: "was the tool called with the right arguments?" — not just "was the tool called?"

### 5. Human-in-the-loop gate for high-stakes parameters

For actions with irreversible consequences (refunds, data deletion, financial transfers), require human confirmation when parameter values exceed defined confidence thresholds. The agent surfaces the call with its reasoning; the human approves before execution.

```python
HIGH_STAKES_TOOLS = {"issue_refund", "delete_user", "transfer_funds", "update_permissions"}

def route_tool(tool_name: str, params: dict, risk_score: float):
    if tool_name in HIGH_STAKES_TOOLS and risk_score > 0.3:
        return {
            "status": "pending_approval",
            "tool": tool_name,
            "params": params,
            "reasoning": model_reasoning,
            "requires_human": True
        }
    return {"status": "execute"}
```

## Detection signals

These are the indicators that your parameter gate is failing:

| Signal | What it means |
|--------|--------------|
| Tool returns 404 on valid-format ID | Model hallucinated an entity ID that passes syntax but not existence check |
| Tool returns 0 results for a query that should match | Wrong field name or wrong operator |
| Tool call succeeds, downstream tool fails | Upstream entity ID was wrong |
| Agent retries same tool 3+ times with identical failure | Parameter gate not translating errors into corrective hints |
| Tool call succeeds, human later flags wrong entity | Semantic parameter was wrong — tool executed on the wrong object |

## The 17-retry pattern

A canonical production failure (Gabriel Anhaia, May 2026): a customer service agent called a database lookup tool that returned truncated JSON (4KB undocumented gateway cap). The model correctly identified the broken response and retried — 17 times. The retries weren't wrong, they were useless: the tool always returned the same truncated payload, and the model always interpreted it as "try again." The loop only ended when the model gave up.

The fix: the parameter gate catches size-anomalous responses and surfaces the signal to the model before the retry loop starts. A `Content-Length` mismatch against the declared schema becomes a structured hint — `"response truncated: expected 12 fields, received 3"` — not another retry.

## Receipt

> Receipt pending — 2026-08-07

## See also

- [S-93 · Tool Side-Effect Idempotency](s93-tool-side-effect-idempotency.md) — idempotency keys prevent duplicate side effects from retries; this entry prevents the retries from happening in the first place
- [S-2199 · The Tool Response Gate Stack](s2199-the-tool-response-gate-stack-when-your-agent-reasons-over-corrupted-output-and-nobody-checks.md) — validates what tools return; S-2276 validates what tools receive
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — retry circuit breakers; S-2276 fixes the retry loop caused by missing parameter-level error translation
