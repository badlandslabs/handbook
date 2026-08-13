# [S-2575] · The Tool Call Schema Failure Stack — When Your Agent Succeeds But Your Tool Doesn't

Your agent called `get_customer_record(id="C-48291")` and received a truncated JSON blob. The upstream gateway has a 4KB response cap nobody documented. The agent correctly identified the blob as broken and retried. The tool returned the same truncated payload. Seventeen retries later, the agent gave up and continued with nothing — or worse, fabricated a plausible record from the fragments. The agent did exactly what it was trained to do. The failure happened at the schema interface, not inside the model. This is the **tool call schema failure problem**: the most common production failure in agentic systems in 2026, and the one no dashboard catches.

## Forces

- **The schema boundary is invisible to both sides.** The model validates output at the schema level. The tool validates nothing — it returns what it returns. When those contracts diverge, the agent reasons correctly from incorrect data and produces confident, wrong tool calls.
- **Tool schemas lie.** A field marked `type: string` accepts any string. The actual upstream API may cap it at 4KB. A field marked `type: array` may silently return a single object. The agent has no way to know the tool's runtime contract differs from its schema.
- **Retries amplify the failure.** Agents are trained to retry on ambiguous responses. A truncated JSON looks like a transient failure — so the agent retries, gets the same truncation, and either loops or invents填补 data. The retry budget burns. The failure becomes permanent.
- **Output validation misses the interface layer.** Standard output evaluation checks whether the agent's final response is correct. It never checks whether the tool call was well-formed, whether the tool response matched the schema, or whether the agent reasoned correctly from what it received.
- **Schema drift is invisible.** Tool implementations change. Upstream APIs change their response shapes without version bumps. The MCP manifest says one thing; the actual server returns another. Nobody logs the delta because there's no contract enforcement layer.

## The Move

### Layer 1 — Schema Pre-Validation Before the Call

Before every tool call, validate the arguments against the actual runtime schema, not just the declared one:

```python
import json, jsonschema

def validate_tool_args(tool_name: str, args: dict, tool_schema: dict) -> dict:
    """Pre-validate tool arguments against declared schema."""
    try:
        jsonschema.validate(args, tool_schema)
    except jsonschema.ValidationError as e:
        # Don't let bad args reach the tool at all
        raise ToolArgumentError(f"{tool_name}: {e.message}") from e

    # Additional runtime contract checks
    for field, constraint in tool_schema.get("x-runtime-constraints", {}).items():
        if field in args:
            value = args[field]
            if "max_length" in constraint and len(str(value)) > constraint["max_length"]:
                raise ToolArgumentError(
                    f"{tool_name}.{field} exceeds runtime max_length "
                    f"{constraint['max_length']}: got {len(str(value))}"
                )
    return args

# Usage in tool dispatcher
def call_tool(tool_name: str, args: dict) -> dict:
    schema = load_tool_schema(tool_name)  # merge declared + runtime contracts
    validate_tool_args(tool_name, args, schema)
    result = _raw_tool_invoke(tool_name, args)
    return result
```

### Layer 2 — Tool Response Validation After the Call

Every tool response must be validated against its expected output schema before the agent reasons on it:

```python
def validate_tool_response(
    tool_name: str, response: dict | str, output_schema: dict
) -> dict:
    """Validate tool response before it reaches the agent's reasoning layer."""
    # Handle truncated responses
    if isinstance(response, str):
        if response.strip().startswith("{") and not response.strip().endswith("}"):
            raise ToolResponseTruncated(
                f"{tool_name} returned truncated JSON — "
                f"length={len(response)}, likely gateway-capped"
            )

    parsed = json.loads(response) if isinstance(response, str) else response

    try:
        jsonschema.validate(parsed, output_schema)
    except jsonschema.ValidationError as e:
        raise ToolResponseSchemaMismatch(
            f"{tool_name} response violates schema: {e.message}\n"
            f"Received keys: {list(parsed.keys())}\n"
            f"Expected: {list(output_schema.get('properties', {}).keys())}"
        ) from e

    # Check for semantic sentinel values
    if parsed.get("error") or parsed.get("status") == "error":
        raise ToolReturnedError(f"{tool_name}: {parsed.get('error')}")

    return parsed
```

### Layer 3 — Truncation Detection and Recovery

The 4KB gateway cap is the canonical failure. Detect it explicitly:

