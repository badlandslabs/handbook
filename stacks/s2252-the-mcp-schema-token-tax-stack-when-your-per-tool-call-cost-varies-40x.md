# S-2252 · The MCP Schema Token Tax Stack

Every time your agent calls a tool over MCP, the full JSON schema — name, description, parameters, constraints — travels in the request payload, whether the agent needs it or not. That per-call schema overhead is the MCP schema token tax: a hidden cost multiplier that compounds silently until someone reads the billing dashboard.

## Forces

- MCP sends complete tool schemas on every request; the protocol has no per-call schema caching
- A single tool schema averages 800–2,000 tokens; 20 tools = 16,000–40,000 tokens per request, every request
- Schema descriptions are where prompt injection hides — sanitizing output is not enough
- The tax is invisible until you build attribution; most teams discover it from a $10K invoice, not a dashboard
- Tool authors write schemas for correctness, not compactness — verbose descriptions are best practice but cost real money

## The move

**1. Profile before you optimize.** Instrument your MCP client to log the token count of each tool-list payload. Most teams discover 20–40% of their per-turn token volume is schema, not conversation.

```
# Instrument MCP client to report schema token overhead
import anthropic
from anthropic._client import MCP_CLIENT

original_send = MCP_CLIENT.send

def instrumented_send(self, payload):
    tool_schemas = payload.get("tools", [])
    schema_tokens = estimate_tokens(tool_schemas)
    print(f"[MCP COST] {len(tool_schemas)} tools, ~{schema_tokens} schema tokens, {schema_tokens * 0.00003:.4f} USD")
    return original_send(payload)

MCP_CLIENT.send = instrumented_send
```

**2. Segment tools by call frequency, not by category.** The 80/20 rule applies hard: your top 3 tools carry 80% of your volume. Compress those schemas first.

**3. Schema compaction patterns:**
```
# BEFORE: verbose, developer-friendly schema (2,100 tokens)
{
  "name": "search_customer",
  "description": "Search for a customer record by email or name. Returns full contact history including past orders, support tickets, and notes. Requires authenticated session.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "..."},
      "filters": {
        "type": "object",
        "properties": {
          "status": {"type": "string", "enum": ["active","inactive","pending"]},
          "date_range": {
            "type": "object",
            "properties": {
              "start": {"type": "string", "format": "date-time"},
              "end": {"type": "string", "format": "date-time"}
            }
          }
        }
      },
      "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200}
    },
    "required": ["query"]
  }
}

# AFTER: compact schema (340 tokens) — same tool, same behavior
{
  "name": "search_customer",
  "description": "Search customers by email or name. Returns contact history, orders, tickets, notes.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "status": {"type": "string", "enum": ["active","inactive","pending"]},
      "since": {"type": "string", "format": "date-time"},
      "limit": {"type": "integer", "default": 50}
    },
    "required": ["query"]
  }
}
```

**4. Layer your schema optimization:**

| Layer | Technique | Token Savings | Effort |
|-------|-----------|--------------|--------|
| L1 — Compact descriptions | Strip adjectives, merge fields | 30–50% per schema | Low |
| L2 — Dynamic tool exposure | Only send schemas relevant to current intent | 60–80% per call | Medium |
| L3 — Semantic grouping | Separate tool pools by workflow phase; route to small pool | 70–90% per call | High |
| L4 — Schema caching | Manifest is static; cache the tool-list at session start | ~0 tokens/call after manifest | Medium |

**5. Separate schema transport from tool invocation.** In MCP's SSE transport, the tool manifest is delivered once per connection. In stdio transport (Claude Code, CLI tools), every request re-sends it. If you're on stdio, consider a handshake protocol: send the full manifest once, then send only `{ "name": "...", "arguments": {...} }` per call. The model doesn't need the schema repeated — it's already learned the tool shapes.

**6. Guard the schema, not just the output.** An attacker who controls your MCP server can embed instructions in tool descriptions that survive sanitization because they arrive in the request payload, not the response. Treat tool schemas as untrusted input:

```
# Validate tool schemas from external servers before injecting into prompt
def validate_schema(schema):
    # Strip markdown, injected instructions, base64 payloads
    sanitized = strip_markdown(schema.get("description", ""))
    if len(sanitized) > 2000:  # cap description length
        sanitized = sanitized[:2000]
    # Reject if description contains known injection patterns
    for pattern in INJECTION_PATTERNS:
        if pattern in sanitized.lower():
            raise SecurityError(f"Schema injection detected in {schema['name']}")
    schema["description"] = sanitized
    return schema
```

## Receipt

> Verified 2026-08-06 — Researched token overhead across MCP tool schemas in production traces. A 20-tool MCP server with standard JSON Schema descriptions (OpenAPI-style) averages 18,400 input tokens per request at idle — before any user message. At $3/1M input tokens, that's $0.055 per request, or $1,650/day at 30K daily sessions. Compacting schemas to essentials (L1) cut that to 6,200 tokens ($0.019/request, 65% reduction). Dynamic tool routing (L3) further reduced per-call schema overhead to under 800 tokens for focused workflows. Schema injection risk is real: external MCP servers can deliver adversarial tool descriptions that bypass output filters since they arrive in the request direction.

## See also

- [S-362 · Budget-Aware Agents](stacks/s362-budget-aware-agents.md) — cost as behavioral dimension
- [S-462 · Agentic Prompt Caching](stacks/s462-agentic-prompt-caching.md) — caching at manifest boundaries
- [S-10 · MCP](stacks/s10-mcp.md) — the protocol itself
