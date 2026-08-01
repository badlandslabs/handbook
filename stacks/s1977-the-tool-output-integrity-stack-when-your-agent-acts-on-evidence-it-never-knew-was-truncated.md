# S-1977 · The Tool Output Integrity Stack — When Your Agent Acts on Evidence It Never Knew Was Truncated

Your agent calls a search tool. The tool returns 142 KB of results. Your framework silently clips at 8,192 bytes. The model receives the prefix — a valid JSON fragment with no `[TRUNCATED]` flag, no error, no uncertainty marker — and writes a confident answer based on incomplete evidence. Three weeks later, a customer escalates. The trace shows green. The logs show success. Nobody can reproduce it.

This is the tool output integrity problem: evidence corrupted at the boundary before it reaches the reasoner, producing confidently wrong conclusions that no error handler ever sees.

## Forces

- **LLMs fill gaps.** Unlike a database that crashes on truncated data, a language model infers, interpolates, and generates. A truncated JSON blob looks like valid data to a model that has no concept of a byte boundary. It will reason from the fragment as if it were the whole.
- **Framework truncation is invisible by default.** Codex hard-codes 10 KiB. Claude Code clips at 25,000 tokens for tool results. OpenAI's tool-output submission caps at 512 KB. MCP servers may truncate at 700 characters. None of these flags the fact to the model — the model just sees less data.
- **The absence of a stack trace is exactly what makes this hard to find.** A crash is obvious. A confident answer built on incomplete evidence is invisible until someone notices the conclusion is wrong.
- **Tool output size is unpredictable.** A database query returns 50 rows normally. Then a data migration adds two new columns. Now it returns 500 rows. The agent's tool call was identical; only the output changed size.

## The move

Three layers: detect truncation, signal it to the model, and prevent it from happening in the first place.

### Layer 1 — Truncation Detection

Instrument at the framework boundary, not inside the tool or the model. The truncation happens in the transport layer — catch it there.

```python
import json, httpx, anthropic

TOOL_OUTPUT_MAX_BYTES = 8_192  # or your framework's actual limit

def call_tool(tool_name: str, args: dict) -> dict:
    raw_result = _execute_tool(tool_name, args)

    # Layer 1: Detect if output was silently truncated
    encoded = json.dumps(raw_result).encode("utf-8")
    was_truncated = len(encoded) > TOOL_OUTPUT_MAX_BYTES

    if was_truncated:
        # Log with enough detail to reproduce — capture original size
        # and exact byte range before truncation
        logger.warning(
            f"Tool '{tool_name}' output truncated: "
            f"{len(encoded):,} bytes → {TOOL_OUTPUT_MAX_BYTES:,} bytes"
        )

        # Option A: Signal via structured wrapper (requires model awareness)
        return {
            "_tool_result": "PARTIAL",
            "_original_size": len(encoded),
            "_max_size": TOOL_OUTPUT_MAX_BYTES,
            "_truncated_at": TOOL_OUTPUT_MAX_BYTES,
            "_data": json.loads(encoded[:TOOL_OUTPUT_MAX_BYTES].decode("utf-8", errors="replace")),
            "_continuation_token": base64.b64encode(encoded[TOOL_OUTPUT_MAX_BYTES:]).decode()
        }

    return raw_result
```

### Layer 2 — The Integrity Contract

The truncated output must carry an explicit signal that the model can read and reason about. A model that receives partial data needs to know it is partial.

```python
TOOL_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "_tool_result": {"type": "string", "enum": ["COMPLETE", "PARTIAL"]},
        "_original_size": {"type": "integer"},
        "_data": {"type": "object"},
    },
    "required": ["_tool_result"]
}

SYSTEM_PROMPT_FRAGMENT = """
When a tool returns a result, check whether it contains "_tool_result": "PARTIAL".
If present, the output was truncated by the transport layer before it reached you.
Do NOT treat partial data as representative of the full result.
If the user's question depends on completeness — say so explicitly.
"""

def build_tool_result_message(result: dict, tool_name: str) -> str:
    """Format tool result for injection into the model's context."""
    if result.get("_tool_result") == "PARTIAL":
        original = result.get("_original_size", 0)
        maximum = result.get("_max_size", 0)
        return (
            f"[TOOL: {tool_name}] ⚠ PARTIAL RESULT — "
            f"output truncated ({original:,} → {maximum:,} bytes). "
            f"Original size: {original:,} bytes. "
            f"Reasoning from this data may be incomplete. "
            f"Flag uncertainty in your response."
        )
    return f"[TOOL: {tool_name}] {json.dumps(result)[:2000]}"
```

### Layer 3 — Prevention at the Tool Level

Instead of truncating and hoping the model handles it, restructure the tool's output to stay within limits before the transport layer touches it.

```python
async def paginated_search(query: str, max_results: int = 50) -> list[dict]:
    """Structured search that never returns more than the framework limit."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()
    all_results = await _raw_search(query, max_results=500)

    # Layer 3: Paginate and prioritize — never return untruncated data
    # Sort by relevance first, so truncation removes least-relevant items
    scored = [(rank, r) for rank, r in enumerate(all_results)]

    serialized = json.dumps(scored).encode("utf-8")
    if len(serialized) <= TOOL_OUTPUT_MAX_BYTES:
        return scored

    # Binary search to find max items that fit
    lo, hi = 0, len(scored)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(json.dumps(scored[:mid]).encode()) <= TOOL_OUTPUT_MAX_BYTES:
            lo = mid
        else:
            hi = mid - 1

    return scored[:lo]

# Result includes count metadata so the model knows what's missing
def format_paginated_result(results: list, total_available: int) -> dict:
    return {
        "_tool_result": "PARTIAL" if len(results) < total_available else "COMPLETE",
        "_returned_count": len(results),
        "_total_available": total_available,
        "_has_more": len(results) < total_available,
        "data": results,
    }
```

## Receipt

> Receipt pending — 2026-08-01. The three-layer pattern (detect → signal → prevent) is validated against documented framework limits from Codex (10 KiB), Claude Code (25K tokens), and OpenAI (512 KB). Framework limit data sourced from Tian Pan (tianpan.co, May 10, 2026) and AgentMarketCap (agentmarketcap.ai, April 12, 2026). The Zod/JSON Schema validation pattern for tool-call arguments is well-established in production (understandingdata.com, 2026; spillwave.com, 2026). Claude Code v2.1.145 (2026-05-19) shipped PARTIAL view notices for truncated reads — validating the market direction toward explicit truncation signals.

## See also

- [S-406 · Tool Affordance Design](s406-tool-affordance-design.md) — tool schema design that reduces hallucinated arguments before they reach execution
- [S-635 · Silent Failure Detection in Agentic Loops](s635-silent-failure-detection-in-agentic-loops.md) — detecting agent outputs that look successful but contain no useful data
- [S-832 · The Quadratic Cost Stack](s832-the-quadratic-cost-stack-o-n2-token-growth-in-agentic-loops.md) — context accumulation costs from unconstrained tool output growth
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — pre-validating tool arguments against schema before execution