```python
TRUNCATION_SIGNALS = [
    lambda r: isinstance(r, str) and r.strip().startswith("{")
              and not r.strip().endswith("}"),
    lambda r: isinstance(r, str) and r.strip().startswith("[")
              and not r.strip().endswith("]"),
    lambda r: isinstance(r, str) and len(r) > 3500,  # conservative 4KB proxy
    lambda r: isinstance(r, dict) and r.get("_truncated"),
]

def detect_truncation(response) -> bool:
    return any(signal(response) for signal in TRUNCATION_SIGNALS)

def call_tool_with_truncation_recovery(tool_name: str, args: dict) -> dict:
    """Call tool with explicit truncation detection and paginated recovery."""
    schema = load_tool_schema(tool_name)
    validate_tool_args(tool_name, args, schema)

    raw = _raw_tool_invoke(tool_name, args)

    if detect_truncation(raw):
        # Try pagination if tool supports it
        if schema.get("x-supports-pagination"):
            return _fetch_all_pages(tool_name, args, schema)
        # Try streaming if available
        if schema.get("x-supports-streaming"):
            return _stream_tool_response(tool_name, args, schema)
        # Raise with diagnostic context — don't let agent guess
        raise ToolResponseTruncated(
            f"{tool_name} returned truncated response (len={len(raw) if isinstance(raw, str) else 'unknown'}). "
            f"No pagination or streaming available. Do not retry — the tool "
            f"will return the same truncation. Abort this branch."
        )

    return validate_tool_response(tool_name, raw, schema.get("output_schema"))
```

### Layer 4 — Retry Discipline with Exhaustion Detection

When retries are needed, make them count and know when to stop:

```python
MAX_TOOL_RETRIES = 2  # far lower than the 17 retries in the wild

def call_tool_with_disciplined_retry(tool_name: str, args: dict) -> dict:
    errors = []
    for attempt in range(MAX_TOOL_RETRIES + 1):
        try:
            return call_tool_with_truncation_recovery(tool_name, args)
        except ToolResponseTruncated as e:
            if "Do not retry" in str(e):
                raise  # already told you not to retry
            errors.append(f"attempt_{attempt}: {e}")
        except (TimeoutError, ConnectionError) as e:
            errors.append(f"attempt_{attempt}_timeout: {e}")
        except Exception as e:
            errors.append(f"attempt_{attempt}_unknown: {e}")

    # All retries exhausted — raise with full diagnostic trail
    raise ToolCallExhausted(
        f"{tool_name} failed after {MAX_TOOL_RETRIES + 1} attempts.\n"
        f"Error trail: {'; '.join(errors)}\n"
        f"Do not fabricate a response. Return an error to the user."
    ) from None
```

### Layer 5 — Instrument the Schema Delta

Track where declared schemas diverge from actual tool behavior:

```python
from collections import defaultdict

schema_drift_log = defaultdict(list)

def log_schema_drift(tool_name: str, event: dict):
    """Track declared vs actual schema divergence for remediation."""
    schema_drift_log[tool_name].append({
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event["type"],  # "truncation", "type_mismatch", "field_missing"
        "declared_schema": event.get("declared"),
        "actual_behavior": event.get("actual"),
        "caller": event.get("caller"),
    })

# Alert on recurring drift patterns
def report_schema_drift():
    for tool, events in schema_drift_log.items():
        if len(events) >= 3:
            unique_types = {e["event_type"] for e in events[-10:]}
            if len(unique_types) > 1:
                yield {
                    "tool": tool,
                    "drift_count": len(events),
                    "drift_types": list(unique_types),
                    "severity": "HIGH" if len(events) >= 10 else "MEDIUM"
                }
```

## Receipt

> Verified 2026-08-13 — Sources: Waxell AI blog (July 24, 2026, 17-retry case study), OWASP LLM Top 10 (LLM05: Output Validation Failure), Microsoft Developer Blog (April 2025, MCP indirect injection), Supergood Solutions case study (April 9, 2026), DellonS enterprise survey (July 4, 2026). Pattern validated against handbook coverage audit: S-816 (Silent Pipeline) covers output validation at the model call boundary; S-2574 (Semantic Failure) covers the agent reasoning layer. Neither covers the tool-call/schema interface failure mode at the dispatch layer. Code patterns are architectural illustrations based on documented production patterns — Receipt pending execution in live agent harness.

## See also

- [S-816 · The Silent Pipeline](stacks/s816-the-silent-pipeline-output-validation-beyond-the-model-call.md) — output validation beyond the model call boundary
- [S-2574 · The Semantic Failure Stack](stacks/s2574-the-semantic-failure-stack-when-your-agent-succeeds-but-gets-it-wrong.md) — when the agent succeeds but gets it wrong
- [S-2571 · The Circuit Breaker Stack](stacks/s2571-the-circuit-breaker-stack-when-nothing-stops-a-failing-agent.md) — retry discipline and failure amplification
- [S-1021 · The MCP Apps Stack](stacks/s1021-the-mcp-apps-stack-when-your-tool-returns-a-form-not-a-paragraph.md) — MCP tool return surface
