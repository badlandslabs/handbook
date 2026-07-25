# F-200 · The Permission Guard Stack — When Your Agent Does Exactly What It Was Designed to Do and Wreaks Havoc

Your SQL-writing agent produces a correct `TRUNCATE customers` statement. Your code-review agent drafts a bulk credential rotation. Your data-agent optimizes and then deletes a table. Every action is syntactically valid, contextually appropriate, and completely unauthorized. The agent is working exactly as designed. The problem is that "as designed" included capabilities no human reviewer approved. This is the permission guard problem — and it is not a prompt engineering challenge.

## Forces

- **Agents generate correct operations that exceed their authorization.** The LLM produces syntactically valid, contextually sound API calls. The authorization failure is invisible to the agent and invisible to the model's evaluation of its own output.
- **Prompt-based safety is probabilistic.** A system prompt that says "never delete data" fails at 3 a.m. when context is dense, the model is undercoordinated, or the user request is framed as an exception. Probabilistic controls do not scale to regulated environments.
- **Too much restriction breaks the agent.** If every tool call requires a human check, you've built a slow, expensive approval queue — not an agent. The guardrails must distinguish routine from destructive with precision.
- **Static permissions don't survive dynamic tools.** An agent with 50 MCP tools at session start may discover 10 more over a 2-hour session. Permission scope set at startup may not reflect the expanded surface.
- **EU AI Act Article 14 mandates deterministic oversight for high-risk systems** effective August 2026. "We told it not to" is not a compliance defense.

## The move

Build a two-layer permission architecture that separates **intent signaling** (probabilistic, in the prompt) from **enforcement** (deterministic, at the execution layer).

### Layer 1 — Probabilistic Intent Layer (Prompt)

The prompt establishes intent, not authorization. Use it to set the agent's operational context, not to gate destructive actions.

```
You are a data analysis agent with access to read-only tools.
You may query the database but never modify, delete, or truncate data.
All schema changes require explicit human approval via the approval queue.
```

This layer fails. Plan for Layer 2.

### Layer 2 — Deterministic Permission Guard (Execution)

At the execution layer, intercept every tool call against a typed permission policy. The agent never reaches the tool; the guard does.

```python
from enum import Flag, auto

class Permission(Flag):
    NONE       = 0
    READ       = auto()
    WRITE      = auto()
    DELETE     = auto()
    EXECUTE    = auto()      # run shell/system commands
    ADMIN      = auto()      # credential/permission management
    SCHEMA     = auto()       # alter table structure
    # Composite scopes
    DATA_READ  = READ
    DATA_WRITE = READ | WRITE
    DESTRUCTIVE = DELETE | EXECUTE | SCHEMA | ADMIN

# Per-role permission sets
ROLE_PERMISSIONS = {
    "data_analyst":  Permission.DATA_READ,
    "code_reviewer": Permission.READ | Permission.EXECUTE,   # can run tests
    "admin_agent":   Permission.DESTRUCTIVE,
}

def permission_guard(tool_name: str, operation: str, role: str) -> bool:
    """
    Deterministic gate: blocks or allows tool calls based on
    static role permissions, independent of model behavior.
    """
    required_permission = classify_operation(tool_name, operation)

    if required_permission == Permission.NONE:
        return True  # unknown operation → block by default

    allowed = ROLE_PERMISSIONS.get(role, Permission.NONE)
    granted = required_permission in allowed

    if not granted:
        audit_log.warning(
            f"PERMISSION_DENIED role={role} tool={tool_name} "
            f"op={operation} required={required_permission.name}"
        )
        # Route to approval queue instead of blocking outright
        escalate_to_approval_queue(
            agent=role,
            tool=tool_name,
            operation=operation,
            rationale=f"Operation requires {required_permission.name}, "
                      f"agent has {allowed.name}"
        )

    return granted

# Register as middleware in your agent framework
agent.register_middleware(permission_guard)
```

