# S-1785 · The Schema Entropy Stack — When Your Tool Definition Freezes but the API Doesn't

You shipped your agent three months ago. The tool schema is identical. The agent calls the same endpoint with the same parameters. But the API started returning a new field six weeks ago, and now the agent silently ignores it. Or the API changed a required parameter from snake_case to camelCase and your agent's output looks valid but the downstream system silently drops the payload. No errors. No retries. The schema document didn't change. The tool kept working. The interface quietly broke. This is schema entropy — the invisible rot that turns working agents into wrong agents.

## Forces

- **Tool schemas don't have to be edited to become wrong.** The services they describe change underneath them. A schema pinned three months ago describes a version of the API that no longer exists in production.
- **~60% of production agent failures trace to tool versioning issues** (Tianpan.co, April 2026) — not model degradation, not prompt drift, not context overflow, but the gap between the tool definition and the tool's actual behavior.
- **Agents are confident with broken interfaces.** Unlike humans who notice an unfamiliar response format, a model keeps generating the same tool calls and interpreting the new response through the old lens. Confidence doesn't correlate with correctness at tool interfaces.
- **The schema document gives no entropy signal.** It looks identical. The agent is still calling the same function. The only symptom is slowly degrading output quality — which looks like a model problem until you audit the actual API traffic.
- **Hard breaks (4xx errors, missing required fields) are visible. Silent breaks (semantic drift, new optional fields, format changes) are invisible.** The dangerous failures are the ones that don't raise exceptions.

## The move

**Schema entropy has three phases — each requires a different intervention.**

### Phase 1: Freeze detection (passive)

Pin API schemas at deploy time. Compare the live API response schema against the pinned schema on every run — not the agent's output, the raw API response. A diff against the registered schema, not the model's interpretation.

```python
import json, jsonschema

def detect_schema_entropy(tool_name: str, live_response: dict, pinned_schema: dict) -> dict:
    """Compare live API response against the schema the agent was trained on."""
    violations = []
    try:
        jsonschema.validate(live_response, pinned_schema)
    except jsonschema.ValidationError as e:
        violations.append({"type": "missing_required", "path": list(e.path), "message": e.message})
    # Detect new fields not in pinned schema
    for field in live_response:
        if field not in pinned_schema.get("properties", {}):
            violations.append({"type": "unknown_field", "field": field, "action": "log_suspicious"})
    return {"tool": tool_name, "entropy_detected": bool(violations), "violations": violations}
```

### Phase 2: Version-aware tool surface

Tag every tool definition with a `schema_version` and a `pinned_at` timestamp. When the underlying API updates, increment the version. The agent gets the new schema; old sessions using the old schema are flagged for review.

```json
{
  "name": "get_customer_order",
  "description": "Retrieve a customer order by ID",
  "schema_version": "2.1.0",
  "pinned_at": "2026-04-01",
  "parameters": {
    "type": "object",
    "properties": {
      "order_id": { "type": "string", "description": "UUID of the order" },
      "include_line_items": { "type": "boolean", "description": "Include itemized products", "default": false }
    }
  }
}
```

### Phase 3: Semantic canary (active)

For high-stakes tools, add a canary call to a known state before the main call. The agent validates the response shape and critical field values against expected canary output before acting on a real call. If the canary returns a response the agent can't parse or that contradicts the canary baseline, halt and alert.

```python
def semantic_canary(tool_name: str, test_payload: dict, expected_keys: list[str]) -> bool:
    """Probe a tool with a known input; validate response hasn't drifted semantically."""
    result = call_tool(tool_name, test_payload)
    for key in expected_keys:
        if key not in result:
            raise SchemaEntropyError(f"{tool_name}: expected key '{key}' missing after schema drift")
    return True
```

**The three structural fixes:**
1. **Schema diffing at runtime** — not diffing the agent's output, diffing the raw API response against the pinned definition. This catches drift that the model would never surface.
2. **Version pinning with auto-invalidation** — schema_version in every tool definition; sessions using stale schemas get flagged, not silently continued.
3. **Canary probing before high-stakes calls** — known input, known output, cross-checked before real execution. The canary breaks before the agent acts on the drifted response.

## Receipt

> Verified 2026-07-28 — Researched against Tianpan.co (Schema Entropy, April 15 2026), Zylos AI context compression survey (Feb 2026), StackNotice enterprise pilot failure analysis (July 2026), Microsoft Semantic Kernel CVE research (May 2026), ExploitGym multi-agent security study. Schema entropy (~60% of production failures) confirmed as distinct from tool poisoning (S-1703), tool surface reliability (S-1631), and tool interface ambiguity (S-1419). Those entries cover security and ambiguity; this covers temporal API drift under frozen schemas. No prior entry addresses the frozen-schema / live-API gap.

## See also

[S-1419 · The Agent Tool Interface Stack](s1419-the-agent-tool-interface-stack-when-your-agent-calls-the-right-tool-and-gets-the-wrong-answer.md) — tool output format ambiguity and error handling  
[S-1631 · The Agent Tool Surface Stack](s1631-the-agent-tool-surface-stack-when-your-agent-has-every-tool-but-reliability.md) — MCP ecosystem quality and tool trust scoring  
[S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — schema version conflicts in multi-agent handoffs  
[S-1779 · The Agent Longevity Stack](s1779-the-agent-longevity-stack-when-your-agent-runs-fine-on-monday-and-brittle-by-friday.md) — longitudinal degradation from environmental drift
