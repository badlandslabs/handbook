# S-2355 · The Tool-Use Hallucination Taxonomy Stack — When the Agent Calls the Wrong Tool and Thinks It Won

A model that generates correct-sounding text but cites non-existent sources is a well-known problem. A model that calls a non-existent function, passes the wrong arguments, or routes a database query to the wrong table is a production incident. Tool-use hallucinations — errors in the *selection*, *parameter construction*, or *output interpretation* of tool invocations — are the dominant failure mode in production agents, and they have resisted every round of fine-tuning. This is the tool-use hallucination taxonomy: the distinct subtypes, why they persist, and the mitigation stack.

## Forces

- **The tool-call hallucination plateau.** Eighteen months of targeted fine-tuning, billions of tool-use training examples, and dedicated function-calling benchmarks on every major model release — and production agents still fumble roughly one in twenty tool invocations. BFCL (Berkeley Function-Calling Leaderboard) scores plateau around 85-90% even on frontier models. The remaining 10-15% is not random noise — it clusters into specific, predictable failure modes.
- **Hallucination subtypes have different causes and different cures.** Treating all tool errors as the same problem leads to generic mitigations that fix nothing. Tool-selection hallucination (calling the wrong tool) has different root causes than parameter hallucination (wrong arguments), solvability hallucination (calling a tool when none exists), or output interpretation hallucination (reading the right output wrong). Each requires a different detection and prevention strategy.
- **Error visibility is inversely correlated with damage.** The subtler the hallucination, the more damage it causes. A missing tool is obvious. A slightly wrong SQL WHERE clause that returns the wrong customer segment looks plausible. A tool that returns data in a format the model misparses produces confident wrong answers.

## The move

The taxonomy has four primary subtypes, each with a distinct mechanism and mitigation:

### 1. Tool-Selection Hallucination — "Call the Wrong Tool"

The model selects an available-but-incorrect tool instead of the correct one. Caused by: tool descriptions that are too similar, ambiguous task framing, or the model optimizing for plausible-sounding names over correct semantics. BFCL studies show selection error rates of 3-8% even on top-performing models.

**Mitigation:**
- **Distinctive, unambiguous tool names** — `send_email` vs `send_invoice` look similar; `dispatch_payment` vs `record_payment` are distinct
- **Semantic tool routing** with a classifier layer that pre-selects candidates before the LLM picks from a narrow set
- **Tool description anchoring** — place the most discriminative capability at the start of each description

### 2. Incorrect-Argument Hallucination — "Right Tool, Wrong Params"

The model calls the correct tool but with wrong, missing, or hallucinated arguments. The core mechanism: LLMs predict tokens, not values. When a required argument isn't in the conversation context, the model often generates a plausible token sequence rather than saying "I don't know." Particularly severe for: dates, IDs, enum values, and computed quantities.

**Mitigation:**
- **Strict schema enforcement** — JSON Schema with `enum` constraints, `minimum`/`maximum` bounds, and regex patterns reduce the hallucination surface
- **Required-field gating** — reject calls with missing required arguments before execution, not after
- **Value pre-validation** — for ID/date/enum arguments, fetch the valid set at call time rather than trusting the model's memory

```python
import json, jsonschema

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "customer_id": {"type": "string", "pattern": "^CUST-[0-9]{6}$"},
        "amount": {"type": "number", "minimum": 0.01, "maximum": 1_000_000},
        "currency": {"type": "string", "enum": ["USD", "EUR", "GBP"]}
    },
    "required": ["customer_id", "amount", "currency"]
}

def validate_tool_call(call: dict) -> tuple[bool, str]:
    try:
        jsonschema.validate(call["arguments"], TOOL_SCHEMA)
        return True, ""
    except jsonschema.ValidationError as e:
        return False, f"Argument validation failed: {e.message}"
    except Exception as e:
        return False, f"Schema error: {e}"

# In the agent loop:
valid, err = validate_tool_call(tool_call)
if not valid:
    return {"status": "rejected", "reason": err, "can_retry": False}
```

### 3. Solvability Hallucination — "Call a Tool That Doesn't Exist"

The model calls a tool that was never registered — or calls it in a context where the tool has no valid input. The model fabricates a tool name from its training distribution (e.g., `search_legal_database` when only `search_documents` exists), or calls a tool with inputs outside its operational domain.

**Mitigation:**
- **Dynamic tool registry** — enforce that every tool call matches a live registry entry; reject anything not registered
- **Scope pre-declaration** — the agent's system prompt explicitly lists the available tool namespace
- **AgentHallu benchmark** (Liu et al., arxiv:2601.06818, Jan 2026): step-level hallucination attribution to identify which reasoning step introduced the invalid tool call

### 4. Output-Interpretation Hallucination — "Read the Right Output Wrong"

The tool call succeeds but the model misinterprets the response — reading a `null` as an empty list, conflating error codes with data, or extracting the wrong field from a JSON response. This is the subtlest type because the execution trace shows no error.

**Mitigation:**
- **Structured output contracts** — define exactly which fields the model should read and their expected types
- **Output semantic validation** — use a secondary LLM call or rule-based check to verify the interpretation
- **Error-code mapping** — convert API error codes to natural-language descriptions before feeding to the model

### Cross-Type: Text2SQL Hallucination

A special case that spans all four types: the model generates a syntactically valid but semantically incorrect SQL query. The table exists, the columns exist, the query runs — but it returns the wrong result. This is the most dangerous production variant because it produces no error signal.

**Mitigation:**
- **Query plan previews** — execute `EXPLAIN` before returning results; surface row counts and execution time to the model
- **Result sanity bounds** — flag results that exceed expected cardinality (0 rows, 1M rows when expecting ~100)
- **Shadow execution** — run the model's query alongside a reference implementation and diff the result sets

## Receipt

> Receipt pending — 2026-08-08

## See also

[S-767](s767-the-tool-call-hallucination-plateau.md) · [S-1007](s1007-tool-call-hallucination-plateau.md) · [S-1086](s1086-the-cascading-hallucination-spill-stack-when-a-95-confidence-error-becomes-ground-truth.md) · [S-1023](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) · [S-1036](s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md)