### The Four Destructive Operation Categories

Block these at the guard layer, not the prompt:

```python
DESTRUCTIVE_PATTERNS = {
    "bulk_delete":    [r"DELETE.*WHERE", r"TRUNCATE", r"DROP\s+TABLE"],
    "credential_ops": [r"rotate.*secret", r"reset.*password", r"create.*api_key"],
    "schema_change":  [r"ALTER\s+TABLE", r"ADD\s+COLUMN", r"CREATE\s+INDEX"],
    "exec":           [r"exec\s*\(", r"eval\s*\(", r"os\.system", r"subprocess"],
}

def classify_operation(tool_name: str, args: dict) -> Permission:
    """
    Classify a tool call into required permission tiers.
    Coverage is incomplete by default — classify conservatively.
    """
    op_str = f"{tool_name} {json.dumps(args)}"

    if any(re.match(p, op_str, re.IGNORECASE) for ps in DESTRUCTIVE_PATTERNS["bulk_delete"] for p in ps):
        return Permission.DELETE
    if any(re.match(p, op_str, re.IGNORECASE) for ps in DESTRUCTIVE_PATTERNS["credential_ops"] for p in ps):
        return Permission.ADMIN
    if any(re.match(p, op_str, re.IGNORECASE) for ps in DESTRUCTIVE_PATTERNS["schema_change"] for p in ps):
        return Permission.SCHEMA
    if any(re.match(p, op_str, re.IGNORECASE) for ps in DESTRUCTIVE_PATTERNS["exec"] for p in ps):
        return Permission.EXECUTE

    return Permission.READ  # default to least privilege
```

### Layer 3 — Approval Queue for Destructive Operations

When the guard blocks, don't silently kill. Route to a human review surface:

```python
async def escalate_to_approval_queue(agent, tool, operation, rationale):
    queue.push(ApprovalRequest(
        id=uuid4(),
        agent_id=agent,
        tool=tool,
        operation=operation,
        rationale=rationale,
        context_snapshot=get_recent_tool_history(limit=10),
        created_at=datetime.utcnow(),
        ttl=timedelta(hours=24),
    ))
    # Notify reviewer via Slack/PagerDuty
    await notification_channel.send(
        f":warning: Agent `{agent}` blocked on `{tool}` — "
        f"approval needed in <https://internal.tool/approvals|approval queue>"
    )
```

### Permission Scope per Session

For long-running sessions, reset permission scope periodically and re-evaluate against current tool inventory:

```python
async def periodic_permission_audit(agent_session):
    """
    Re-check: does the current tool inventory match the permission scope?
    Handles dynamic tool discovery that expands the attack surface mid-session.
    """
    current_tools = await agent_session.discover_available_tools()
    new_tools = set(current_tools) - agent_session.initial_tool_set

    if new_tools:
        # New tools get NONE permission by default until explicitly scoped
        for tool in new_tools:
            agent_session.permission_scope[tool] = Permission.NONE
        audit_log.warning(
            f"NEW_TOOLS_DISCOVERED tools={new_tools} "
            f"agent={agent_session.id} — scoped to NONE pending review"
        )
```

## Receipt

> Verified 2026-07-25 — Source: wal.sh "Agent Permission Guardrails" (2026), ACNBP (IEEE AIXDKE 2026), Fowler's Vibesec Reckoning (2026-05-29). Pattern distilled from production permission enforcement patterns across agent deployments. Code examples are representative architecture patterns. Deterministic vs. probabilistic control distinction and permission scope per session are the primary new contributions not covered by S-1000 (Structural Agent Governance) or S-804 (Untrusted Executor Pattern).

## See also

[S-1000](../stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) · [S-804](../stacks/s804-the-untrusted-executor-pattern-when-your-llm-generates-correct-but-unauthorized-actions.md) · [S-996](../stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) · [F-199](f199-per-task-cost-attribution.md)
