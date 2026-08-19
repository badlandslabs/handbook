# S-2826 · The MCP Agent Production Evaluation Stack — When Your Agent Passes Staging and Fails Every Tool Call in Production

Your eval suite returns 94% on the coding benchmark. Your staging run returns 100%. Your first week in production returns 31% task completion. The agent passed every test because none of the tests were about what MCP actually breaks: transport state, schema drift between tool-discovery calls, and argument construction against augmented tool descriptions that change between runs.

## Forces

- **Standard agent eval ignores the transport layer.** Most eval frameworks treat tool calls as pure function invocations. MCP's stdio, SSE, and Streamable HTTP transports have fundamentally different reliability profiles — a server that times out on SSE mid-session is not a tool-call failure in the eval harness, but it is a production failure.
- **The tool surface changes between requests.** MCP servers publish their capabilities at runtime. A server update, an OAuth token refresh, or a schema evolution means the agent faces a different tool surface than the one your eval captured. Your eval is testing the wrong version.
- **97% of MCP tool descriptions contain defects.** An arXiv study (Hasan et al., arXiv:2602.14878v3, Queen's University, 2026) audited 856 tools across 103 MCP servers and found 97.1% have at least one quality smell. You cannot build reliable evals on an unreliable tool description baseline.
- **Chain efficiency is MCP-specific.** MCP's tool result format, streaming capabilities, and server-side pagination all affect how many tokens the agent consumes per step. A generic agent eval that doesn't measure tokens-per-tool-call and context utilization will not catch the MCP-specific cost and latency regressions.

## The Move

### The Five MCP Evaluation Pillars

Production MCP agent evaluation requires five specific measurements that general-purpose agent frameworks miss:

#### 1. Tool Selection Accuracy
Does the agent pick the right tool given the current tool schema?

This is not the same as "correct tool" in a static eval. With MCP, the agent must select from a dynamically-discovered tool list. Measure precision and recall per tool category, not just overall accuracy.

```python
# Measure tool selection with MCP-specific grounding
from mcp import ClientSession
import asyncio

async def eval_tool_selection(agent, task, expected_tools):
    async with ClientSession(stdio_transport) as session:
        await session.initialize()
        tools = await session.list_tools()
        
        selected = await agent.select_tool(task, tools)
        
        precision = len(selected & expected_tools) / len(selected)
        recall    = len(selected & expected_tools) / len(expected_tools)
        
        return {"precision": precision, "recall": recall, "selected": selected}
```

#### 2. Argument Correctness
When the agent calls a tool, does it construct valid arguments against the *actual* schema the server is currently serving — not the schema from the last eval run?

This is distinct from S-2813 (Argument Contract Stack) because the MCP evaluation dimension asks: how stable is argument construction across schema versions? Track per-parameter rejection rates, not just call success rates.

```python
# Track argument correctness across MCP schema versions
async def eval_argument_correctness(agent, mcp_server, n_runs=50):
    results = []
    for run in range(n_runs):
        # Re-discover tools on every run (simulates production dynamics)
        tools = await mcp_server.list_tools()
        task  = generate_task(tools)
        
        call = await agent.invoke_tool(task, tools)
        
        # Attempt call against the *current* server state
        try:
            result = await mcp_server.call(call.name, call.arguments)
            status = "success" if result else "failure"
        except Exception as e:
            status = f"error: {type(e).__name__}"
        
        results.append({
            "tool":        call.name,
            "schema_hash": hash_schema(tools),
            "status":      status,
            "error_type":  type(e).__name__ if "error" in status else None,
        })
    
    df = pd.DataFrame(results)
    return {
        "per_tool_rejection_rate": df.groupby("tool")["status"].apply(
            lambda x: (x != "success").mean()
        ).to_dict(),
        "schema_version_count": df["schema_hash"].nunique(),
    }
```

#### 3. Task Completion Rate (MCP-Grounded)
Did the agent complete the user's task end-to-end? For MCP agents, this requires evaluating against the actual server state, not a mocked or recorded response. If the server's database changed between eval and production, the ground truth changed too.

The MCP-AgentBench (arXiv:2604.01532, Linux Foundation AI / Agentic AI Foundation) establishes this by running agents against live MCP servers with verifiable backend state. Your eval harness must do the same.

#### 4. Chain Efficiency (Tokens + Steps per Tool Call)
Measure tokens sent per tool call, including the tool schema, tool result, and conversation history context. A single MCP server with 25 tools sends 5,000–8,000 tokens of schema with every request — before any user message. Track this per tool and per session.

```python
# Measure MCP-specific chain efficiency
def measure_chain_efficiency(trace):
    mcp_calls = [span for span in trace.spans 
                 if span.attributes.get("mcp.server.version")]
    
    efficiency = []
    for call in mcp_calls:
        schema_tokens = call.attributes.get("mcp.schema_tokens", 0)
        result_tokens = call.attributes.get("mcp.result_tokens", 0)
        history_tokens = call.attributes.get("mcp.history_tokens", 0)
        
        total = schema_tokens + result_tokens + history_tokens
        efficiency.append({
            "tool":        call.name,
            "schema_tax":  schema_tokens / total if total else 0,
            "result_overhead": result_tokens / total if total else 0,
            "steps":       call.attributes.get("mcp.call_depth", 1),
        })
    
    return pd.DataFrame(efficiency)
```

#### 5. Context Utilization
How effectively does the agent use its available context window given the MCP tool schema inflation? Measure the ratio of useful context (retrieved documents, task history, tool results) to overhead (schema descriptions, duplicate metadata, unused tool definitions).

The 97% smell rate in MCP tool descriptions means your eval must measure whether the agent correctly interprets tool descriptions — not just whether it calls the right tool. An agent that picks the right tool for the wrong reason (misinterpreting a vague or misleading description) will degrade in production when descriptions change.

### The MCP Eval Hygiene Checklist

Before running any MCP agent eval:

1. **Refresh the tool list on every eval run.** Do not cache `list_tools()` results between runs. Production MCP servers change.
2. **Use live server state as ground truth.** Mocked responses hide the schema-drift failure mode. MCP-AgentBench and production-grade evals both require live backends.
3. **Measure schema tokens as a first-class metric.** Track tool schema token overhead per session. Flag sessions where schema tokens exceed 30% of total context.
4. **Vary the MCP transport.** Test with stdio, SSE, and Streamable HTTP. Each has different failure modes: stdio has no reconnect semantics, SSE is deprecated, and Streamable HTTP is the only one with proper lifecycle management.
5. **Audit tool description quality before evaluating.** Run the FM-based scanner from arXiv:2602.14878 on your MCP servers. If descriptions score below the "Unclear Purpose" threshold, fix them before evaluating — bad descriptions mean unreliable eval signals.

## Receipt

> Verified 2026-08-18 — MCP-AgentBench (arXiv:2604.01532, Linux Foundation Agentic AI Foundation) establishes the five-pillar framework. The arXiv:2602.14878 study (Queen's University, 2026) on 856 tools across 103 MCP servers provides the 97.1% smell baseline. Shareuhack (April 2026) documents the stdio transport failure rate (91% at 20 concurrent connections) and the 55K-token schema overhead for five MCP servers. Kognita (2025) documents the 11-day, $47,000 runaway incident where no transport-level timeout existed. MCP Transport Lifecycle (S-2794) and Tool Schema Contract (S-2813) provide the underlying failure modes this eval stack measures.

## See also

- [S-2794 · The MCP Transport Lifecycle Stack](s2794-the-mcp-transport-lifecycle-stack-when-your-agent-stops-working-and-nobody-told-it-the-server-was-gone.md) — the transport failures this eval must catch
- [S-2813 · The Tool-Call Argument Contract Stack](s2813-the-tool-call-argument-contract-stack-when-your-agent-picks-the-right-tool-and-gets-it-completely-wrong.md) — argument correctness in depth
- [S-2717 · The Tool Description Augmentation Paradox](s2717-the-tool-description-augmentation-paradox-when-better-descriptions-produce-worse-agents.md) — the 97% smell baseline and its eval implications
