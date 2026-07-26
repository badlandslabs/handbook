# [S-1671] · The Reasoning Trap Stack

When your agent thinks harder, it gets worse at using tools.

## Forces
- Every major model family in 2026 ships with reasoning mode enabled by default — and tool hallucination rates increase proportionally.
- RL for reasoning, distillation, and toggleable reasoning modes all produce the same paradoxical effect: capability up, tool reliability down.
- Existing mitigations (prompt engineering, DPO) force a fundamental trade-off: reducing hallucination degrades the very reasoning capability you were optimizing.
- Tool hallucination is not just a description problem. It is a representational collapse problem inside the model — and it lives in the late-layer residual streams.

## The move

The insight: the reasoning step itself — not RL in general — amplifies tool hallucination. Reasoning RL collapses the representations the model uses to evaluate tool-reliability. This is why "think-then-act" agents hallucinate more than direct-response agents, even on the same task. And it is why disabling reasoning to fix the problem is not a viable solution.

### 1. Know the two failure modes

**R_NTA — No Tool Available:** The user names a tool that doesn't exist. The agent fabricates a plausible one anyway.
**R_DT — Distractor Tools Available:** The agent has access to tools but calls the wrong one or invents arguments for a tool it already has.

On SimpleToolHalluBench (ACL 2026), base models score 34.8% R_NTA / 54.7% R_DT. After "think-then-act" RL training, scores jump to 90.2% / 100.0% — meaning the enhanced model almost always hallucinates when a tool is missing, and fabricates spurious tool outputs even when correct tools exist.

### 2. Log proposed vs. registered tool names

```python
available_tools = {t["name"]: t for t in registered_tool_schemas}

def call_tool(tool_name: str, args: dict) -> dict:
    if tool_name not in available_tools:
        # Tool hallucination detected
        logger.warning(
            f"TOOL_HALLUCINATION: agent proposed '{tool_name}' "
            f"but available tools are {list(available_tools.keys())}"
        )
        return {"error": "unknown_tool", "proposed": tool_name, "available": list(available_tools.keys())}
    return _execute(available_tools[tool_name], args)
```

This is the single most actionable signal in production. Every mismatch between *proposed* and *registered* tool names is a hallucination event you can track, count, and correlate with reasoning mode activation.

### 3. Profile your model's hallucination rate by reasoning mode

```python
# Instrument reasoning mode detection
REASONING_TRIGGERS = ["<think>", "## Analysis", "Let me reason", "Step-by-step"]

def detect_reasoning_mode(response: str) -> bool:
    return any(token in response for token in REASONING_TRIGGERS)

# Track hallucination rate per mode
metrics.gauge("tool_hallucination_rate", 
    labels={"reasoning_mode": reasoning_active, "model": model_id})
```

Run this on your eval set. If your agent uses reasoning and your hallucination rate exceeds 5%, the Reasoning Trap is active in your system.

### 4. Route by task complexity, not by habit

The reliability-capability trade-off is not uniform across task types:

| Task Type | Reasoning Mode | Tool Reliability Impact |
|---|---|---|
| Fact lookup (low complexity) | OFF | Minimal degradation |
| Multi-step planning (medium) | ON, brief | Moderate degradation |
| Novel tool orchestration (high) | ON, extended | **Severe degradation** |
| Code generation with execution | ON | High degradation |

Route based on task complexity. For tasks requiring novel tool combinations, prefer shorter reasoning traces or direct-action mode. The goal is not to remove reasoning — it is to avoid extended reasoning before tool use on tasks where the tool surface is unfamiliar.

### 5. Use structured tool pre-selection before the model reasons

Rather than letting the model discover which tool to call through reasoning, pre-select the candidate tool set:

```python
def pre_select_tools(user_intent: str, all_tools: list[dict]) -> list[dict]:
    # Fast embedding match — no reasoning model needed
    intent_embedding = embed(user_intent)
    candidates = [
        t for t in all_tools
        if cosine_similarity(intent_embedding, embed(t["description"])) > 0.75
    ]
    return candidates[:5]  # Present only top candidates to model
```

This constrains the tool surface the model sees before it enters reasoning mode, reducing the hallucination opportunity window.

### 6. Semantic output validation for tool responses

```python
def validate_tool_response(tool_name: str, response: dict, expected_schema: dict) -> bool:
    """Validate that tool response matches the schema semantics, not just structure."""
    if not set(response.keys()) == set(expected_schema.keys()):
        return False
    # Cross-check: does the response content make sense for the tool's documented behavior?
    semantic_check = llm_judge(
        f"Tool '{tool_name}' returned {response}. "
        f"Is this a plausible output for a tool that {expected_schema['description']}?"
    )
    return semantic_check.confidence > 0.7
```

This catches hallucinated tool outputs (valid JSON, wrong semantics) that pass structural validation.

### 7. The trade-off is real — plan for it

ACL 2026 confirms: you cannot fully eliminate tool hallucination from reasoning-enhanced models without degrading their reasoning capability. The mitigations above reduce hallucination rates and surface them for detection, but the root cause is architectural. Three strategic options:

1. **Isolate** — Run low-complexity tool tasks through a direct-mode agent; reserve reasoning-mode for tasks without tool dependencies.
2. **Detect and escalate** — Instrument hallucination detection at the boundary; escalate hallucination-flagged tool calls to a separate verification step.
3. **Wait for architectural fixes** — Joint capability-reliability training objectives are an active research area. The fix is not yet production-ready, but benchmark-hugging for the first model that solves it is a viable strategy.

> Verified 2026-07-26 — Source: Chenlong Yin et al., ACL 2026 Long Paper #376, "The Reasoning Trap: How Enhancing LLM Reasoning Amplifies Tool Hallucination" (Penn State / Nanjing Univ, arXiv:2510.22977v2). Benchmark: SimpleToolHalluBench. GitHub: albert-y1n/Reasoning_Trap. Supporting: SentinelOne CVE-2026-0757 (MCP RCE via tool hallucination exploitation), HalluciTrap interactive simulator (RLASAF12/hallucitrap), OpenReview ACC framework for agentic UQ. Code examples: functional Python stubs for instrumentation. Coverage gap confirmed: existing S-406 (tool affordance) covers description design; S-1072 (tool schema) covers schema validation. Neither covers the representational/RL mechanism or the reliability-capability tradeoff as a first-class architectural concern.

## See also
- [S-406](s406-the-tool-affordance-design-stack-when-your-agent-doesnt-know-how-to-use-a-tool.md) — Tool affordance and schema design (description-level)
- [S-1072](s1072-the-tool-schema-stack-when-agents-get-lost-in-a-hundred-generic-tools.md) — Schema validation for tool calls (structural)
- [S-1622](s1622-the-confidence-calibration-stack-when-your-agent-is-wrong-but-sounds-certain.md) — Confidence calibration and uncertainty propagation
