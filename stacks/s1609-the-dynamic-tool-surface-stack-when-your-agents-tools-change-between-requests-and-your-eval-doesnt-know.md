# S-1609 · The Dynamic Tool Surface Stack — When Your Agent's Tools Change Between Requests and Your Eval Doesn't Know

You write a deterministic test for your agent: given input X, it should call `search_docs` with parameters Y. The test passes. Three weeks later your MCP server is updated — `search_docs` now requires a `tenant_id` field, the agent adapts, and your test still passes because the parameters you hardcoded are now silently ignored. Your eval suite reports 100% pass. Your agent is dropping queries in production. This is the **dynamic tool surface problem**: when agents discover and use tools at runtime from MCP servers, the eval surface shifts underneath your test suite without a signal.

## Forces

- **MCP flips evaluation from deterministic to probabilistic.** Before MCP, tool sets were declared at build time — hardcoded, versioned, tested. With MCP, the available tool surface is a runtime artifact. The agent decides which tool to call based on a tool list it received from one or more connected MCP servers. The same query can produce different tool-call sequences depending on which servers are connected, which tools are available, and which schema version the server returned.
- **Traditional eval assumes closed-world tools; MCP is open-world.** Test suites that assert "agent calls `search_docs` on query X" break when `search_docs` doesn't exist in the current server configuration. Teams react by either (a) ignoring MCP servers in eval entirely — which means the eval doesn't test what production does — or (b) locking server versions — which defeats the purpose of dynamic discovery.
- **MCP schema drift is silent.** MCP servers can rename tools, change parameter types, alter required fields, or change output shapes — and none of this produces an error. The agent receives a new `tools/list` response and updates its behavior. No 500, no crash log, no CI failure. Just silently different behavior between builds. MCP schema drift rates of 7.1% over 48 hours have been documented in production environments.
- **Golden-path tests become stale the moment the MCP server updates.** The most common pattern — recording the tool-call sequence from a successful production run and asserting it repeats — captures one path through a non-deterministic decision space. It tells you the agent *can* produce that sequence, not that it *will*, and certainly not that it's the right sequence for the new tool surface.

## The Move

The five-pillar MCP evaluation framework, run on a sampled production slice:

### Pillar 1 — Tool Selection Accuracy (Precision + Recall)
Log all tool-call sequences at runtime across diverse MCP configurations. Build a **tool selection corpus**: for each query, the set of tools the agent chose. Assert against the corpus, not a golden path. Track precision (did it call only relevant tools?) and recall (did it call all necessary tools?) against a human-annotated ground truth. Reject new MCP server versions that change the agent's precision/recall by >5% without a corresponding intent change.

```python
# Tool selection corpus vs golden-path assertion
from collections import Counter
from typing import Set

def evaluate_tool_selection(
    logged_sequences: list[list[str]],   # Runtime tool-call logs
    corpus: dict[str, Set[str]],         # query → valid tools from corpus
    query: str,
    threshold: float = 0.80
) -> dict:
    """Replace golden-path tests with corpus-based tool selection eval."""
    observed = Counter(tool for seq in logged_sequences for tool in seq)
    valid_tools = corpus.get(query, set())
    
    precision = sum(v for k, v in observed.items() if k in valid_tools) / sum(observed.values())
    recall = len(set(observed.keys()) & valid_tools) / max(len(valid_tools), 1)
    f1 = 2 * (precision * recall) / max(precision + recall, 1e-9)
    
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "pass": f1 >= threshold,
        "new_tools": set(observed.keys()) - valid_tools,
        "missing_tools": valid_tools - set(observed.keys()),
    }
```

### Pillar 2 — Argument Correctness (Schema Compliance + Semantic Accuracy)
Assert JSON schema compliance (parameter types, required fields) first — this is mechanical and automatable via JSON Schema validation against the MCP server's `tools/list` response. Then assert semantic correctness: did the agent pass the right values? Pair this with a trajectory judge on a sampled slice (run every 100th production trace through a judge model scoring argument quality).

