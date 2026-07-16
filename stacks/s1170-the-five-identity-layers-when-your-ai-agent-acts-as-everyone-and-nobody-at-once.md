# [S-1170] · The Five Identity Layers: When Your AI Agent Acts as Everyone and Nobody at Once

Your customer-support agent works perfectly in staging. In production, it starts creating GitHub issues in the wrong repository — one belonging to a different customer. The agent isn't "hacked." It has no identity at all. Every session shares the same OAuth token, and the routing logic that was supposed to scope it broke silently three months ago.

This is the multi-tenant identity problem in agent platforms. It is not a security attack. It is a configuration gap that looks like one.

## Forces

- Agents perform real actions with real credentials — not just generating text, but writing records, sending emails, creating tickets, and spending money
- Multi-tenant deployments share infrastructure but must enforce hard isolation between principals
- Most teams model one identity (the user) and miss the other four layers that matter for agent reliability and compliance
- Parameter injection via message payload is the primary failure mode — it bypasses every access-control check because it originates inside the trusted request
- The EU AI Act (Articles 9, 12, 13, 14) and NIS2 require that automated actions be attributable to a named principal — a faceless agent breaks compliance

## The move

Treat every agent action as a five-layer identity problem:

### Layer 1 — Trigger Identity (who started this)

The user or system event that initiated the agent session. This determines authorization scope, audit attribution, and GDPR data processing basis. Without it, you cannot answer "who authorized this action" in a compliance review.

```python
@dataclass
class TriggerIdentity:
    principal_id: str          # "user_abc123"
    principal_type: str         # "user" | "system" | "api_key" | "another_agent"
    session_id: str             # Isolates from other concurrent sessions
    tenant_id: Optional[str]    # For multi-tenant: which org owns this request
    auth_context: dict          # JWT claims, OAuth scopes, upstream headers
```

### Layer 2 — Execution Identity (which agent acted)

The specific agent instance, version, and configuration that handled this request. Two agents with identical prompts but different versions can produce different actions. Attribution requires pinning to a named deployment.

```python
@dataclass
class ExecutionIdentity:
    agent_id: str               # "support-agent-v3.2.1"
    deployment_id: str          # "prod-us-east-1a"
    model_id: str               # "claude-sonnet-4-20250514"
    invocation_id: str          # Unique per call for deduplication
    parent_invocation_id: Optional[str]  # Links to orchestrating agent
```

### Layer 3 — Authorization Identity (what it was allowed to do)

The effective permission set for this specific invocation — not the maximum the agent *could* do, but what this session is *approved* to do. Must be resolved at request time, not build time, because authorization can change between deployments.

```python
@dataclass
class AuthorizationIdentity:
    effective_scopes: set[str]   # Intersection of: user × tenant × agent × temporal rules
    resource_boundaries: dict    # { "github_repos": ["customer-org/repo-123"] }
    expiry: datetime
    issued_by: str               # Policy engine that resolved these permissions
    version: str                 # Policy version — enables rollback on bad policy push
```

### Layer 4 — Tenant Identity (whose resources)

In multi-tenant deployments, every action must be explicitly scoped to the owning tenant's resource namespace. Scope parameters must come from the config — never inferred from the prompt.

```python
# WRONG — infers from prompt content (parameter injection vulnerable)
def get_github_client(prompt_context):
    return GitHubClient(token=prompt_context["user_token"])

# RIGHT — sources from verified config, not prompt
def get_github_client(tenant_config: TenantConfig, auth_identity: AuthorizationIdentity):
    allowed_repos = auth_identity.resource_boundaries.get("github_repos", [])
    return GitHubClient(
        token=tenant_config.github_app_token,
        org=tenant_config.github_org,
        allowed_repos=allowed_repos
    )
```

### Layer 5 — Attribution Identity (where the cost lands)

For FinOps, chargeback, and compliance reporting, every LLM call and tool invocation must be attributable to a cost center. Token counts alone are not enough — a multi-step agent session can cross 3 models and 12 tool calls. The attribution ID must propagate through the entire trace.

```python
@dataclass
class AttributionIdentity:
    cost_center: str            # "engineering" | "customer-success" | "prod-auto"
    project_id: str             # For per-project billing
    chargeback_entity: str      # Which tenant or team pays
    attribution_tags: dict      # Arbitrary key-value for reporting
```

### The enforcement pattern

```python
class AgentIdentityMiddleware:
    """Resolve all five identity layers before any tool invocation."""
    
    def resolve(self, trigger: TriggerIdentity) -> ResolvedIdentity:
        tenant = self.tenant_registry.get(trigger.tenant_id)
        authz = self.policy_engine.evaluate(
            principal=trigger.principal_id,
            resource_owner=tenant.id,
            action="agent:execute",
            context={"session_id": trigger.session_id}
        )
        return ResolvedIdentity(
            trigger=trigger,
            execution=self.execution_identityResolver.resolve(),
            authorization=authz,
            tenant=tenant,
            attribution=self.attribution_resolver.resolve(trigger, tenant)
        )
    
    def wrap_tool(self, tool: Tool, resolved: ResolvedIdentity) -> Tool:
        """Inject identity context into tool call parameters."""
        # Never allow prompt content to influence scope parameters
        return Tool(
            name=tool.name,
            params={
                **tool.params,
                "_tenant_id": resolved.tenant.id,
                "_auth_scopes": list(resolved.authorization.effective_scopes),
                "_invocation_id": resolved.execution.invocation_id,
                "_cost_center": resolved.attribution.cost_center,
            }
        )
```

The critical invariant: **all four scope-controlling parameters** (`_tenant_id`, `_auth_scopes`, `_invocation_id`, `_cost_center`) are sourced exclusively from the resolved identity — never from the prompt, never from tool results, never from memory store.

## Receipt

> Verified 2026-07-16 — Scalekit blog (March 2026): 5-layer identity pattern documented at scalekit.com/blog/access-control-multi-tenant-ai-agents. Systemshardening.com (June 2026): 5 failure modes of session isolation in multi-tenant agent platforms confirmed at systemshardening.com/articles/ai-landscape/ai-agent-session-isolation. Real incident: shared GitHub OAuth token with no tenant boundary caused cross-channel issue creation after 3 months in production.

## See also

- [S-663 · MCP Credential Provisioning at Scale](stacks/s663-mcp-credential-provisioning-at-scale.md) — Layer 3 (authorization identity) at the MCP tool level
- [S-88x · MCP Ambient Authority: Capability Bucketing](stacks/s88x-the-mcp-ambient-authority-problem-when-your-agent-always-runs-with-more-permissions-than-it-needs.md) — Least-privilege enforcement for tool chains
- [S-1168 · The Append-Only Cost Ledger](stacks/s1168-the-append-only-cost-ledger-when-you-cant-tell-who-spent-what-in-your-agent-fleet.md) — Layer 5 (attribution identity) for FinOps
