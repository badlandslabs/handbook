# S-2835 · The Silent Coercion Stack — When Your Tool Accepts Wrong Arguments and Returns Wrong Data

A customer service agent calls a user lookup tool with `user_id: "abc123"`. The parameter should be numeric. The API coerces the string to `0`, finds no match, returns an empty result — not an error. The agent sees "no user found" and takes the next action as if the user doesn't exist. The tool never complained. The response code was 200.

This is **silent coercion**: the most dangerous failure mode in production tool calling because nothing breaks, nothing errors, and the agent trusts the output completely. The gap between "wrong arguments that raise errors" (S-833) and "wrong arguments that silently return wrong data" is where real systems quietly fail at scale.

## Forces

- **Parameter-mismatch errors outnumber wrong-tool selection in production.** BFCL v3 benchmark data (May 2026) shows 60–75% of tool-calling failures at scale are argument errors, not routing errors. A 90% per-call accuracy compounds to 59% at five calls — most of those drops are argument failures, not tool-selection failures.
- **37% of tool calls have parameter mismatches that never raise errors.** A 72-hour trace of a Claude agent in production (QVeris, 2026) found over a third of mismatched parameters were silently coerced or ignored — no exception fired, no HTTP error returned, the response looked legitimate.
- **Coercion is invisible in single-step tests.** Schema validation passes. JSON parses. The API accepts the payload. You only discover the coercion when you compare what the agent asked for against what it got back — a cross you can't do at call time without a pre/post validator.
- **Agents propagate coerced output downstream as fact.** Once the tool returns a 200, the agent treats it as ground truth and reasons forward from it. The corrupted data becomes the substrate for every subsequent decision.

## The move

**1. Pre-call schema guard — validate before dispatch.**
```python
from pydantic import BaseModel, ValidationError

class ToolCallGuard:
    def __init__(self, schema: dict):
        self.schema = schema

    def validate(self, tool_name: str, args: dict) -> list[str]:
        errors = []
        for param, spec in self.schema.get(tool_name, {}).items():
            if param not in args and spec.get("required"):
                errors.append(f"Missing required: {param}")
            elif param in args:
                expected = spec.get("type")
                actual = type(args[param]).__name__
                if expected == "integer" and not isinstance(args[param], int):
                    try:
                        int(args[param])
                    except (ValueError, TypeError):
                        errors.append(f"{param}: expected int, got {actual}")
        return errors

guard = ToolCallGuard({
    "get_user": {
        "user_id": {"type": "integer", "required": True}
    }
})

issues = guard.validate("get_user", {"user_id": "abc123"})
if issues:
    raise ValueError(f"Pre-call validation failed: {issues}")
```

**2. Semantic pre-condition checks — the API won't catch these, you must.**
```python
# A date range tool that accepts start > end and silently returns empty
if args.get("start_date") and args.get("end_date"):
    if args["start_date"] > args["end_date"]:
        raise ValueError("start_date must be before end_date")

# Enum coercion: "active" vs "Active" vs "1" — all coerce differently
VALID_STATUSES = {"active", "inactive", "pending"}
if args.get("status", "").lower() not in VALID_STATUSES:
    raise ValueError(f"status must be one of {VALID_STATUSES}, got: {args['status']}")
```

**3. Output contradiction check — catch what the API didn't.**
```python
def validate_response(call_args: dict, response: dict) -> None:
    """Post-call: did the response contradict what we asked for?"""
    # Asked for user_id=42, got user_id=0 — silently coerced
    if "user_id" in call_args and response.get("user_id") == 0:
        if call_args["user_id"] != 0:
            raise ValueError(
                f"Coercion detected: requested user_id={call_args['user_id']}, "
                f"got back user_id=0 — API likely coerced string to 0"
            )

    # Asked for ≥1 results, got empty for non-optional query
    if call_args.get("required", False) and not response.get("results"):
        raise ValueError("required query returned empty — possible parameter coercion")

    # Range coercion: asked for 10 items, got 0 — silently treated as 0-limit
    if "limit" in call_args and response.get("count", 1) == 0:
        if call_args["limit"] > 0:
            raise ValueError(f"limit={call_args['limit']} returned 0 results — possible coercion to limit=0")
```

**4. Tool response wrapper — wrap every tool with validation by default.**
```python
import functools

def wrapped_tool(tool_fn, schema: dict, name: str):
    @functools.wraps(tool_fn)
    def wrapper(args: dict):
        # Pre-validate
        guard = ToolCallGuard(schema)
        issues = guard.validate(name, args)
        if issues:
            raise ValueError(f"Pre-call validation failed for {name}: {issues}")

        # Execute
        response = tool_fn(args)

        # Post-validate (contradiction check)
        validate_response(args, response)

        return response
    return wrapper
```

## Receipt

> Verified 2026-08-18 — BFCL v3 (May 2026): parameter-mismatch errors represent 60–75% of production tool-calling failures vs. wrong-tool selection. QVeris 72-hour production trace (2026): 37% of tool calls had mismatched parameters that passed silently. Gabriel Anhaia production trace (May 2026): 17-retries caused by truncated response the model correctly identified as broken but couldn't recover from — the failure was in the output contract, not the model's handling.

## See also

- [S-833 · The Tool-Validation Stack — When Agents Call the Right Tool with Fabricated Args](s833-the-tool-validation-stack-when-agents-call-the-right-tool-with-fabricated-args.md) — explicit validation failures (this entry covers the silent-coercion sibling)
- [S-2199 · The Tool-Response Gate Stack — When Your Agent Reasons Over Corrupted Output](s2199-the-tool-response-gate-stack-when-your-agent-reasons-over-corrupted-output-and-nobody-checks.md) — downstream response validation
- [S-2605 · The Tool Description Engineering Stack — Where Your Tool Selection Decisions Get Made](s2605-the-tool-description-engineering-stack-when-your-system-prompt-is-not-where-your-tool-selection-decisions-get-made.md) — the upstream description layer
