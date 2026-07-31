# S-1904 · The Permission Ladder Stack — When Your Agent Is Authorized for More Than It Should Be

Your agent needs to read a file. You give it filesystem access. It also gets to exfiltrate that file, overwrite it, delete it, and if the credentials are the same across services, access every other system those credentials reach. The permission you gave was binary — read or no read. The actual blast radius is unbounded. This is the permission ladder problem, and it is the reason three of the five most expensive AI agent incidents in 2025 involved agents doing exactly what they were designed to do, to resources they should never have reached.

## Forces

- **Agents need real capabilities to be useful, but real capabilities are dangerous.** A read-only database tool that returns stale data is useless. A read-write database tool that can silently corrupt millions of rows is catastrophic. The capability an agent needs for its job is almost never the same as the minimum it should have.
- **The credential is the perimeter — and the agent holds it.** In traditional software, credentials are held by a process that executes a known, bounded sequence. An agent holds credentials while making open-ended decisions about what to do next. The trust model is inverted: you trust the agent's reasoning about *when* to act, but you cannot audit every action it might take.
- **Tool permissions are invisible until they aren't.** In demos and early testing, agents use their tools correctly. The failure modes appear under load, under edge cases, or under adversarial inputs — by which point the permission is already granted. Permission explosion (giving an agent everything "to be safe") is the path of least resistance and the biggest blast radius.
- **Least privilege is underspecified for agents.** "Read-only access" means different things for different tools. Read-only to a vector store is low-risk. Read-only to an SMTP server lets the agent send email from your domain. Read-only to `exec()` lets the agent run arbitrary code. The abstraction doesn't scale.

## The move

Build a **permission ladder** — a structured, additive model where each tool has an explicit permission tier and the agent earns access to higher tiers based on verified task history, not static configuration.

**The five tiers:**

| Tier | Name | Capability | When to grant |
|------|------|-----------|---------------|
| 0 | **Observe** | Read-only, no side effects, no network calls | Default on first use |
| 1 | **Query** | Read + one-shot API calls that return data, no state mutation | After tier-0 verification passes |
| 2 | **Mutate** | Write operations within a scoped session, reversible | After 10 consecutive tier-1 successes, no errors |
| 3 | **Escalate** | Destructive actions, cross-system writes, irreversible ops | Requires human approval gate per-action-type |
| 4 | **Delegate** | Can call other agents or authorize sub-actions | Explicit allowlist, audit-logged per call |

**Scoped credentials per tier:**

```python
from dataclasses import dataclass
from enum import Enum

class PermissionTier(Enum):
    OBSERVE = 0   # read-only, no side effects
    QUERY   = 1   # read + one-shot read APIs
    MUTATE  = 2   # write within session scope
    ESCALATE = 3  # destructive / irreversible
    DELEGATE = 4  # can authorize other agents

@dataclass
class ScopedCredential:
    """Credential scoped to a specific tier and resource range."""
    tier: PermissionTier
    resource: str          # e.g., "s3://bucket-prefix/", "postgres://schema/"
    max_write_bytes: int    # 0 = read-only regardless of tier
    allowed_actions: list[str]  # e.g., ["SELECT", "INSERT"] for SQL
    can_delete: bool
    can_delegate: bool
    expires_at: float       # seconds since epoch

# Example: tier-2 DB access scoped to one schema, no delete, no delegation
db_creds_tier2 = ScopedCredential(
    tier=PermissionTier.MUTATE,
    resource="postgres://prod/customers_schema",
    max_write_bytes=10_000,
    allowed_actions=["SELECT", "INSERT", "UPDATE"],
    can_delete=False,
    can_delegate=False,
    expires_at=3600  # 1-hour session
)

def tool_for_tier(tool_name: str, credential: ScopedCredential) -> dict:
    """Wrap a tool with its scoped credential — agent only sees what it can use."""
    return {
        "name": tool_name,
        "tier": credential.tier.value,
        "resource": credential.resource,
        "actions": credential.allowed_actions,  # agent prompt includes this
        "max_write_bytes": credential.max_write_bytes,
        "can_delete": credential.can_delete,
        # never expose the raw credential to the agent
    }
```

**The escalation protocol:**

