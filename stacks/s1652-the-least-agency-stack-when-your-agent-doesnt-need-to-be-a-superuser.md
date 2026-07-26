# S-1652 · The Least Agency Stack — When Your Agent Doesn't Need to Be a Superuser

Your agent can delete your entire S3 bucket. Not because it needs to — because you gave it full read/write access to the entire account "to keep things simple." Now it receives a malicious prompt injection via email, calls the `delete-bucket` tool, and your production artifacts are gone in 90 seconds. You didn't build a stupid agent. You built a powerful agent with no boundaries. This is the least agency gap, and it is the root cause behind most of the OWASP ASI Top 10 for Agentic Applications.

## Forces

- **Agents get the maximum privilege their tools allow, not the minimum they need.** Cloud credentials, API tokens, database access — agents receive whatever unlocks the next capability, compounding into a superuser that no human employee would ever receive.
- **Least privilege and least agency are different things.** Least privilege controls *what* an agent can access. Least agency controls *how much autonomy* it has to act without a human checkpoint. You can have read-only credentials and still approve a $50,000 wire transfer because the agent "seemed confident."
- **Agency accumulates silently between sessions.** Each successful interaction teaches the agent to act faster and more independently. The scope creeps. The human-in-the-loop becomes a rubber stamp. The agent graduates itself.
- **Product pressure drives agency inflation.** Feature requests assume the agent can do more. Demos reward agents that act autonomously. The path of least resistance is always more agency.
- **Agents cannot self-limit their agency.** A tool with `delete-bucket` permission will use it if the context suggests it solves the task. Agents optimize for completion, not for restraint.

## The Move

Design agency as a tiered, earned, and revocable property — not a one-time configuration.

### 1. Map capabilities to explicit tiers

Define agency levels as first-class properties, not as a byproduct of tool availability:

```
Tier 0 — Inquiry Only
  Agent may read, summarize, query.
  No mutations. No external calls beyond the LLM itself.
  Examples: research tasks, document analysis, data exploration.

Tier 1 — Bounded Mutation
  Agent may make reversible changes within a constrained scope.
  Requires: scope tags on all mutations, rollback capability.
  Examples: create draft, update metadata, send non-critical notifications.

Tier 2 — Approved Mutation
  Agent proposes changes. Human approves before execution.
  Requires: structured diff presentation, explicit approval gate.
  Examples: send emails, update tickets, modify configuration.

Tier 3 — Unconstrained Mutation
  Agent acts autonomously within defined boundaries.
  Requires: budget limits, blast-radius constraints, audit trail.
  Examples: auto-scaling, automated deployments, financial transactions.

Tier 4 — Privileged
  Agent operates with elevated system access.
  Requires: real-time monitoring, hard budget caps, immediate revoke capability.
  Examples: infrastructure provisioning, access control changes, data exports.
```

### 2. Earn agency through demonstrated reliability

Never grant Tier 2+ on first deployment. Require evidence:

```python
class AgencyEscalationPolicy:
    def can_elevate(self, agent_id: str, proposed_tier: int) -> bool:
        if proposed_tier <= 1:
            return True  # Inquiry and bounded mutation are always available

        tier_2_requires = {
            "eval_score_min": 0.85,
            "failure_rate_max": 0.05,
            "audit_log_complete": True,
            "scope_defined": True,
        }

        tier_3_requires = {
            **tier_2_requires,
            "eval_score_min": 0.95,
            "failure_rate_max": 0.01,
            "shadow_mode_runs": 50,
            "human_review_runs": 20,
        }

        reqs = tier_3_requires if proposed_tier >= 3 else tier_2_requires
        return self._meets_requirements(agent_id, reqs)
```

### 3. Scope-lock every mutation

Every agent action at Tier 1+ must carry an explicit scope tag. This makes the blast radius computable at decision time, not audit time:

```python
@dataclass
class ScopedAction:
    action: str
    target_resource: str  # e.g., "orders/ord_123", "customer/c_456"
    scope_tag: str        # e.g., "own-record", "own-org", "cross-org"
    reversibility: str    # "none" | "rollback" | "manual-review"

def enforce_scope(action: ScopedAction, agent_tier: int) -> bool:
    if agent_tier < 2:
        return False  # Tier 1 cannot act — only propose

    if action.scope_tag == "cross-org" and agent_tier < 4:
        return False  # Cross-org mutations require Tier 4

    if action.reversibility == "none" and agent_tier < 3:
        return False  # Irreversible actions need Tier 3+

    return True
```

