# S-1663 · The MCP Tool Curation Stack — When Your Agent Has 200 Tools and Uses the Wrong One

You wire up the MCP registry. You expose every server. Your agent now has 214 tools. Task completion drops 18%. The agent calls `create_database` when it should call `check_database_exists`. It picks `send_email_v1` instead of `send_email_v2` because both names are equally plausible. It times out trying to "decide" between 12 similar file operations. This is the tool curation problem: more tools help until they don't, and the break point comes earlier than you think.

## Forces

- **Tool count and task accuracy have an inverted-U relationship.** Multiple studies and practitioner reports confirm agent performance peaks around 10-30 tools per agent and degrades as the surface grows — the model spends tokens reasoning about options instead of executing them (Qodo/Agent Patterns, 2026; Zylos Research, Feb 2026).
- **MCP's "discover everything" model is an anti-pattern in production.** Runtime tool discovery is powerful for dev tooling. For production agents handling sensitive operations, exposing the full registry creates both a performance problem and a security attack surface.
- **Tool naming and schema ambiguity increases with count.** When the agent sees `delete_file`, `delete_file_permanent`, `soft_delete_file`, and `delete_file_v2`, it must disambiguate intent from names alone — and the wrong guess costs more than calling nothing.
- **Different conversation stages need different tool subsets.** An agent that has 40 tools available at every step is wastefully polluting context and increasing the chance of a wrong pick. The right tool set at the right step is a gating concern.
- **Curation cannot be manual and static.** Teams that hard-code a fixed tool list spend weeks updating it, miss new tools, and ship stale configurations. The curation layer must be dynamic and policy-driven.

## The move

Split tool management from tool exposure. Use a **tool curation layer** between the MCP registry and the agent's runtime context.

### 1. The registry is the source of truth, not the agent

```python
# Tool registry: all known tools, versioned, with metadata
TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "send_email_v2": ToolDefinition(
        version="2.0.1",
        server="mcp-email-prod",
        capability="communication",
        risk_level="medium",       # destructive / irreversible
        requires_approval=True,   # human-in-the-loop gate
        context_window="post-authentication",
        tags=["email", "outbound", "customer-facing"],
    ),
    "send_email_v1": ToolDefinition(
        version="1.4.0",
        server="mcp-email-legacy",
        capability="communication",
        risk_level="medium",
        deprecated=True,           # excluded from all agent contexts
        sunset_date="2026-09-01",
    ),
}
```

Register every tool with rich metadata. Deprecate explicitly. Never let the agent see deprecated versions.

### 2. Tiered exposure by agent role

```python
def get_exposed_tools(agent_role: str, conversation_stage: str) -> list[str]:
    """Return the curated tool list for an agent + stage, not the full registry."""
    
    base_tiers = {
        "research_agent": [
            "web_search", "read_file", "query_database",
            "summarize_document", "fetch_api",
        ],
        "code_agent": [
            "read_file", "write_file", "run_command",
            "list_directory", "search_codebase", "git_status",
        ],
        "ops_agent": [
            "read_file", "query_database", "send_webhook",
            "check_health", "get_logs",
        ],
    }
    
    stage_additions: dict[str, list[str]] = {
        "authenticated": ["send_email_v2", "create_record", "update_record"],
        "review_needed": [],  # no tool calls — human approval only
        "escalated": ["*"],  # emergency: full access, with audit
    }
    
    tools = list(base_tiers.get(agent_role, []))
    tools += stage_additions.get(conversation_stage, [])
    return tools
```

### 3. Context-aware tool gating

The same agent needs different tools at different conversation phases. Gate at the **stage level**, not the agent level:

```python
# Conversation stage machine — drives tool exposure
class AgentStage(Enum):
    GREETING = auto()
    AUTHENTICATING = auto()
    WORKING = auto()
    REVIEW = auto()      # no mutating tools
    ESCALATED = auto()  # emergency overrides

STAGE_TOOL_POLICY: dict[AgentStage, ToolPolicy] = {
    AgentStage.GREETING: ToolPolicy(
        allow_tools=["read_kb", "classify_intent"],
        block_tools=["*"],  # block everything not explicitly allowlisted
    ),
    AgentStage.AUTHENTICATING: ToolPolicy(
        allow_tools=["read_kb", "verify_identity", "classify_intent"],
        block_tools=["*"],
    ),
    AgentStage.WORKING: ToolPolicy(
        allow_tools=["*"],  # full operational set
        block_tools=["delete_database", "send_external_email"],
        approval_required=["send_email_v2", "create_database"],
    ),
    AgentStage.REVIEW: ToolPolicy(
        allow_tools=["read_file", "query_database", "generate_summary"],
        block_tools=["*"],  # read-only stage
    ),
    AgentStage.ESCALATED: ToolPolicy(
        allow_tools=["*"],
        approval_required=[],
        audit=True,  # log every call with full trace
    ),
}
```