```python
import jsonschema

def validate_tool_arguments(
    tool_call: dict,
    mcp_server_schema: dict   # Fresh from tools/list at eval time
) -> dict:
    """Validate against LIVE schema, not a pinned snapshot."""
    tool_name = tool_call["name"]
    args = tool_call["arguments"]
    
    # Find schema for this tool in current server response
    schema = next(
        (t["inputSchema"] for t in mcp_server_schema["tools"] 
         if t["name"] == tool_name),
        None
    )
    if schema is None:
        return {"valid": False, "reason": f"Tool {tool_name} not in current schema — MCP server may have removed it"}
    
    try:
        jsonschema.validate(instance=args, schema=schema)
        return {"valid": True, "schema_version": "current"}
    except jsonschema.ValidationError as e:
        return {"valid": False, "reason": str(e.message), "schema_version": "current"}
```

### Pillar 3 — End-to-End Task Completion (Trajectory Judge)
Score whether the agent achieved the goal, not just whether it called the right tools. Use a trajectory judge — a separate LLM call that reads the full agent trace and outputs a completion score — on a 1-5% sampled production slice. Run this nightly. A task completion rate <80% on the sampled slice is a production signal, not a test failure.

### Pillar 4 — Chain Efficiency
Measure calls per task, retry rate, redundant call rate, and tool-call depth. An agent that achieves 90% task completion by calling 47 tools when 5 would suffice is a cost problem. Track the efficiency ratio: `outcome_score / (tool_calls × avg_latency_ms)`. Alert when efficiency degrades >20% week-over-week.

### Pillar 5 — Context Utilization (Groundedness)
Score whether the agent's responses are grounded in the MCP resources it retrieved. Run a groundedness probe: for each tool call that returned data, assert that the subsequent LLM reasoning and final output cite the retrieved content. A groundedness score <85% means the agent is hallucinating on top of valid tool outputs.

### CI Gate: MCP Schema Drift Detection
The most important operational component. On every MCP server update, run the full five-pillar eval against both the old and new schema before the new server goes live. Reject deployments where any pillar drops >5%. Treat MCP servers as first-class API surfaces with breaking-change discipline.

```bash
# CI gate: run on every MCP server update
python -m your_eval_lib.pillar_suite \
  --mcp-server-url http://localhost:3100 \
  --eval-corpus ./test_corpus.jsonl \
  --drift-threshold 0.05 \
  --sample-rate 0.01 \
  --judge-model gpt-5-2025-08-07
# Exit code 0 = pass, 1 = drift detected, 2 = schema breaking change
```

## Receipt

> Verified 2026-07-25 — Concept validated against futureagi.com (Jul 2026), MCPAgentBench (arXiv:2512.24565), and five-pillar eval framework documented in the MCP evaluation step-by-step guide. MCP schema drift rate of 7.1% over 48 hours from agentmarketcap.ai (Apr 2026) confirms the problem severity. Framework components are implementable with standard trace libraries (OTel GenAI conventions), JSON Schema validation, and trajectory judges.

## See also

- [S-1056 · The MCP Tool Contract Gate](stacks/s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — schema versioning as a CI-gated API surface (the sibling problem)
- [S-1108 · The MCP Tool-Gluttony Stack](stacks/s1108-the-mcp-tool-gluttony-stack-when-your-agent-has-a-thousand-tools-and-nothing-to-wear.md) — tool selection overhead when the surface grows
- [S-1604 · The Three-Layer Eval Stack](stacks/s1604-the-three-layer-eval-stack-measuring-agents-not-just-answers.md) — measuring agents not just answers (trajectory judges as Pillar 3)
- [S-1022 · The MCP Tool Catalog](stacks/s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — the shared vocabulary that makes dynamic discovery possible