### 4. Budget-time revocation, not budget-dollar caps

The standard FinOps approach (cap spend in dollars) misses the real threat. Revoke by *operational budget* — number of destructive actions, scope of state mutations, blast radius of a single step:

```python
class OperationalBudget:
    def __init__(self, max_mutations: int = 10,
                 max_cross_boundary: int = 2,
                 max_stateful_steps: int = 50):
        self.mutations = 0
        self.cross_boundary = 0
        self.stateful_steps = 0
        self.max_mutations = max_mutations
        self.max_cross_boundary = max_cross_boundary
        self.max_stateful_steps = max_stateful_steps

    def consume(self, action: ScopedAction) -> bool:
        if self.mutations >= self.max_mutations:
            raise AgencyBudgetExceeded(f"mutation cap reached: {self.mutations}")
        if action.scope_tag == "cross-boundary":
            if self.cross_boundary >= self.max_cross_boundary:
                raise AgencyBudgetExceeded("cross-boundary cap reached")
        if is_stateful(action):
            if self.stateful_steps >= self.max_stateful_steps:
                raise AgencyBudgetExceeded("stateful step cap reached")
        self.mutations += 1
        self.cross_boundary += (action.scope_tag == "cross-boundary")
        self.stateful_steps += is_stateful(action)
        return True
```

### 5. The MCP least-agency gate

For MCP-connected tools, wrap every server with a permission layer that enforces scope before forwarding:

```typescript
// MCP permission middleware
async function mcpPermissionGate(
  toolCall: ToolCall,
  sessionTier: number,
  budget: OperationalBudget
): Promise<ToolCall | ToolCallRejected> {
  // 1. Scope check
  const scope = inferScope(toolCall);
  if (!scopeTagsPermitted(scope, sessionTier)) {
    return {
      status: "rejected",
      reason: `Tier ${sessionTier} cannot act on scope: ${scope}`,
      escalation: "request_tier_boost",
    };
  }

  // 2. Budget check
  try {
    budget.consume(toScopedAction(toolCall, scope));
  } catch (e) {
    return {
      status: "rejected",
      reason: e.message,
      escalation: "human_review_required",
    };
  }

  // 3. Destructive-action human-in-the-loop
  if (isDestructive(toolCall) && sessionTier < 3) {
    return {
      status: "pending_approval",
      reason: "Destructive action requires human review",
      structured_diff: generateDiff(toolCall),
    };
  }

  return toolCall;
}
```

## Receipt

> Verified 2026-07-26 — Research confirmed OWASP ASI Top 10 v2.01 (Jun 2026) as primary source. Least-agency principle appears verbatim in OWASP agentic security guidance: "Autonomy should be earned, not granted by default." Fortune 500 procurement questionnaires now include ASI framework questions (lineation.ai, 2026). Three-tier+ agency escalation documented in agent governance frameworks (Microsoft Agent Governance Toolkit, 2026). Framework patterns are synthesized from documented OWASP guidance and production agent governance patterns — not run as live code.

## See also

- [S-990 · The Agent Traps Stack](/stacks/s990-the-agent-traps-stack-when-the-web-attacks-your-agent.md) — OWASP ASI01–ASI06 attack surface that least agency mitigates
- [S-1000 · The Structural Agent Governance Stack](/stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — prompt guardrails vs. structural enforcement
- [S-1065 · The Inter-Agent Trust Escalation Stack](/stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-trusts-another-agent-too-much.md) — escalation between agents following least-agency logic
- [S-1650 · The Tool Interface Stack](/stacks/s1650-the-tool-interface-stack-when-your-tool-description-works-for-humans-but-not-for-agents.md) — tool descriptions as the agency contract surface
- [S-1612 · The Intent Certificate Stack](/stacks/s1612-the-intent-certificate-stack-when-your-agent-authorized-an-action-that-broke-the-system.md) — goal provenance that enables scope-bounded authorization
