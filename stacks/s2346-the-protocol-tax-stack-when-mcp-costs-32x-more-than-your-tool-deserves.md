# S-2346 · The Protocol Tax Stack — When MCP Costs 32x More Than Your Tool Deserves

Your agent needs to check a repository's language. The CLI takes 50ms and returns `"python"`. MCP takes 1,400ms, returns 44,026 tokens, and costs $0.11. The tool did the same job. The protocol added 880x more data and 28x more latency — for a task that doesn't need a protocol at all.

## Forces

- **MCP's token overhead compounds with scale.** The Model Context Protocol was designed to solve tool discovery and standardization — not to be the most efficient execution path. Each MCP interaction includes protocol framing, schema transmission, and intermediate result serialization. For a single call, the overhead is negligible. For 10,000 daily calls in production, it is a line item on your invoice.
- **The benchmark data is real and it's damning.** Scalekit ran 75 head-to-head comparisons between MCP and direct CLI for identical operations using Claude Sonnet 4. MCP used 4x–32x more tokens per operation. Simplest task (repo language check): CLI 1,365 tokens vs MCP 44,026 tokens. Estimated monthly cost for equivalent workload: $3.20 CLI vs $55.20 MCP — a 17x cost difference. MCP's failure rate was 28%. Perplexity's CTO publicly cited similar numbers when moving away from MCP in March 2026.
- **Protocol overhead is architectural, not accidental.** MCP wraps every tool call in a standardized request/response envelope. That envelope includes authentication headers, schema metadata, resource URIs, and pagination tokens — all useful when you need them, all present when you don't. The question is whether your use case justifies the overhead.
- **The ecosystem convinced you MCP was free.** Anthropic's SDK, 9,400+ registered servers, and 97M monthly SDK downloads create the impression that MCP is the default — and therefore costless. It is neither. The demo works. The production bill surprises.

## The move

### Know the tax before you pay it

Run a single comparison before committing:

```
# Direct CLI — no protocol overhead
$ time gh repo view badlandslabs/handbook --json primaryLanguage 2>/dev/null
# Output: {"primaryLanguage":"Python"}
# Tokens: ~1,365 input + ~50 output = 1,415 total

# MCP equivalent via Anthropic SDK
# Tool definition + prompt + schema + results = ~44,000 tokens
# Latency: ~1,400ms vs ~50ms
# Cost ratio: 17x at production scale
```

If the task is a simple API call or CLI command, **direct function calling wins on cost and latency**. Reserve MCP for the cases where it actually earns its overhead.

### The decision matrix

| Use case | Approach | Why |
|---|---|---|
| 1–5 stable tools, known at build time | Direct function calling | Zero protocol overhead, provider-native |
| 10–100 tools, dynamic discovery needed | MCP with selective exposure | Protocol tax worth paying for discovery |
| Cross-framework portability required | MCP | Value of standard > overhead cost |
| High-volume simple operations | Direct API / CLI | Token savings are 4x–32x |
| Tool needs OAuth or dynamic auth | MCP | Protocol handles auth lifecycle |
| Rapid prototyping, low volume | Either | Overhead doesn't matter yet |

### Minimize MCP overhead when you do use it

```python
# BAD: Load all 50 tool definitions into every prompt
tools=[...50_tools...]  # Every call pays 50x schema overhead

# BETTER: Lazy-load only the tool the agent is about to use
async def get_tool_smart(tool_name: str) -> dict:
    """Load MCP tool definition on-demand, not at startup."""
    server = mcp_servers["data-ops"]
    result = await server.execute_tool(tool_name, {})
    # Only load this tool's schema, not the full catalog
    return result

# BEST: Fall back to direct API when MCP is overkill
def resolve_tool(tool_name: str, volume: int) -> str:
    if is_simple_api_tool(tool_name) and volume > 1000:
        return call_direct_api(tool_name)  # No MCP framing
    return call_via_mcp(tool_name)           # Protocol for discovery/auth
```

### Monitor the ratio, not just the absolute cost

```python
def mcp_health_ratio(tool_name: str, mcp_tokens: int, result_tokens: int) -> float:
    """
    Protocol overhead ratio. 
    > 10x means the protocol is carrying very little value for this call.
    Flag for direct API migration.
    """
    ratio = mcp_tokens / max(result_tokens, 1)
    if ratio > 10:
        logger.warning(
            f"Tool '{tool_name}': protocol overhead is {ratio:.1f}x "
            f"(MCP {mcp_tokens} tokens for {result_tokens} result tokens). "
            f"Consider direct API."
        )
    return ratio
```

## Receipt

> Verified 2026-08-08 — Scalekit 75-task benchmark: MCP 4x–32x token overhead vs CLI, 28% MCP failure rate, $3.20 vs $55.20/month at equivalent workload. Perplexity CTO cited comparable numbers moving to direct APIs (March 2026). MCP Institute comparative analysis confirms token efficiency gap. Anthropic SDK documentation notes context overhead at scale with 100+ tools.

## See also

- [S-1048 · The Tool Modality Stack](/opt/data/handbook/stacks/s1048-the-tool-modality-stack-when-your-agent-calls-a-tool-five-ways-and-you-picked-the-wrong-one.md) — Tool modality trade-offs; MCP is one option among five
- [S-1022 · The MCP Tool Catalog](/opt/data/handbook/stacks/s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — Why MCP became the ecosystem default; when standardization earns its cost
- [S-1079 · The Tool-Aware Model Router](/opt/data/handbook/stacks/s1079-the-tool-aware-model-router-when-cheap-tools-burn-budget-because-routing-ignores-them.md) — Tool cost awareness in routing decisions
