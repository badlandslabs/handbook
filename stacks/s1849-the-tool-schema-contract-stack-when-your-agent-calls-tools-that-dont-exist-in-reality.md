# S-1849 · The Tool Schema Contract Stack: When Your Agent Calls Tools That Don't Exist in Reality

[Your agent's tool definitions are a contract. The API behind them is another. When those two diverge — and they always diverge — your agent doesn't fail loudly. It fails by inventing parameters, hallucinating IDs, and shipping wrong data to real systems. This entry is about keeping the contract honest at production scale.]

## Forces

- [S-03 Tool Use](s03-tool-use.md) covers how to define tools and call them. It doesn't cover what happens when the definition and the reality diverge over time.
- [S-10 MCP](s10-mcp.md) standardizes tool discovery but not tool contract integrity — the schema can drift from the implementation without anyone noticing.
- Tool schema drift is silent: the agent doesn't error, it just confidently sends wrong data to a live system.
- Every schema mismatch is a potential data corruption event, not just a tool-call failure.
- The model generates tool calls based on natural-language descriptions and example schemas — it has no way to know if the actual API backend accepts `user_id` or `uid` or `userId`.

## The move

### The four mismatch modes

**1. Field name drift.** The schema says `user_id`; the API expects `uid`. The model follows the schema and the API returns 422. This is the most common mode — it appears in 30–40% of production MCP integrations after any API version bump.

**2. Type coercion collapse.** The schema says `amount: "string"` (common when JSON Schema is hand-written); the API expects `amount: "number"`. Depending on the API framework, this either throws a 400 or silently truncates values like `"29.99"` → `29`. Your agent happily continues with a corrupted ledger entry.

**3. Required field inflation.** The API team added a new required field `idempotency_key` to the payment endpoint. Your tool schema still lists it as optional. The model omits it. The payment succeeds but is non-idempotent — a retry creates a duplicate charge. No error, no alert, just a duplicate payment.

**4. Enum ghost values.** The schema defines `status: ["pending", "processing", "done"]` from three months ago. The API backend added `"cancelled"` and `"refunded"`. The model generates `"refunded"` — not in the schema's enum. The API accepts it (relaxed validation) or rejects it with an unexpected value. Either way, the agent's world model of valid states is wrong.

### The mitigation stack

**A. Schema-first tool definition with a lint gate.**
Generate the schema from the API spec (OpenAPI/JSON Schema) rather than hand-writing it. Every schema is a derived artifact, not a hand-maintained one.

```python
import json
from openapi_schema_validator import validate
from prance import ResolvingParser

def get_tool_schema(tool_name: str) -> dict:
    """Derive tool schema from OpenAPI spec — no hand-maintained schemas."""
    spec = ResolvingParser("openapi.yaml").specification
    path = find_path_for_tool(spec, tool_name)
    op = spec["paths"][path]["post"]  # or appropriate method
    return {
        "name": tool_name,
        "description": op["summary"],
        "input_schema": op["requestBody"]["content"]["application/json"]["schema"]
    }

def validate_tool_call(tool_name: str, params: dict) -> dict:
    """Gate: reject mismatched params before they reach the API."""
    schema = get_tool_schema(tool_name)
    try:
        validate(params, schema["input_schema"])
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": str(e), "params": params}
```

**B. Shadow-mode parameter validation before production calls.**
Run the tool call against a test/mock endpoint first with the exact parameters the model generated. Only route to the real API if the mock returns 2xx.

```python
def safe_tool_call(tool_name: str, params: dict, dry_run: bool = True):
    if dry_run:
        mock_result = mock_tool_endpoint(tool_name, params)
        if mock_result.status_code >= 400:
            # Block the call, surface the mismatch to the agent
            return {"blocked": True, "api_error": mock_result.json(), "params": params}
    return real_tool_call(tool_name, params)
```

**C. Schema fingerprinting with drift alerts.**
Track a hash of each tool's current schema. If the schema changes (API update, MCP server version bump), alert before the agent runs. This catches Mode 3 and Mode 4 drift proactively.

```python
import hashlib, json

def schema_fingerprint(schema: dict) -> str:
    # Normalize then hash — ignore ordering differences
    normalized = json.dumps(schema, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]

def check_schema_drift(tool_name: str, current_schema: dict, baseline: dict) -> list[str]:
    """Return list of field-level changes between baseline and current."""
    baseline_fields = set(flatten_schema(baseline))
    current_fields = set(flatten_schema(current_schema))
    added = current_fields - baseline_fields
    removed = baseline_fields - current_fields
    type_changes = detect_type_changes(baseline, current_schema)
    return [f"+ {a}" for a in added] + [f"- {r}" for r in removed] + type_changes
```

**D. Enum-aware prompt injection — inject the live enum values into the tool description at runtime.**
Don't bake enum values into the schema and forget them. Pull them fresh from the API on each agent session init.

```python
def refresh_tool_enum(tool_name: str) -> dict:
    """Replace static enum values in schema with live values from the API."""
    schema = get_tool_schema(tool_name)
    for field, spec in find_enum_fields(schema).items():
        live_values = fetch_enum_values(tool_name, field)  # GET /schema/enums/{field}
        spec["enum"] = live_values
    return schema
```

### The architectural principle

**Tools are not functions — they are contracts with a remote system.** The contract has two authors: the schema (what the agent sees) and the API (what actually happens). When they disagree, the agent trusts the schema and the API punishes it.

The fix is not "better prompts." It's: make the schema a derived artifact of the API spec, validate against it before every call, track its fingerprint for drift, and keep enum values live. This turns the tool layer from a source of silent failure into a governed contract surface.

## Receipt

> Verified 2026-07-30 — Compiled from: Presenc AI Tool-Calling Benchmarks 2026 (Berkeley BFCL data, parameter-mismatch rates); meritshot.com (March 2026, four mismatch modes); Composio 2026 Integration Report (brittle API connectors, schema drift as top-3 failure cause); qveris.ai (JSON Schema in function calling); agentpatterns.ai (strict mode enforcement); GitHub VoltAgent issue #1195 (schema mismatch as a live bug).

## See also

- [S-03 · Tool Use](s03-tool-use.md) — foundational tool definition patterns
- [S-10 · MCP](s10-mcp.md) — the protocol for tool discovery and exposure
- [S-22 · Tool Selection at Scale](s22-tool-selection-at-scale.md) — selecting the right tool, not just calling it correctly
- [S-1240 · The Reliability Multiplication Law](s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — why per-step failures compound
- [S-1834 · The Partial Output Termination Stack](s1834-the-partial-output-termination-stack-when-your-agent-confidently-completes-a-task-it-only-half-did.md) — the symptom: confident completion on broken tool calls
