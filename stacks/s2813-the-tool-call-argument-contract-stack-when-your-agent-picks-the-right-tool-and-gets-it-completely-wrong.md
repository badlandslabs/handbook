# S-2813 · The Tool-Call Argument Contract Stack — When Your Agent Picks the Right Tool and Gets It Completely Wrong

Your agent correctly identified it needs to `transfer_funds`. It called `transfer_funds` with `amount: -1` and `recipient_id: "". Your backend accepted both silently. The agent confidently reported success. This is not a tool-selection failure. This is an argument contract failure — and it is far more common than teams realize.

## Forces

- **The schema is advisory, not enforced.** Most tool schemas are documentation with types attached. The model generates arguments against the schema description. Nothing validates those arguments before dispatch.
- **Type coercion makes invalid look valid.** A string `"$49.99"` passed where a float is expected may coerce silently in some backends and error in others. The agent never learns which.
- **Silent failures are worse than noisy ones.** A 500 produces a retry. An HTTP 200 with an empty payload produces a confident "done."
- **The agent has no feedback loop on argument quality.** Unlike a human who would catch `amount=-1`, the model doesn't "feel" that the argument is wrong — it follows the conversation's implicit math.
- **Blanket retry logic is a cost multiplier, not a fix.** Retrying a call with invalid arguments just burns tokens and delays human escalation.

## The move

**Treat tool-call arguments as a typed API contract enforced at runtime — not at inference time.**

### 1. Validate before dispatch, not after failure

```python
from pydantic import BaseModel, field_validator, conint
from typing import Literal

class TransferFundsArgs(BaseModel):
    recipient_id: str
    amount: conint(gt=0)          # Rejects negative, zero
    memo: str | None = None

    @field_validator("recipient_id")
    @classmethod
    def non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("recipient_id cannot be blank")
        return v

def validate_and_dispatch(tool_name: str, args: dict) -> dict:
    schema = TOOL_SCHEMAS[tool_name]          # Pydantic model per tool
    validated = schema.model_validate(args)   # Raises on bad args
    return dispatch(tool_name, validated.model_dump())
```

### 2. Classify failures by recovery path — not all retries are equal

| Failure class | Signal | Correct response |
|---|---|---|
| **Schema validation** (wrong type, missing required, constraint violation) | `ValidationError` from validator | Fix args + retry once; if still invalid → escalate |
| **Semantic** (right type, wrong value for domain) | Custom validator catches `amount=-1` | Never retry — escalate immediately |
| **Tool unavailability** | HTTP 503, timeout | Retry with backoff |
| **Silent null-return** | HTTP 200, empty body | Retry with timeout; escalate if persists |

### 3. Log the argument fingerprint

```python
import hashlib, json

def dispatch_with_audit(tool_name: str, raw_args: dict) -> dict:
    fingerprint = hashlib.sha1(
        json.dumps(raw_args, sort_keys=True).encode()
    ).hexdigest()[:8]

    logger.info("tool_dispatch", extra={
        "tool": tool_name,
        "args_hash": fingerprint,
        "args_keys": list(raw_args.keys()),
        # Never log args in plaintext — they may contain PII
    })

    result = validate_and_dispatch(tool_name, raw_args)

    logger.info("tool_result", extra={
        "tool": tool_name,
        "args_hash": fingerprint,
        "status": result.get("status"),
    })
    return result
```

### 4. Enforce at the gateway layer

For MCP and HTTP-based tool dispatch, validate at the gateway — not inside the tool handler:

```python
# MCP Gateway (or HTTP proxy in front of tools)
class ToolGateway:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def dispatch(self, tool: str, args: dict) -> dict:
        if tool not in self.registry:
            raise ToolNotFoundError(tool)

        model = self.registry.schema_model(tool)
        try:
            validated = model.model_validate(args)
        except ValidationError as e:
            # Log, alert, and surface to the agent
            raise ToolArgumentContractViolation(tool, e.errors())

        return await self.registry.execute(tool, validated.model_dump())
```

### 5. Give the agent structured feedback on argument failures

```python
class ToolArgumentContractViolation(Exception):
    def __init__(self, tool: str, errors: list[dict]):
        self.tool = tool
        self.errors = errors
        self.hint = self._build_hint(errors)

    def _build_hint(self, errors: list[dict]) -> str:
        lines = []
        for e in errors:
            loc = ".".join(str(l) for l in e["loc"])
            lines.append(f"  - {loc}: {e['msg']} (got {e['input']!r})")
        return f"Argument errors for {self.tool}:\n" + "\n".join(lines)

# In agent loop:
try:
    result = gateway.dispatch(tool, args)
except ToolArgumentContractViolation as e:
    return f"Tool call failed: {e.hint}\nPlease retry with corrected arguments."
```

## Receipt

> Verified 2026-08-18 — The pattern was validated against the taxonomy from AgentMarketCap (April 2026) and Harness Engineering's tool-calling reliability guide. The three-column failure classification (schema / semantic / availability) maps directly to their documented failure categories. The Pydantic validation pattern is standard production Python (v2.x). Gateway-layer enforcement was documented by PADISO in their MCP Gateway analysis (July 2026), where the airlock prototype blocked 12/12 malformed payloads at the contract layer with 0 false positives.

## See also

- [S-1849 · The Tool Schema Contract Stack](stacks/s1849-the-tool-schema-contract-stack-when-your-agent-calls-tools-that-dont-exist-in-reality.md) — schema drift and wrong tool selection
- [S-2630 · The Description-Code Divergence Stack](stacks/s2630-the-description-code-divergence-stack-when-your-mcp-tool-description-is-not-your-tool-interface.md) — the description/implementation gap that causes these failures
- [S-2794 · The MCP Transport Lifecycle Stack](stacks/s2794-the-mcp-transport-lifecycle-stack-when-your-agent-stops-working-and-nobody-told-it-the-server-was-gone.md) — transport-layer failures that look like tool failures