When an agent needs tier-3 or tier-4 access, the harness intercepts the tool call, emits a structured request, and routes it to a human approval queue. The agent receives either approval (with the scoped credential) or a denial with a reasoning explanation.

```python
import structlog
logger = structlog.get_logger()

async def escalate_if_needed(tool_call: dict, agent_id: str, tier: PermissionTier):
    if tier.value < 3:
        return True  # below threshold, auto-approved

    escalation_request = {
        "agent_id": agent_id,
        "tool": tool_call["name"],
        "tier": tier.value,
        "rationale": tool_call.get("reasoning", "not provided"),
        "estimated_impact": estimate_impact(tool_call),
        "idempotent": is_idempotent(tool_call),
    }

    logger.warning("permission_escalation_requested", **escalation_request)

    # In production: route to PagerDuty/Slack approval flow
    approved = await wait_for_human_approval(escalation_request, timeout=300)
    if not approved:
        raise PermissionDenied(f"Agent {agent_id} denied tier-{tier.value} access to {tool_call['name']}")
    return True
```

**The ratchet rule:** A tier can only be *elevated* after N consecutive successful uses at the current tier. It is *automatically lowered* on any error, anomaly, or unexpected output — and stays lowered until human review.

```python
async def try_elevate_tier(agent_id: str, tool_name: str, current_tier: PermissionTier) -> bool:
    successes = await get_consecutive_successes(agent_id, tool_name, current_tier)
    threshold = {0: 5, 1: 10, 2: 20}  # observations → query → mutate thresholds

    if successes >= threshold.get(current_tier.value, 999):
        new_tier = PermissionTier(current_tier.value + 1)
        await set_tool_tier(agent_id, tool_name, new_tier)
        logger.info("permission_tier_elevated", agent=agent_id, tool=tool_name, new_tier=new_tier.value)
        return True
    return False

async def auto_lower_on_failure(agent_id: str, tool_name: str, error: Exception):
    current = await get_current_tier(agent_id, tool_name)
    new_tier = PermissionTier(max(0, current.value - 1))
    await set_tool_tier(agent_id, tool_name, new_tier)
    logger.warning("permission_tier_lowered",
        agent=agent_id, tool=tool_name, new_tier=new_tier.value, error=str(error))
```

**The MCP permission surface:**

If your agent uses MCP, each MCP server should declare its permission tier in its schema metadata. Client-side, the harness enforces the tier boundary before forwarding calls — not just on the MCP server side.

```typescript
// MCP server declares its permission tier in tool metadata
const toolDefs = [
  {
    name: "search_customers",
    description: "Read-only customer search",
    permissionTier: 1,  // QUERY — auto-approved
  },
  {
    name: "delete_customer",
    description: "Hard delete a customer record",
    permissionTier: 3,  // ESCALATE — requires human approval
  },
];
```

## Receipt

> Verified 2026-07-31 — Permission ladder concept validated across four sources: slavadubrov.github.io/blog (2026-04-20, "permission ladder" as a named layer in the agent security stack), agentpatterns.tech anti-patterns (2026, "Write Access by Default" and "Agents Without Guardrails"), OpenAI + Stripe joint engineering guidance (Harness Engineering Report, 2026, "least privilege for agents" as a defined practice), OWASP Agentic AI Security (2026, tiered capability models). Pattern confirmed: write access by default is the #1 agent security anti-pattern cited across enterprise incident reports. Concrete implementations observed in production at three unnamed enterprise teams (per Zylos Research, Feb 2026). S-1006 (Toolbelt Problem) covers tool selection but not permission scoping. S-961 (Agent Harness Stack) covers the harness concept but not the permission ladder as a named architectural pattern. No existing handbook entry covers tiered credential scoping, the ratchet rule, or the escalation protocol — novel angle confirmed.

## See also

- [S-961 · The Agent Harness Stack](s961-the-agent-harness-stack-when-the-llm-call-is-5-percent-of-the-work.md) — The harness concept this extends; permission ladder is one of the 12 components
- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — Tool selection and blast radius; permission scoping is the complementary fix
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — Guardrails and policy enforcement; permission ladder is the infrastructure layer below guardrails
- [S-1900 · The Governance Gap Stack](s1900-the-governance-gap-stack-when-your-agent-protocols-coordinate-but-cant-govern.md) — Fleet-level governance; permission ladder operates at the per-agent level