### 4. Tool name disambiguation at the schema layer

When multiple tools share a domain, use schema-level disambiguation to help the model pick correctly:

```json
{
  "name": "send_email_v2",
  "description": "Send a transactional email via the approved ESP (SendGrid). " +
    "Use this for customer-facing notifications, order confirmations, and " +
    "password resets. For marketing emails use send_marketing_email. " +
    "For legacy system emails use send_email_v1 (deprecated, sunset 2026-09-01).",
  "parameters": {
    "type": "object",
    "properties": {
      "to": { "type": "string", "description": "Recipient email address" },
      "template_id": {
        "type": "string",
        "description": "SendGrid template ID from the approved template registry. " +
          "Do NOT construct raw HTML — use a template. Do NOT use this for " +
          "marketing (see: send_marketing_email)."
      },
      "context": { "type": "object" }
    }
  }
}
```

The description does three things: names the exact use case, names the adjacent tool to prevent confusion, and states what this tool is NOT for.

### 5. Runtime tool registry health checks

```python
def validate_tool_registry(registry: dict[str, ToolDefinition]) -> list[str]:
    """Catch curation debt before it reaches production."""
    issues = []
    
    # Check for duplicate-capability tools without deprecation marks
    by_capability: dict[str, list[str]] = defaultdict(list)
    for name, tool in registry.items():
        by_capability[tool.capability].append(name)
    
    for capability, tools in by_capability.items():
        active = [t for t in tools if not registry[t].deprecated]
        if len(active) > 3:
            issues.append(
                f"Capability '{capability}' has {len(active)} active tools: "
                f"{active}. Select 1-3 or add deprecation marks."
            )
    
    # Check that every tool has a non-generic description
    for name, tool in registry.items():
        if len(tool.description) < 50:
            issues.append(f"Tool '{name}' has a description under 50 chars — too ambiguous for reliable routing.")
    
    return issues
```

Run this in CI. Block merges that introduce tool count above the per-agent ceiling without an approved exception.

### 6. The MCP gateway as enforcement point

```python
# Centralized enforcement: the gateway rejects out-of-policy tool calls
# even if the agent proposes them
@app.middleware
async def enforce_tool_policy(request: MCPRequest, call_next):
    agent_role = await get_agent_role(request.agent_id)
    stage = await get_conversation_stage(request.session_id)
    policy = STAGE_TOOL_POLICY[stage]
    
    if request.tool_name not in policy.allow_tools and "*" not in policy.allow_tools:
        logger.warning(f"Blocked {request.tool_name} for {agent_role} in stage {stage}")
        return ToolResult(
            success=False,
            error="TOOL_NOT_PERMITTED",
            message=f"Tool '{request.tool_name}' is not permitted in the current conversation stage.",
        )
    
    if request.tool_name in policy.approval_required:
        await request_human_approval(request)
    
    return await call_next(request)
```

The gateway is the wall. Prompt instructions are suggestions. Code is enforcement.

## Receipt

> Verified 2026-07-26 — Code patterns from the MCP registry governance pattern documented at agentscamp.com (Jun 2026), Qodo/Agent Patterns research on tool surface management (2026), and Zylos Research on capability-binding failures (Feb 2026). The tool count ceiling (10-30 per agent) is confirmed across practitioner reports and correlates with the S-1084 (Tool Catalog Antipattern) findings in this handbook. Stage-gated tool exposure maps to the least-agency principle from S-1652. Gateway enforcement complements the Policy Kernel (S-1458) and Pre-Execution Gate (S-1400).

## See also

- [S-1084 · The Tool Catalog Antipattern](stacks/s1084-the-tool-catalog-antipattern-when-giving-your-agent-every-tool-hurts-reliability.md) — the quantitative evidence that tool count hurts performance
- [S-1652 · The Least Agency Stack](stacks/s1652-the-least-agency-stack-when-your-agent-doesnt-need-to-be-a-superuser.md) — exposure-minimization as a reliability principle
- [S-1391 · The MCP Gateway Registry Stack](stacks/s1391-the-mcp-gateway-registry-stack-when-your-agent-tool-sprawl-becomes-a-security-nightmare.md) — the governance layer this sits on top of
- [S-1458 · The Policy Kernel Stack](stacks/s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — the deterministic enforcement that makes curation stick
