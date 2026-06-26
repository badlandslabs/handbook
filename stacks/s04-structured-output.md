# S-04 · Structured Output

Make the model return JSON (or any typed schema) that your code can consume without parsing guesswork.

## Forces
- LLMs generate text — downstream code needs data structures
- Prompt-based "return JSON" is brittle; the model may add markdown fences, prose preambles, or invalid keys
- Strict JSON mode breaks on complex schemas if the model isn't guided
- Overly rigid schemas reduce quality — the model hedges to fit the format

## The move

Two approaches, in order of preference:

**1. Tool use as structured output** — define a tool whose sole job is to return structured data. The model must call the tool to "answer," so the output is always valid.

```python
schema_tool = {
    "name": "extract_person",
    "description": "Extract person details from text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "email": {"type": "string"}
        },
        "required": ["name"]
    }
}
# Pass as tool, set tool_choice to force the call
response = client.messages.create(
    model="claude-sonnet-4-6",
    tools=[schema_tool],
    tool_choice={"type": "tool", "name": "extract_person"},
    messages=[{"role": "user", "content": text}]
)
```

**2. JSON mode prompt** — when tool use isn't available:
```
Return ONLY valid JSON with these fields: {"name": string, "age": integer}.
No markdown. No prose. No explanation.
```

**Rules:**
- Prefer tool use over prompt-based JSON — it's enforced at the API level
- Keep schemas flat where possible; deeply nested objects increase error rates
- Validate and retry on schema mismatch — one retry fixes most cases

## Receipt
> Receipt pending — 2026-06-25. Tool use schema pattern follows Anthropic API docs. `tool_choice` forcing is documented but needs live verification.

## See also
[S-03](s03-tool-use.md) · [S-05](s05-multi-agent-patterns.md) · [S-10](s10-mcp.md)

## Go deeper
Keywords: `JSON mode` · `tool_choice` · `Pydantic AI` · `Instructor library` · `output validation` · `schema enforcement`
