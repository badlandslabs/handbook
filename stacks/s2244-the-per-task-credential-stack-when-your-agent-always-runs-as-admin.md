# [S-2244] · The Per-Task Credential Stack — When Your Agent Always Runs as Admin

RBAC was designed for humans with stable job functions. A developer role gets read/write on repositories but not database admin. The role reflects a stable job function that changes on an organizational timescale. AI agents operate on a different timescale: a single agent may perform read-only analysis, propose a schema change, and execute a deployment — all within ten minutes of the same task. Applying traditional RBAC produces two failure modes. Over-privilege with a single role: grant one role that covers every operation the agent might ever need. This defeats access control entirely. Role thrashing: swap roles at each subtask, flooding audit logs with noise and creating race conditions when concurrent tasks need different roles.

## Forces

- **Agents are multi-credential by design** — a coding agent needs repo read, PR write, CI trigger, and notification permissions, each in different security domains with different TTLs.
- **Traditional RBAC uses ambient delegation** — a human assumes a role and all actions happen under that identity. Agents need per-action scoped tokens, not persistent assumed identities.
- **Human offboarding doesn't work** — when a contractor leaves, you revoke their access. When a task ends, you need to revoke only the credentials for that task, not the agent's other capabilities.
- **Audit trails must be per-task, not per-agent** — a compliance review needs to answer "what did this specific task see and modify?" not "what can this agent do in general?"
- **The tool is the permission boundary** — in agentic systems, capability manifests through tool calls, not raw API access. Authorization decisions must happen at the tool-invocation layer.

## The Move

**Hybrid RBAC + ABAC, with the tool interface as the primary enforcement surface:**

### 1. RBAC Sets Structural Boundaries

Use static RBAC roles to enforce hard limits that never change within a task:

```python
from enum import Enum, auto

class AgentRole(Enum):
    CODE_REVIEWER = auto()      # Can read repos, cannot delete or deploy
    DEPLOYMENT_AGENT = auto()   # Can deploy to staging only, never production
    DATA_ANALYST = auto()       # Can query read replicas, cannot write
    ORCHESTRATOR = auto()       # Can spawn sub-agents, cannot touch data

ROLE_TOOL_BLOCKLIST: dict[AgentRole, set[str]] = {
    AgentRole.CODE_REVIEWER: {"delete_repository", "drop_table", "exec_sql", "deploy_production"},
    AgentRole.DEPLOYMENT_AGENT: {"deploy_production", "delete_resource", "modify_network_policy"},
    AgentRole.DATA_ANALYST: {"write_table", "delete_record", "create_user"},
    AgentRole.ORCHESTRATOR: {"exec_sql", "delete_repository"},
}
```

These hard limits are enforced at the gateway layer before any tool call reaches the LLM.

### 2. ABAC Enforces Runtime Constraints

For each task, generate ephemeral scoped credentials with a TTL matching the estimated task duration:

```python
from datetime import datetime, timedelta
from uuid import uuid4
import structlog
logger = structlog.get_logger()

class TaskCredential:
    """Ephemeral scoped credential for a single task execution."""
    def __init__(
        self,
        task_id: str,
        agent_role: AgentRole,
        resources: list[ResourceScope],
        ttl_minutes: int,
        sponsor_id: str,  # Human who authorized this task
    ):
        self.task_id = task_id
        self.credential_id = f"cred_{uuid4().hex[:12]}"
        self.agent_role = agent_role
        self.resources = resources        # e.g., ["repo:org/*", "db:analytics-db:read"]
        self.expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        self.sponsor_id = sponsor_id
        self.status = "active"
        self.used_tools: list[ToolCall] = []
        self.revoked = False

    def authorize(self, tool_name: str, resource: str) -> bool:
        """Check if this task credential authorizes a specific tool+resource call."""
        # Hard RBAC blocklist check
        if tool_name in ROLE_TOOL_BLOCKLIST.get(self.agent_role, set()):
            logger.warning("per_task_cred.blocked_by_rbac",
                         task_id=self.task_id, tool=tool_name,
                         role=self.agent_role.name)
            return False
        # ABAC resource scope check
        allowed = any(
            resource.startswith(scope.pattern)
            for scope in self.resources
            if scope.permission == "read"
        )
        # Write operations need explicit resource match
        if not allowed:
            logger.warning("per_task_cred.resource_violation",
                         task_id=self.task_id, resource=resource)
        return allowed

    def revoke(self):
        """Called when task completes, times out, or exceeds budget."""
        self.status = "revoked"
        self.revoked = True
        # Invalidate underlying token/credential in each backend
        invalidate_credential(self.credential_id)
        logger.info("per_task_cred.revoked", task_id=self.task_id,
                   ttl_used=self.ttl_used())
```

### 3. The Sponsor Model

Every agent action traces back to a human. Embed sponsor identity in the credential:

```python
class AgentTask:
    def __init__(self, sponsor_id: str, objective: str, role: AgentRole, ttl: int):
        self.credential = TaskCredential(
            task_id=str(uuid4()),
            agent_role=role,
            resources=self._derive_resources(objective, role),
            ttl_minutes=ttl,
            sponsor_id=sponsor_id,
        )
        self.capability_blueprint = self._build_blueprint(objective, role)
        # The blueprint is what the agent actually sees in its system prompt
        # (capabilities, not raw credential tokens)

    def _derive_resources(self, objective: str, role: AgentRole) -> list[ResourceScope]:
        """Map task objective to specific resource scopes."""
        if "code review" in objective.lower():
            return [
                ResourceScope("repo:org/*", "read"),
                ResourceScope("ci:org/*", "read"),
            ]
        elif "deploy" in objective.lower():
            return [
                ResourceScope("repo:org/*", "read"),
                ResourceScope("k8s:staging-ns", "write"),
                ResourceScope("deploy:staging", "execute"),
            ]
        return []

    def _build_blueprint(self, objective: str, role: AgentRole) -> dict:
        """What the agent's system prompt sees — not raw credentials."""
        return {
            "role": role.name,
            "tools": self._allowed_tools(role),
            "resource_patterns": [r.pattern for r in self.resources],
            "ttl": self.credential.ttl_minutes,
            "sponsor": self.credential.sponsor_id,
        }
```

The agent receives `capability_blueprint` in its system prompt, not raw credentials. The actual credential token never touches the LLM's context.

### 4. Enforcement at the Gateway Layer

```python
async def tool_call_gateway(
    task_credential: TaskCredential,
    tool_name: str,
    tool_args: dict,
    resource_targets: list[str],
) -> GatewayDecision:
    """
    Enforce per-task credential policy at every tool invocation.
    Returns ALLOW, DENY, ESCALATE, or DOWNGRADE.
    """
    if task_credential.revoked:
        return GatewayDecision.DENY  # Task credential already invalidated

    if datetime.utcnow() > task_credential.expires_at:
        task_credential.revoke()
        return GatewayDecision.DENY  # TTL exceeded

    for resource in resource_targets:
        if not task_credential.authorize(tool_name, resource):
            return GatewayDecision.DENY

    # Flag sensitive operations for sponsor notification
    if tool_name in SENSITIVE_OPERATIONS:
        await notify_sponsor(
            sponsor_id=task_credential.sponsor_id,
            event=f"agent_requested_{tool_name}",
            task_id=task_credential.task_id,
            can_revoke=True,
        )
        return GatewayDecision.ESCALATE

    return GatewayDecision.ALLOW
```

## Receipt

> Verified 2026-08-06 — Source: Zylos Research "RBAC for AI Agent Systems" (2026-05-20) — hybrid RBAC+ABAC pattern confirmed as industry standard; Tian Pan "RBAC Is Not Enough for AI Agents" (2026-04-20) — per-task TTL credentials and sponsor model documented; Tony Kipkemboi "RBAC for AI Agents" (2026) — implementation guide with agent identity and permission scoping; Microsoft Community Hub "Authorization and Identity Governance Inside AI Agents" (2026-02-25) — Entra ID RBAC enforcement at the tool invocation layer. Key insight: authorization must happen at the tool-invocation layer, not at the agent identity layer. Agent RBAC is fundamentally different from human RBAC because the principal (the agent) is not the party who bears responsibility (the sponsor). Pattern: per-task credentials replace ambient delegation tokens.

## See also

- [S-200 · The Permission Guard Stack](stacks/s200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — permission boundary enforcement
- [S-2067 · The Agentic Browser Stack](stacks/s2067-the-agentic-browser-stack-when-your-agent-becomes-the-same-origin-policy-attacker.md) — trust boundary enforcement in agentic systems
- [S-2239 · The NHI Governance Gap Stack](stacks/s2243-the-nhi-governance-gap-stack-when-your-iga-system-knows-every-employee-but-no-agents.md) — non-human identity governance
- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — role-based tool sets
